
from spatch.backend_system import BackendSystem

_backend_system = BackendSystem(
    "_spatch_example_backends",
    default_primary_types=["builtins:int"]
)


backend_opts = _backend_system.backend_opts

@_backend_system.dispatchable(["x", "y"])
def divide(x, y):
    """Divide integers, other types may be supported via backends"""
    if not isinstance(x, int) or not isinstance(y, int):
        raise TypeError("x must be an integer")
    return x // y
