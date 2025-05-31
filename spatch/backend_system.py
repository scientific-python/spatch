
import contextlib
import contextvars
from dataclasses import dataclass
import functools
import graphlib
import importlib_metadata
import warnings
import textwrap
from types import MethodType

from spatch import from_identifier, get_identifier


class Backend:
    @classmethod
    def default_backend(cls, primary_types):
        self = cls()
        self.name = "default"
        self.functions = None
        self.primary_types = frozenset(primary_types)
        self.secondary_types = frozenset()
        self.supported_types = self.primary_types
        self.known_backends = frozenset()
        self.prioritize_over_backends = frozenset()
        return self

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
        if other.name in self.prioritize_over_backends:
            return 2

        # If our primary types are a subset of the other, we match more
        # precisely/specifically.
        # TODO: Think briefly whether secondary types should be considered
        if self.primary_types.issubset(other.primary_types | other.secondary_types):
            return 1
        elif other.primary_types.issubset(self.primary_types | self.secondary_types):
            return -1

        return NotImplemented  # unknown order (must check other)


def compare_backends(backend1, backend2):
    # Sort by the backends compare function (i.e. type hierarchy and manual order).
    # We default to a type based comparisons but allow overriding this, so check
    # both ways (to find the overriding).  This also find inconcistencies.
    cmp1 = backend1.compare_with_other(backend2)
    cmp2 = backend2.compare_with_other(backend1)
    if cmp1 is NotImplemented and cmp2 is NotImplemented:
        return 0

    if cmp1 == cmp2:
        raise RuntimeError(
            "Backends {backend1.name} and {backend2.name} report inconsistent "
            "priorities (this means they are buggy).  You can manually set "
            "a priority or remove one of the backends.")
    if cmp1 != 0:
        return cmp1
    return -cmp2



class BackendOpts:
    # Base-class, we create a new subclass for each backend system.
    _dispatch_state = None
    _backend_system = None
    __slots__ = ("backends", "type", "trace", "_state", "_token")

    def __init__(self, *, prioritize=(), disable=(), type=None, trace=False):
        """Customize or query the backend dispatching behavior.

        Context manager to allow customizing the dispatching behavior.
        Instantiating the context manager fetches the current dispatching state,
        modifies it as requested, and then stores the state.
        You can use this context multiple times (but not nested).
        ``enable_globally()`` can be used for convenience but should only
        be used from the main program.

        Initializing ``BackendOpts`` without arguments can be used to query
        the current state.

        .. warning::
            When modifying dispatching behavior you must be aware that this
            may have side effects on your program.  See details in notes.

        Parameters
        ----------
        prioritize : str or list of str
            The backends to prioritize, this may also enable a backend that
            would otherwise never be chosen.
            Prioritization nests, outer prioritization remain active.
        disable : str or list of str
            Specific backends to disable.  This nests, outer disabled are
            still disabled (unless prioritized).
        type : type
            A type to dispatch for. Functions will behave as if this type was
            used when calling (additionally to types passed).
            This is a way to enforce use of this type (and thus backends using
            it). But if used for a larger chunk of code it can clearly break
            type assumptions easily.
            (The type argument of a previous call is replaced.)

            .. note::
                If no version of a function exists that supports this type,
                then dispatching will currently fail.  It may try without the
                type in the future to allow a graceful fallback.

        trace : bool
            If ``True`` entering returns a list and this list will contain
            information for each call to a dispatchable function.
            (When nesting, an outer existing tracing is currently paused.)

            .. note::
                Tracing is considered for debugging/human readers and does not
                guarantee a stable API for the ``trace`` result.

        Attributes
        ----------
        backends
            List of active backend names in order of priority (if the type
            is set, not all of may not be applicable).
        type
            The type to dispatch for within this context.
        trace
            The trace object (currenly a list as described in the examples).
            The trace is also returned when entering the context.

        Notes
        -----
        Both ``prioritize`` and ``type`` can modify behavior of the contained
        block in significant ways.

        For ``prioritize=`` this depends on the backend.  A backend may for
        example result in lower precision results.  Assuming no bugs, a backend
        should return roughly equivalent results.

        For ``type=`` code behavior will change to work as if you were using this
        type.  This will definitely change behavior.
        I.e. many functions may return the given type. Sometimes this may be useful
        to modify behavior of code wholesale.

        Especially if you call a third party library, either of these changes may
        break assumptions in their code and it while a third party may ensure the
        correct type for them locally it is not a bug to not do so.

        Examples
        --------
        This example is based on a hypothetical ``cucim`` backend for ``skimage``:

        >>> with skimage.backend_opts(prioritize="cucim"):
        ...     ...

        Which might use cucim also for NumPy inputs (but return NumPy arrays then).
        (I.e. ``cucim`` would use the fact that it is prioritized here to decide
        it is OK to convert NumPy arrays -- it could still defer for speed reasons.)

        On the other hand:

        >>> with skimage.backend_opts(type=cupy.ndarray):
        ...     ...

        Would guarantee that we work with CuPy arrays that the a returned array
        is a CuPy array.  Together with ``prioritize="cucim"`` it ensure the
        cucim version is used (otherwise another backend may be preferred if it
        also supports CuPy arrays) or cucim may choose to require prioritization
        to accept NumPy arrays.

        Backends should simply document their behavior with ``backend_opts`` and
        which usage pattern they see for their users.

        Tracing calls can be done using, where ``trace`` is a list of informations for
        each call.  This contains a tuple of the function identifier and a list of
        backends called (typically exactly one, but it will also note if a backend deferred
        via ``should_run``).

        >>> with skimage.backend_opts(trace=True) as trace:
        ...     ...

        """
        if isinstance(prioritize, str):
            prioritize = (prioritize,)
        else:
            prioritize = tuple(prioritize)

        if isinstance(disable, str):
            disable = (disable,)
        else:
            disable = tuple(disable)

        # TODO: I think these should be warnings maybe.
        for b in prioritize + disable:
            if b not in self._backend_system.backends:
                raise ValueError(f"Backend '{b}' not found.")

        if type is not None:
            if not self._backend_system.known_type(type, primary=True):
                raise ValueError(
                    f"Type '{type}' not a valid primary type of any backend. "
                    "It is impossible to enforce use of this type for any function.")

        ordered_backends, _, curr_trace = self._dispatch_state.get()
        ordered_backends = prioritize + ordered_backends

        # TODO: We could/should have a faster deduplication here probably
        #       (i.e. reduce the overhead of entering the context manager)
        ordered_backends = tuple({b: None for b in ordered_backends if b not in disable})

        if trace:
            # replace the current trace state.
            curr_trace = []

        self.backends = ordered_backends
        self._state = (ordered_backends, type, curr_trace)
        self.trace = curr_trace
        self._token = None

    def enable_globally(self):
        """Enforce the current backend options globalle.

        Setting this state globally should only be done by the end user
        and never by a library.  This method will issue a warning if the
        dispatching state has been previously modified programatically.
        """
        curr_state = self._dispatch_state.get(None)  # None used before default
        # If the state was never set or the state matches (ignoring trace)
        # and there was no trace registered before this is OK. Otherwise warn.
        if curr_state is not None and (
                curr_state[:-1] != self._state[:-1]
                or curr_state[-1] is not None):
            warnings.warn(
                "Backend options were previously modified, global change of the "
                "backends state should only be done once from the main program.",
                UserWarning,
            )
        self._token = self._dispatch_state.set(self._state)

    def __enter__(self):
        if self._token is not None:
            raise RuntimeError("Cannot enter backend options more than once (at a time).")
        self._token = self._dispatch_state.set(self._state)

        return self.trace

    def __exit__(self, *exc_info):
        self._dispatch_state.reset(self._token)
        self._token = None


class BackendSystem:
    def __init__(self, group, default_primary_types=()):
        """Create a backend system that provides a @dispatchable decorator.

        The backend system also has provides the ``backend_opts`` context manager
        which can be re-exposed by the library.

        .. note::
            Currently, there is a lot of public methods here, these should be hidden
            away.

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
        self.backends = {"default": Backend.default_backend(default_primary_types)}
        self._default_primary_types = frozenset(default_primary_types)

        eps = importlib_metadata.entry_points(group=group)
        for ep in eps:
            self.backend_from_namespace(ep.load())

        # The topological sorter uses insertion sort, so sort backend names
        # alphabetically first.  But ensure that we put default first.
        backends = sorted(b for b in self.backends)
        graph = {"default": set()}
        graph.update({b: set() for b in backends})
        for i, n_b1 in enumerate(backends):
            for n_b2 in backends[i+1:]:
                cmp = compare_backends(self.backends[n_b1], self.backends[n_b2])
                if cmp < 0:
                    graph[n_b1].add(n_b2)
                elif cmp > 0:
                    graph[n_b2].add(n_b1)

        ts = graphlib.TopologicalSorter(graph)
        try:
            order = tuple(ts.static_order())
        except graphlib.CycleError as e:
            cycle = e.args[1]
            raise RuntimeError(
                "Backend dependencies form a cycle.  This is a bug in a backend, you can "
                "fix this by doing <not yet implemented>.\n"
                f"The backends creating a cycle are: {cycle}")

        # Finalize backends to be a dict sorted by priority.
        self.backends = {b: self.backends[b] for b in order}
        # The state is the ordered (active) backends and the prefered type (None)
        # and the trace (None as not tracing).
        self._dispatch_state = contextvars.ContextVar(
            f"{group}.dispatch_state", default=(order, None, None))

    @functools.lru_cache(maxsize=128)
    def known_type(self, relevant_type, primary=False):
        if get_identifier(relevant_type) in self._default_primary_types:
            return True

        for backend in self.backends.values():
            if backend.known_type(relevant_type):
                return True
        return False

    def get_known_unique_types(self, relevant_types):
        # From a list of args, return only the set of relevant types
        return frozenset(val for val in relevant_types if self.known_type(val))

    @functools.lru_cache(maxsize=128)
    def get_types_and_backends(self, relevant_types, ordered_backends):
        """Fetch relevant types and matching backends.

        The main purpose of this function is to cache the results for a set
        of unique input types to functions.
        Since not all backends will support all functions, the implementation
        still needs to filter for that.
        (For now, we assume that this is OK, it shouldl be but we could optimize
        it by not using dicts/in C or move/add caching to the function level.)

        Returns
        -------
        relevant_types : frozenset
            The set of relevant types that are known to the backend system.
        matching_backends : tuple
            A tuple of backend names sorted by priority.
        """
        # Filter out unknown types:
        relevant_types = self.get_known_unique_types(relevant_types)

        matching_backends = tuple(
            n for n in ordered_backends if self.backends[n].matches(relevant_types)
        )
        return relevant_types, matching_backends

    def backend_from_namespace(self, info_namespace):
        new_backend = Backend.from_namespace(info_namespace)
        if new_backend.name in self.backends:
            warnings.warn(
                UserWarning,
                f"Backend of name '{new_backend.name}' already exists. Ignoring second!")
            return
        self.backends[new_backend.name] = new_backend

    def dispatchable(self, relevant_args=None, *, module=None, qualname=None):
        """
        Decorator to mark functions as dispatchable.

        Decorate a Python function with information on how to extract
        the "relevant" arguments, i.e. arguments we wish to dispatch for.

        Parameters
        ----------
        relevant_args : str, list, tuple, or None
            The names of parameters to extract (we use inspect to
            map these correctly).
            If ``None`` all parameters will be considered relevant.
        module : str
            Override the module of the function (actually modifies it)
            to ensure a well defined and stable public API.
        qualname : str
            Override the qualname of the function (actually modifies it)
            to ensure a well defined and stable public API.

        Note
        ----
        The module/qualname overrides are useful because you may not want to
        advertise that a function is e.g. defined in the module
        ``library._private`` when it is exposed at ``library`` directly.
        Unfortunately, changing the module can confuse some tools, so we may
        wish to change the behavior of actually overriding it.
        """
        def wrap_callable(func):
            # Overwrite original module (we use it later, could also pass it)
            if module is not None:
                func.__module__ = module
            if qualname is not None:
                func.__qualname__ = qualname

            disp = Dispatchable(self, func, relevant_args)

            return disp

        return wrap_callable

    @property
    def backend_opts(self):
        """Property returning a :py:class:`BackendOpts` class specific to this library
        (tied to this backend system).
        """        
        return type(
            f"BackendOpts",
            (BackendOpts,),
            {"_dispatch_state": self._dispatch_state, "_backend_system": self},
        )


# TODO: Make it a nicer singleton
NotFound = object()


class Implementation:
    __slots__ = (
        "backend",
        "should_run_symbol",
        "should_run",
        "function_symbol",
        "function",
        "uses_info",
    )

    def __init__(self, backend, function_symbol, should_run_symbol=None, uses_info=False):
        """The implementation of a function, internal information?
        """
        self.backend = backend
        self.uses_info = uses_info

        self.should_run_symbol = should_run_symbol
        if should_run_symbol is None:
            self.should_run = None
        else:
            self.should_run = NotFound

        self.function = NotFound
        self.function_symbol = function_symbol


@dataclass
class DispatchInfo:
    """Additional information passed to backends.

    ``DispatchInfo`` is passed as first (additional) argument to ``should_run``
    and to a backend implementation (if desired).
    Some backends will require the ``types`` attribute.

    Attributes
    ----------
    types : Sequence[type]
        The (unique) types we are dispatching for.  It is possible that
        not all types are passed as arguments if the user is requesting
        a specific type.

        Backends that have more than one primary types *must* use this
        information to decide which type to return.
        I.e. if you allow mixing of types and there is more than one type
        here, then you have to decide which one to return (promotion of types).
        E.g. a ``cupy.ndarray`` and ``numpy.ndarray`` together should return a
        ``cupy.ndarray``.

        Backends that strictly match a single primary type can safely ignore this
        (they always return the same type).

        .. note::
            This is a frozenset currently, but please consider it a sequence.

    prioritized : bool
        Whether the backend is prioritized. You may use this for example when
        deciding if you want to defer with ``should_run``.  Or it may be fine
        to use this to decide that e.g. a NumPy array will be converted to a
        cupy array, but only if prioritized.
    """
    # This must be a very light-weight object, since unless we cache it somehow
    # we have to create it on most calls (although only if we use backends).
    types: tuple[type]
    prioritized: bool
    # Should we pass the original implementation here?


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
        self._implementations = {}
        for backend in backend_system.backends.values():
            if backend.name == "default":
                # The default is not stored on the backend, so explicitly
                # create an Implementation for it.
                impl = Implementation(
                    backend, self._ident, None, False,
                )
                impl.function = self._default_func
                self._implementations["default"] = impl
                continue

            info = backend.functions.get(self._ident, None)

            if info is None:
                # Backend does not implement this function.
                continue

            self._implementations[backend.name] = Implementation(
                backend, info["function"],
                info.get("should_run", None),
                info.get("uses_info", False),
            )

            new_blurb = info.get("additional_docs", "No backend documentation available.")
            new_doc.append(f"{backend.name} :\n" + textwrap.indent(new_blurb, "    "))

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

    def _get_relevant_types(self, *args, **kwargs):
        # Return all relevant types, these are not filtered by the known_types
        if self._relevant_args is None:
            return set(list(args) + [k for k in kwargs])
        else:
            return set(
                type(val) for name, pos in self._relevant_args.items()
                if (val := args[pos] if pos < len(args) else kwargs.get(name)) is not None
            )

    def __call__(self, *args, **kwargs):
        relevant_types = self._get_relevant_types(*args, **kwargs)
        # Prioritized backends is a tuple, so can be used as part of a cache key.
        ordered_backends, type_, trace = self._backend_system._dispatch_state.get()
        if type_ is not None:
            relevant_types.add(type_)
        relevant_types = frozenset(relevant_types)

        relevant_types, matching_backends = self._backend_system.get_types_and_backends(
            relevant_types, ordered_backends)

        # TODO: If we ever anticipate a large number of backends that each only
        #       support a small number of functions this is not ideal.
        matching_impls = [
            impl for name in matching_backends
            if (impl := self._implementations.get(name)) is not None
        ]
    
        if trace is not None:
            call_trace = []
            trace.append((self._ident, call_trace))
        else:
            call_trace = None

        for impl in matching_impls:
            prioritized = impl.backend.name in ordered_backends
            info = DispatchInfo(relevant_types, prioritized)

            if impl.should_run is NotFound:
                impl.should_run = from_identifier(impl.should_run_symbol)

            # We use `is True` to possibly add information to the trace/log in the future.
            if impl.should_run is None or impl.should_run(info, *args, **kwargs) is True:
                if impl.function is NotFound:
                    impl.function = from_identifier(impl.function_symbol)

                if call_trace is not None:
                    call_trace.append((impl.backend.name, "called"))

                if impl.uses_info:
                    return impl.function(info, *args, **kwargs)
                else:
                    return impl.function(*args, **kwargs)
            elif trace is not None and impl.should_run is not None:
                call_trace.append((impl.backend.name, "deferred in should run"))

        if call_trace is not None:
            call_trace.append(("default fallback", "called"))
        return self._default_func(*args, **kwargs)
