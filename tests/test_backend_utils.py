import pathlib
import subprocess
import sys
import textwrap

import pytest

from spatch.backend_utils import _verify_entrypoint_dict


def test_entry_point_func_gen(tmp_path):
    # Check that our example entry points can re-generated themselves when run.
    # This also checks that the "functions" part doesn't get outdated.
    import spatch._spatch_example

    path = pathlib.Path(spatch._spatch_example.__file__).parent

    for entry_point in ["entry_point.toml", "entry_point2.toml"]:
        work_file = tmp_path / "entry_point_test.toml"
        content = (path / entry_point).read_text()
        corrupted_content = content.replace("spatch._spatch_example.backend:divide", "wrong")
        assert corrupted_content != content  # make sure corruption worked

        # Add a non-existing function to see it gets deleted
        corrupted_content += textwrap.dedent(
            """
            [functions."spatch._spatch_example.library:this_does_not_exist"]
            function = "spatch._spatch_example.backend:huhu"
            should_run = "spatch._spatch_example.backend:divide._should_run"
            """
        )
        work_file.write_text(corrupted_content)

        # Run the script
        subprocess.run(
            [sys.executable, "-m", "spatch", "update-entrypoints", work_file],
            check=True,
            capture_output=True,
        )

        # The file should have been fixed to contain the original text:
        assert work_file.read_text().strip() == content.strip()

        # Also verify the contents of the entrypoint
        subprocess.run(
            [sys.executable, "-m", "spatch", "verify-entrypoints", work_file],
            check=True,
            capture_output=True,
        )


def test_verify_entrypoint():
    schema = {
        "name": "backend1",
        "primary_types": [],
        "secondary_types": [],
        "requires_opt_in": True,
        "functions": {},
    }
    _verify_entrypoint_dict(schema)
    backend1_identifier = "spatch._spatch_example.backend:backend1"
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        _verify_entrypoint_dict({**schema, "name": "bad-backend"})
    with pytest.raises(TypeError, match="is not a list"):
        _verify_entrypoint_dict({**schema, "primary_types": "builtins:float"})
    with pytest.raises(TypeError, match="must be a type"):
        _verify_entrypoint_dict({**schema, "primary_types": ["builtins:float.__name__"]})
    with pytest.raises(ValueError, match="identifier not found"):
        _verify_entrypoint_dict({**schema, "primary_types": ["builtins:does_not_exist"]})
    with pytest.raises(ValueError, match="identifier not found"):
        _verify_entrypoint_dict({**schema, "secondary_types": ["foo:bar"]})
    with pytest.warns(UserWarning, match="identifier not found"):
        _verify_entrypoint_dict({**schema, "secondary_types": ["foo:bar"]}, {"foo"})
    with pytest.raises(TypeError, match="is not a bool"):
        _verify_entrypoint_dict({**schema, "requires_opt_in": "should_be_bool"})
    with pytest.raises(TypeError, match="is not a str"):
        _verify_entrypoint_dict({**schema, "functions": {"defaults": {"additional_docs": 777}}})
    with pytest.raises(TypeError, match="must be callable"):
        _verify_entrypoint_dict(
            {
                **schema,
                "functions": {
                    "spatch._spatch_example.library:divide": {
                        "function": "spatch._spatch_example.backend:divide.__name__"
                    }
                },
            }
        )
    with pytest.raises(TypeError, match="must be callable"):
        _verify_entrypoint_dict(
            {
                **schema,
                "functions": {
                    "spatch._spatch_example.library:divide.__name__": {
                        "function": "spatch._spatch_example.backend:divide"
                    }
                },
            }
        )
    with pytest.raises(TypeError, match="must be a BackendImplementation"):
        _verify_entrypoint_dict(
            {**schema, "functions": {"auto-generation": {"backend": "builtins:float"}}}
        )
    with pytest.raises(ValueError, match="'backend1' != 'backend_name'"):
        _verify_entrypoint_dict(
            {
                **schema,
                "name": "backend_name",
                "functions": {"auto-generation": {"backend": backend1_identifier}},
            }
        )
    with pytest.raises(ValueError, match="module not found"):
        _verify_entrypoint_dict(
            {
                **schema,
                "functions": {
                    "auto-generation": {
                        "backend": backend1_identifier,
                        "modules": ["bad_module_name"],
                    }
                },
            }
        )
    with pytest.warns(UserWarning, match="module not found"):
        _verify_entrypoint_dict(
            {
                **schema,
                "functions": {
                    "auto-generation": {
                        "backend": backend1_identifier,
                        "modules": "bad_module_name",
                    }
                },
            },
            {"bad_module_name"},
        )
    with pytest.raises(TypeError, match="str or list"):
        _verify_entrypoint_dict(
            {
                **schema,
                "functions": {"auto-generation": {"backend": backend1_identifier, "modules": 777}},
            },
            {"bad_module_name"},
        )
    with pytest.raises(TypeError, match="is not a dict"):
        _verify_entrypoint_dict({**schema, "functions": {"defaults": 777}})
    with pytest.raises(TypeError, match="is not a dict"):
        _verify_entrypoint_dict({**schema, "functions": 777})
    with pytest.warns(UserWarning, match="extra keys: extra_key"):
        _verify_entrypoint_dict({**schema, "extra_key": True})
    with pytest.warns(UserWarning, match="extra keys: extra_key"):
        _verify_entrypoint_dict({**schema, "functions": {"defaults": {"extra_key": True}}})
    incomplete_schema = dict(schema)
    del incomplete_schema["name"]
    with pytest.raises(KeyError, match="Missing required key"):
        _verify_entrypoint_dict(incomplete_schema)
    with pytest.raises(TypeError, match="dict"):
        _verify_entrypoint_dict(777)
