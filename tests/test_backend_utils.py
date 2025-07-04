import pathlib
import subprocess
import sys


def test_entry_point_func_gen(tmp_path):
    # Check that our example entry points can re-generated themselves when run.
    # This also checks that the "functions" part doesn't get outdated.
    import spatch._spatch_example

    path = pathlib.Path(spatch._spatch_example.__file__).parent

    for entry_point in ["entry_point.py", "entry_point2.py"]:
        work_file = tmp_path / "entry_point_test.py"
        content = (path / entry_point).read_text()
        corrupted_content = content.replace("functions =", "#modified\nfunctions =")
        assert corrupted_content != content  # make sure corruption worked
        work_file.write_text(corrupted_content)

        # Run the script
        subprocess.run([sys.executable, work_file], check=True, capture_output=True)

        # The file should have been fixed to contain the original text:
        assert work_file.read_text() == content
