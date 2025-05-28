try:
    from spatch.backend_utils import BackendImplementation
except ModuleNotFoundError:
    class Noop:
        def __call__(self, *args, **kwargs):
            return Noop()

        __init__ = __getattr__ = __getitem__ = __call__

    BackendImplementation = Noop

from . import library

backend1 = BackendImplementation("backend1")
backend2 = BackendImplementation("backend2")

# For backend 1
@backend1.implements(library.divide, uses_info=True, should_run=lambda info, x, y: True)
def divide(info, x, y):
    """This implementation works well on floats."""
    print("hello from backend 1")
    # Because the default implementation returns ints for int inputs
    # we do this as well here.  We _must_ use `info.relevant_types`
    # to make this decision (to honor the `backend_opts` state)
    if float not in info.relevant_types:
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
