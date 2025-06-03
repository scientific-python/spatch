.. _for_users:

User API
========

Users of libraries that integrate spatch should usually refer to the
library documentation.

In general, the main interaction with spatch will be to modify dispatching
behavior.
We expect further inspection and modification API to be added int he future.

Modifying and tracing dispatching
---------------------------------

Libraries will re-expose all of this functionality under their own API/names.

There are currently three global environment variables to modify dispatching
behavior at startup time:

* ``<SPECIFIC_NAME>_PRIORITIZE``: Comma seperated list of backends.
  This is the same as :py:class:`BackendOpts` ``prioritize=`` option.
* ``<SPECIFIC_NAME>_BLOCK``: Comma seperated list of backends.
  This prevents loading the backends completely as if they were not installed.
* ``<SPECIFIC_NAME>_SET_ORDER``: Comma seperated list of backend orders.
  seperated by ``>``.  I.e. ``name1>name2,name3>name2`` means that ``name1``
  and ``name3`` are ordered before ``name1``.  This is more fine-grained
  than the above two and the above two take precedence.  Useful to fix relative
  order of backends without affecting the priority of backends not listed
  (including when backends have issues and loading fails).

Note that unknown backend names are ignored in these variables, so check these
carefully.

The main interaction of users should however be via the backend options system:

.. autoclass:: spatch.backend_system.BackendOpts
    :class-doc-from: init
    :members: enable_globally, __call__
