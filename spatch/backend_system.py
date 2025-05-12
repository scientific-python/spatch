
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
        self.known_backends = frozenset(
            info.known_backends if hasattr(info, "known_backends") else []
        )
        return self

    def matches(self, relevant_type):
        # The default implementation (for now only one) uses exact checks on the
        # type string.
        type_strs = frozenset(get_identifier(t) for t in relevant_type)

        if type_strs.isdisjoint(self.primary_types):
            return False
        elif type_strs.issubset(self.supported_types):
            return True
        else:
            return False

    def knows_other(self, other_name):
        return other_name in self.known_backends


class BackendSystem:
    def __init__(self, group):
        # TODO: Should we use group and name, or is group enough?
        # TODO: We could define types of the fallback here, or known "scalar"
        #       (i.e. unimportant types).
        #       In a sense, the fallback should maybe itself just be a normal
        #       backend, except we always try it if all else fails...
        self.backends = {}

        eps = importlib_metadata.entry_points(group=group)
        for ep in eps:
            self.backend_from_dict(ep.load())

        print(self.backends)

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
            functools.update_wrapper(disp, func)

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
    """Dispatchable function object

    TODO: We may want to return a function just to be nice (not having a func was
    OK in NumPy for example, but has a few little stumbling blocks)
    """
    def __init__(self, backend_system, func, relevant_args, ident=None):
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
            new_doc.append(f"backend.name :\n" + textwrap.indent(new_blurb, "    "))

        self._implementations = frozenset(_implementations)
        if not new_doc:
            new_doc = ["No backends found for this function."]

        new_doc = "\n\n".join(new_doc)
        new_doc = "\n\nBackends\n--------\n" + new_doc

        # Just dedent, so it makes sense to append (should be fine):
        self.__doc__ = textwrap.dedent(self.__doc__) + new_doc

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return MethodType(self, obj)

    @property
    def _backends(self):
        # Extract the backends:
        return [impl.backend for impl in self._implementations]

    def _get_relevant_types(self, *args, **kwargs):
        return frozenset(
            type(val) for name, pos in self._relevant_args.items()
            if (val := args[pos] if pos < len(args) else kwargs.get(name)) is not None
        )

    def __call__(self, *args, **kwargs):
        relevant_types = self._get_relevant_types(*args, **kwargs)

        matching_backends = [
            impl for impl in self._implementations if impl.backend.matches(relevant_types)
        ]
        print([impl.backend.matches(relevant_types) for impl in self._implementations])
        print(matching_backends)
    
        if len(matching_backends) == 0:
            return self._default_func(*args, **kwargs)
        elif len(matching_backends) == 1:
            impl = matching_backends[0]
        else:
            # Try to figure out which backend "beats" the others
            # TODO: We can add a form of caching here, although user settings
            # can mean we have to invalidate the cache.
            # (If we had a clear priority from the user, we can start with that!)
            for backend in matching_backends:
                for other in matching_backends:
                    if backend == other:
                        continue

                    if not backend.knows_other(backend.name):
                        break
                else:
                    # This backend knew all others, so it wins
                    impl = backend
                    break

        if impl.should_run is NotFound:
            impl.should_run = from_identifier(impl.should_run_symbol)

        if impl.should_run is None or impl.should_run(*args, **kwargs):
            if impl.function is NotFound:
                impl.function = from_identifier(impl.function_symbol)

            return impl.function(*args, **kwargs)

        return self._default_func(*args, **kwargs)
