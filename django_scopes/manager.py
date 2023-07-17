import logging
from collections import defaultdict
from typing import Dict, List, Union

from django.db import models
from django.db.models.base import Model

from .exceptions import InconsistentScope, ScopeError
from .state import get_scope

logger = logging.getLogger("django_scopes")


ScopeMap = Dict[str, Dict[str, int]]


def _follow_related(instance: Model, lookup: str) -> Model:
    current_value = instance
    pieces = lookup.split('__')

    for piece in pieces[:-1]:
        current_value = getattr(current_value, piece, None)

        if current_value is None:
            break

    return current_value


def _ensure_scopes(instance: Model, active_scope: Model, scope_lookups: List[str]):
    """
    Traverse through the given instance and ensure that all scopes are both
    met and consistent.
    """

    scope_pks = {}

    for lookup in scope_lookups:
        deepest_value = _follow_related(instance, lookup)

        scope_pks[lookup] = deepest_value.pk if deepest_value else None

    for value in scope_pks.values():
        if value is None:
            continue

        if value != active_scope.pk:
            action = 'create' if instance._state.adding else 'update'
            raise InconsistentScope(
                f"Found inconsistent scopes for scope pk '{active_scope.pk}' when attempting to {action} an instance of {instance.__class__};"
                f" Relations: {'; '.join(f'{key}={value}' for key, value in scope_pks.items())};"
            )


def _build_instance_scope_map(instance: Model, scopes: Dict[str, List[str]]) -> ScopeMap:
    scope_map = defaultdict(dict)

    for scope, scope_fields in scopes.items():
        for scope_field in scope_fields:
            attr_piece = scope_field.split('__', 1)[0]
            attr_id = getattr(instance, attr_piece + '_id', None)
            scope_map[scope][scope_field] = attr_id

    return dict(scope_map)


def _diff_scope_maps(old_map: ScopeMap, new_map: ScopeMap) -> List[str]:
    """
    Compute the diff between two scope maps and return a list of scope keys
    that will need to be rechecked. Of note, if a scope is no longer in the
    new map, it is not included in the diff, since there's no instance to check.
    """
    diff_scopes = []

    for scope, field_dict in old_map.items():
        for field, old_id in field_dict.items():
            new_id = new_map.get(scope, {}).get(field, None)

            if old_id != new_id and new_id is not None:
                diff_scopes.append(scope)
                break

    return diff_scopes


class DisabledQuerySet(models.QuerySet):

    def __init__(self, *args, **kwargs):
        self.missing_scopes = kwargs.pop('missing_scopes', None)
        super().__init__(*args, **kwargs)

    def error(self, *args, **kwargs):
        raise ScopeError("A scope on dimension(s) {} needs to be active for this query.".format(
            ', '.join(self.missing_scopes)
        ))

    def _clone(self):
        c = super()._clone()
        c.missing_scopes = self.missing_scopes
        return c

    def none(self):
        c = models.QuerySet(model=self.model, query=self.query.chain(), using=self._db, hints=self._hints)
        c._sticky_filter = self._sticky_filter
        c._for_write = self._for_write
        c._prefetch_related_lookups = self._prefetch_related_lookups[:]
        c._known_related_objects = self._known_related_objects
        c._iterable_class = self._iterable_class
        c._fields = self._fields
        return c.none()

    # We protect disable everything except for .using(), .none() and .create()
    __bool__ = error
    __getitem__ = error
    __iter__ = error
    __len__ = error
    __erpr__ = error
    all = error
    aggregate = error
    annotate = error
    count = error
    earliest = error
    complex_filter = error
    select_for_update = error
    filter = error
    first = error
    get = error
    get_or_create = error
    update_or_create = error
    delete = error
    dates = error
    datetimes = error
    iterator = error
    last = error
    latest = error
    only = error
    order_by = error
    reverse = error
    union = error
    update = error
    raw = error
    values = error
    values_list = error


def ScopedManager(_manager_class=models.Manager, enforce_fk_consistency=False, **scopes: Dict[str, Union[str, List[str]]]):
    required_scopes = set(scopes.keys())

    class Manager(_manager_class):
        def __init__(self):
            super().__init__()

        def get_queryset(self):
            current_scope = get_scope()

            if not current_scope.get('_enabled', True):
                return super().get_queryset()

            missing_scopes = required_scopes - set(current_scope.keys())
            if missing_scopes:
                return DisabledQuerySet(self.model, using=self._db, missing_scopes=missing_scopes)

            filter_kwargs = {}
            filter_kwarg_sets = []
            for dimension in required_scopes:
                current_value = current_scope[dimension]
                if isinstance(current_value, (list, tuple)):
                    filter_kwargs[scopes[dimension] + '__in'] = current_value
                elif current_value is not None:
                    scope_value = scopes[dimension]
                    if isinstance(scope_value, (list, tuple)):
                        kwarg_set = []
                        for scope_value in scopes[dimension]:
                            filter_kwargs[scope_value] = current_value
                            kwarg_set.append(scope_value)

                        filter_kwarg_sets.append(kwarg_set)
                    else:
                        filter_kwargs[scopes[dimension]] = current_value

            return super().get_queryset().filter(**filter_kwargs)

        def all(self):
            a = super().all()
            if isinstance(a, DisabledQuerySet):
                a = a.all()
            return a

        def _check_fk_consistency(self, instance: Model, update_fields, **kwargs):
            current_scope = get_scope()
            if not current_scope.get('_enabled', True):
                return

            missing_scopes = required_scopes - set(current_scope.keys())
            if missing_scopes:
                raise ScopeError("A scope on dimension(s) {} needs to be active to create or update objects.".format(
                    ', '.join(missing_scopes)
                ))

            existing_scope_map = getattr(instance._meta, '_scope_map', {})
            latest_scope_map = _build_instance_scope_map(instance, scopes)
            scope_map_diff = _diff_scope_maps(existing_scope_map, latest_scope_map)

            for dimension in required_scopes:
                current_value = current_scope[dimension]
                scope_value = scopes[dimension]

                if isinstance(scope_value, (list, tuple)) and instance._state.adding or dimension in scope_map_diff:
                    _ensure_scopes(instance, current_value, scope_value)

        def _build_fk_cache(self, sender, instance: Model, **kwargs):
            """
            When an instance is loaded from the database, we need to cache first level
            foreign key values. If a foreign key changes to a non-null value, we need
            to re-traverse through related descriptors on that instance to ensure that
            scopes are still consistent.
            """
            instance._meta._scope_map = _build_instance_scope_map(instance, scopes)

        def contribute_to_class(self, model, name: str) -> None:
            super().contribute_to_class(model, name)
            if enforce_fk_consistency:
                models.signals.pre_save.connect(
                    self._check_fk_consistency,
                    sender=model,
                    dispatch_uid='django_scopes.check_fk_consistency.{}'.format(model.__name__),
                )
                models.signals.post_init.connect(
                    self._build_fk_cache,
                    sender=model,
                    dispatch_uid='django_scopes.build_fk_cache.{}'.format(model.__name__),
                )

    return Manager()
