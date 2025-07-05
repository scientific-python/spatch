import pytest

from spatch.backend_system import BackendSystem
from spatch.testing import BackendDummy


class FloatWithContext(BackendDummy):
    name = "FloatWithContext"
    primary_types = ("~builtins:float",)
    secondary_types = ("builtins:int",)
    uses_context = True
    requires_opt_in = False


def test_context_basic():
    bs = BackendSystem(
        None,
        environ_prefix="SPATCH_TEST",
        default_primary_types=("builtin:int",),
        backends=[FloatWithContext()]
    )

    # Add a dummy dispatchable function that dispatches on all arguments.
    @bs.dispatchable(None, module="<test>", qualname="dummy_func")
    def dummy_func(*args, **kwargs):
        return "fallback", args, kwargs

    _, (ctx, *args), kwargs = dummy_func(1, 1.)
    assert ctx.name == "FloatWithContext"
    assert set(ctx.types) == {int, float}
    assert ctx.dispatch_args == (1, 1.)
    assert not ctx.prioritized

    class float_subclass(float):
        pass

    with bs.backend_opts(prioritize=("FloatWithContext",)):
        _, (ctx, *args), kwargs = dummy_func(float_subclass(1.))
        assert ctx.name == "FloatWithContext"
        assert set(ctx.types) == {float_subclass}
        assert ctx.dispatch_args == (float_subclass(1.),)
        assert ctx.prioritized

    with bs.backend_opts(type=float):
        # No argument, works if explicitly prioritized...
        _, (ctx, *args), kwargs = dummy_func()
        assert ctx.name == "FloatWithContext"
        assert set(ctx.types) == {float}
        assert ctx.dispatch_args == ()
        assert not ctx.prioritized  # not prioritized "just" type enforced

