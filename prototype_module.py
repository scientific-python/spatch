# This is a silly module that might be used by a user.
from spatch import Backend, BackendSystem, WillNotHandle

_backend_sys = BackendSystem()

# This part would have to happen through entry-points:
from prototype_backend import backend_info

_backend_sys.backend_from_dict(backend_info)


@_backend_sys.dispatchable("arg", "optional")
def func1(arg, /, optional=None, parameter="param"):
    """
    This is my function

    Parameters
    ----------
    ...

    """
    if parameter != "param":
        # I suppose even the fallback/default can refuse to handle it?
        return WillNotHandle("Don't know how to do param.")

    return "default implementation called!"

