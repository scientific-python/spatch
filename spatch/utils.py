from importlib import import_module


def get_identifier(obj):
    """Helper to get any objects identifier.  Is there an exiting short-hand?"""
    return f"{obj.__module__}:{obj.__qualname__}"


def from_identifier(ident):
    module, qualname = ident.split(":")
    obj = import_module(module)
    for name in qualname.split("."):
        obj = getattr(obj, name)
    return obj
