Backend API
===========

Backends have to do the heavy lifting of using spatch.
At the moment we suggest to check the
`example <https://github.com/scientific-python/spatch/tree/main/spatch/_spatch_example>`_.

Entry point definition
----------------------
To extend an existing library with a backend, you need to define an entry point.
This entry point includes the necessary information for spatch to find and
dispatch to your backend.

Before writing a backend, you need to think about a few things:

* Which types do you accept?  This could be NumPy, dask, jax, etc. arrays.
  There are two kind of types "primary" and "secondary".
  Secondary types are types that you accept, but intend to convert (e.g.
  you may accept NumPy arrays, but always convert them to cupy).
  Primary types are types that you work with (e.g. you return).
  If you have more than one primary type, you may need to take a lot of
  care about which type to return!
* Do you change behavior of the library (or existing major backends) by
  e.g. providing a faster but less accurate implementation?
  In that case, your backend should likely only be used if prioritized
  by the user.  (`spatch` tries to make this the default)

Please check the example linked above.  These example entry-points include
code that means running them modifies them in-place if the `@implements`
decorator is used (see next section).

Implementations for dispatchable functions
------------------------------------------

Spatch provides a decorator to mark functions as implementations.
Applying this decorator is not enough to actually dispatch but it can
be used to fill in the necessary information into the entry-point
definition.

.. autoclass:: spatch.backend_utils.BackendImplementation
    :members: implements, set_should_run

.. autoclass:: spatch.backend_system.DispatchContext
