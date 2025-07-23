import contextvars
import dataclasses
import functools
import os
import sys
import textwrap
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from types import MethodType
from typing import Any

import importlib_metadata

from spatch import from_identifier, get_identifier
from spatch.utils import TypeIdentifier, valid_backend_name

__doctest_skip__ = ["BackendOpts.__init__"]


@dataclass(slots=True)
class Backend:
    name: str
    primary_types: TypeIdentifier = TypeIdentifier([])
    secondary_types: TypeIdentifier = TypeIdentifier([])
    functions: dict = dataclasses.field(default_factory=dict)
    known_backends: frozenset = frozenset()
    higher_priority_than: frozenset = frozenset()
    lower_priority_than: frozenset = frozenset()
    requires_opt_in: bool = False
    supported_types: TypeIdentifier = dataclasses.field(init=False)

    def __post_init__(self):
        if not valid_backend_name(self.name):
            raise ValueError("Invalid backend name {self.name!r}, must be a valid identifier.")

        if len(self.primary_types.identifiers) == 0:
            raise ValueError("A backend must have at least one primary type.")

        self.supported_types = self.primary_types | self.secondary_types

    @classmethod
    def from_namespace(cls, info):
        return cls(
            name=info.name,
            primary_types=TypeIdentifier(info.primary_types),
            secondary_types=TypeIdentifier(info.secondary_types),
            functions=info.functions,
            higher_priority_than=frozenset(getattr(info, "higher_priority_than", [])),
            lower_priority_than=frozenset(getattr(info, "lower_priority_than", [])),
            requires_opt_in=info.requires_opt_in,
        )

    def known_type(self, dispatch_type):
        if dispatch_type in self.primary_types:
            return "primary"  # TODO: maybe make it an enum?
        if dispatch_type in self.secondary_types:
            return "secondary"
        return False

    def matches(self, dispatch_types):
        matches = frozenset(self.known_type(t) for t in dispatch_types)
        if "primary" in matches and False not in matches:
            return True
        return False

    def compare_with_other(self, other):
        # NOTE: This function is a symmetric comparison
        if other.name in self.higher_priority_than:
            return 2
        if other.name in self.lower_priority_than:
            return -2

        # If our primary types are a subset of the other, we match more
        # precisely/specifically. In theory we could also distinguish whether
        # the other has it as a primary or secondary type, but we do not.
        if other.supported_types.encompasses(self.primary_types):
            return 1
        if other.primary_types.encompasses(self.primary_types, subclasscheck=True):
            return 1

        return NotImplemented  # unknown order (must check other)


def compare_backends(backend1, backend2, prioritize_over):
    # Environment variable prioritization beats everything:
    if (prio := prioritize_over.get(backend1.name)) and backend2.name in prio:
        return 3
    if (prio := prioritize_over.get(backend2.name)) and backend1.name in prio:
        return -3

    # Sort by the backends compare function (i.e. type hierarchy and manual order).
    # We default to a type based comparisons but allow overriding this, so check
    # both ways (to find the overriding).  This also find inconcistencies.
    cmp1 = backend1.compare_with_other(backend2)
    cmp2 = backend2.compare_with_other(backend1)
    if cmp1 is NotImplemented and cmp2 is NotImplemented:
        return 0
    if cmp1 is NotImplemented:
        return -cmp2
    if cmp2 is NotImplemented:
        return cmp1

    if cmp1 == cmp2:
        raise RuntimeError(
            "Backends {backend1.name} and {backend2.name} report inconsistent "
            "priorities (this means they are buggy).  You can manually set "
            "a priority or remove one of the backends."
        )
    if cmp1 > cmp2:
        return cmp1
    return -cmp2


def _modified_state(
    backend_system,
    curr_state,
    prioritize=(),
    disable=(),
    type=None,
    trace=None,
    unknown_backends="raise",
):
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
        if b not in backend_system.backends:
            if unknown_backends == "raise":
                raise ValueError(f"Backend '{b}' not found.")
            if unknown_backends == "ignore":
                pass
            else:
                raise ValueError("_modified_state() unknown_backends must be raise or ignore")

    if type is not None:
        if not backend_system.known_type(type, primary=True):
            raise ValueError(
                f"Type '{type}' not a valid primary type of any backend. "
                "It is impossible to enforce use of this type for any function."
            )

    ordered_backends, _, prioritized, curr_trace = curr_state
    prioritized = prioritized | frozenset(prioritize)
    ordered_backends = prioritize + ordered_backends

    # TODO: We could/should have a faster deduplication here probably
    #       (i.e. reduce the overhead of entering the context manager)
    ordered_backends = tuple({b: None for b in ordered_backends if b not in disable})

    if trace:
        # replace the current trace state.
        curr_trace = []

    return (ordered_backends, type, prioritized, curr_trace)


class BackendOpts:
    # Base-class, we create a new subclass for each backend system.
    _dispatch_state = None
    _backend_system = None
    __slots__ = ("backends", "prioritized", "type", "trace", "_state", "_token")

    def __init__(self, *, prioritize=(), disable=(), type=None, trace=False):
        """Customize or query the backend dispatching behavior.

        Context manager to allow customizing the dispatching behavior.
        Instantiating the context manager fetches the current dispatching state,
        modifies it as requested, and then stores the state.
        You can use this context multiple times (but not nested).
        :py:func:`~BackendOpts.enable_globally()` can be used for convenience but
        should only be used from the main program.

        Initializing ``BackendOpts`` without arguments can be used to query
        the current state.

        See :py:func:`~BackendOpts.__call__` for information about use as a
        function decorator.

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
        backends : tuple of str
            Tuple of active backend names in order of priority. If type
            is set, not all will be applicable and type specialized backends
            have typically a lower priority since they will be chosen based
            on input types.
        prioritized : frozenset
            Frozenset of currently prioritized backends.
        type
            The type to dispatch for within this context.
        trace
            The trace object (currenly a list as described in the examples).
            If used, the trace is also returned when entering the context.

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
        break assumptions in their code and while a third party may ensure the
        correct type for them locally it is not a bug for them not to do so.

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
        self._state = _modified_state(
            self._backend_system,
            self._dispatch_state.get(),
            prioritize=prioritize,
            disable=disable,
            type=type,
            trace=trace,
        )
        # unpack new state to provide information:
        self.backends, self.prioritized, self.type, self.trace = self._state
        self._token = None

    def __repr__(self):
        # We could allow a repr that can be copy pasted, but this seems more clear?
        inactive = tuple(b for b in self._backend_system.backends if b not in self.backends)
        type_str = "    type: {tuple(self.type)[0]!r}\n" if self.type else ""
        return (
            f"<Backend options:\n"
            f"   active: {self.backends}\n"
            f"   inactive: {inactive}\n"
            f"{type_str}"
            f"   tracing: {self.trace is not None}\n"
            f">"
        )

    def enable_globally(self):
        """Apply these backend options globally.

        Setting this state globally should only be done by the end user
        and never by a library. Global change of behavior may modify
        unexpected parts of the code (e.g. in third party code) so that it
        is safer to use the contextmanager ``with`` statement instead.

        This method will issue a warning if the
        dispatching state has been previously modified programatically.
        """
        curr_state = self._dispatch_state.get(None)  # None used before default
        # If the state was never set or the state matches (ignoring trace)
        # and there was no trace registered before this is OK. Otherwise warn.
        if curr_state is not None and (
            curr_state[:-1] != self._state[:-1] or curr_state[-1] is not None
        ):
            warnings.warn(
                "Backend options were previously modified, global change of the "
                "backends state should only be done once from the main program.",
                UserWarning,
                2,
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

    def __call__(self, func):
        """Decorate a function to freeze its dispatching state.

        ``BackendOpts`` can be used as a decorator, it means freezing the
        state early (user context around call is ignored).
        In other words, the following two patterns are very different, because
        for the decorator, ``backend_opts`` is called outside of the function::

            @backend_opts(...)
            def func():
                # code

            def func():
                with backend_opts(...):
                    # code

        .. note::
            An option here is to add ``isolated=False`` to allow mutating
            the context at call-time/time of entering (``isolated=False``
            would do nothing in a simple context manager use-case).

        Parameters
        ----------
        func : callable
            The function to decorate.

        Returns
        -------
        func : callable
            The decorated function.
        """

        # In this form, allow entering multiple times by storing the token
        # inside the wrapper functions locals
        @functools.wraps(func)
        def bakendopts_wrapped(*args, **kwargs):
            _token = self._dispatch_state.set(self._state)
            try:
                return func(*args, **kwargs)
            finally:
                self._dispatch_state.reset(_token)

        return bakendopts_wrapped


class BackendSystem:
    def __init__(self, group, environ_prefix, default_primary_types=None, backends=None):
        """Create a backend system that provides a @dispatchable decorator.

        The backend system also has provides the ``backend_opts`` context manager
        which can be re-exposed by the library.

        .. note::
            Currently, there is a lot of public methods here, these should be hidden
            away.

        Parameters
        ----------
        group : str or None
            The group of the backend entry points.  All backends are entry points
            that are immediately loaded.
            If None, no entry points will be loaded (this is mainly for testing).
        environ_prefix : str
            Prefix for environment variables to modify the dispatching behavior.
            ``spatch`` currently queries the following variables (see :ref:`for_users`).

            - ``f"{environ_prefix}_SET_ORDER"``
            - ``f"{environ_prefix}_PRIORITIZE"``
            - ``f"{environ_prefix}_BLOCK"``

        default_primary_types : frozenset or None
            The set of types that are considered primary by default.  Types listed
            here must be added as "secondary" types to backends if they wish
            to support them.
            If not provided, a "default" backend is not created!

        backends : sequence of backend namespaces
            Register a set of backends explicitly.  This exists largely for testing
            but may be used for a library to add internal backends.
            (The order of backends passed is used and should be consistent between runs.)

        """
        self.backends = {}
        if default_primary_types is not None:
            self.backends["default"] = Backend(
                name="default", primary_types=TypeIdentifier(default_primary_types)
            )

        try:
            set_order = os.environ.get(f"{environ_prefix}_SET_ORDER", "").split(",")
            set_order = [_ for _ in set_order if _]  # ignore empty chunks
            prioritize_over = {}
            for orders_str in set_order:
                orders = orders_str.split(">")
                if len(set(orders)) != len(orders):
                    # A backend showing up twice, means there is an inconsistency
                    raise ValueError(
                        f"Invalid order with duplicate backend in environment "
                        f"variable {environ_prefix}_SET_ORDER:\n"
                        f"    {orders_str}"
                    )
                prev_b = None
                for b in orders:
                    if not valid_backend_name(b):
                        raise ValueError(
                            f"Name {b!r} in {environ_prefix}_SET_ORDER is not a valid backend name."
                        )
                    if prev_b is not None:
                        prioritize_over.setdefault(prev_b, set()).add(b)
                        # If an opposite prioritization was already set, discard it.
                        # This allows `,backend2>backend1` to overrides a previous setting.
                        if b in prioritize_over:
                            prioritize_over[b].discard(prev_b)
                    prev_b = b
        except Exception as e:
            warnings.warn(
                f"Ignoring invalid environment variable {environ_prefix}_SET_ORDER "
                f"due to error: {e}",
                UserWarning,
                2,
            )

        try:
            prioritize = os.environ.get(f"{environ_prefix}_PRIORITIZE", "").split(",")
            prioritize = [_ for _ in prioritize if _]  # ignore empty chunks
            for b in prioritize:
                if not valid_backend_name(b):
                    raise ValueError(
                        f"Name {b!r} in {environ_prefix}_PRIORITIZE is not a valid backend name."
                    )
        except Exception as e:
            warnings.warn(
                f"Ignoring invalid environment variable {environ_prefix}_PRIORITIZE "
                f"due to error: {e}",
                UserWarning,
                2,
            )

        try:
            blocked = os.environ.get(f"{environ_prefix}_BLOCK", "").split(",")
            blocked = [_ for _ in blocked if _]  # ignore empty chunks
            for b in blocked:
                if not b.isidentifier():
                    raise ValueError(
                        f"Name {b!r} in {environ_prefix}_PRIORITIZE is not a valid backend name."
                    )
        except Exception as e:
            warnings.warn(
                f"Ignoring invalid environment variable {environ_prefix}_SET_ORDER "
                f"due to error: {e}",
                UserWarning,
                2,
            )

        # Note that the order of adding backends matters, we add `backends` first
        # and then entry point ones in alphabetical order.
        backends = list(backends) if backends is not None else []
        backends = backends + self._get_entry_points(group, blocked)
        for backend in backends:
            if backend.name in blocked:
                continue  # also skip explicitly added ones (even "default")
            try:
                self.backend_from_namespace(backend)
            except Exception as e:
                warnings.warn(f"Skipping backend {backend.name} due to error: {e}", UserWarning, 2)

        # Create a directed graph for which backends have a known higher priority than others.
        # The topological sorter is stable with respect to the original order, so we add
        # the "default" first and then other backends in order.  The one additional step is that
        # non-abstract matching backends are always ordered before abstract ones.
        graph = {"default": []}
        graph.update({n: [] for n, b in self.backends.items() if not b.primary_types.is_abstract})
        graph.update({n: [] for n, b in self.backends.items() if b.primary_types.is_abstract})

        backends = [self.backends[n] for n in graph]
        for i, b1 in enumerate(backends):
            for b2 in backends[i + 1 :]:
                cmp = compare_backends(b1, b2, prioritize_over)
                if cmp < 0:
                    graph[b1.name].append(b2.name)
                elif cmp > 0:
                    graph[b2.name].append(b1.name)

        order = self._toposort(graph)

        # Finalize backends to be a dict sorted by priority.
        self.backends = {b: self.backends[b] for b in order}
        # The state is the ordered (active) backends and the prefered type (None)
        # and the trace (None as not tracing).
        base_state = (order, None, frozenset(), None)
        disable = {b.name for b in self.backends.values() if b.requires_opt_in}
        state = _modified_state(
            self, base_state, prioritize=prioritize, disable=disable, unknown_backends="ignore"
        )
        self._dispatch_state = contextvars.ContextVar(f"{group}.dispatch_state", default=state)

    @staticmethod
    def _toposort(graph):
        # Adapted from Wikipedia's depth-first pseudocode. We are not using graphlib,
        # because it doesn't preserve the original order correctly.
        # This depth-first approach does preserve it.
        def visit(node, order, _visiting={}):
            if node in order:
                return
            if node in _visiting:
                cycle = (tuple(_visiting.keys()) + (node,))[::-1]
                raise RuntimeError(
                    f"Backends form a priority cycle.  This is a bug in a backend or your\n"
                    f"environment settings. Check the environment variable {environ_prefix}_SET_ORDER\n"
                    f"and change it for example to:\n"
                    f'    {environ_prefix}_SET_ORDER="{cycle[-1]}>{cycle[-2]}"\n'
                    f"to break the offending cycle:\n"
                    f"    {'>'.join(cycle)}"
                ) from None

            _visiting[node] = None  # mark as visiting/in-progress
            for n in graph[node]:
                visit(n, order, _visiting)

            del _visiting[node]
            order[node] = None  # add sorted node

        to_sort = list(graph.keys())
        order = {}  # dict as a sorted set
        for n in list(graph.keys()):
            visit(n, order)

        return tuple(order.keys())

    @staticmethod
    def _get_entry_points(group, blocked):
        """Get backends from entry points.  Result is sorted alphabetically
        to ensure a stable order.
        """
        if group is None:
            return []

        backends = []
        eps = importlib_metadata.entry_points(group=group)
        for ep in eps:
            if ep.name in blocked:
                continue
            try:
                namespace = ep.load()
                if ep.name != namespace.name:
                    raise RuntimeError(
                        f"Entrypoint name {ep.name!r} and actual name {namespace.name!r} mismatch."
                    )
                backends.append(namespace)
            except Exception as e:
                warnings.warn(f"Skipping backend {ep.name} due to error: {e}", UserWarning, 3)

        return sorted(backends, key=lambda x: x.name)

    @functools.lru_cache(maxsize=128)
    def known_type(self, dispatch_type, primary=False):
        for backend in self.backends.values():
            if backend.known_type(dispatch_type):
                return True
        return False

    def get_known_unique_types(self, dispatch_types):
        # From a list of args, return only the set of dispatch types
        return frozenset(val for val in dispatch_types if self.known_type(val))

    @functools.lru_cache(maxsize=128)
    def get_types_and_backends(self, dispatch_types, ordered_backends):
        """Fetch dispatch types and matching backends.

        The main purpose of this function is to cache the results for a set
        of unique input types to functions.
        Since not all backends will support all functions, the implementation
        still needs to filter for that.
        (For now, we assume that this is OK, it shouldl be but we could optimize
        it by not using dicts/in C or move/add caching to the function level.)

        Returns
        -------
        dispatch_types : frozenset
            The set of dispatch types that are known to the backend system.
        matching_backends : tuple
            A tuple of backend names sorted by priority.
        """
        # Filter out unknown types:
        dispatch_types = self.get_known_unique_types(dispatch_types)

        matching_backends = tuple(
            n for n in ordered_backends if self.backends[n].matches(dispatch_types)
        )
        return dispatch_types, matching_backends

    def backend_from_namespace(self, info_namespace):
        new_backend = Backend.from_namespace(info_namespace)
        if new_backend.name in self.backends:
            warnings.warn(
                f"Backend of name '{new_backend.name}' already exists. Ignoring second!",
                UserWarning,
                3,
            )
            return
        self.backends[new_backend.name] = new_backend

    def dispatchable(self, dispatch_args=None, *, module=None, qualname=None):
        """
        Decorator to mark functions as dispatchable.

        Decorate a Python function with information on how to extract
        the "dispatch" arguments, i.e. arguments we wish to dispatch for.

        Parameters
        ----------
        dispatch_args : str, sequence of str, dict, callable, or None
            Indicate the parameters that we should consider for dispatching.
            Parameters not listed here will be ignored for dispatching
            purposes. For example, this may be all array inputs to a function.
            Can be one of:

            * ``None``: All parameters are used.
            * string: The name of the parameter to extract.
            * list or tuple of string: The names of parameters to extract.
            * dict: A dictionary of `{name: position}` (not checked for
              correctness).
            * callable: A function that matches the signature and returns
              an iterable of dispatch arguments.

            If one or more names, ``spatch`` uses ``inspect.signature`` to
            find which positional argument it refers to.
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

            disp = Dispatchable(self, func, dispatch_args)

            return disp

        return wrap_callable

    @functools.cached_property
    def backend_opts(self):
        """Property returning a :py:class:`BackendOpts` class specific to this library
        (tied to this backend system).
        """
        return type(
            "BackendOpts",
            (BackendOpts,),
            {"_dispatch_state": self._dispatch_state, "_backend_system": self},
        )


@dataclass(slots=True)
class DispatchContext:
    """Additional information passed to backends about the dispatching.

    ``DispatchContext`` is passed as first (additional) argument to
    ``should_run``and to a backend implementation (if desired).
    Some backends will require the ``types`` attribute.

    Attributes
    ----------
    types : tuple[type, ...]
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

    dispatch_args : tuple[Any, ...]
        The arguments for which we dispatched. This can be useful information
        for some generic wrappers who still need to inspect all dispatch arguments.

        .. note::
            ``dispatch_args`` can be empty if a function takes no arguments.
            Yet, a backend version may be called explicitly e.g. in a
            ``with backend_opts(type=): ...`` context.

    name : str
        The name of the backend that was selected.

    prioritized : bool
        Whether the backend is prioritized. You may use this for example when
        deciding if you want to defer with ``should_run``.  Or it may be fine
        to use this to decide that e.g. a NumPy array will be converted to a
        cupy array, but only if prioritized.
    """

    # The idea is for the context to be very light-weight so that specific
    # information should be properties (because most likely we will never need it).
    # This object can grow to provide more information to backends.
    types: tuple[type, ...]
    dispatch_args: tuple[Any, ...]
    name: str
    _state: tuple

    @property
    def prioritized(self):
        return self.name in self._state[2]


@dataclass(slots=True)
class _Implementation:
    # Represent the implementation of a function.  Both function and should_run
    # are stored either as string identifiers or callables.
    # (In theory, we could move `should_run` loading to earlier to not re-check it.)
    backend: str
    _function: Callable | str
    should_run: Callable | None
    uses_context: bool

    @property
    def function(self):
        # Need to load function as lazy as possible to avoid loading if should_run
        # defers.
        _function = self._function
        if type(_function) is not str:
            return _function
        _function = from_identifier(_function)
        self._function = _function
        return _function


class _Implentations(dict):
    # A customized dict to lazy load some information from the implementation.
    # Right now, this is just `should_run`, `function` should be later so that
    # `should_run` could be light-weight if desired.
    def __init__(self, _impl_infos):
        self._impl_infos = _impl_infos

    def __missing__(self, backend_name):
        info = self._impl_infos.get(backend_name)
        if info is None:
            return None

        should_run = info.get("should_run", None)
        if should_run is not None:
            should_run = from_identifier(should_run)

        return _Implementation(
            backend_name,
            info["function"],
            should_run,
            info.get("uses_context", False),
        )

    def __repr__(self):
        # Combine evaluated and non-evaluated information for printing.
        all_infos = {}
        all_infos.update(self._impl_infos)
        all_infos.update(self)
        return f"_Implentations({all_infos!r})"


class Dispatchable:
    # Dispatchable function object
    #
    # TODO: We may want to return a function just to be nice (not having a func was
    # OK in NumPy for example, but has a few little stumbling blocks)
    def __init__(self, backend_system, func, dispatch_args, ident=None):
        functools.update_wrapper(self, func)

        self._backend_system = backend_system
        self._default_func = func
        if ident is None:
            ident = get_identifier(func)

        self._ident = ident

        if isinstance(dispatch_args, str | list | tuple):
            import inspect

            if isinstance(dispatch_args, str):
                dispatch_args = (dispatch_args,)

            sig = inspect.signature(func)
            new_dispatch_args = {}
            for i, p in enumerate(sig.parameters.values()):
                if p.name not in dispatch_args:
                    continue
                if (
                    p.kind == inspect.Parameter.POSITIONAL_ONLY
                    or p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                ):
                    # Accepting it as a keyword is irrelevant here (fails later)
                    new_dispatch_args[p.name] = i
                elif p.kind == inspect.Parameter.KEYWORD_ONLY:
                    new_dispatch_args[p.name] = sys.maxsize
                else:
                    raise TypeError(
                        f"Parameter {p.name} is variable. Must use callable `dispatch_args`."
                    )

            if len(dispatch_args) != len(new_dispatch_args):
                not_found = set(dispatch_args) - set(new_dispatch_args)
                raise TypeError(f"Parameters not found in signature: {not_found!r}")
            dispatch_args = new_dispatch_args
        elif isinstance(dispatch_args, dict):
            pass  # assume the dict is correct.
        elif isinstance(dispatch_args, Callable):
            # Simply use the function as is (currently ensure a tuple later)
            self._get_dispatch_args = dispatch_args
            dispatch_args = None
        elif dispatch_args is not None:
            raise ValueError(f"Invalid dispatch_args: {dispatch_args!r}")

        self._dispatch_args = dispatch_args

        new_doc = []
        impl_infos = {}
        for backend in backend_system.backends.values():
            if backend.name == "default":
                continue

            info = backend.functions.get(self._ident, None)
            if info is None:
                continue  # Backend does not implement this function.

            impl_infos[backend.name] = info

            new_blurb = info.get("additional_docs", "No backend documentation available.")
            new_doc.append(f"{backend.name} :\n" + textwrap.indent(new_blurb, "    "))

        # Create implementations, lazy loads should_run (and maybe more in the future).
        self._implementations = _Implentations(impl_infos)
        self._implementations["default"] = _Implementation(
            "default",
            self._default_func,
            None,
            False,
        )

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

    def _get_dispatch_args(self, *args, **kwargs):
        # Return all dispatch args
        if self._dispatch_args is None:
            return args + tuple(kwargs.values())
        return tuple(
            val
            for name, pos in self._dispatch_args.items()
            if (val := args[pos] if pos < len(args) else kwargs.get(name)) is not None
        )

    def __call__(self, *args, **kwargs):
        dispatch_args = tuple(self._get_dispatch_args(*args, **kwargs))
        # At this point dispatch_types is not filtered for known types.
        dispatch_types = {type(val) for val in dispatch_args}
        state = self._backend_system._dispatch_state.get()
        ordered_backends, type_, prioritized, trace = state

        if type_ is not None:
            dispatch_types.add(type_)
        dispatch_types = frozenset(dispatch_types)

        dispatch_types, matching_backends = self._backend_system.get_types_and_backends(
            dispatch_types, ordered_backends
        )

        if trace is not None:
            call_trace = []
            trace.append((self._ident, call_trace))
        else:
            call_trace = None

        for name in matching_backends:
            impl = self._implementations[name]
            if impl is None:
                # Backend does not implement this function, in the future we
                # may want to optimize this (in case many backends have few functions).
                continue

            context = DispatchContext(tuple(dispatch_types), dispatch_args, name, state)

            should_run = impl.should_run
            if should_run is None or (should_run := should_run(context, *args, **kwargs)) is True:
                if call_trace is not None:
                    call_trace.append((name, "called"))

                if impl.uses_context:
                    return impl.function(context, *args, **kwargs)
                return impl.function(*args, **kwargs)

            if should_run is not False:
                # Strict to allow future use as "should run if needed only".  That would merge
                # "can" and "should" run.  I can see a dedicated `can_run`, but see it as more
                # useful if `can_run` was passed only cachable parameters (e.g. `method="meth"`,
                # or even `backend=`, although that would be special).
                # (We may tag on a reason for a non-True return value as well or use context.)
                raise NotImplementedError("Currently, should run must return True or False.")
            if trace is not None and impl.should_run is not None:
                call_trace.append((name, "skipped due to should_run returning False"))

        if call_trace is not None:
            call_trace.append(("default fallback", "called"))

        return self._default_func(*args, **kwargs)
