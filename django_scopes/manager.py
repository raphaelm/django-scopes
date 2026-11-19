import copy
from functools import partial
from typing import Self, Sequence

from django.db import connections, models

from .exceptions import ScopeError, UnsafeLockingError
from .state import get_scope

ALLOWED_METHODS = [
    # Allowed
    "using",
    "none",
    "create",
    "bulk_create",
    "bulk_update",
    # Required for proper functioning
    "error",
    "query",
    "model",
    "db",
    "ordered",
]


class DisabledQuerySet(models.QuerySet):

    def __init__(self, *args, **kwargs):
        self.__missing_scopes = kwargs.pop('missing_scopes', None)
        super().__init__(*args, **kwargs)

    def error(self, *args, **kwargs):
        raise ScopeError("A scope on dimension(s) {} needs to be active for this query.".format(
            ', '.join(self.__missing_scopes)
        ))

    def _clone(self):
        c = super()._clone()
        c.__missing_scopes = self.__missing_scopes
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

    def __getattribute__(self, item):
        if item in ALLOWED_METHODS or item.startswith("_"):
            return super().__getattribute__(item)
        return self.error

    def __repr__(self):
        return "<[QuerySet disabled by scopes]>"

    __bool__ = error
    __getitem__ = error
    __iter__ = error
    __len__ = error


def build_scoped_queryset(_base_class=models.QuerySet, *args, **kwargs):
    class ScopedQuerySet(_base_class):
        def select_for_update(self, nowait: bool = False, skip_locked: bool = False, of: Sequence[str] = (),
                              no_key: bool = False) -> Self:  # pragma: no cover -- different branch per databases
            if not connections[self._db or "default"].features.has_select_for_update_of:
                return super().select_for_update(nowait, skip_locked, of, no_key)

            if not of:
                raise UnsafeLockingError(
                    "If you are using `select_for_update()` with django-scopes and your database supports it, "
                    "you should always pass `of=('self',)` to avoid locking the object your scoping depends on."
                )

            return super().select_for_update(nowait, skip_locked, of, no_key)

    return ScopedQuerySet(*args, **kwargs)


def ScopedManager(_manager_class=models.Manager, **scopes):
    required_scopes = set(scopes.keys())

    class Manager(_manager_class):
        def __init__(self):
            super().__init__()

        def with_scope(self, **scope):
            cloned = copy.copy(self)
            scope['_enabled'] = True
            cloned._override_scope = scope
            return cloned

        def with_scopes_disabled(self):
            cloned = copy.copy(self)
            cloned._override_scope = {'_enabled': False}
            return cloned

        def get_scoped_queryset(self):
            """
            Return a new QuerySet object. Subclasses can override this method to
            customize the behavior of the Manager.
            """
            queryset_class = self._queryset_class
            self._queryset_class = partial(build_scoped_queryset, self._queryset_class)
            try:
                return super().get_queryset()
            finally:
                self._queryset_class = queryset_class

        def get_queryset(self):
            if hasattr(self, '_override_scope'):
                current_scope = self._override_scope
            else:
                current_scope = get_scope()
            if not current_scope.get('_enabled', True):
                return super().get_queryset()
            missing_scopes = required_scopes - set(current_scope.keys())
            if missing_scopes:
                return DisabledQuerySet(self.model, using=self._db, missing_scopes=missing_scopes)
            else:
                filter_kwargs = {}
                for dimension in required_scopes:
                    current_value = current_scope[dimension]
                    if isinstance(current_value, (list, tuple)):
                        filter_kwargs[scopes[dimension] + '__in'] = current_value
                    elif current_value is not None:
                        filter_kwargs[scopes[dimension]] = current_value
                return self.get_scoped_queryset().filter(**filter_kwargs)

        def all(self):
            a = super().all()
            if isinstance(a, DisabledQuerySet):
                a = a.all()
            return a

    return Manager()
