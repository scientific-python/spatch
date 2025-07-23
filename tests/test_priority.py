import pytest

from spatch.backend_system import BackendSystem
from spatch.testing import BackendDummy


class IntB(BackendDummy):
    name = "IntB"
    primary_types = ("builtins:int",)
    secondary_types = ()
    requires_opt_in = False  # True would make sense, but let's not.


class IntB2(BackendDummy):
    name = "IntB2"
    primary_types = ("builtins:int",)
    secondary_types = ()
    requires_opt_in = False


class FloatB(BackendDummy):
    name = "FloatB"
    primary_types = ("builtins:float",)
    secondary_types = ("builtins:int",)
    requires_opt_in = False


class FloatBH(BackendDummy):
    name = "FloatBH"
    primary_types = ("builtins:float", "builtins:int")
    secondary_types = ()
    # This one is manually higher prioritized that FloatB
    # Without that, it should be lower (due to the primary type)
    # NOTE: Is it a design flaw that FloatBL is needed?
    # (Based on types FloatBL > FloatBH so we would get the circle:
    #  FloatBL > FloatBH > FloatB > FloatB)
    higher_priority_than = ("FloatB", "FloatBL")
    requires_opt_in = False


class FloatBL(BackendDummy):
    name = "FloatBL"
    primary_types = ("builtins:float",)
    secondary_types = ("builtins:int",)
    # This one is manually lower prioritized that FloatB
    lower_priority_than = ("FloatB",)
    requires_opt_in = False


class IntSubB(BackendDummy):
    name = "IntSubB"
    primary_types = ("~builtins:int",)
    secondary_types = ()
    requires_opt_in = False


class RealB(BackendDummy):
    name = "RealB"
    primary_types = ("@numbers:Real",)
    secondary_types = ()
    requires_opt_in = False


@pytest.mark.parametrize(
    "backends, expected",
    [
        (
            [RealB(), IntB(), IntB2(), FloatB(), IntSubB()],
            ["default", "IntB", "IntB2", "IntSubB", "FloatB", "RealB"],
        ),
        # Reverse, gives the same order, except for IntB and IntB2
        (
            [RealB(), IntB(), IntB2(), FloatB(), IntSubB()][::-1],
            ["default", "IntB2", "IntB", "IntSubB", "FloatB", "RealB"],
        ),
        # And check that manual priority works:
        (
            [RealB(), IntB(), FloatB(), FloatBH(), FloatBL(), IntSubB()],
            ["default", "IntB", "IntSubB", "FloatBH", "FloatB", "FloatBL", "RealB"],
        ),
        (
            [RealB(), IntB(), FloatB(), FloatBH(), FloatBL(), IntSubB()][::-1],
            ["default", "IntB", "IntSubB", "FloatBH", "FloatB", "FloatBL", "RealB"],
        ),
    ],
)
def test_order_basic(backends, expected):
    bs = BackendSystem(
        None,
        environ_prefix="SPATCH_TEST",
        default_primary_types=("builtin:int",),
        backends=backends,
    )

    order = bs.backend_opts().backends
    assert order == tuple(expected)


@pytest.fixture
def bs():
    bs = BackendSystem(
        None,
        environ_prefix="SPATCH_TEST",
        default_primary_types=("builtin:int",),
        backends=[RealB(), IntB(), IntB2(), FloatB(), IntSubB()],
    )
    assert bs.backend_opts().backends == ("default", "IntB", "IntB2", "IntSubB", "FloatB", "RealB")

    # Add a dummy dispatchable function that dispatches on all arguments.
    @bs.dispatchable(None, module="<test>", qualname="dummy_func")
    def dummy_func(*args, **kwargs):
        return "fallback", args, kwargs

    # Monkey patch the function the backend (could certainly change this)
    bs.dummy_func = dummy_func
    return bs


def test_global_opts_basic(bs):
    opts = bs.backend_opts(prioritize=("RealB",), disable=("IntB2",), trace=True)
    opts.enable_globally()
    new_prio = ("RealB", "default", "IntB", "IntSubB", "FloatB")
    assert bs.backend_opts().backends == new_prio
    assert bs.dummy_func(1) == ("RealB", (1,), {})


def test_opts_context_basic(bs):
    with bs.backend_opts(prioritize=("RealB",), disable=("IntB", "default")):
        assert bs.backend_opts().backends == ("RealB", "IntB2", "IntSubB", "FloatB")

        assert bs.dummy_func(a=1) == ("RealB", (), {"a": 1})

        # Also check nested context, re-enables IntB
        with bs.backend_opts(prioritize=("IntB",)):
            assert bs.backend_opts().backends == ("IntB", "RealB", "IntB2", "IntSubB", "FloatB")

            assert bs.dummy_func(1) == ("IntB", (1,), {})
