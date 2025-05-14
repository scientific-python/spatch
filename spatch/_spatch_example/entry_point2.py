
name = "backend2"    
primary_types = ["builtins:float", "builtins:complex"]
secondary_types = ["builtins:int"]


functions = {
    "spatch._spatch_example.library:divide": {
        "function": "spatch._spatch_example.backend:divide2",
        "should_run": "spatch._spatch_example.backend:divide2._should_run",
        "additional_docs": "This is a test backend."
    }
}
