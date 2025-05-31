User API
========

Users of libraries that integrate spatch should usually refer to the
library documentation.

In general, the main interaction with spatch will be to modify dispatching
behavior.
We expect further inspection and modification API to be added int he future.

Modifying and tracing dispatching
---------------------------------

(This functionality will be re-exposed by the library in some form.)

.. autoclass:: spatch.backend_system.BackendOpts
    :class-doc-from: init
    :members: enable_globally
