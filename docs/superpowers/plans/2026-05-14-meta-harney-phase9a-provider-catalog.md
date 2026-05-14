# meta-harney Phase 9a: Provider Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a domain-agnostic provider catalog to meta-harney v0.0.8: `ProviderSpec` (frozen dataclass), `BUILT_IN_PROVIDERS` (9 specs), `provider_from_spec()` factory, and `register_provider()` extension hook.

**Architecture:** Single new module `src/meta_harney/providers/catalog.py` containing 4 public symbols. Zero breaking change — purely additive on top of existing `AnthropicProvider` / `OpenAIProvider` classes. 10 new unit tests in one file. Push v0.0.8 tag through existing GitHub Actions CI.

**Tech Stack:** Python 3.10+ · dataclass with `frozen=True` · `typing.Literal` for `kind` discriminator · existing `AnthropicProvider` / `OpenAIProvider` from v0.0.7 · pytest · mypy strict · ruff · GitHub Actions.

**Pre-conditions:**
- On `main` at `01f3692` (Phase 9a spec committed) or later
- v0.0.7 baseline: 305 tests passing
- mypy strict + ruff check + ruff format clean
- GitHub remote `origin` configured (`bailaohe/meta-harney`)

**Execution model:** 4 tasks. T1 adds the catalog module + tests. T2 wires it into top-level public API. T3 verifies all quality gates locally. T4 releases v0.0.8 (version bump + tag + push + watch CI).

---

## File Structure After Phase 9a

```
src/meta_harney/
├── __init__.py                                 # MODIFIED — 4 new exports + version 0.0.8
└── providers/
    └── catalog.py                              # NEW

tests/
└── unit/providers/
    └── test_catalog.py                         # NEW

pyproject.toml                                  # MODIFIED — version 0.0.8
```

---

## Task 1: `providers/catalog.py` module + 10 unit tests

**Files:**
- Create: `src/meta_harney/providers/catalog.py`
- Create: `tests/unit/providers/test_catalog.py`

- [ ] **Step 1: Write failing tests in `tests/unit/providers/test_catalog.py`**

```python
"""Tests for the Provider Catalog (Phase 9a)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from meta_harney.providers.anthropic import AnthropicProvider
from meta_harney.providers.catalog import (
    BUILT_IN_PROVIDERS,
    ProviderSpec,
    provider_from_spec,
    register_provider,
)
from meta_harney.providers.openai import OpenAIProvider


# --------------------------------------------------------------------------- #
# ProviderSpec data contract
# --------------------------------------------------------------------------- #


def test_provider_spec_construction() -> None:
    spec = ProviderSpec(
        name="foo",
        kind="openai",
        base_url="https://example.com/v1",
        default_model="foo-model",
        description="example",
    )
    assert spec.name == "foo"
    assert spec.kind == "openai"
    assert spec.base_url == "https://example.com/v1"
    assert spec.default_model == "foo-model"
    assert spec.description == "example"


def test_provider_spec_is_frozen() -> None:
    spec = ProviderSpec(name="x", kind="openai", base_url=None, default_model="y")
    with pytest.raises(FrozenInstanceError):
        spec.name = "z"  # type: ignore[misc]


def test_provider_spec_with_invalid_kind_caught_by_mypy_not_runtime() -> None:
    """Constructing ProviderSpec with kind not in Literal does NOT raise at
    runtime. Type errors are caught by mypy (Literal["anthropic","openai"]).
    This test documents that the dataclass does no runtime validation."""
    spec = ProviderSpec(
        name="future",
        kind=cast(Any, "vertex"),  # mypy would reject without cast
        base_url=None,
        default_model="x",
    )
    # No exception raised — runtime accepts any string for kind.
    assert spec.name == "future"


# --------------------------------------------------------------------------- #
# BUILT_IN_PROVIDERS completeness
# --------------------------------------------------------------------------- #


_EXPECTED_NAMES = {
    "anthropic", "openai", "moonshot", "deepseek", "gemini",
    "minimax", "nvidia", "dashscope", "modelscope",
}


def test_built_in_providers_contains_all_nine() -> None:
    assert set(BUILT_IN_PROVIDERS.keys()) == _EXPECTED_NAMES
    for name, spec in BUILT_IN_PROVIDERS.items():
        assert spec.name == name  # dict key matches spec.name
        assert spec.kind in {"anthropic", "openai"}
        assert spec.default_model  # non-empty


def test_built_in_providers_anthropic_and_openai_have_none_base_url() -> None:
    assert BUILT_IN_PROVIDERS["anthropic"].base_url is None
    assert BUILT_IN_PROVIDERS["openai"].base_url is None
    # Other 7 have explicit https URLs
    for name in _EXPECTED_NAMES - {"anthropic", "openai"}:
        spec = BUILT_IN_PROVIDERS[name]
        assert spec.base_url is not None
        assert spec.base_url.startswith("https://"), f"{name}: {spec.base_url}"


# --------------------------------------------------------------------------- #
# provider_from_spec factory
# --------------------------------------------------------------------------- #


def test_provider_from_spec_anthropic_constructs_anthropic_provider() -> None:
    spec = BUILT_IN_PROVIDERS["anthropic"]
    p = provider_from_spec(spec, api_key="sk-ant-test")
    assert isinstance(p, AnthropicProvider)
    assert p._api_key == "sk-ant-test"
    assert p._base_url is None


def test_provider_from_spec_openai_constructs_openai_provider() -> None:
    spec = BUILT_IN_PROVIDERS["moonshot"]
    p = provider_from_spec(spec, api_key="sk-moon")
    assert isinstance(p, OpenAIProvider)
    assert p._api_key == "sk-moon"
    assert p._base_url == "https://api.moonshot.cn/v1"


def test_provider_from_spec_unknown_kind_raises() -> None:
    bad_spec = ProviderSpec(
        name="future-vertex",
        kind=cast(Any, "vertex"),
        base_url=None,
        default_model="x",
    )
    with pytest.raises(ValueError, match="unknown provider kind"):
        provider_from_spec(bad_spec, api_key="k")


# --------------------------------------------------------------------------- #
# register_provider extension hook
# --------------------------------------------------------------------------- #


@pytest.fixture
def _clean_register() -> object:
    """Remove any test-added entries from BUILT_IN_PROVIDERS after the test."""
    yield None
    for name in list(BUILT_IN_PROVIDERS.keys()):
        if name not in _EXPECTED_NAMES:
            del BUILT_IN_PROVIDERS[name]


def test_register_provider_adds_new_spec(_clean_register: object) -> None:
    spec = ProviderSpec(
        name="local-llama",
        kind="openai",
        base_url="http://localhost:8080/v1",
        default_model="llama-3.1-8b",
    )
    register_provider(spec)
    assert "local-llama" in BUILT_IN_PROVIDERS
    assert BUILT_IN_PROVIDERS["local-llama"].base_url == "http://localhost:8080/v1"


def test_register_provider_existing_name_without_overwrite_raises(
    _clean_register: object,
) -> None:
    duplicate = ProviderSpec(
        name="openai",
        kind="openai",
        base_url="https://different/v1",
        default_model="z",
    )
    with pytest.raises(ValueError, match="already registered"):
        register_provider(duplicate)
    # With overwrite=True it succeeds:
    register_provider(duplicate, overwrite=True)
    assert BUILT_IN_PROVIDERS["openai"].base_url == "https://different/v1"
    # Restore the original openai spec so we don't pollute other tests.
    register_provider(
        ProviderSpec(
            name="openai",
            kind="openai",
            base_url=None,
            default_model="gpt-4o",
            description="OpenAI (official)",
        ),
        overwrite=True,
    )
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_catalog.py -v
```

Expected: ModuleNotFoundError on `meta_harney.providers.catalog`.

- [ ] **Step 3: Implement `src/meta_harney/providers/catalog.py`**

```python
"""Provider catalog: built-in provider specs + factory + extension hook.

Generic infrastructure for multi-provider apps. Specs are plain data
(frozen dataclasses). `provider_from_spec()` is the only factory you need.
`register_provider()` lets apps inject custom specs at startup.

Phase 9a addition — see docs/superpowers/specs/2026-05-14-meta-harney-phase9a-provider-catalog-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from meta_harney.providers.anthropic import AnthropicProvider
from meta_harney.providers.base import LLMProvider
from meta_harney.providers.openai import OpenAIProvider


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata for a known LLM provider.

    Specs are immutable. To replace a spec at runtime, call
    `register_provider(new_spec, overwrite=True)`.
    """

    name: str
    kind: Literal["anthropic", "openai"]
    base_url: str | None
    default_model: str
    description: str = ""


BUILT_IN_PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        kind="anthropic",
        base_url=None,
        default_model="claude-sonnet-4-5",
        description="Anthropic Claude (official)",
    ),
    "openai": ProviderSpec(
        name="openai",
        kind="openai",
        base_url=None,
        default_model="gpt-4o",
        description="OpenAI (official)",
    ),
    "moonshot": ProviderSpec(
        name="moonshot",
        kind="openai",
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2-0905-preview",
        description="Moonshot AI (Kimi, OpenAI-compatible)",
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        kind="openai",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        description="DeepSeek (OpenAI-compatible)",
    ),
    "gemini": ProviderSpec(
        name="gemini",
        kind="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.0-flash",
        description="Google Gemini (OpenAI-compatible endpoint)",
    ),
    "minimax": ProviderSpec(
        name="minimax",
        kind="openai",
        base_url="https://api.minimax.io/v1",
        default_model="MiniMax-M2",
        description="MiniMax (OpenAI-compatible)",
    ),
    "nvidia": ProviderSpec(
        name="nvidia",
        kind="openai",
        base_url="https://integrate.api.nvidia.com/v1",
        default_model="meta/llama-3.1-405b-instruct",
        description="NVIDIA NIM (OpenAI-compatible)",
    ),
    "dashscope": ProviderSpec(
        name="dashscope",
        kind="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-max",
        description="Alibaba Dashscope (OpenAI-compatible)",
    ),
    "modelscope": ProviderSpec(
        name="modelscope",
        kind="openai",
        base_url="https://api-inference.modelscope.cn/v1",
        default_model="Qwen/Qwen2.5-72B-Instruct",
        description="ModelScope (OpenAI-compatible)",
    ),
}


def provider_from_spec(
    spec: ProviderSpec,
    *,
    api_key: str,
    model: str | None = None,
) -> LLMProvider:
    """Build an LLMProvider from a spec + api_key.

    `model` is accepted for API symmetry but unused here; the engine
    consumes the model id via RuntimeConfig. Higher-level callers can
    use spec.default_model as their default.

    Raises:
        ValueError: When spec.kind is not "anthropic" or "openai".
    """
    if spec.kind == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=spec.base_url)
    if spec.kind == "openai":
        return OpenAIProvider(api_key=api_key, base_url=spec.base_url)
    raise ValueError(f"unknown provider kind: {spec.kind!r}")


def register_provider(
    spec: ProviderSpec,
    *,
    overwrite: bool = False,
) -> None:
    """Register or replace a provider spec at runtime.

    Args:
        spec: The provider spec to register.
        overwrite: If False (default), raises ValueError when a provider
            with the same name already exists. Set to True to replace.

    Raises:
        ValueError: When the name conflicts and overwrite=False.

    Thread safety: not thread-safe. Intended for startup-time
    configuration. Do not call from request paths or worker threads.
    """
    if not overwrite and spec.name in BUILT_IN_PROVIDERS:
        raise ValueError(
            f"provider {spec.name!r} already registered "
            f"(use overwrite=True to replace)"
        )
    BUILT_IN_PROVIDERS[spec.name] = spec
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/providers/test_catalog.py -v
pytest -q
ruff check src/meta_harney/providers/catalog.py tests/unit/providers/test_catalog.py
mypy src/meta_harney/providers/catalog.py
```

Expected: 10/10 new tests pass; full suite 315/315; mypy + ruff clean.

If mypy complains about `Literal["anthropic", "openai"]` exhaustiveness on the `provider_from_spec` if/if chain (warning that the `raise ValueError` is unreachable when input matches the Literal), that's expected from the runtime-unknown-kind test path — keep the `raise`.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/providers/catalog.py tests/unit/providers/test_catalog.py
git commit -m "feat(providers): Provider Catalog — generic multi-provider support

New module providers/catalog.py:
- ProviderSpec frozen dataclass (name, kind, base_url, default_model, description)
- BUILT_IN_PROVIDERS dict with 9 entries:
  anthropic, openai, moonshot, deepseek, gemini, minimax, nvidia,
  dashscope, modelscope
- provider_from_spec(spec, api_key) factory dispatches on spec.kind
- register_provider(spec, overwrite=False) for app-level extension

Zero breaking change — purely additive on top of existing
AnthropicProvider / OpenAIProvider classes.

10 new unit tests cover construction, frozen invariant, factory
dispatch, catalog completeness, registration with/without overwrite."
```

---

## Task 2: Expose 4 new APIs at top level

**Files:**
- Modify: `src/meta_harney/__init__.py`

- [ ] **Step 1: Update imports in `src/meta_harney/__init__.py`**

Find the section that imports from `meta_harney.providers.base` (currently around line 56):

```python
from meta_harney.providers.base import (
    LLMProvider,
    ProviderCallConfig,
    ProviderRedactedThinking,
    ProviderStreamDone,
    ProviderStreamEvent,
    ProviderTextDelta,
    ProviderThinkingBlock,
    ProviderThinkingDelta,
    ProviderToolCall,
    ToolSpec,
)
```

Directly **below** that block, add a new import line for the catalog module:

```python
from meta_harney.providers.catalog import (
    BUILT_IN_PROVIDERS,
    ProviderSpec,
    provider_from_spec,
    register_provider,
)
```

- [ ] **Step 2: Add the 4 new names to `__all__`**

Open `src/meta_harney/__init__.py` and find the `__all__` list. Insert the 4 new names in **alphabetical position**. Specifically:

- `"BUILT_IN_PROVIDERS"` goes between `"BaseTool"` and `"CompactionStrategy"`
- `"ProviderSpec"` goes between `"ProviderRedactedThinking"`/`"ProviderStreamDone"` block area (alphabetically after `"ProviderStreamEvent"` is wrong; correct alphabetical: between `"ProviderRedactedThinking"` and `"ProviderStreamDone"`)
- `"provider_from_spec"` (lowercase) goes after the uppercase identifiers — alphabetically; locate the existing `"run_turn"` / `"runtime_for_testing"` / `"tool_to_spec"` lowercase cluster
- `"register_provider"` (lowercase) goes near the same lowercase cluster

The exact correct positions depend on the current ordering. Safest: add them in obvious slots, then run `ruff check --fix src/meta_harney/__init__.py` — ruff's `RUF022` rule will alphabetize `__all__` automatically.

Concrete diff approach: just append the 4 names anywhere in the list, then let ruff fix order:

```python
__all__ = [
    # ... existing entries ...
    "BUILT_IN_PROVIDERS",
    "ProviderSpec",
    "provider_from_spec",
    "register_provider",
]
```

- [ ] **Step 3: Verify imports work + ruff fixes `__all__` order**

```bash
source .venv/bin/activate
python -c "
from meta_harney import (
    ProviderSpec,
    BUILT_IN_PROVIDERS,
    provider_from_spec,
    register_provider,
)
print('OK:', len(BUILT_IN_PROVIDERS))
"
```

Expected: `OK: 9`.

```bash
ruff check --fix src/meta_harney/__init__.py
ruff check src/meta_harney/__init__.py
```

Expected: any `RUF022` fix applied; clean recheck.

- [ ] **Step 4: Run full quality gates**

```bash
source .venv/bin/activate
pytest -q
mypy src/meta_harney
ruff check src/meta_harney tests
ruff format --check src/meta_harney tests
```

Expected: 315 tests pass; mypy + ruff all clean.

If `ruff format --check` reports diffs (e.g., on the modified `__init__.py`):

```bash
ruff format src/meta_harney
ruff format --check src/meta_harney tests
```

Re-run pytest after formatting to be sure nothing broke.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/__init__.py
git commit -m "feat: expose Provider Catalog at meta_harney top level

4 new public names:
- ProviderSpec
- BUILT_IN_PROVIDERS
- provider_from_spec
- register_provider

All added to __all__ (alphabetically sorted by ruff RUF022).
Catalog now reachable via: from meta_harney import ProviderSpec, ..."
```

---

## Task 3: Module docstring update + final quality gates

**Files:**
- Modify: `src/meta_harney/__init__.py` (docstring only)

- [ ] **Step 1: Update module docstring in `src/meta_harney/__init__.py`**

Find the current docstring at the top of `src/meta_harney/__init__.py`. The current Phase 7 docstring should look roughly like:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 7 status: extended-thinking full mode + GitHub Actions CI.
- ThinkingBlock + RedactedThinkingBlock content blocks (persisted, round-tripped)
...
"""
```

Replace it with:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 9a status: Provider Catalog.
- ProviderSpec + BUILT_IN_PROVIDERS for 9 known providers
  (anthropic, openai, moonshot, deepseek, gemini, minimax, nvidia,
  dashscope, modelscope)
- provider_from_spec() factory and register_provider() extension hook
- Anthropic extended-thinking full mode (Phase 7)
- ThinkingBlock + RedactedThinkingBlock content blocks
- OpenAIProvider (Phase 5) + AnthropicProvider (Phase 4)
- 9 core abstractions + builtin defaults
- GitHub Actions CI matrix (3.10/3.11/3.12 x ubuntu/macos)
"""
```

- [ ] **Step 2: Re-run all quality gates**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -2
```

Expected: 315 tests pass; mypy + ruff check + ruff format all clean.

- [ ] **Step 3: Smoke test public API**

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
print('Version:', mh.__version__)  # will be 0.0.7 until Task 4
print('Exports:', len(mh.__all__))

# Catalog reachable
assert mh.ProviderSpec
assert mh.BUILT_IN_PROVIDERS
assert len(mh.BUILT_IN_PROVIDERS) == 9
assert mh.provider_from_spec
assert mh.register_provider

# Round-trip: spec → provider
spec = mh.BUILT_IN_PROVIDERS['moonshot']
p = mh.provider_from_spec(spec, api_key='sk-test')
print('moonshot provider:', type(p).__name__)
print('OK')
"
```

Expected: `Version: 0.0.7` (bump comes in Task 4), `Exports: 59` (was 59 from v0.0.7 + 4 new = 63 — adjust expected count), `moonshot provider: OpenAIProvider`, `OK`.

Wait — actually the test should expect 63 exports. Updated:

```bash
source .venv/bin/activate
python -c "
import meta_harney as mh
print('Version:', mh.__version__)
print('Exports:', len(mh.__all__))
assert len(mh.__all__) == 63, f'expected 63 exports, got {len(mh.__all__)}'
assert len(mh.BUILT_IN_PROVIDERS) == 9
spec = mh.BUILT_IN_PROVIDERS['moonshot']
p = mh.provider_from_spec(spec, api_key='sk-test')
print('OK; moonshot provider:', type(p).__name__)
"
```

Expected: prints `Version: 0.0.7`, `Exports: 63`, `OK; moonshot provider: OpenAIProvider`.

- [ ] **Step 4: Commit**

```bash
git add src/meta_harney/__init__.py
git commit -m "docs: update meta_harney module docstring for Phase 9a

Reflects the new Provider Catalog. Version bump + tag land in Task 4."
```

---

## Task 4: v0.0.8 release — version bump + tag + push + CI watch

**Files:**
- Modify: `src/meta_harney/__init__.py` (version)
- Modify: `pyproject.toml` (version)

- [ ] **Step 1: Bump version in `src/meta_harney/__init__.py`**

Find `__version__ = "0.0.7"` and change to:

```python
__version__ = "0.0.8"
```

- [ ] **Step 2: Bump version in `pyproject.toml`**

Find `version = "0.0.7"` and change to:

```python
version = "0.0.8"
```

- [ ] **Step 3: Run full local gates one more time**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/meta_harney 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/meta_harney tests 2>&1 | tail -2
ruff format --check src/meta_harney tests 2>&1 | tail -2
```

Expected: 315 tests pass; clean.

If `ruff format --check` reports diffs:

```bash
ruff format src/meta_harney tests
git add -A
git commit -m "style: ruff format pass on Phase 9a sources"
```

- [ ] **Step 4: Commit version bump + tag + push**

```bash
git add src/meta_harney/__init__.py pyproject.toml
git commit -m "release: bump version to 0.0.8 for Phase 9a milestone

Phase 9a deliverable: Provider Catalog
- ProviderSpec frozen dataclass
- BUILT_IN_PROVIDERS with 9 entries
- provider_from_spec() factory
- register_provider() extension hook

Tests: 315 (was 305), all green.

Next: Phase 9b — oh-mini v0.2.0 consumes the catalog and adds
credentials + config system."

git tag -a v0.0.8 HEAD -m "$(cat <<'EOF'
meta-harney v0.0.8 — Phase 9a (Provider Catalog)

Builds on v0.0.7. Adds:

Provider Catalog (purely additive):
- ProviderSpec frozen dataclass with name/kind/base_url/default_model/description
- BUILT_IN_PROVIDERS dict[str, ProviderSpec] with 9 entries:
  anthropic, openai, moonshot, deepseek, gemini, minimax, nvidia,
  dashscope, modelscope (all OpenAI-compatible except anthropic)
- provider_from_spec(spec, api_key, model?) factory dispatches on spec.kind
- register_provider(spec, overwrite=False) for app-level extension

Public API surface: 4 new symbols added to meta_harney top level.

Zero breaking change. v0.0.7 user code unchanged.

Tests: 315 (was 305), all green.
Quality: mypy strict + ruff check + ruff format all clean.

Next: Phase 9b — oh-mini v0.2.0 consumes the catalog and adds full
credentials + config system (keyring/file storage, ~/.oh-mini/settings.json,
oh auth login/list/remove/show/profile CLI).
EOF
)"

GITHUB_TOKEN= git push origin main
GITHUB_TOKEN= git push origin v0.0.8
```

- [ ] **Step 5: Watch CI on the release commit**

```bash
GITHUB_TOKEN= gh run list --workflow=ci.yml --limit 1
```

Wait for the run to complete (use Bash `run_in_background` with an `until` poll loop, or `gh run watch <id>` foreground).

Expected: 6/6 jobs pass on the v0.0.8 commit.

If any job fails, debug and fix in a follow-up commit. The tag stays on the broken commit unless the user agrees to delete + retag.

- [ ] **Step 6: Final verification**

```bash
git log --oneline v0.0.7..HEAD
git tag -l 'v*'
source .venv/bin/activate
python -c "
import meta_harney as mh
print('Version:', mh.__version__)
print('Exports:', len(mh.__all__))
"
```

Expected:
- 4-5 commits between v0.0.7 and v0.0.8
- `v0.0.8` tag exists
- Version 0.0.8, exports 63

---

## Phase 9a Completion Checklist

- [ ] `src/meta_harney/providers/catalog.py` exists with all 4 public symbols
- [ ] `ProviderSpec` is a frozen dataclass
- [ ] `BUILT_IN_PROVIDERS` contains exactly 9 entries (anthropic, openai, moonshot, deepseek, gemini, minimax, nvidia, dashscope, modelscope)
- [ ] `anthropic` and `openai` specs have `base_url=None`; others have https URLs
- [ ] `provider_from_spec` returns `AnthropicProvider` for kind=anthropic, `OpenAIProvider` for kind=openai
- [ ] `provider_from_spec` raises `ValueError` for unknown kind
- [ ] `register_provider(spec)` adds to dict; `overwrite=False` rejects duplicates; `overwrite=True` replaces
- [ ] 4 new names in `meta_harney.__all__`
- [ ] 10 new tests in `tests/unit/providers/test_catalog.py`
- [ ] 315 total tests pass
- [ ] mypy strict + ruff check + ruff format all clean
- [ ] `__version__ = "0.0.8"` in `src/meta_harney/__init__.py`
- [ ] `version = "0.0.8"` in `pyproject.toml`
- [ ] `v0.0.8` git tag exists locally + pushed to origin
- [ ] GHA CI 6 jobs all green on the release commit

---

## Self-Review

**Spec coverage:**

- §1 Goals 1 (new module) → Task 1
- §1 Goals 2 (4 public APIs) → Tasks 1 (module), 2 (top-level export)
- §1 Goals 3 (10 unit tests) → Task 1 (RED + GREEN)
- §1 Goals 4 (v0.0.8 release) → Task 4
- §3 File Structure → Tasks 1, 2 cover both new files; Tasks 3, 4 modify __init__ + pyproject
- §4 APIs (ProviderSpec, BUILT_IN_PROVIDERS, provider_from_spec, register_provider) → Task 1
- §5 Data flow → Task 1 implements both startup (catalog load) and query (factory dispatch)
- §6 Error handling → Task 1 covers all error paths (KeyError pass-through, ValueError on duplicate, ValueError on unknown kind, FrozenInstanceError on field mutation)
- §7 Testing (10 unit tests + teardown fixture) → Task 1
- §8 Version + tag → Task 4
- §9 Completion criteria → Tracked by per-task checkboxes + Phase 9a Completion Checklist
- §10 Phase 9b衔接 → Documented as out-of-scope; mentioned in v0.0.8 tag message

**Placeholder scan:**

- No "TBD", "TODO", "implement later", or vague requirements.
- Task 2 step 2 acknowledges that `ruff check --fix` auto-sorts `__all__` (alphabetical placement is best-effort, then ruff finalizes). This is a concrete recovery path, not a placeholder.
- Task 3 step 3 has a corrected expected-count check (63 exports). Initial draft showed 59, then corrected; final expected count is 63 (v0.0.7's 59 + 4 new = 63).
- Task 4 step 4 uses GITHUB_TOKEN= prefix to bypass the broken-token env var, matching the pattern used in Phase 7's CI work.

**Type consistency:**

- `ProviderSpec(name, kind, base_url, default_model, description="")` — fields used identically in Tasks 1, 2, 3, 4 and in tests
- `kind: Literal["anthropic", "openai"]` — consistent across spec definition, factory dispatch, and test cast
- `BUILT_IN_PROVIDERS: dict[str, ProviderSpec]` — module-level dict, used directly in tests and via `register_provider` mutation
- `provider_from_spec(spec, *, api_key, model=None) -> LLMProvider` — keyword-only api_key, optional model accepted but unused; consistent
- `register_provider(spec, *, overwrite=False) -> None` — keyword-only overwrite; consistent
- `_clean_register` fixture removes any name not in `_EXPECTED_NAMES` (the 9 built-ins); used in 2 tests; symmetric

**Risk callouts:**

- Task 2 step 2 relies on ruff auto-sorting `__all__`. If RUF022 is disabled, the manual placement must be exactly alphabetical (no other ordering scheme).
- Task 3 expects exports = 63 (v0.0.7 was 59 + 4 new). If meta-harney's v0.0.7 actually has a different export count, update the assertion or the expected value.
- Task 4's `git push origin v0.0.8` requires GitHub auth working with the local `gh` keyring (env `GITHUB_TOKEN` is broken; the prefix bypass is documented in Phase 7's experience).
- Task 4 step 5's CI watch is async — use `gh run watch <id>` foreground OR Bash `run_in_background` with `until` poll loop.
