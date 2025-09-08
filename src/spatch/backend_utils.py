import pathlib
import warnings
from collections.abc import Callable
from dataclasses import dataclass

from .utils import from_identifier, get_identifier


@dataclass
class BackendFunctionInfo:
    func: Callable
    api_identity: str
    impl_identity: str
    uses_context: bool
    should_run: Callable | None
    should_run_identity: str | None


class BackendImplementation:
    name: str
    api_to_info: dict[str, BackendFunctionInfo]
    impl_to_info: dict[str, BackendFunctionInfo]

    def __init__(self, backend_name: str):
        """Helper class to create backends."""
        self.name = backend_name
        self.api_to_info = {}  # {api_identity_string: backend_function_info}
        self.impl_to_info = {}  # {impl_identity_string: backend_function_info}

    def implements(
        self,
        api_identity: str | Callable,
        *,
        should_run: str | Callable | None = None,
        uses_context: bool = False,
    ):
        """Mark function as an implementation of a dispatchable library function.

        This is a decorator to facilitate writing an entry-point and potentially
        attaching ``should_run``. It is not necessary to use this decorator
        and you may want to wrap it into a convenience helper for your purposes.

        Parameters
        ----------
        api_identity
            The original function to be wrapped. Either as a string identity
            or the callable (from which the identifier is extracted).
        should_run
            Callable or a string with the module and name for a ``should_run``
            function.  A ``should_run`` function takes a ``DispatchInfo``
            object as first argument and otherwise all arguments of the wrapped
            function.
            It must return ``True`` if the backend should be used.

            It is the backend author's responsibility to ensure that ``should_run``
            is not called unnecessarily and is ideally very light-weight (if it
            doesn't return ``True``).
            (Any return value except ``True`` is considered falsy to allow the return
            to be used for diagnostics in the future.)
        uses_context
            Whether the function should be passed a ``DispatchContext`` object
            as first argument.
        """
        if callable(api_identity):
            api_identity = get_identifier(api_identity)

        if should_run is None:
            should_run_identity = None
        elif isinstance(should_run, str):
            should_run_identity = should_run
            should_run = from_identifier(should_run)
        else:
            try:
                # Handle misc. callables such as `functools.partial`
                should_run_identity = get_identifier(should_run)
            except Exception:
                should_run_identity = None
            else:
                if should_run_identity.endswith(":<lambda>"):
                    should_run_identity = None

        def inner(func):
            impl_identity = get_identifier(func)
            if should_run is not None and should_run_identity is None:
                # If `should_run` is not resolvable, save it on the function
                func._should_run = should_run
                should_run_ident = f"{impl_identity}._should_run"
            else:
                should_run_ident = should_run_identity
            info = BackendFunctionInfo(
                func,
                api_identity,
                impl_identity,
                uses_context,
                should_run,
                should_run_ident,
            )
            self.api_to_info[api_identity] = info
            self.impl_to_info[impl_identity] = info  # Assume 1:1 for now
            return func

        return inner

    def set_should_run(self, backend_func: str | Callable):
        """Alternative decorator to set the ``should_run`` function.

        This is a decorator to decorate a function as ``should_run``.  If
        the function is a lambda or called ``_`` it is attached to the
        wrapped backend function (cannot be a string).
        Otherwise, it is assumed that the callable can be found at runtime.

        Parameters
        ----------
        backend_func
            The backend function for which we want to set ``should_run``.
        """
        if isinstance(backend_func, str):
            impl_identity = backend_func
        else:
            impl_identity = get_identifier(backend_func)

        def inner(func: Callable):
            identity = get_identifier(func)
            if identity.endswith((":<lambda>", ":_")):
                backend_func._should_run = func
                identity = f"{impl_identity}._should_run"
            info = self.impl_to_info[impl_identity]
            info.should_run = func
            info.should_run_identity = identity
            return func

        return inner


def find_submodules(module_name: str):
    import importlib
    import pkgutil

    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return
    yield module_name
    if not spec.submodule_search_locations:
        return
    for info in pkgutil.iter_modules(spec.submodule_search_locations):
        yield from find_submodules(f"{module_name}.{info.name}")


def import_all_submodules(module_name: str):
    """Import a module and all of its submodules."""
    import importlib

    for modname in find_submodules(module_name):
        importlib.import_module(modname)


def update_entrypoint(filepath: str):
    import inspect  # for `inspect.cleandoc`

    import tomlkit

    with pathlib.Path(filepath).open() as f:
        data = tomlkit.load(f)

    defaults = {
        "function": None,
        "should_run": None,
        "uses_context": False,
        "additional_docs": None,
    }
    defaults.update(data["functions"].get("defaults", {}))
    auto_generation = data["functions"].get("auto-generation", {})

    try:
        backend = auto_generation["backend"]
    except KeyError:
        raise KeyError(
            "entry-point toml file must contain a `functions.auto-generation.backend` key."
        )

    backend = from_identifier(backend)
    if backend.name != data["name"]:
        raise ValueError(
            f"toml backend '{backend.name}' name and loaded backend name "
            f"'{data['name']}' do not match."
        )
    module_names = auto_generation.get("modules", [])

    # Step 1: import all backend modules
    if isinstance(module_names, str):
        module_names = [module_names]
    if module_names:
        for module_name in module_names:
            import_all_submodules(module_name)

    if "functions" not in data:
        data["functions"] = {}

    functions = data["functions"]

    # Step 2: collect function info and make sure entries match defaults or are removed
    for _, info in sorted(backend.api_to_info.items(), key=lambda item: item[0]):
        if info.api_identity not in functions:
            functions[info.api_identity] = {}

        func_info = functions[info.api_identity]

        new_values = {
            "function": info.impl_identity,
            "should_run": info.should_run_identity,
            "uses_context": info.uses_context,
            "additional_docs": tomlkit.string(inspect.cleandoc(info.func.__doc__), multiline=True),
        }

        for attr, value in new_values.items():
            if value != defaults[attr]:
                func_info[attr] = value
            elif attr in func_info:
                func_info.pop(attr)

    # Step 3: remove functions that are not in the backend
    for func_ident in list(functions.keys()):
        if func_ident in ["auto-generation", "defaults"]:
            continue  # not function identifiers that may be deleted
        if func_ident not in backend.api_to_info:
            del functions[func_ident]

    with pathlib.Path(filepath).open(mode="w") as f:
        tomlkit.dump(data, f)


def verify_entrypoint(filepath: str):
    from importlib import import_module

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # for Python 3.10 support

    with pathlib.Path(filepath).open("rb") as f:
        data = tomllib.load(f)

    schema = {
        "name": "python_identifier",
        "primary_types": ["dispatch_identifier"],
        "secondary_types": ["dispatch_identifier"],
        "requires_opt_in": bool,
        "higher_priority_than?": ["python_identifier"],
        "lower_priority_than?": ["python_identifier"],
        "functions": {
            "auto-generation?": {
                "backend": "dispatch_identifier",
                "modules?": "modules",
            },
            "defaults?": {
                "function?": "dispatch_identifier",
                "should_run?": "dispatch_identifier",
                "additional_docs?": str,
                "uses_context?": bool,
            },
        },
    }
    function_schema = {
        "function": "dispatch_identifier",
        "should_run?": "dispatch_identifier",
        "additional_docs?": str,
        "uses_context?": bool,
    }

    def to_path_key(path):
        # We indicate list elements with [i], which isn't proper toml
        path_key = ".".join(f'"{key}"' if "." in key or ":" in key else key for key in path)
        return path_key.replace(".[", "[")

    def handle_bool(path_key, val):
        if not isinstance(val, bool):
            raise TypeError(f"{path_key} = {val} value is not a bool; got type {type(val)}")

    def handle_str(path_key, val):
        if not isinstance(val, str):
            raise TypeError(f"{path_key} = {val} value is not a str; got type {type(val)}")

    def handle_python_identifier(path_key, val):
        handle_str(path_key, val)
        if not val.isidentifier():
            raise ValueError(f"{path_key} = {val} value is not a valid Python identifier")

    def handle_dispatch_identifier(path_key, val, path):
        handle_str(path_key, val)
        try:
            from_identifier(val)
        except ModuleNotFoundError as exc:
            # Should we allow this to be strict? What if other packages aren't installed?
            warnings.warn(
                f"{path_key} = {val} identifier not found: {exc.args[0]}",
                UserWarning,
                len(path) + 1,  # TODO: figure out
            )
        except AttributeError as exc:
            raise ValueError(f"{path_key} = {val} identifier not found") from exc

    def handle_modules(path_key, val):
        if isinstance(val, str):
            val = [val]
        elif not isinstance(val, list):
            raise TypeError(f"{path_key} = {val} value is not a str or list; got type {type(val)}")
        for i, module_name in enumerate(val):
            inner_path_key = f"{path_key}[{i}]"
            handle_str(inner_path_key, module_name)
            try:
                import_module(module_name)
            except ModuleNotFoundError as exc:
                raise ValueError(f"{inner_path_key} = {module_name} module not found") from exc

    def check_schema(schema, data, path=()):
        # Show possible misspellings with a warning
        schema_keys = {key.removesuffix("?") for key in schema}
        extra_keys = data.keys() - schema_keys
        if extra_keys and path != ("functions",):
            path_key = to_path_key(path)
            extra_keys = ", ".join(sorted(extra_keys))
            warnings.warn(
                f'"{path_key}" section has extra keys: {extra_keys}',
                UserWarning,
                len(path) + 1,  # TODO: figure out
            )

        for schema_key, schema_val in schema.items():
            key = schema_key.removesuffix("?")
            path_key = to_path_key((*path, key))
            if len(key) != len(schema_key):  # optional key
                if key not in data:
                    continue
            elif key not in data:
                raise KeyError(f"Missing required key: {path_key}")

            val = data[key]
            if schema_val is bool:
                handle_bool(path_key, val)
            elif schema_val is str:
                handle_str(path_key, val)
            elif isinstance(schema_val, dict):
                if not isinstance(val, dict):
                    raise TypeError(f"{path_key} value is not a dict; got type {type(val)}")
                check_schema(schema_val, val, (*path, key))
            elif isinstance(schema_val, list):
                if not isinstance(val, list):
                    raise TypeError(f"{path_key} value is not a list; got type {type(val)}")
                val_as_dict = {f"[{i}]": x for i, x in enumerate(val)}
                schema_as_dict = dict.fromkeys(val_as_dict, schema_val[0])
                check_schema(schema_as_dict, val_as_dict, (*path, key))
            elif schema_val == "python_identifier":
                handle_python_identifier(path_key, val)
            elif schema_val == "dispatch_identifier":
                handle_dispatch_identifier(path_key, val, path)
            elif schema_val == "modules":
                handle_modules(path_key, val)
            else:
                raise RuntimeError(f"unreachable: unknown schema: {schema_val}")

    check_schema(schema, data)

    def check_functions(function_schema, schema, data):
        function_keys_to_skip = {key.removesuffix("?") for key in schema.get("functions", {})}
        data_functions_schema = dict.fromkeys(
            (key for key in data["functions"] if key not in function_keys_to_skip),
            function_schema,
        )
        check_schema(data_functions_schema, data["functions"], ("functions",))

    check_functions(function_schema, schema, data)

    if (backend := data.get("functions", {}).get("auto-generation", {}).get("backend")) is not None:
        backend = from_identifier(backend)
        if backend.name != data["name"]:
            raise ValueError(
                f"toml backend '{backend.name}' name and loaded backend name "
                f"'{data['name']}' do not match."
            )
