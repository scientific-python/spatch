# spatch

**`spatch` is still exploratory and design/API may change significantly
based on feedback.**

<!-- SPHINX-START -->

Spatch is a dispatching tool with a focus on scientific python libraries.
It integrates two forms of dispatching into a single backend system:
* Type dispatching for the main type used by a library.
  In the scientific python world, this is often the array object.
* Backend selection to offer alternative implementations to users.
  These may be faster or less precise, but using them should typically
  not change code behavior drastically.

Spatch is opinionated about these points being two different, but related,
use-cases.
It thus combines machinery to do both, but keeps the related choices
separate for the user (and library/backend authors).

## Type dispatching

Many libraries are written for NumPy, but users may wish to use them
with other types, for example because code needs to scale from an experiment
to a large scale deployment.

Unfortunately, providing code for a host of such types isn't easy
and the original library authors usually have neither the bandwidth nor
expertise to do it.  Additionally, such layers would have to be optional
components of the library.

`spatch` allows for a solution to this dilemma by allowing a third party
to enable library functions to work with alternative types.

It should be noted that spatch is not a generic multiple dispatching
library. It is opinionated about being strictly typed (we can and probably
will support subclasses in the future, though).
It also considers all arguments identically.  I.e. if a function takes
two inputs (of the kind we dispatch for), there is no distinction for
their order.
Besides these two things, `spatch` is however a typical type dispatching
library.

Type dispatching mostly _extends_ functionality to cover function inputs
that it did not cover before.
Users may choose to work with a specific type explicitly but in many cases
the input types decide the use here.

## Backend selection

The type dispatching functionality extends a library to support new types.
Another use-case is to not change which types we work with, but to
provide alternative implementations.

For example, we may have a faster algorithm that is parallelized while the
old one was not. Or an implementation that dispatches to the GPU but still
returns NumPy arrays (as the library always did).

Backend selection _modifies_ behavior rather than extending it.  In some
cases those modifications may be small (maybe it is really only faster).
For the user, backend _selection_ often means that they should explicitly
select a preferred backend (e.g. over the default implementation).
This could be for example via a context manager:
```python
with backend_opts(prioritize="gpu_backend"):
    library.function()  # now running on the GPU
```

<!-- SPHINX-STOP -->

# Development status

(Please bear in mind that this section may get outdated)

`spatch` is functional but not complete at this point and
it should be considered a prototype when it comes to API stability.

Some examples for missing things we are still working on:
* No way to conveniently see which backends may be used when calling a
  function (rather than actually calling it). And probably more inspection
  utilities.
* We have implemented the ability for a backend to defer and not run,
  but not the ability to run anyway if there is no alternative.
* The main library implementation currently can't distinguish fallback
  and default path easily. It should be easy to do this (two functions,
  `should_run`, or just via `uses_context`).
* `spatch` is very much designed to be fast but that doesn't mean it
  is particularly fast yet.  We may need to optimize parts (potentially
  lowering parts to a compiled language).
* We have not implemented tools to test backends, e.g. against parts
  of the original library.  We expect that "spatch" actually includes most
  tools to do this.  For example, we could define a `convert` function
  that backends can implement to convert arguments in tests as needed.

There are also many smaller or bigger open questions and those include whether
the API proposed here is actually quite what we want.
Other things are for example whether we want API like:
* `dispatchable.invoke(type=, backend=)`.
* Maybe libraries should use `like=` in functions that take no dispatchable
  arguments.
* How do we do classes such as scikit-learn estimators. A simple solution might
  a `get_backend(...)` dispatching explicitly once. But we could use more involved
  schemes, rather remembering the dispatching state of the `.fit()`.

We can also see many small conveniences, for example:
* Extract the dispatchable arguments from type annotations.
* Support a magic `Defer` return, rather than the `should_run` call.


# Usage examples

Please see the example readme for a (very minimal) usage example.

# For library and backend authors

Please see our small example for how to use `spatch` in a library and how to
implement backends for a library that uses `spatch`.

We would like to note that while `spatch` is designed in a way that tries
to ensure that simply installing a backend will not modify library behavior,
in practice it must be the backend author who ensures this.

Thus, backend authors must review library documentation and when in doubt
contact the library authors about acceptable behavior.
