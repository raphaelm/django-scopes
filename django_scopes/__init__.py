from .exceptions import ScopeError
from .manager import ScopedManager
from .state import get_scope, scope, scopes_disabled

version = '1.1.0'

__all__ = [
    'version',
    'ScopeError',
    'ScopedManager',
    'scope',
    'get_scope',
    'scopes_disabled'
]
