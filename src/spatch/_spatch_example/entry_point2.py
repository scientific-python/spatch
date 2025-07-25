name = "backend2"
primary_types = ["builtins:float", "builtins:complex"]
secondary_types = ["builtins:int"]
requires_opt_in = False


# BEGIN AUTOGENERATED CODE: functions
functions = {
    "spatch._spatch_example.library:divide": {
        "function": "spatch._spatch_example.backend:divide2",
        "should_run": "spatch._spatch_example.backend:divide2._should_run",
        "additional_docs": (
            "This is a test backend!\n"
            "and it has a multi-line docstring which makes this longer than normal."
        ),
    }
}
# END AUTOGENERATED CODE: functions

if __name__ == "__main__":  # pragma: no cover
    # Run this file as a script to update this file
    from spatch._spatch_example.backend import backend2
    from spatch.backend_utils import update_entrypoint

    update_entrypoint(__file__, backend2, "spatch._spatch_example.backend")
