"""Tests for _serialize_tool_output helper."""

from __future__ import annotations

from datetime import datetime

from meta_harney.abstractions._serialize import _serialize_tool_output


def test_none_returns_empty_string() -> None:
    assert _serialize_tool_output(None) == ""


def test_str_passes_through_unchanged() -> None:
    assert _serialize_tool_output("hello") == "hello"


def test_empty_str_passes_through() -> None:
    assert _serialize_tool_output("") == ""


def test_dict_becomes_json() -> None:
    out = _serialize_tool_output({"a": 1, "b": "x"})
    # Order-stable: json.dumps preserves insertion order
    assert out == '{"a": 1, "b": "x"}'


def test_list_becomes_json() -> None:
    assert _serialize_tool_output([1, 2, 3]) == "[1, 2, 3]"


def test_int_becomes_json() -> None:
    assert _serialize_tool_output(42) == "42"


def test_unicode_preserved_not_escaped() -> None:
    # ensure_ascii=False should keep CJK characters readable
    assert _serialize_tool_output({"name": "张三"}) == '{"name": "张三"}'


def test_datetime_uses_str_fallback() -> None:
    # default=str fallback handles non-JSON-serializable objects
    out = _serialize_tool_output(datetime(2026, 5, 14, 12, 0, 0))
    assert "2026-05-14" in out


def test_circular_reference_returns_repr_not_raise() -> None:
    d: dict[str, object] = {}
    d["self"] = d
    # Should NOT raise; should return some string (repr fallback)
    result = _serialize_tool_output(d)
    assert isinstance(result, str)
    assert len(result) > 0
