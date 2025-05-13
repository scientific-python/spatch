
name = "backend1"    
primary_types = ["builtins:float", "builtins:complex"]
secondary_types = ["builtins:int"]


functions = {
    "spatch._spatch_example.library:divide": {
        "function": "spatch._spatch_example.backend:divide",
        "should_run": "spatch._spatch_example.backend:divide._should_run",
        "additional_docs": "This is a test backend."
    }
}
