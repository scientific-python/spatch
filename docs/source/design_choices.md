# `spatch` design choices

This document is designed as a companion to reading the normal API documentation
to answer why the API is designed as it is (not detail questions such as naming).

Please always remember that `spatch` serves two distinct use-cases:

- Type dispatching, which extending functionality to new types. E.g. without the backend
  you only support NumPy, but with the backend you also support CuPy.
- Alternative backend selection where the backend provides an alternative
  implementation that is for example faster. It may even use the GPU
  but the user might still only work with NumPy arrays.

A backend can choose to serve one or both of these.

Particularly important design considerations are:

- Light-weight import.
- Fast dispatching especially when the user has backends installed but the code
  is not using them.
- No magic by default: Just installing a backend should _not_ change behavior.
  (This largely requires backend discipline and coordination with libraries.)
- Adopting `spatch` should be easy for libraries.
- We should aim to make backend authors lives easy but not by making that
  of library authors much harder.

% This section really just to keep the first TOC a bit cleaner...
Specific design questions/reasons

---

The following are some specific questions/arguments. The answers may be
rambling at times :).

```{contents}
:local:
```

### Use of entry-points

`spatch` uses entry-points like plugin systems and also like NetworkX.
Entry-points allow us to do a few things:

- Good user API: If the backend is installed and adds CuPy support, the user
  has to change no code at all.
  Since the backend is not included neither in the library nor `cupy` entry-points
  are the only solution to this. (For type dispatching.)
- Introspection and documentation: Users can introspect available backends
  right away and the list cannot magically change at run-time due to an import.
- We can push many decisions (such as backend priority order) to the startup time.

### Use of identifier strings for everything

We expect it to be common enough that users have an environment with backends
installed but much of their code does not actually use them.
In that use-case, it is vital to delay all expensive imports as much as possible.
The string approach solves this: A backend can add `cupy` support, but if the user
doesn't use `cupy` only the entry-point will ever be imported, and that is very
light-weight.

### Using `type=` to choose a desired type rather than the backend name

Spatch allows using `backend_opts(type=cupy.ndarray)` as a _type unsafe_ way for
users to change behavior and ensuring a CuPy arrays are returned.
This needs to be done with care, but is useful locally (e.g. array creation with
no inputs) or just for experiments.

If we think of choosing backends, it may come easier to think about it in terms
of a name. For example `skimage` could have a backend `"cucim"` and that
backend adds `cupy` support.

So the question is why shouldn't the user just activate the cucim backend with
its name and that might change behavior of functions to return cupy arrays?

We tried to do this and believe wasted a lot of time trying to find a way to
square it.
`"cucim"` users might in principle want to do any of three things:

1. Add `cupy` support to `skimage`, i.e. type dispatching for CuPy.
2. Use the GPU for NumPy arrays (i.e. make code faster hopefully without
   changing behavior significantly).
3. Enforce _unsafe_ use of `cupy` arrays ("zero code change" story)
   because point 2. would incur unnecessary and slow host/device copies.

The first use-case is implicit: The user never has to do anything, it will
always just work.
But use-cases 2 and 3, both require some explicit opt-in via
`with backend_opts(...)`. We could have distinguished these two with two backend
names so users would either do `with backend_opts("cucim[numpy]")`
or `with backend_opts("cucim[cupy]")`.
And that may be easier to understand for users.

But unfortunately, it is trying to reduce a two dimensional problem into a one dimensional one
and this lead to a long tail of paper-cuts:

- You still need to educate users about `cucim[numpy]` and `cucim[cupy]` and it
  is no easier for the backend to implement both.
  Does `cucim` need 2-3 backends that look similar? Or a mechanism to have multiple
  names for one backend? But then the type logic inside the backend depends on the
  name in complicated ways, while in `spatch` it depends exactly on
  `DispatchContext.types`.
- It isn't perfectly clear what happens if `cucim[cupy]` is missing a function.
  Maybe there is another backend to run, but it won't know about the `[cupy]`
  information!
- If there was a backend that also takes cupy arrays, but has a faster, less-precise
  version, the user would have to activate both `cucim-fast[cupy]` and `cucim[cupy]`
  to get the desired behavior.

We firmly believe that teaching users about `cucim[cupy]` or some backend
specific (unsafe) option is not significantly easier than teaching them to use:

- `with backend_opts(prioritize="cucim"):` for the safe first case and
- `with backend_opts(type=cupy.ndarray):` for the unsafe second case.
  (May also include a `priority="cucim"` as well.)

And this is much more explicit about the desire ("use cupy") while avoiding above
issues.

Admittedly, currently we do not provide a way to _prefer_ `type=cupy.ndarray`
but be OK with not using it if implementation provides it, although we think
it could be done if the need truly arises.
On the other hand, the `cucim[cupy]` idea can serve _neither_ use-case quite
right.

### Automatic type-conversion of inputs

Spatch doesn't want to add the complexity of auto-converting between types.
Mostly because type conversion can get quite complicated and we don't want
to burden either `spatch` or the library with it.

NetworkX for example did chose to do it and that is very much a valid choice.
It even has mechanisms for caching such conversions.

Spatch still allows backends to do conversions, but we ask the backend to handle it.
The main downside is that if you wish to enable all functions for a specific type,
you have to implement them all.
Most of them could just be stubs that convert inputs, call the original function
and possibly convert the result, but you will have to explicitly create them.

Note that it is at plausible for a library to provide a "catch all"
fallback (or backend) that uses a custom `library.convert(...)` function
and calls the default implementation.

If libraries are very interested in this, we should consider extending
`spatch` here. But otherwise, we think it should be backends authors taking the
lead, although that might end up in extending spatch.

### No generic catch-all implementations?

We have not included the capability to provide a generic catch-all implementation.
I.e. a backend could write _one_ function that works for all (or many) original
functions.
For example, NumPy has `__array_ufunc__` and because all ufuncs are similar Dask
can have a single implementation that always works!

If there are well structured use-cases (like the NumPy ufunc one) a library
_can_ choose to explicitly support it: Rather than dispatching for `np.add`,
you would dispatch for `np.ufunc()` and pass `np.add` as an argument.

In general, we accept that this may be useful and could be a future addition.
But to do this well, you ideally need trickier tooling to find which arguments
were the ones we dispatched for.
At this point we are not convinced that it is worthwhile to provide it (and
burdening libraries with it).

### Primary and secondary types and why enforce using types?

`spatch` forces the use of types to check whether a backend "matches"
meaning it probably can handle the inputs.
The reason for this design is convenience, speed, and simplicity.

Matching on types is the only truly fast thing, because it allows a design
where the decision of which backend to call is done by:

1. Fetching the current dispatching state. This is very fast, but unavoidable
   as we must check user configuration.
2. Figuring out which (unique) types the user passed to do type dispatching.
3. Doing a single cache lookup using these two pieces of information above.

Users will use a small set of unique types and configurations so caching works great.
Now consider a world _without_ type based matching.
Step 2. needs to be repeated by possibly `N` backends and we can expect _each_
of them to be slower then `spatch` needs to do all three steps.
(We may ask multiple backends even if we never use any backend at all.)
Additionally, by enforcing the use of types we avoid any temptation by backends
to, intentionally or not, do expensive checks to see whether they "match".

Caching, type-safety, and no accidentally slow behavior explains why
`spatch` insists on using types as much as possible.

However, we could still ask each backend to provide a `matches(types)` function
rather than asking them to list primary and secondary types.
This choice is just for convenience right now. Since we insist on types we might
as well handle the these things inside `spatch`.

The reason for "primary" and "secondary" type is to make backends simple if
they might get multiple inputs. For example, a backend that has `cupy.ndarray`
as it's primary type can just use `cupy.asarray()` on inputs without worrying
about which type to return.
It may also allow us to match more precisely, although the backend priority order
could probably ensure to call the right backend first.
And if you just want a single type, then ignore the "secondary" one...

### How would I create for example an "Array API" backend?

This is actually not a problem at all. But the backend will have to provide
an abstract base class and make sure it is importable in a very light-weight way:

```python
class SupportsArrayAPI(abc.ABC):
    @classmethod
    def __subclasshook__(cls, C):
        return hasattr(C, "__array_nanespace__")
```

Then you can use `"@mymodule:SupportsArrayAPI"` _almost_ like the normal use.

### Why not use dunder methods (like NumPy, NetworkX, or Array API)?

Magic dunders (`__double_underscore_method__`) are a great way to implement
type dispatching (it's also how Python operators work)!
But it cannot serve our use-case (and also see advantages of entry-points).
The reasons for this is that:

- For NumPy/NetworkX, CuPy is the one that provides the type and thus can attach a
  magic dunder to it and provide the implementations for all functions.
  But for `spatch` the implementation would be a third party (and not e.g. CuPy).
  And a third party can't easily attach a dunder (e.g. to `cupy.ndarray`)
  It would not be reliable or work well with the entry-point path to avoid costly
  imports. Rather than `spatch` providing the entry-point, cupy would have to.
- Dunders really don't solve the backend selection problem. If they wanted to,
  you would need another layer pushing the backend selection into types.
  This may be possible, but would require the whole infrastructure to
  be centered around the type (i.e. `cupy.ndarray`) rather than the library
  using spatch (like `skimage`).

We would agree that piggy backing on an existing dunder approach (such as the
Array API) seems nice.
But ultimately it would be far less flexible (Array API has no backend selection)
and be more complex since the Array API would have to provide infrastructure that
can deal with arbitrary libraries different backends for each of them.
To us, it seems simply the wrong way around: The library should dispatch and it
can dispatch to a function that uses the Array API.

### Context manager to modify the dispatching options/state

Context managers are safe way to manage options for users at runtime.
This is _not_ strictly needed for type dispatching, because we could just
choose the right version implicitly based on what the user passed.

But it is needed for backend selection. There could be a fast, but imprecise,
backend and the user should possibly use it only for a specific part of their
code.

Context managers simply serve this use-case nicely, quickly, and locally.

#### Why not a namespace for explicit dispatching?

Based on ideas from NEP 37, the Array API for example dispatches once and then the user has an
`xp` namespace they can pass around. That is great!

But it is not targeted to end-users. An end-users should write:

```
library.function(cupy_array)
```

and not:

```
libx = library.dispatch(cupy_array)
libx.function(cupy_array)
```

The second is very explicit and allows to explicitly pass around a "dispatched" state
(i.e. the `libx` namespace). This is can be amazing to write a function that
wants to work with different inputs because by using `libx` you don't have to worry
about anything and you can even pass it around.

So we love this concept! But we think that the first "end-user" style use-case has to
be center stage for `spatch`.
For the core libraries (i.e. NumPy vs. CuPy) the explicit library
use-case seems just far more relevant. We think the reason for this are:

- It is just simpler there, since there no risk of having multiple such contexts.
- Backend selection is not a thing, if it was NumPy or CuPy should naturally handle it
  themselves.
  (Tis refers to backend selection for speed, not type dispatching.
  NumPy _does_ type dispatch to cupy and while unsafe, it would not be unfathomable
  to ask NumPy to dispatch even creation function within a context.)
- User need: It seems much more practical for end-users to just use cupy maybe via
  `import cupy as np` then it is to also modify many library imports.

```{admonition} Future note
`spatch` endeavors to provide a more explicit path (and if this gets outdated, maybe we do).
We expect this to be more of the form of `library.function.invoke(state, ...)` or also
`state.invoke(library.function, ...)` or `library.function.invoke(backend=)(...)`.

I.e. a way to pass state explicitly and write a function that passes on existing context.
We do not consider a "dispatched namespace" to be worth the complexity at this point.
```

### The backend priority seems complicated/not complex enough?

We need to decide on a priority for backends, which is not an exact science.
For backend-selection there is no hard-and-fast rule: Normally an alternative
implementation should have lower priority unless all sides agree it is drop-in
enough to be always used.

For the type dispatching part there are well defined rules to follow
(although those rules may not lead to a fully defined order always):
Given two implementations A and B and A accepts a superclass of what
B accepts, then we must prefer the B because it matches more precisely
(assuming both match).
This is the equivalence to the Python binary operator rule "subclass before superclass".
This rule is important, for example because B may be trying to correct behavior of A.

Now accepts "superclass" in the above is a rather broad term. For example backend A
may accept `numpy.ndarray | cupy.ndarray` while B only accepts `numpy.ndarray`.
"NumPy or CuPy array" here is a superclass of NumPy array.
Alternatively, if A accepts all subclasses of `numpy.ndarray` and B accepts only
exactly `numpy.ndarray` (which spatch supports),
then A is again the "superclass" because `numpy.ndarray` is also a subclasses of
`numpy.ndarray` so A accepts a broader class of inputs.

In practice, the situation is even more complex, though. It is possible that
neither backend represents a clear superclass of the other and the above fails to
establish an order.

So we try to do the above, because we think it simplifies life of backend authors
and ensure the correct type-dispatching order in some cases.

But of course it is not perfect! We think it would be a disservice to users to
attempt a more precise solution (no solution is perfect), because we want to
provide users with an understandable, ordered, list of backends, but:

- We can't import all types for correct `issubclass` checks and we don't want the
  priority order to change if types get imported later.
- An extremely precise order might even consider types passed by the user but
  a context dependent order would be too hard to understand.

So we infer the correct "type order" where it seems clear/simple enough and otherwise
ask backends to define the order themselves.
We believe this helps backends because they often will just get the right order and
neither backend authors or end-users need to understand the "how".

Of course, one can avoid this complexity by just asking backends to fix the order where
if it matters.
We believe that the current complexity in spatch is manageable, although we would agree that
a library that isn't dedicated to dispatching should likely avoid it.

### Choice of environment variables

We don't mind changing these at all. There are three because:

- We need `_BLOCK` to allow avoiding loading a buggy backend entirely.
  It is named "block" just because "disable" also makes sense at runtime.
- `_PRIORITIZE` is there as the main user API.
- `_SET_ORDER` is fine grained to prioritize one backend over another.
  At runtime this seemed less important (can be done via introspection).
  This largely exists because if backend ordering is buggy,
  we tell users to set this to work around the issue.

But of course there could be more or different ones.
