# Minimal usage example

A minimal example can be found below. If you are interested in the
implementation side of this, please check
[the source](https://github.com/scientific-python/spatch/spatch/_spatch_example).

This is a very minimalistic example to show some of the concepts of
creating a library and backends and how a user might work with them.

The "library" contains only:

- `backend_opts()` a context manager for the user to change dispatching.
- A `divide` function that is dispatching enabled and assumed to be
  designed for only `int` inputs.

We then have two backends with their corresponding definitions in `backend.py`.
The entry-points are `entry_point.toml` and `entry_point2.toml`. When code changes,
these can be updated via `python -m spin update-entrypoints *.toml`
(the necessary info is in the file itself).

For users we have the following basic capabilities. Starting with normal
type dispatching.
First, import the functions and set up tracing globally:

```pycon
>>> import pprint
>>> from spatch._spatch_example.library import divide, backend_opts
>>> opts = backend_opts(trace=True)  # enable tracing
>>> opts.enable_globally()  # or with opts() as trace:

```

Now try calling the various implementations:

```pycon
>>> divide(1, 2)  # use the normal library implementation (int inputs)
0
>>> divide(1.0, 2.0)  # uses backend 1 (float input)
hello from backend 1
0.5
>>> divide(1j, 2.0)  # uses backend 2 (complex input)
hello from backend 2
0.5j
>>> pprint.pprint(opts.trace)
[('spatch._spatch_example.library:divide', [('default', 'called')]),
 ('spatch._spatch_example.library:divide', [('backend1', 'called')]),
 ('spatch._spatch_example.library:divide', [('backend2', 'called')])]

```

The user can use `backend_opts` to modify the dispatching behavior as
a context manager (or via the `enable_globally()`).
The first thing is to prioritize the use of a backend over another
(possibly including the default implementation).

Backend 1 also has integers as a primary type, so we can prefer
it over the default implementation for integer inputs as well:

```pycon
>>> with backend_opts(prioritize="backend1"):
...     divide(1, 2)  # now uses backend1
...
hello from backend 1
0

```

Similarly backend 2 supports floats, so we can prefer it over backend 1.
We can still also prioritize "backend1" if we want:

```pycon
>>> with backend_opts(prioritize=["backend2", "backend1"]):
...     divide(1.0, 2.0)  # now uses backend2
...
hello from backend 2
0.5
>>> pprint.pprint(opts.trace[-2:])
[('spatch._spatch_example.library:divide', [('backend1', 'called')]),
 ('spatch._spatch_example.library:divide', [('backend2', 'called')])]

```

The default priorities are based on the backend types or an explicit request to have
a higher priority by a backend (otherwise default first and then alphabetically).
Backends do have to make sure that the priorities make sense (i.e. there are no
priority circles).

Prioritizing a backend will often effectively enable it. If such a backend changes
behavior (e.g. faster but less precision) this can change results and confuse third
party library functions.
This is a user worry, backends must make sure that they never change types (even if
prioritized), though.

In the array world there use-cases that are not covered in the above:

- There are functions that create new arrays (say random number generators)
  without inputs. We may wish to change their behavior within a scope or
  globally.
- A user may try to bluntly modify behavior to use e.g. arrays on the GPU.

This is supported, but requires indicating the _type_ preference and users
must be aware that this can even easier break their or third party code:

```pycon
>>> with backend_opts(type=float):
...     divide(1, 2)  # returns float (via backend 1)
...
hello from backend 1
0.5
>>> with backend_opts(type=complex):
...     # backen 2 returning a float for complex "input" is probably OK
...     # (but may be debatable)
...     divide(1, 2)
...
hello from backend 2
0.5
>>> with backend_opts(type=float, prioritize="backend2"):
...     # we can of course combine both type and prioritize.
...     divide(1, 2)  # backend 2 with float result (int inputs).
...
hello from backend 2
0.5
>>> pprint.pprint(opts.trace[-3:])
[('spatch._spatch_example.library:divide', [('backend1', 'called')]),
 ('spatch._spatch_example.library:divide', [('backend2', 'called')]),
 ('spatch._spatch_example.library:divide', [('backend2', 'called')])]

```

How types work precisely should be decided by the backend, but care should be taken.
E.g. it is not clear if returning a float is OK when the user said `type=complex`.
(In the future, we may want to think more about this, especially if `type=complex|real`
may make sense, or if we should fall back if no implementation can be found.)
