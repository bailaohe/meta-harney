"""
OpenAI-compatible provider quirks — single audit point for vendor hacks.

This module is the home for every behavioural oddity and non-OpenAI-spec
extension field that specific OpenAI-protocol-compatible providers
require. Things that don't belong in a clean wire-format adapter, but
without which we'd lose user-visible features.

WHY A SEPARATE FILE
-------------------
`openai.py` is the wire-format adapter: plain OpenAI Chat Completions
in/out. As soon as it starts branching on "is this DeepSeek? then add
thinking enabled", it's no longer a protocol adapter — it's a parallel
rule book of provider-specific knowledge. Keeping that knowledge here
gives us:

* `openai.py` stays a clean protocol adapter.
* Quirks have a single audit point — one grep tells you "what providers
  are we special-casing? for what reasons?".
* Each quirk has its own commented rationale + upstream reference,
  so deleting one later is a deliberate, informed action.
* Adding a new vendor (Moonshot Kimi, DashScope qwen-reasoning,
  Fireworks llama-r1, etc.) means adding *here*, not editing
  `openai.py`.

DOUBLE-GATE PRINCIPLE
---------------------
Every quirk that affects request shape (e.g. injecting extension fields)
gates on BOTH `base_url` matching the vendor AND a model-name match.
Either gate alone is too loose:

* Model name alone may collide with user-named OpenAI-protocol
  passthrough configs (e.g. a custom "deepseek-mock" pointed at the
  real OpenAI endpoint for testing). Sending `thinking: {type: enabled}`
  to OpenAI proper returns 400 `unknown_parameter`.
* Base URL alone would catch non-reasoner deployments on the same
  vendor (e.g. `deepseek-coder` predecessor, which doesn't accept
  thinking-mode params).

Both together — essentially zero false-positive risk; the user has to
deliberately point at a vendor endpoint AND use a model in that
vendor's reasoner family.

REFERENCES
----------
DeepSeek-TUI's `apply_reasoning_effort` + `requires_reasoning_content`
in `crates/tui/src/client.rs` / `crates/tui/src/client/chat.rs` are the
prior art for the DeepSeek rules below.

OpenHarness's `api/openai_client.py:168-170` (force
`reasoning_content: ""` on tool-call follow-ups) and `:293-297` (pop
`stream_options` workaround) are prior art for the multi-turn replay
constraint.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# DeepSeek
# ---------------------------------------------------------------------------


def _is_deepseek_endpoint(base_url: str | None) -> bool:
    """True iff base_url points at a DeepSeek-hosted endpoint.

    Covers `api.deepseek.com` and `api.deepseek.cn` (CN-mirror), as well
    as any custom DeepSeek-named relay. Substring match is intentionally
    loose on the path so private mirrors at e.g.
    `https://deepseek.internal.corp/v1` still gate correctly.
    """
    if base_url is None:
        return False
    return "deepseek" in base_url.lower()


def _is_deepseek_reasoner_model(model: str) -> bool:
    """Conservative match for DeepSeek's V4-family reasoner aliases.

    * `deepseek-chat` is the public API alias that resolves server-side
      to `deepseek-v4-flash` (thinking-mode reasoner).
    * `deepseek-reasoner` is the public API alias for `deepseek-v4-pro`.
    * `deepseek-v4-*` direct model IDs are also in the family.

    We intentionally do NOT match generic substrings like `reasoner` or
    `-thinking` here — those go through the double-gate
    `is_deepseek_reasoner` below, which requires the endpoint to be
    DeepSeek-hosted before any model-name guesswork applies. That guards
    against custom OpenAI-passthrough configs that happen to use those
    substrings in user-chosen aliases.
    """
    lower = model.lower()
    return (
        lower.startswith("deepseek-chat")
        or lower.startswith("deepseek-reasoner")
        or "deepseek-v4" in lower
    )


def is_deepseek_reasoner(model: str, base_url: str | None) -> bool:
    """Top-level double-gate: this call IS a DeepSeek reasoner request.

    All DeepSeek-specific quirks should funnel through this single
    predicate so the audit surface stays one line wide.
    """
    return _is_deepseek_endpoint(base_url) and _is_deepseek_reasoner_model(model)


def deepseek_thinking_extras(model: str, base_url: str | None) -> dict[str, Any]:
    """Extra body fields to enable DeepSeek's true token-by-token reasoning
    streaming. Empty dict when the gate doesn't fire — caller can merge
    unconditionally.

    DEFAULT (without these fields)
        DeepSeek's "fast thinking" mode: the server buffers the entire
        reasoning span server-side and bursts the `reasoning_content`
        chunks back in ~100ms once thinking is done. UX impact: the
        thinking block appears all-at-once, the streaming illusion is
        lost. Observed live in oh-tui via OH_TUI_DEBUG logs: 93
        reasoning chunks landed within a 90ms window.

    WITH these fields
        DeepSeek's "real thinking" mode: every reasoning token is its
        own SSE event, so the UI can render the chain of thought as it's
        being produced.

    The two fields are kept together because DeepSeek-TUI's
    `apply_reasoning_effort` always sets them together for the DeepSeek
    provider family (see client.rs:915-923). `reasoning_effort: "high"`
    is the upper-tier setting; we don't currently expose a knob to dial
    it down — if a user is paying for reasoning we assume they want it
    full-strength. A future `ProviderCallConfig.reasoning_effort`
    addition can override this without touching the gating logic here.
    """
    if not is_deepseek_reasoner(model, base_url):
        return {}
    return {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }


def requires_reasoning_content_replay(model: str, base_url: str | None) -> bool:
    """True iff this provider rejects multi-turn assistant messages that
    omit `reasoning_content` — even when no reasoning was produced.

    UPSTREAM ERROR (when this isn't honored)
        400 — `The reasoning_content in the thinking mode must be passed
        back to the API.`

    This fires on agent-loop tool follow-ups: an assistant message with
    only tool_calls (no text, no thinking) still needs a `reasoning_content`
    key to ride along, even if empty string. OpenHarness independently
    discovered this for Kimi and DeepSeek
    (`api/openai_client.py:168-170`).

    Currently scoped to DeepSeek reasoners. Expand here when other
    vendors hit the same constraint.
    """
    return is_deepseek_reasoner(model, base_url)
