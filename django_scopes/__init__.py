from .exceptions import ScopeError, UnsafeLockingError
from .manager import ScopedManager
from .state import get_scope, scope, scopes_disabled

version = '2.2.0'

__all__ = [
    'version',
    'ScopeError',
    'ScopedManager',
    'UnsafeLockingError',
    'scope',
    'get_scope',
    'scopes_disabled'
]
