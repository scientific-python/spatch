# This should be fetched via an entry-point, but lets do it here for now!

# This type of dictionary could be all there is to a backend for now.
# Of course... the backend will need machinery to conveniently build it.
backend_info = {
    "name": "my_backend",
    "types": "numpy:matrix",
    "symbol_mapping": {
        "prototype_module:func1": {
            "impl_symbol": "prototype_backend:my_func1",
            "doc_blurp": "This text added by `my_backend`!",
        }
    }
}


from spatch import WillNotHandle

# TODO/NOTE: This function would of course be in a different module!
def my_func1(arg, optional=None, parameter="param"):
    if parameter != "param":
        return WillNotHandle("Don't know how to do param.")
    return "my_backend called"
