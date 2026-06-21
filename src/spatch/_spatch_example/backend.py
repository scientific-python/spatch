try:
    from spatch.backend_utils import BackendImplementation
except ModuleNotFoundError:  # pragma: no cover

    class Noop:
        # No-operation/do nothing version of a BackendImplementation
        def __call__(self, *args, **kwargs):
            return Noop()

        __init__ = __getattr__ = __getitem__ = __call__

    BackendImplementation = Noop

from . import library

backend1 = BackendImplementation("backend1")
backend2 = BackendImplementation("backend2")


# For backend 1
@backend1.implements(library.divide, uses_context=True, should_run=lambda info, x, y: True)
def divide(context, x, y):
    """This implementation works well on floats."""
    print("hello from backend 1")
    # Because the default implementation returns ints for int inputs
    # we do this as well here.  We _must_ use `context.types`
    # to make this decision (to honor the `backend_opts` state)
    if float not in context.types:
        return x // y  # mirror library implementation for ints
    return x / y


# For backend 2
@backend2.implements("spatch._spatch_example.library:divide")
def divide2(x, y):
    """This is a test backend!
    and it has a multi-line docstring which makes this longer than normal.
    """
    print("hello from backend 2")
    return x / y


@backend2.set_should_run(divide2)
def _(info, x, y):
    return True


class StatefulClassImpl:
    @backend1.implements("spatch._spatch_example.library:StatefulClass.apply")
    @classmethod
    def _from_apply(cls, original_self, x, y):
        impl = cls()
        impl.method = original_self.method
        return impl

    def apply(self, x, y):
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
