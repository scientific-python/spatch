
import functools
import importlib
import importlib_metadata
import warnings
import textwrap
from types import MethodType


def get_identifier(obj):
    """Helper to get any objects identifier.  Is there an exiting short-hand?
    """
    return f"{obj.__module__}:{obj.__qualname__}"


def from_identifier(ident):
    module, qualname = ident.split(":")
    obj = importlib.import_module(module)
    for name in qualname.split("."):
        obj = getattr(obj, name)

    return obj


class Backend:
    @classmethod
    def from_namespace(cls, info):
        self = cls()
        self.name = info.name
        self.functions = info.functions

        self.primary_types = frozenset(info.primary_types)
        self.secondary_types = frozenset(info.secondary_types)
        self.supported_types = self.primary_types | self.secondary_types
        self.known_backends = frozenset(getattr(info, "known_backends", []))
        self.prioritize_over_backends = frozenset(getattr(info, "prioritize_over_backends", []))
        return self

    def known_type(self, relevant_type):
        if get_identifier(relevant_type) in self.primary_types:
            return "primary"  # TODO: maybe make it an enum?
        elif get_identifier(relevant_type) in self.secondary_types:
            return "secondary"
        else:
            return False

    def matches(self, relevant_types):
        matches = frozenset(self.known_type(t) for t in relevant_types)
        if "primary" in matches and False not in matches:
            return True
        return False

    def compare_with_other(self, other):
        if other in self.prioritize_over_backends:
            return 1

        # If our primary types are a subset of the other, we match more
        # precisely/specifically.
        # TODO: Think briefly whether secondary types should be considered
        if self.primary_types.issubset(other.primary_types):
            return 1
        elif other.primary_types.issubset(self.primary_types):
            return -1

        return NotImplemented  # unknown order (must check other)


def compare_backends(impl1, impl2):
    backend1 = impl1.backend
    backend2 = impl2.backend

    cmp = backend1.compare_with_other(backend2)
    if cmp is not NotImplemented:
        return cmp
    cmp = backend2.compare_with_other(backend1)
    if cmp is not NotImplemented:
        return -cmp

    return 0


class BackendSystem:
    def __init__(self, group, default_primary_types=()):
        """Create a backend system that provides a @dispatchable decorator.

        Parameters
        ----------
        group : str
            The group of the backend entry points.  All backends are entry points
            that are immediately loaded.
        default_primary_types : frozenset
            The set of types that are considered primary by default.  Types listed
            here must be added as "secondary" types to backends if they wish
            to support them.
        """
        # TODO: Should we use group and name, or is group enough?
        # TODO: We could define types of the fallback here, or known "scalar"
        #       (i.e. unimportant types).
        #       In a sense, the fallback should maybe itself just be a normal
        #       backend, except we always try it if all else fails...
        self.backends = {}
        self._default_primary_types = frozenset(default_primary_types)

        eps = importlib_metadata.entry_points(group=group)
        for ep in eps:
            self.backend_from_dict(ep.load())

    def known_type(self, relevant_type):
        if get_identifier(relevant_type) in self._default_primary_types:
            return True

        for backend in self.backends.values():
            if backend.known_type(relevant_type):
                return True
        return False

    def get_known_unique_types(self, relevant_types):
        # From a list of args, return only the set of relevant types
        return set(val for val in relevant_types if self.known_type(val))

    def backend_from_dict(self, info_namespace):
        new_backend = Backend.from_namespace(info_namespace)
        if new_backend.name in self.backends:
            warnings.warn(
                UserWarning,
                f"Backend of name '{new_backend.name}' already exists. Ignoring second!")
            return
        self.backends[new_backend.name] = new_backend

    def dispatchable(self, relevant_args, module=None):
        """
        Decorate a Python function with information on how to extract
        the "relevant" arguments, i.e. arguments we wish to dispatch for.
        Parameters
        ----------
        *relevant_args : The names of parameters to extract (we use inspect to
                map these correctly).
        """
        def wrap_callable(func):
            # Overwrite original module (we use it later, could also pass it)
            if module is not None:
                func.__module__ = module

            disp = Dispatchable(self, func, relevant_args)

            return disp

        return wrap_callable


# TODO: Make it a nicer singleton
NotFound = object()


class Implementation:
    __slots__ = ("backend", "should_run_symbol", "should_run", "function_symbol", "function")

    def __init__(self, backend, function_symbol, should_run_symbol=None):
        """The implementation of a function, internal information?
        """
        self.backend = backend

        self.should_run_symbol = should_run_symbol
        if should_run_symbol is None:
            self.should_run = None
        else:
            self.should_run = NotFound

        self.function = NotFound
        self.function_symbol = function_symbol


class Dispatchable:
    # Dispatchable function object
    #
    # TODO: We may want to return a function just to be nice (not having a func was
    # OK in NumPy for example, but has a few little stumbling blocks)
    def __init__(self, backend_system, func, relevant_args, ident=None):
        functools.update_wrapper(self, func)

        self._backend_system = backend_system
        self._default_func = func
        if ident is None:
            ident = get_identifier(func)

        self._ident = ident

        if isinstance(relevant_args, str):
            relevant_args = {relevant_args: 0}
        elif isinstance(relevant_args, list | tuple):
            relevant_args = {val: i for i, val in enumerate(relevant_args)}
        self._relevant_args = relevant_args

        new_doc = []
        _implementations = []
        for backend in backend_system.backends.values():
            info = backend.functions.get(self._ident, None)

            if info is None:
                continue  # not implemented by backend

            _implementations.append(
                Implementation(backend, info["function"], info.get("should_run", None))
            )

            new_blurb = info.get("additional_docs", "No backend documentation available.")
            new_doc.append(f"{backend.name} :\n" + textwrap.indent(new_blurb, "    "))

        self._implementations = frozenset(_implementations)
        if not new_doc:
            new_doc = ["No backends found for this function."]

        new_doc = "\n\n".join(new_doc)
        new_doc = "\n\nBackends\n--------\n" + new_doc

        # Just dedent, so it makes sense to append (should be fine):
        if func.__doc__ is not None:
            self.__doc__ = textwrap.dedent(func.__doc__) + new_doc
        else:
            self.__doc__ = None  # not our problem

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return MethodType(self, obj)

    @property
    def _backends(self):
        # Extract the backends:
        return [impl.backend for impl in self._implementations]

    def _get_relevant_types(self, *args, **kwargs):
        relevant_types = [
            type(val) for name, pos in self._relevant_args.items()
            if (val := args[pos] if pos < len(args) else kwargs.get(name)) is not None
        ]
        return self._backend_system.get_known_unique_types(relevant_types)

    def __call__(self, *args, **kwargs):
        relevant_types = self._get_relevant_types(*args, **kwargs)
        matching_backends = [
            impl for impl in self._implementations if impl.backend.matches(relevant_types)
        ]
    
        if len(matching_backends) == 0:
            return self._default_func(*args, **kwargs)
        elif len(matching_backends) == 1:
            impl = matching_backends[0]
        else:
            # TODO: All of the following TODOs are related to sorting a graph and finding
            # if it is a forest we need to find a single root node.
            # @eriknw is smart enough to figure this out ;).
            # Try to figure out which backend "beats" the others
            # TODO: We can add a form of caching here, although user settings
            # can mean we have to invalidate the cache.
            # TODO: I think we can formulate rules that linearlization works
            # (I.e I think we could cache the sorted list here.)
            # TODO: We should maybe have a "debug" thing here to check if the
            # backends are getting their priorities right.
            # TODO: sorting with functools.cmp_to_key feels weird/slow (although we can cache).
            matching_backends.sort(key=functools.cmp_to_key(compare_backends), reverse=True)

            impl = matching_backends[0]
            if compare_backends(impl, matching_backends[-1]) <= 0:
                # If the above isn't certain, we could check all of them :).
                raise RuntimeError("Multiple backends found but cannotprioritize them!")

        if impl.should_run is NotFound:
            impl.should_run = from_identifier(impl.should_run_symbol)

        if impl.should_run is None or impl.should_run(*args, **kwargs):
            if impl.function is NotFound:
                impl.function = from_identifier(impl.function_symbol)

            return impl.function(*args, **kwargs)

        return self._default_func(*args, **kwargs)
