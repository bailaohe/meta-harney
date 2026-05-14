"""Tests for shared data contracts: ContentBlock variants + Message."""

import pytest
from pydantic import ValidationError

from meta_harney.abstractions._types import (
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)


def test_text_block_roundtrip():
    b = TextBlock(text="hello")
    assert b.type == "text"
    assert b.text == "hello"
    assert TextBlock.model_validate(b.model_dump()) == b


def test_image_block_requires_url_or_data():
    # Allowed: url only
    b = ImageBlock(url="https://x/y.png", media_type="image/png")
    assert b.url == "https://x/y.png"
    # Allowed: data only
    b2 = ImageBlock(data="iVBORw0...", media_type="image/png")
    assert b2.data is not None


def test_tool_call_block_fields():
    b = ToolCallBlock(invocation_id="inv1", name="read_doc", args={"id": 42})
    assert b.type == "tool_call"
    assert b.invocation_id == "inv1"
    assert b.name == "read_doc"
    assert b.args == {"id": 42}


def test_tool_result_block_fields():
    b = ToolResultBlock(invocation_id="inv1", success=True, output={"ok": 1})
    assert b.type == "tool_result"
    assert b.success
    assert b.error is None


def test_tool_result_block_failure():
    b = ToolResultBlock(invocation_id="inv1", success=False, output=None, error="boom")
    assert not b.success
    assert b.error == "boom"


def test_message_role_constrained():
    Message(role="user", content=[TextBlock(text="hi")])
    Message(role="assistant", content=[TextBlock(text="hi")])
    Message(role="system", content=[TextBlock(text="hi")])
    Message(role="tool", content=[TextBlock(text="hi")])
    with pytest.raises(ValidationError):
        Message(role="customer", content=[TextBlock(text="hi")])  # type: ignore[arg-type]  # not allowed


def test_message_author_is_free_form():
    m = Message(role="user", author="sales", content=[TextBlock(text="hi")])
    assert m.author == "sales"
    m2 = Message(role="user", author="customer", content=[TextBlock(text="hi")])
    assert m2.author == "customer"


def test_message_mixed_content():
    m = Message(
        role="assistant",
        content=[
            TextBlock(text="here's the result"),
            ToolCallBlock(invocation_id="inv2", name="fetch", args={}),
        ],
    )
    assert len(m.content) == 2
    assert m.content[0].type == "text"
    assert m.content[1].type == "tool_call"


def test_thinking_block_construction() -> None:
    from meta_harney.abstractions._types import ThinkingBlock

    b = ThinkingBlock(text="reasoning", signature="sig-abc")
    assert b.type == "thinking"
    assert b.text == "reasoning"
    assert b.signature == "sig-abc"


def test_redacted_thinking_block_construction() -> None:
    from meta_harney.abstractions._types import RedactedThinkingBlock

    b = RedactedThinkingBlock(data="opaque-blob")
    assert b.type == "redacted_thinking"
    assert b.data == "opaque-blob"


def test_message_with_thinking_blocks_json_roundtrip() -> None:
    """Discriminated union must reconstruct concrete subclasses from JSON."""
    from meta_harney.abstractions._types import (
        Message,
        RedactedThinkingBlock,
        TextBlock,
        ThinkingBlock,
    )

    msg = Message(
        role="assistant",
        content=[
            ThinkingBlock(text="r", signature="s"),
            RedactedThinkingBlock(data="d"),
            TextBlock(text="final"),
        ],
    )
    j = msg.model_dump_json()
    parsed = Message.model_validate_json(j)
    assert isinstance(parsed.content[0], ThinkingBlock)
    assert parsed.content[0].signature == "s"
    assert isinstance(parsed.content[1], RedactedThinkingBlock)
    assert parsed.content[1].data == "d"
    assert isinstance(parsed.content[2], TextBlock)
    assert parsed.content[2].text == "final"


def test_content_block_discriminator_rejects_unknown_type() -> None:
    """Validation must fail when 'type' is not in the discriminator set."""
    import pytest
    from pydantic import ValidationError

    from meta_harney.abstractions._types import Message

    bad_json = '{"role":"assistant","content":[{"type":"unknown","whatever":1}]}'
    with pytest.raises(ValidationError):
        Message.model_validate_json(bad_json)
