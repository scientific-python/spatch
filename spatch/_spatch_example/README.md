This is a very minimalistic example to show some of the concepts of
creating a library and backends and how a user might work with them.

The "library" contains only:
* `backend_opts()` a context manager for the user to change dispatching.
* A `divide` function that is dispatching enabled and assumed to be
  designed for only `int` inputs.

We then have two backends with their corresponding definitions in `backend.py`.
The entry-points are `entry_point.py` and `entry_point2.py` and these files
can be run to generate their `functions` context (i.e. if you add more functions).

For users we have the following basic capabilities.  Starting with normal
type dispatching:
```
import pprint
from spatch._spatch_example.library import divide, backend_opts

# trace globally (or use `with backend_opts(trace=True) as trace`).
_opts = backend_opts(trace=True)  # need to hold on to _opts to not exit
trace = _opts.__enter__()

divide(1, 2)  # use the normal library implementation (int inputs)
divide(1., 2.)  # uses backend 1 (float input)
divide(1j, 2.)  # uses backend 2 (complex input)

pprint.pprint(trace[-3:])
# [('spatch._spatch_example.library:divide', [('default', 'called')]),
#  ('spatch._spatch_example.library:divide', [('backend1', 'called')]),
#  ('spatch._spatch_example.library:divide', [('backend2', 'called')])]
```

The user can use `backend_opts` to modify the dispatching behavior.  At the moment
if you wanted to do this globally you can use `backend_opts().__enter__()`.

The first thing is to prioritize the use of a backend over another (possibly
including the default implementation):
```
# Backend 1 also has integers as a primary type, so we can prefer
# it over the default implementation for integer inputs as well:
with backend_opts(prioritize="backend1"):
    res = divide(1, 2)  # now uses backend1
    assert type(res) is int  # backend 1 is written to ensure this!

# Similarly backend 2 supports floats, so we can prefer it over backend 1
with backend_opts(prioritize="backend2"):
    divide(1., 2.)  # now uses backend2

pprint.pprint(trace[-2:])
# [('spatch._spatch_example.library:divide', [('backend1', 'called')]),
#  ('spatch._spatch_example.library:divide', [('backend2', 'called')])] 
```
The default priorities are based on the backend types or an explicit request to have
a higher priority by a backend (otherwise default first and then alphabetically).
Backends do have to make sure that the priorities make sense (i.e. there are no
priority circles).

Prioritizing a backend will often effectively enable it.  If such a backend changes
behavior (e.g. faster but less precision) this can change results and confuse third
party library functions.
This is a user worry, backends must make sure that they never change types (even if
prioritized), though.

In the array world there use-cases that are not covered in the above:
* There are functions that create new arrays (say random number generators)
  without inputs.  We may wish to change their behavior within a scope or
  globally.
* A user may try to bluntly modify behavior to use e.g. arrays on the GPU.

This is supported, but requires indicating the _type_ preference and users
must be aware that this can even easier break their or third party code:
```
with backend_opts(type=float):
    res = divide(1, 2)  # we use backend 1 and it returns floats!
    assert type(res) is float

with backend_opts(type=complex):
    res = divide(1, 2)  # we use backend 2
    # backend 2 decided returning float for complex "input" is OK
    # (that may be debatable)
    assert type(res) is float

with backend_opts(type=float, prioritize="backend2"):
    # we can of course combine both type and prioritize.
    divide(1, 2)  # backend 2 with float result (int inputs).

pprint.pprint(trace[-3:])
# [('spatch._spatch_example.library:divide', [('backend1', 'called')]),
#  ('spatch._spatch_example.library:divide', [('backend2', 'called')]),
#  ('spatch._spatch_example.library:divide', [('backend2', 'called')])]
```
How types work precisely should be decided by the backend, but care should be taken.
E.g. it is not clear if returning a float is OK when the user said `type=complex`.

TODO: I (seberg) like using the `type=` and I suspect it's the right path.  But it
isn't clear that returning a float above is OK?  It also makes you wonder if
`type=complex|float` would make more sense, but it would be the same as `type=float`.
