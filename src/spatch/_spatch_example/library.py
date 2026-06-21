from spatch.backend_system import BackendSystem, dispatchable_stateful_class

_backend_system = BackendSystem(
    "_spatch_example_backends",  # entry point group
    "_SPATCH_EXAMPLE_BACKENDS",  # environment variable prefix
    default_primary_types=["builtins:int"],
)


backend_opts = _backend_system.backend_opts


@_backend_system.dispatchable(["x", "y"])
def divide(x, y):
    """Divide integers, other types may be supported via backends"""
    if not isinstance(x, int) or not isinstance(y, int):
        # We could allow context being passed in to do this check.
        raise TypeError("x and y must be an integer")
    return x // y


@dispatchable_stateful_class()
class StatefulClass:
    def __init__(self, method):
        self.method = method

    @_backend_system.stateful_dispatching(["x", "y"])
    def apply(self, x, y):
        if not isinstance(x, int) or not isinstance(y, int):
            raise TypeError("x and y must be an integer")

        if self.method == "add":
            res = x + y
        elif self.method == "sub":
            res = x - y
        else:
            raise ValueError(f"Unknown method: {self.method}")

        self._last_result = res
        return res

    @property
    def last_result(self):
        return self._last_result
