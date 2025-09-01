Backend API
===========

Backends have to do the heavy lifting of using spatch.
At the moment we suggest to check the
`example <https://github.com/scientific-python/spatch/tree/main/src/spatch/_spatch_example>`_.

Entry point definition
----------------------
To extend an existing library with a backend, you need to define a
`Python entry-point <https://packaging.python.org/en/latest/specifications/entry-points/>`_.
This entry point includes the necessary information for spatch to find and
dispatch to your backend.

``spatch`` entry-points are TOML files and *not* Python objects.
The entry-point value must point to the file with
``module.submodule:filename.toml``. [#ep-value-structure]_

Before writing a backend, you need to think about a few things:

* Which types do you accept?  This could be NumPy, dask, jax, etc. arrays.
  There are two kind of types "primary" and "secondary".
  Secondary types are types that you accept, but intend to convert (e.g.
  you may accept NumPy arrays, but always convert them to cupy).
  Primary types are types that you work with and return.
  If you have more than one primary type, you may need to take a lot of
  care about which type to return!
* Do you change behavior of the library (or existing major backends) by
  e.g. providing a faster but less accurate implementation?
  In that case, your backend should likely only be used if prioritized
  by the user.

Please check the example linked above.  ``spatch`` can automatically update
the functions entries in these entry-points if the ``@implements`` decorator
is used (see next section).

Some of the most important fields are:

``name``
^^^^^^^^

The name of the backend, must match the name of the entry-point.

``primary_types`` and ``secondary_types``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Primary and secondary types are defined by a sequence of strings
and stored as ``primary_types`` and ``secondary_types`` attributes in
the entry-point.
As everything, they are identified by ``"__module__:__qualname__"`` strings,
for example ``"numpy:ndarray"``.

We suggest that backends initially use exact type matches.
At least for arrays, subclasses commonly change behavior in large ways
(breaking Liskov substitution principle), so functions may not behave
correctly for them anyway.
However, we do support the following, e.g.:

- ``"numpy:ndarray"`` to match NumPy arrays exactly
- ``"~numpy:ndarray"`` to match any subclass of NumPy arrays
- ``"@module:qualname"`` to match any subclass of an abstract base class

.. warning::
  If you use an abstract base class, note that you must take additional care:

  - The abstract base class must be *cheap to import*, because we cannot avoid
    importing it.
  - Since we can't import all classes, ``spatch`` has no ability to order abstract
    classes correctly (but we order them last if a primary type, which is typically correct).
  - ``spatch`` will not guarantee correct behavior if an ABC is mutated at runtime.

``requires_opt_in``
^^^^^^^^^^^^^^^^^^^

A boolean indicating whether your backend should be active by default.
Typically, set this to ``True`` for a type dispatching backend and ``False`` otherwise.
A backend doing both needs to set it to ``True``, and must use ``should_run`` with
a ``context`` to disambiguate.

Based on library guidance and feedback a non-type dispatching backend may also
set this to ``True`` if it's behavior matches the library behavior closely.

.. warning::
   **Always** check with library guidelines or reach out to authors before setting
   this to ``True``.

   The golden rule is that behavior must be the same if your backend is
   installed but nothing else changes.

   And remember that *identical* is typically impossible in numerical computing.
   So always check with the library (or other backends) authors first what they
   consider to be an acceptable difference.

   Failure to do this, will just mean that ``spatch`` needs a way to block backends
   or only allow specific ones, and then everyone loses...


functions
^^^^^^^^^

A mapping of library functions to your implementations.  All fields use
the ``__module__:__qualname__`` identifiers.
The following fields are supported for each function:

- ``function``: The implementation to dispatch to.
- ``should_run`` (optional): A function that gets all inputs (and context)
  and can decide to defer.  Unless you know things will error, try to make sure
  that this function is light-weight.
- ``uses_context`` (optional): Whether the implementation needs a ``DispatchContext``.
- ``additional_docs`` (optional): Brief text to add to the documentation
  of the original function. We suggest keeping this short but including a
  link, but the library guidance should be followed.

A typical part of the entry-point TOML will look like this::

  [functions."skimage.filters:gaussian"]
  function = "cucim.skimage.filters:gaussian"
  uses_context = true
  additional_docs = "CUDA enabled version..."

An additional ``[functions.defaults]`` key can be added to set defaults for all
functions and avoid repeating e.g. ``uses_context``.

``spatch`` provides tooling to help create this mapping.  This tooling uses the
additional fields::

  [functions.auto-generation]
  # where to find the BackendImplementation:
  backend = "module.submodule:backend_name"
  # Additional modules to be imported (to ensure all functions are found):
  modules = ["spatch._spatch_example.backend"]

Manual backend prioritization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``spatch`` tries to order backends based on the types,
but this cannot get the order right always.
Thus, you can manually prioritize your backend over others by defining
for example ``higher_priority_than = ["default"]`` or
``lower_priority_than = ["default"]``.

It is your responsibility to ensure that these prioritizations make sense and
are acceptable to other backends.

More?
^^^^^

.. note:: Missing information?
  We are probably missing important information currently.  For example,
  maybe a version?  (I don't think we generally need it, but it may be
  interesting.)

.. [#ep-value-structure]
   ``spatch`` currently assumes submodules follow directory structure so that
   the file is located relative to the main ``module`` at
   ``module/submodule/filename.toml``.  As of 2025, do *not* use ``/`` in
   the filename, since the entry-point value may be checked for being a
   valid Python object ``__qualname__``, which a ``/`` is not.

Implementations for dispatchable functions
------------------------------------------

Spatch provides a decorator to mark functions as implementations.
Applying this decorator is not enough to actually dispatch but it can
be used to fill in the necessary information into the entry-point
definition.

.. autoclass:: spatch.backend_utils.BackendImplementation
    :members: implements, set_should_run

.. autoclass:: spatch.backend_system.DispatchContext
