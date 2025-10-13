def __getattr__(name):
    if name == "__version__":
        from .utils import get_project_version

        return get_project_version(__name__)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
