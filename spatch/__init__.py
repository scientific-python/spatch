import inspect
import functools
import importlib
import importlib_metadata
import textwrap
import warnings


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


class WillNotHandle:
    """Class to return when an implementation does not want to handle
    args/kwargs.
    """
    def __init__(self, info="<unknown reason>"):
        self.info = info


class Backend: 
    @classmethod
    def from_info_dict(cls, info):
        return cls.from_mapping_and_types(info["name"], info["types"], info["symbol_mapping"])

    @classmethod
    def from_mapping_and_types(cls, name, types, symbol_mapping):
        """
        Create a new backend.
        """
        self = cls()
        self.name = name
        self.type_names = types
        self.symbol_mapping = symbol_mapping
        return self

    def match_types(self, types):
        """See if this backend matches the types, we do this by name.

        Of course, we could use more complicated ways in the future.
        E.g. one thing is that we can have to kind of types:
        1. Types that must match (at least once).
        2. Types that are understood (we do not break for them).

        Returns
        -------
        matches : boolean
            Whether or not the types matches.
        unknown_types : sequence of types
            A sequence of types the backend did not match/know.
            This may be a way to e.g. deal with scalars, that we assume
            all backends can convert, but creating an extensive list may
            not be desireable?
        """
        matches = False
        unknown_types = []
        for t in types:
            ident = get_identifier(t)

            if ident in self.type_names:
                matches = True
                unknown_types.append(t)

        return matches, unknown_types


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

    def backend_from_dict(self, info_dict):
        new_backend = Backend.from_info_dict(info_dict)
        if new_backend.name in self.backends:
            warnings.warn(
                UserWarning,
                f"Backend of name '{new_backend.name}' already exists. Ignoring second!")
            return
        self.backends[new_backend.name] = new_backend

    def dispatchable(self, *relevant_args, module=None):
        """
        Decorate a Python function with information on how to extract
        the "relevant" arguments, i.e. arguments we wish to dispatch for.

        Parameters
        ----------
        *relevant_args : The names of parameters to extract (we use inspect to
                map these correctly).
        """
        def wrap_callable(func):
            disp = Dispatchable(self, func, relevant_args)
            if module is not None:
                disp.__module__ = module

        return wrap_callable

class Dispatchable:
    """Dispatchable function object

    """
    def __init__(self, backend_system, func, relevant_args):
        self._backend_system = backend_system
        self._sig = inspect.signature(func)
        self._relevant_args = relevant_args
        self._default_impl = func
        # Keep a list of implementations for this backend
        self._implementations = []

        ident = get_identifier(func)

        functools.update_wrapper(self, func)

        new_doc = []
        for backend in backend_system.backends.values():
            info = backend.symbol_mapping.get(ident, None)
            print(backend.symbol_mapping, ident)
            if info is None:
                continue  # not implemented by backend (apparently)

            self._implementations.append((backend, info["impl_symbol"]))

            impl_symbol = info["impl_symbol"]
            doc_blurp = info.get("doc_blurp", "No backend documentation available.")
            new_doc.append(f"backend.name :\n" + textwrap.indent(doc_blurp, "    "))

        if not new_doc:
            new_doc = ["No backends found for this function."]

        new_doc = "\n\n".join(new_doc)
        new_doc = "\n\nBackends\n--------\n" + new_doc

        # Just dedent, so it makes sense to append (should be fine):
        self.__doc__ = textwrap.dedent(self.__doc__) + new_doc

    def __get__(self, ):
        raise NotImplementedError(
            "Need to implement this eventually to act like functions.")

    @property
    def _backends(self):
        # Extract the backends:
        return [impl[0] for impl in self._implementations]

    def _find_matching_backends(self, relevant_types):
        """Find all matching backends.
        """
        matching = []
        unknown_types = relevant_types
        for backend, impl in self._implementations:
            matches, unknown_types_backend = backend.match_types(relevant_types)
            unknown_types = unknown_types.union(unknown_types_backend)

            if matches:
                matching.append((backend, impl, unknown_types))

        match_with_unknown = []
        for backend, impl, unknown_types_backend in matching:
            # If the types the backend didn't know are also not known by
            # any other backend, we just ignore them
            if unknown_types_backend.issubset(unknown_types):
                match_with_unknown.append((backend, impl))

        return match_with_unknown

    def __call__(self, *args, **kwargs):
        partial = self._sig.bind_partial(*args, **kwargs)

        relevant_types = set()
        for arg in self._relevant_args:
            val = partial.arguments.get(arg, None)
            if val is not None:
                relevant_types.add(type(val))

        matching_impls = self._find_matching_backends(relevant_types)

        # TODO: When more than one backend matches, we could:
        # 1. Ensure e.g. an alphabetic order early on during registration.
        # 2. Inspect types, to see if one backend is clearly more specific
        #    than another one.
        reasons = []
        for backend, impl in matching_impls + [(None, self._default_impl)]:
            # Call the backend:
            if isinstance(impl, str):
                # TODO: Should update the impl we store, to do this only once!
                impl = from_identifier(impl)

            result = impl(*args, **kwargs)
            if isinstance(result, WillNotHandle):
                # The backend indicated it cannot/does not want to handle
                # this.
                reasons.append((backend, result))
            else:
                return result

        if len(reasons) == 1:
            backends = self._backends
            msg = (f"No backend matched out of {backends} and the default "
                   f"did not work because of: {reasons[0][1].info}")
        else:
            msg = f"Of the available backends, the following were tried but failed:"
            for backend, reason in reasons:
                name = "default" if backend is None else backend.name
                msg += f"\n - {name}: {reason}"

        raise TypeError(msg)

