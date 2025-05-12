

def implements(ident, should_run=None):
    """Attach should_run to the function.  In the future this would
    also be used to generate the function dict for the entry point.
    """
    def decorator(func):
        func._should_run = should_run
        return func
    return decorator


@implements("spatch._spatch_example.library:divide", should_run=lambda x, y: True)
def divide(x, y):
    return x / y


