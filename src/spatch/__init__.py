from importlib.metadata import version
from .utils import from_identifier, get_identifier

try:
    __version__ = version("spatch")
except ModuleNotFoundError:
    import warnings

    warnings.warn(
        "No version metadata found for spatch, so `spatch.__version__` will be "
        "set to None. This may mean that spatch was incorrectly installed or "
        "not installed at all. For local development, consider doing an "
        "editable install via `python -m pip install -e .` from within the "
        "root `spatch/` repository folder."
    )
    __version__ = None
    del warnings
del version
