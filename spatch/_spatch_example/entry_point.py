
name = "backend1"    
primary_types = ["builtins:float"]
secondary_types = ["builtins:int"]


functions = {
    "spatch._spatch_example.library:divide": {
        "function": "spatch._spatch_example.backend:divide",
        "should_run": "spatch._spatch_example.backend:divide._should_run",
        "additional_docs": "This is a test backend.",
        "uses_info": True,
    }
}

# TODO: The documentation has to tell people not to create circles.
# and that includes with the types?!
# prioritize_over_backends = ["numpy"]
