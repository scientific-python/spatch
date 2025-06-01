.. _for_users:

User API
========

Users of libraries that integrate spatch should usually refer to the
library documentation.

In general, the main interaction with spatch will be to modify dispatching
behavior.
We expect further inspection and modification API to be added int he future.

Libraries will have three environment variables that can modify behavior
at startup time.

* ``<SPECIFIC_NAME>_SET_ORDER``: Comma seperated list of backend orders.
  seperated by ``>``.  I.e. ``name1>name2,name3>name2`` means that ``name1``
  and ``name3`` are ordered before ``name1``.
  (The below environment variable take precedence.)
* ``<SPECIFIC_NAME>_DISABLE``: Comma seperated list of backends.
  This is the same as :py:class:`BackendOpts` ``disable=`` option.
* ``<SPECIFIC_NAME>_PRIORITIZE``: Comma seperated list of backends.
  This is the same as :py:class:`BackendOpts` ``prioritize=`` option.

Note that unknown backend names are ignored in these variables, so check these
carefully.

Modifying and tracing dispatching
---------------------------------

(This functionality will be re-exposed by the library in some form.)

.. autoclass:: spatch.backend_system.BackendOpts
    :class-doc-from: init
    :members: enable_globally, __call__
