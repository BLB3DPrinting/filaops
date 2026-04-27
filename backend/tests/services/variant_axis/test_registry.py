"""Registry contract tests — no resolvers registered yet."""
import pytest
from app.services.variant_axis import registry


def test_register_and_get():
    class FakeResolver:
        type_name = "fake"
    registry.register(FakeResolver())
    try:
        got = registry.get("fake")
        assert got.type_name == "fake"
    finally:
        registry._REGISTRY.pop("fake", None)


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        registry.get("nonexistent_axis_type")


def test_all_types_returns_registered_names():
    class A: type_name = "a_test"
    class B: type_name = "b_test"
    registry.register(A())
    registry.register(B())
    try:
        names = set(registry.all_types())
        assert {"a_test", "b_test"}.issubset(names)
    finally:
        registry._REGISTRY.pop("a_test", None)
        registry._REGISTRY.pop("b_test", None)


def test_protocol_requires_three_methods():
    """AxisTypeResolver must expose list_options, resolve_to_component, synthesize_legacy."""
    from app.services.variant_axis.registry import AxisTypeResolver
    expected = {"list_options", "resolve_to_component", "synthesize_legacy", "type_name"}
    assert expected.issubset(set(dir(AxisTypeResolver)))


def test_axis_option_dataclass_shape():
    from app.services.variant_axis.types import AxisOption
    opt = AxisOption(value={"k": 1}, label="L", preview_sku="X-1", preview_name="X 1")
    assert opt.value == {"k": 1}
    assert opt.label == "L"
