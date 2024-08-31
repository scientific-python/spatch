import textwrap

# This should be fetched via an entry-point, but lets do it here for now!

# This type of dictionary could be all there is to a backend for now.
# Of course... the backend will need machinery to conveniently build it.
# The backend-info dict, after build needs to live in a minimal/cheap to
# import module.
backend_info = {
    "name": "my_backend",
    "types": ["numpy:matrix"],
    "symbol_mapping": {},
}


from spatch import WillNotHandle


def implements(func):
    """Helper decorator.  Since/if we name our modules identically to the
    main module, we can just do a simple replace the module and be done.
    """
    mod = func.__module__
    # TODO: May want to make sure to replace the start exactly, but OK...
    orig_mod = mod.replace("prototype_backend", "prototype_module")
    name = func.__qualname__

    backend_info["symbol_mapping"][f"{orig_mod}:{name}"] = {
        "impl_symbol": f"{mod}:{name}",
        "doc_blurp": textwrap.dedent(func.__doc__).strip("\n"),
    }

    # We don't actually change the function, just keep track of it.
    return func


# TODO/NOTE: This function would of course be in a different module!
@implements
def func1(arg, optional=None, parameter="param"):
    """
    This text is added by `my_backend`!
    """
    if parameter != "param":
        return WillNotHandle("Don't know how to do param.")
    return "my_backend called"
