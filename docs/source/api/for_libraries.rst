Libraries
=========

Libraries using spatch need to create a backend and mark all their
functions as dispatchable.

You will also wish to re-expose the ``BackendSystem.backend_opts`` context
manager to users.

Please also see the `example code <https://github.com/scientific-python/spatch/tree/main/spatch/_spatch_example>`_
at this time.

API to create dispatchable functions
------------------------------------

.. autoclass:: spatch.backend_system.BackendSystem
    :class-doc-from: init
    :members: dispatchable, backend_opts
