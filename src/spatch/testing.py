from spatch.utils import get_identifier

class _FuncGetter:
    def __init__(self, get):
        self.get = get


class BackendDummy:
    """Helper to construct a minimal "backend" for testing.

    Forwards any lookup to the class.  Documentation are used from
    the function which must match in the name.
    """
    def __init__(self):
        self.functions = _FuncGetter(self.get_function)

    @classmethod
    def get_function(cls, name, default=None):
        # Simply ignore the module for testing purposes.
        _, name = name.split(":")

        # Not get_identifier because it would find the super-class name.
        res = {"function": f"{cls.__module__}:{cls.__name__}.{name}" }
        if hasattr(cls, "uses_context"):
            res["uses_context"] = cls.uses_context
        if hasattr(cls, "should_run"):
            res["should_run"] = get_identifier(cls.should_run)

        func = getattr(cls, name)
        if func.__doc__ is not None:
            res["additional_docs"] = func.__doc__

        return res

    @classmethod
    def dummy_func(cls, *args, **kwargs):
        # Always define a small function that mainly forwards.
        return cls.name, args, kwargs

