import pathlib
import subprocess
import sys
import textwrap


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
