from django.db import models

from .exceptions import ScopeError
from .state import get_scope


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

    # We protect disable everything except for .none()
    __len__ = error
    __bool__ = error
    __getitem__ = error
    __iter__ = error
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


def ScopedManager(**scopes):
    required_scopes = set(scopes.keys())

    class Manager(models.Manager):
        def __init__(self):
            super().__init__()

        def get_queryset(self):
            current_scope = get_scope()
            if not current_scope.get('_enabled', True):
                return super().get_queryset()
            missing_scopes = required_scopes - set(current_scope.keys())
            if missing_scopes:
                return DisabledQuerySet(self.model, using=self._db, missing_scopes=missing_scopes)
            else:
                return super().get_queryset().filter(**{
                    scopes[dimension]: current_scope[dimension] for dimension in required_scopes
                    if current_scope[dimension] is not None
                })

        def all(self):
            a = super().all()
            if isinstance(a, DisabledQuerySet):
                a = a.all()
            return a

    return Manager()
