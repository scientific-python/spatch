

def implements(ident, should_run=None):
    """Attach should_run to the function.  In the future this would
    also be used to generate the function dict for the entry point.
    """
    def decorator(func):
        func._should_run = should_run
        return func
    return decorator


# for backend 1
@implements("spatch._spatch_example.library:divide", should_run=lambda info, x, y: True)
def divide(x, y):
    print("hello from backend 1")
    return x / y


# For backend 2
@implements("spatch._spatch_example.library:divide", should_run=lambda info, x, y: True)
def divide2(x, y):
    print("hello from backend 2")
    return x / y

