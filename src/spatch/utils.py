import re
import sys
import warnings
from dataclasses import dataclass, field
from importlib import import_module

from importlib_metadata import version


def get_identifier(obj):
    """Helper to get any objects identifier.  Is there an exiting short-hand?"""
    return f"{obj.__module__}:{obj.__qualname__}"


def from_identifier(ident):
    module, qualname = ident.split(":")
    obj = import_module(module)
    for name in qualname.split("."):
        obj = getattr(obj, name)
    return obj


def get_project_version(project_name, *, action_if_not_found="warn", default=None):
    """Get the version of a project from ``importlib_metadata``.

    This is useful to ensure a package is properly installed regardless of the
    tools used to build the project and create the version. Proper installation
    is important to ensure entry-points of the project are discoverable. If the
    project is not found by ``importlib_metadata``, behavior is controlled by
    the ``action_if_not_found`` and ``default`` keyword arguments.

    Parameters
    ----------
    project_name : str
        The name of the project of a package. For example, this is given by the
        ``[project.name]`` metadata in the pyproject.toml file. This is often,
        but not necessarily, the same as the package name.
    action_if_not_found : {"ignore", "warn", "raise"}
        What action to take if project metadata is not found by importlib:
        "ignore" to return the default value, "warn" to emit a warning and
        return the default value, and "raise" to raise a ModuleNotFoundError.
        Default is "warn".
    default : str or None, optional
        The default version to return if project metadata is not found.
        Default is None.
    """
    if action_if_not_found not in {"ignore", "warn", "raise"}:
        raise ValueError(
            f"`action=` keyword must be 'ignore', 'warn', or 'raise'; got: {action_if_not_found!r}."
        )
    try:
        project_version = version(project_name)
    except ModuleNotFoundError as exc:
        project_version = default
        if action_if_not_found == "warn":
            behavior = f", so the version will be set to {default!r}"
        else:
            behavior = ""
        msg = (
            f"No version metadata found for {project_name}{behavior}. This "
            f"may mean that {project_name} was incorrectly installed or not "
            "installed at all. For local development, consider doing an "
            "editable install via `python -m pip install -e .` from within "
            f"the root `{project_name}/` repository folder."
        )
        if action_if_not_found == "warn":
            warnings.warn(msg, RuntimeWarning, stacklevel=2)
        elif action_if_not_found == "raise":
            raise ModuleNotFoundError(msg) from exc
    return project_version


# Valid recommended entry point name, but we could allow more, see:
# https://packaging.python.org/en/latest/specifications/entry-points/#data-model
_VALID_NAME_RE = re.compile(r"[\w.-]+")


def valid_backend_name(name):
    """Check that name is a valid backend name based on what is recommended
    for entry point names.
    """
    return _VALID_NAME_RE.fullmatch(name) is not None


@dataclass(slots=True)
class _TypeInfo:
    identifier: str
    allow_subclasses: bool = False
    is_abstract: bool = False
    resolved_type: type | None = None
    module: str = field(init=False)
    qualname: str = field(init=False)

    def __post_init__(self):
        if self.identifier[0] == "~":
            self.allow_subclasses = True
            self.identifier = self.identifier[1:]
        elif self.identifier[0] == "@":
            self.allow_subclasses = True
            self.is_abstract = True
            self.identifier = self.identifier[1:]

        try:
            self.module, self.qualname = self.identifier.rsplit(":")
        except ValueError as e:
            # Try to be slightly more helpful and print the bad identifier.
            raise ValueError(f"Invalid type identifier {self.identifier!r}") from e

    def matches(self, type):
        if type.__module__ == self.module and type.__qualname__ == self.qualname:
            return True

        if not self.allow_subclasses:
            return False

        if not self.is_abstract and self.module not in sys.modules:
            # If this isn't an abstract type there can't be subclasses unless
            # the module was already imported.
            return False

        if self.resolved_type is None:
            self.resolved_type = from_identifier(self.identifier)
            # Note: It would be nice to check if a class is correctly labeled as
            # abstract or not.  But there seems no truly reliable way to do so.

        return issubclass(type, self.resolved_type)


class TypeIdentifier:
    """Represent a set of type identifiers.

    A set of type identifier as supported by spatch, each has a string
    identifier consisting of ``"__module__:__qualname__"``.
    The identifier may be prefixed with ``"~"`` to indicate that subclasses
    are allowed, or ``"@"`` to indicate that the type is abstract.

    Abstract types are different in that we must import them always to check
    for subclasses.  For concrete types we can assume that subclasses only
    exist if their module is already imported.
    (In principle we could also walk the ``__mro__`` of the type we check
    and see if we find the superclass by name matching.)
    """

    def __init__(self, identifiers):
        self.identifiers = tuple(identifiers)
        # Fill in type information for later use, sort by identifier (without ~ or @)
        self._type_infos = tuple(
            sorted((_TypeInfo(ident) for ident in identifiers), key=lambda ti: ti.identifier)
        )
        self.is_abstract = any(info.is_abstract for info in self._type_infos)
        self._idents = frozenset(ti.identifier for ti in self._type_infos)

    def __repr__(self):
        return f"TypeIdentifier({self.identifiers!r})"

    def encompasses(self, other, subclasscheck=False):
        """Checks if this type is more broadly defined for priority purposes.

        To be a supertype all identifiers from this one must present in
        the other.
        If ``subclasscheck`` is true and the identifiers are the same we will say
        that we encompass the other one if we allow subclasses and the other does
        not (for the identical identifier).

        When in doubt, this function returns ``False`` (may even be equal then).
        """
        if other._idents.issubset(self._idents):
            if self._idents != other._idents:
                return True

            if subclasscheck:
                # We have the same identifier, check if other represents
                # subclasses of this.
                any_subclass = False
                for self_ti, other_ti in zip(self._type_infos, other._type_infos, strict=True):
                    if self_ti.allow_subclasses == other_ti.allow_subclasses:
                        continue
                    if self_ti.allow_subclasses and not other_ti.allow_subclasses:
                        any_subclass = True
                    else:
                        return False
                if any_subclass:
                    return True

        return False

    def __contains__(self, type):
        # Check if this type is included in the type identifier.
        # Effectively an `__issubclass__` but don't feel like metaclassing.
        if isinstance(type, TypeIdentifier):
            raise TypeError("Cannot subclasscheck TypeIdentifier use `encompasses`.")

        return any(ti.matches(type) for ti in self._type_infos)

    def __or__(self, other):
        """Union of two sets of type identifiers."""
        if not isinstance(other, TypeIdentifier):
            return NotImplemented
        return TypeIdentifier(set(self.identifiers + other.identifiers))


EMPTY_TYPE_IDENTIFIER = TypeIdentifier([])
