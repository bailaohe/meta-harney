# meta-harney Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the `feature/meta-harney` branch from an OpenHarness fork into a clean `meta_harney` Python package skeleton containing all 9 core abstractions, their builtin default implementations, and a contract-test foundation. No engine, no providers, no runtime yet — those are Phase 2/3.

**Architecture:** Hard fork. Delete every coding-flavored module in one sweep, then build the new abstraction layer from scratch using TDD. Each abstraction is one file with tests; each builtin implementation is one file with contract-test coverage. The result is a package that imports cleanly and ships verified abstraction contracts, ready for Phase 2 (engine + provider).

**Tech Stack:**
- Python 3.10+
- `pydantic` v2 (data contracts)
- `pytest` + `pytest-asyncio` (testing)
- `mypy --strict` (type checking)
- `uv` (env + dep management)
- `ruff` (lint + format)

**Spec reference:** `docs/superpowers/specs/2026-05-13-meta-harney-design.md`

---

## File Structure After Phase 1

```
meta-harney/
├── pyproject.toml                                    # NEW (replaces existing)
├── README.md                                         # Heavily simplified
├── CHANGELOG.md                                      # Reset
├── docs/                                             # Preserved
│
├── src/meta_harney/
│   ├── __init__.py                                   # Public API
│   ├── errors.py                                     # Exception hierarchy
│   │
│   ├── abstractions/
│   │   ├── __init__.py
│   │   ├── _types.py                                 # ContentBlock, Message
│   │   ├── tool.py                                   # BaseTool, ToolInvocation, ToolResult, ToolContext
│   │   ├── hook.py                                   # BaseHook, HookEvent, HookDecision
│   │   ├── permission.py                             # PermissionResolver, PermissionDecision
│   │   ├── prompt.py                                 # PromptBuilder
│   │   ├── task.py                                   # BaseTask, TaskState
│   │   ├── session.py                                # Session, SessionStore
│   │   ├── trace.py                                  # TraceEvent, TraceSink
│   │   ├── multi_agent.py                            # MultiAgentBackend, AgentSpec, SpawnHandle
│   │   └── compaction.py                             # CompactionStrategy
│   │
│   └── builtin/
│       ├── __init__.py
│       ├── permission/
│       │   ├── __init__.py
│       │   ├── allow_all.py                          # AllowAllPermissionResolver
│       │   └── deny_all.py                           # DenyAllPermissionResolver
│       ├── session/
│       │   ├── __init__.py
│       │   ├── memory_store.py                       # MemorySessionStore
│       │   └── file_store.py                         # FileSessionStore
│       ├── trace/
│       │   ├── __init__.py
│       │   ├── null_sink.py                          # NullSink
│       │   └── jsonl_sink.py                         # JsonlSink
│       ├── prompt/
│       │   ├── __init__.py
│       │   └── minimal.py                            # MinimalPromptBuilder
│       └── compaction/
│           ├── __init__.py
│           └── summarization.py                      # SummarizationCompactor
│
└── tests/
    ├── __init__.py
    ├── conftest.py                                   # Shared fixtures
    │
    ├── unit/
    │   ├── test_errors.py
    │   ├── abstractions/
    │   │   ├── test_types.py
    │   │   ├── test_tool.py
    │   │   ├── test_hook.py
    │   │   ├── test_permission.py
    │   │   ├── test_prompt.py
    │   │   ├── test_task.py
    │   │   ├── test_session.py
    │   │   ├── test_trace.py
    │   │   ├── test_multi_agent.py
    │   │   └── test_compaction.py
    │   └── builtin/
    │       ├── test_allow_all.py
    │       ├── test_deny_all.py
    │       ├── test_memory_store.py
    │       ├── test_file_store.py
    │       ├── test_null_sink.py
    │       ├── test_jsonl_sink.py
    │       ├── test_minimal_prompt.py
    │       └── test_summarization.py
    │
    └── contracts/
        ├── __init__.py
        ├── session_store.py                          # SessionStoreContract
        ├── permission_resolver.py                    # PermissionResolverContract
        ├── trace_sink.py                             # TraceSinkContract
        ├── prompt_builder.py                         # PromptBuilderContract
        └── compaction_strategy.py                    # CompactionStrategyContract
```

**Deleted (relative to OpenHarness main):** `ohmo/`, `frontend/`, `autopilot-dashboard/`, `src/openharness/` (entire), `tests/` (entire), `scripts/`, `.agents/`, `.openharness/`, `.sisyphus/`, all `RELEASE_NOTES_*.md`, `CONTRIBUTING.md` (regenerate later), `README.zh-CN.md` (regenerate later), `assets/` (will be reset later).

---

## Task 1: Workspace Prep & Verification

**Files:**
- Read: `pyproject.toml`, `.python-version` (if exists)

- [ ] **Step 1: Confirm branch and clean state**

```bash
git status
git rev-parse --abbrev-ref HEAD
```
Expected output:
```
On branch feature/meta-harney
... (only frontend/terminal/package-lock.json modified + .sisyphus/ untracked)
feature/meta-harney
```

- [ ] **Step 2: Set up Python venv**

```bash
test -d .venv || uv venv .venv --python 3.11
source .venv/bin/activate
python --version
```
Expected: `Python 3.11.x`

- [ ] **Step 3: Install minimal dev dependencies**

```bash
uv pip install pydantic pytest pytest-asyncio mypy ruff
python -c "import pydantic; print(pydantic.VERSION)"
```
Expected: Pydantic version 2.x

- [ ] **Step 4: Note current commit**

```bash
git log --oneline -1
```
Expected: most recent commit on feature/meta-harney (design doc commit).

No commit at this task.

---

## Task 2: Delete Top-Level Coding-Flavored Directories

**Files:**
- Delete: `ohmo/`, `frontend/`, `autopilot-dashboard/`, `assets/`, `scripts/`
- Delete: `RELEASE_NOTES_v0.1.8.md`, `RELEASE_NOTES_v0.1.9.md`, `README.zh-CN.md`, `CONTRIBUTING.md`
- Delete: `.agents/`, `.openharness/`, `.sisyphus/`

- [ ] **Step 1: Verify what we're about to delete exists**

```bash
ls -d ohmo frontend autopilot-dashboard assets scripts 2>&1
ls RELEASE_NOTES_v0.1.8.md RELEASE_NOTES_v0.1.9.md README.zh-CN.md CONTRIBUTING.md 2>&1
ls -d .agents .openharness .sisyphus 2>&1
```
Expected: all listed (or "No such file" for .sisyphus if cleaned earlier).

- [ ] **Step 2: Delete top-level dirs and files**

```bash
rm -rf ohmo frontend autopilot-dashboard assets scripts .agents .openharness .sisyphus
rm -f RELEASE_NOTES_v0.1.8.md RELEASE_NOTES_v0.1.9.md README.zh-CN.md CONTRIBUTING.md
```

- [ ] **Step 3: Verify deletion**

```bash
ls -la | grep -E "^d" | awk '{print $NF}'
```
Expected: should NOT contain `ohmo`, `frontend`, `autopilot-dashboard`, `assets`, `scripts`, `.agents`, `.openharness`, `.sisyphus`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete coding-flavored top-level directories

Phase 1 demolition: remove ohmo, frontend, autopilot-dashboard, assets,
scripts, release notes, contributing guide, and .agents/.openharness/.sisyphus
config dirs. None of these belong in the new business-agent runtime.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: Delete Old `src/openharness/` Package Entirely

**Files:**
- Delete: `src/openharness/` (all subdirectories and files)

- [ ] **Step 1: Inventory the size of what we're deleting**

```bash
find src/openharness -type f | wc -l
du -sh src/openharness
```
Expected: hundreds of files, several MB.

- [ ] **Step 2: Delete the entire src/openharness directory**

```bash
rm -rf src/openharness
ls src/
```
Expected: `src/` directory is now empty (or contains only non-openharness items).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete src/openharness/ entirely

Phase 1 demolition: the engine, providers, tools, prompts, permissions,
memory, hooks, tasks, swarm, coordinator, plugins, skills, mcp, auth,
ui, commands, services, config, state — all of it. Phase 1 will build
a fresh src/meta_harney/ from scratch.

Old code remains accessible via origin/main for reference.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: Delete Old `tests/` Directory

**Files:**
- Delete: `tests/`

- [ ] **Step 1: Confirm tests are coupled to deleted code**

```bash
find tests -type f -name "*.py" | head -5
```
Expected: all reference `openharness.*` imports (now broken).

- [ ] **Step 2: Delete tests/**

```bash
rm -rf tests
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: delete old tests/

Phase 1 demolition: existing tests target deleted openharness modules.
New tests/ will be rebuilt task-by-task in this plan.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: Replace `pyproject.toml` with Fresh meta-harney Config

**Files:**
- Modify: `pyproject.toml` (full replacement)
- Delete: `uv.lock` (regenerated)
- Delete: `CHANGELOG.md` (reset)

- [ ] **Step 1: Verify dependencies we need**

We need `pydantic>=2.5`, plus dev deps `pytest`, `pytest-asyncio`, `mypy`, `ruff`.

- [ ] **Step 2: Write new pyproject.toml**

```toml
[project]
name = "meta-harney"
version = "0.0.1"
description = "Domain-agnostic agent runtime SDK — abstractions for tool, hook, permission, prompt, task, session, trace, multi-agent, and compaction."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
authors = [
    { name = "meta-harney contributors" },
]
dependencies = [
    "pydantic>=2.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/meta_harney"]

[tool.hatch.build.targets.sdist]
include = [
    "src/meta_harney",
    "README.md",
    "CHANGELOG.md",
    "docs",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra"

[tool.mypy]
strict = true
python_version = "3.10"
mypy_path = "src"

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_decorators = false

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
```

- [ ] **Step 3: Delete the old uv.lock and CHANGELOG.md**

```bash
rm -f uv.lock CHANGELOG.md
```

- [ ] **Step 4: Write minimal README.md**

Overwrite `README.md` with:

```markdown
# meta-harney

A domain-agnostic agent runtime SDK. Provides clean abstractions for tools,
hooks, permissions, prompts, tasks, sessions, tracing, multi-agent coordination,
and context compaction — without making any assumptions about your business domain.

**Status:** Phase 1 — abstractions and defaults under construction. Not yet usable.

See `docs/superpowers/specs/2026-05-13-meta-harney-design.md` for full design.
```

- [ ] **Step 5: Verify pyproject parses**

```bash
python -c "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml README.md
git rm -f uv.lock CHANGELOG.md
git commit -m "build: replace pyproject.toml with meta-harney config

Reset project metadata: name meta-harney, version 0.0.1, py>=3.10,
pydantic v2 as the only runtime dep. Dev tools: pytest+asyncio+mypy+ruff.
README simplified to status placeholder. uv.lock and CHANGELOG.md deleted —
will regenerate as we go.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: Create Empty Package Skeleton

**Files:**
- Create: `src/meta_harney/__init__.py`
- Create: `src/meta_harney/abstractions/__init__.py`
- Create: `src/meta_harney/builtin/__init__.py`
- Create: `src/meta_harney/builtin/permission/__init__.py`
- Create: `src/meta_harney/builtin/session/__init__.py`
- Create: `src/meta_harney/builtin/trace/__init__.py`
- Create: `src/meta_harney/builtin/prompt/__init__.py`
- Create: `src/meta_harney/builtin/compaction/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/abstractions/__init__.py`
- Create: `tests/unit/builtin/__init__.py`
- Create: `tests/contracts/__init__.py`

- [ ] **Step 1: Create all package directories**

```bash
mkdir -p src/meta_harney/abstractions
mkdir -p src/meta_harney/builtin/{permission,session,trace,prompt,compaction}
mkdir -p tests/unit/{abstractions,builtin}
mkdir -p tests/contracts
```

- [ ] **Step 2: Create __init__.py files (empty)**

```bash
touch src/meta_harney/__init__.py
touch src/meta_harney/abstractions/__init__.py
touch src/meta_harney/builtin/__init__.py
touch src/meta_harney/builtin/permission/__init__.py
touch src/meta_harney/builtin/session/__init__.py
touch src/meta_harney/builtin/trace/__init__.py
touch src/meta_harney/builtin/prompt/__init__.py
touch src/meta_harney/builtin/compaction/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/unit/abstractions/__init__.py
touch tests/unit/builtin/__init__.py
touch tests/contracts/__init__.py
```

- [ ] **Step 3: Write conftest.py**

Create `tests/conftest.py` with content:

```python
"""Shared pytest fixtures for meta_harney tests."""
import pytest


@pytest.fixture(autouse=True)
def _isolate_event_loop():
    """Default-on: each test gets a fresh event loop via pytest-asyncio's auto mode."""
    yield
```

- [ ] **Step 4: Install package in editable mode**

```bash
uv pip install -e ".[dev]"
python -c "import meta_harney; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Run pytest (no tests yet) to verify config**

```bash
pytest
```
Expected: `no tests ran` (exit 5) or `collected 0 items`. Not an error.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: scaffold src/meta_harney package skeleton

Empty __init__.py files establishing the abstractions/ and builtin/
package layout. tests/conftest.py for pytest-asyncio auto mode.
Package installs and imports cleanly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: Implement Exception Hierarchy (`errors.py`)

**Files:**
- Create: `src/meta_harney/errors.py`
- Test: `tests/unit/test_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_errors.py`:

```python
"""Tests for the meta_harney exception hierarchy."""
import pytest

from meta_harney.errors import (
    MetaHarneyError,
    ConfigurationError,
    ProviderError,
    RetryableProviderError,
    NonRetryableProviderError,
    ToolError,
    ToolNotFoundError,
    ToolInvalidArgsError,
    ToolExecutionError,
    ToolTimeoutError,
    PermissionDeniedError,
    HookError,
    HookHaltError,
    HookExecutionError,
    SessionError,
    SessionNotFoundError,
    SessionConflictError,
    SessionStoreError,
    CompactionError,
    MultiAgentError,
    SpawnError,
    ChildTimeoutError,
)


def test_root_is_exception():
    assert issubclass(MetaHarneyError, Exception)


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigurationError,
        ProviderError,
        ToolError,
        PermissionDeniedError,
        HookError,
        SessionError,
        CompactionError,
        MultiAgentError,
    ],
)
def test_top_level_subclasses_root(exc_cls):
    assert issubclass(exc_cls, MetaHarneyError)


@pytest.mark.parametrize(
    "child,parent",
    [
        (RetryableProviderError, ProviderError),
        (NonRetryableProviderError, ProviderError),
        (ToolNotFoundError, ToolError),
        (ToolInvalidArgsError, ToolError),
        (ToolExecutionError, ToolError),
        (ToolTimeoutError, ToolError),
        (HookHaltError, HookError),
        (HookExecutionError, HookError),
        (SessionNotFoundError, SessionError),
        (SessionConflictError, SessionError),
        (SessionStoreError, SessionError),
        (SpawnError, MultiAgentError),
        (ChildTimeoutError, MultiAgentError),
    ],
)
def test_nested_hierarchy(child, parent):
    assert issubclass(child, parent)


def test_hook_halt_carries_reason():
    err = HookHaltError(reason="user requested stop")
    assert err.reason == "user requested stop"
    assert "user requested stop" in str(err)


def test_session_conflict_carries_versions():
    err = SessionConflictError(session_id="s1", expected_version=3, found_version=5)
    assert err.session_id == "s1"
    assert err.expected_version == 3
    assert err.found_version == 5


def test_tool_timeout_carries_timeout_value():
    err = ToolTimeoutError(tool_name="my_tool", timeout_s=10.0)
    assert err.tool_name == "my_tool"
    assert err.timeout_s == 10.0
```

- [ ] **Step 2: Run test to confirm it fails (module missing)**

```bash
pytest tests/unit/test_errors.py -v
```
Expected: `ModuleNotFoundError: No module named 'meta_harney.errors'`

- [ ] **Step 3: Write errors.py**

Create `src/meta_harney/errors.py`:

```python
"""meta_harney exception hierarchy.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §7.1.
"""
from __future__ import annotations


class MetaHarneyError(Exception):
    """Root of all meta_harney exceptions."""


# ---- Configuration ----

class ConfigurationError(MetaHarneyError):
    """Raised at runtime construction time (fail-fast)."""


# ---- LLM Provider ----

class ProviderError(MetaHarneyError):
    """Base for all LLM provider issues."""


class RetryableProviderError(ProviderError):
    """429, 5xx, network blips — engine will retry."""


class NonRetryableProviderError(ProviderError):
    """Auth failures, invalid request, etc. — propagate immediately."""


# ---- Tool ----

class ToolError(MetaHarneyError):
    """Base for tool-execution failures (converted to ToolResult)."""


class ToolNotFoundError(ToolError):
    """Tool name not registered."""


class ToolInvalidArgsError(ToolError):
    """Tool arg schema validation failed."""


class ToolExecutionError(ToolError):
    """Tool raised during execute()."""


class ToolTimeoutError(ToolError):
    """Tool exceeded its configured timeout."""

    def __init__(self, tool_name: str, timeout_s: float):
        super().__init__(f"Tool {tool_name!r} timed out after {timeout_s}s")
        self.tool_name = tool_name
        self.timeout_s = timeout_s


# ---- Permission ----

class PermissionDeniedError(MetaHarneyError):
    """Permission resolver returned 'deny'. Converted to ToolResult by engine."""


# ---- Hook ----

class HookError(MetaHarneyError):
    """Base for hook subsystem errors."""


class HookHaltError(HookError):
    """Business hook explicitly halts the agent loop. Propagates to invoke caller."""

    def __init__(self, reason: str):
        super().__init__(f"Hook halt: {reason}")
        self.reason = reason


class HookExecutionError(HookError):
    """Hook raised unexpectedly. Engine logs and continues (fail-open)."""


# ---- Session ----

class SessionError(MetaHarneyError):
    """Base for session/store errors."""


class SessionNotFoundError(SessionError):
    """Session id does not exist in the store."""


class SessionConflictError(SessionError):
    """Optimistic-lock conflict on save."""

    def __init__(self, session_id: str, expected_version: int, found_version: int):
        super().__init__(
            f"Session {session_id!r} version mismatch: expected {expected_version}, "
            f"found {found_version}"
        )
        self.session_id = session_id
        self.expected_version = expected_version
        self.found_version = found_version


class SessionStoreError(SessionError):
    """Underlying store I/O failure."""


# ---- Compaction ----

class CompactionError(MetaHarneyError):
    """Compactor raised. Engine logs and skips this compaction (fail-open)."""


# ---- MultiAgent ----

class MultiAgentError(MetaHarneyError):
    """Base for multi-agent backend errors."""


class SpawnError(MultiAgentError):
    """Failed to spawn a child agent."""


class ChildTimeoutError(MultiAgentError):
    """Child agent did not return within the join timeout."""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_errors.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/errors.py tests/unit/test_errors.py
git commit -m "feat(errors): implement exception hierarchy

10-level hierarchy under MetaHarneyError covering Configuration, Provider
(retryable/non-retryable), Tool (5 variants), Permission, Hook (Halt and
ExecutionError), Session (NotFound/Conflict/Store), Compaction, MultiAgent
(Spawn/ChildTimeout). HookHaltError carries reason, SessionConflictError
carries version mismatch detail, ToolTimeoutError carries tool name and
timeout value.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: Implement Shared Data Contracts (`abstractions/_types.py`)

**Files:**
- Create: `src/meta_harney/abstractions/_types.py`
- Test: `tests/unit/abstractions/test_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_types.py`:

```python
"""Tests for shared data contracts: ContentBlock variants + Message."""
import pytest
from pydantic import ValidationError

from meta_harney.abstractions._types import (
    ContentBlock,
    TextBlock,
    ImageBlock,
    ToolCallBlock,
    ToolResultBlock,
    Message,
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
    b = ToolResultBlock(
        invocation_id="inv1", success=False, output=None, error="boom"
    )
    assert not b.success
    assert b.error == "boom"


def test_message_role_constrained():
    Message(role="user", content=[TextBlock(text="hi")])
    Message(role="assistant", content=[TextBlock(text="hi")])
    Message(role="system", content=[TextBlock(text="hi")])
    Message(role="tool", content=[TextBlock(text="hi")])
    with pytest.raises(ValidationError):
        Message(role="customer", content=[TextBlock(text="hi")])  # not allowed


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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_types.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `_types.py`**

Create `src/meta_harney/abstractions/_types.py`:

```python
"""Shared data contracts: Content blocks and Message envelope.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.1.
"""
from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class _ContentBlockBase(BaseModel):
    type: str


class TextBlock(_ContentBlockBase):
    type: Literal["text"] = "text"
    text: str


class ImageBlock(_ContentBlockBase):
    type: Literal["image"] = "image"
    url: str | None = None
    data: str | None = None  # base64
    media_type: str


class ToolCallBlock(_ContentBlockBase):
    type: Literal["tool_call"] = "tool_call"
    invocation_id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(_ContentBlockBase):
    type: Literal["tool_result"] = "tool_result"
    invocation_id: str
    success: bool
    output: Any = None
    error: str | None = None


ContentBlock = Union[TextBlock, ImageBlock, ToolCallBlock, ToolResultBlock]


class Message(BaseModel):
    """A single message in a session's history.

    `role` is constrained to the LLM wire vocabulary; `author` is a free-form
    business label (e.g., "sales", "customer") that provider adapters map to
    the wire (OpenAI: `name`; Anthropic: text prefix injection).
    """

    role: Literal["user", "assistant", "system", "tool"]
    author: str | None = None
    name: str | None = None  # OpenAI passthrough
    content: list[ContentBlock]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_types.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/_types.py tests/unit/abstractions/test_types.py
git commit -m "feat(abstractions): shared data contracts (ContentBlock, Message)

TextBlock, ImageBlock, ToolCallBlock, ToolResultBlock as discriminated
union under ContentBlock. Message constrains 'role' to the LLM wire
vocabulary (user/assistant/system/tool) while exposing free-form
'author' for business labels like 'sales'/'customer'.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: Implement `abstractions/tool.py`

**Files:**
- Create: `src/meta_harney/abstractions/tool.py`
- Test: `tests/unit/abstractions/test_tool.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_tool.py`:

```python
"""Tests for BaseTool, ToolInvocation, ToolResult, ToolContext."""
from __future__ import annotations
import uuid
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, ValidationError

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)


def test_tool_invocation_fields():
    inv = ToolInvocation(
        name="my_tool",
        args={"x": 1},
        invocation_id="inv-1",
        session_id="s-1",
    )
    assert inv.name == "my_tool"
    assert inv.session_id == "s-1"


def test_tool_invocation_session_id_required():
    with pytest.raises(ValidationError):
        ToolInvocation(name="t", args={}, invocation_id="i")  # type: ignore


def test_tool_result_success():
    r = ToolResult(success=True, output={"ok": True})
    assert r.success
    assert r.error is None
    assert r.metadata == {}


def test_tool_result_failure():
    r = ToolResult(success=False, output=None, error="bad input")
    assert not r.success
    assert r.error == "bad input"


def test_tool_context_dataclass_fields():
    """ToolContext is a dataclass exposing runtime services to tools."""
    ctx = ToolContext(
        session_store=object(),  # type: ignore  # placeholder for protocol
        trace_sink=object(),  # type: ignore
        current_span_id="span-1",
        new_span_id=lambda: uuid.uuid4().hex[:16],
    )
    assert ctx.current_span_id == "span-1"
    assert isinstance(ctx.new_span_id(), str)


def test_base_tool_is_abstract():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore[abstract]


def test_concrete_tool_can_subclass():
    class EchoInput(BaseModel):
        text: str

    class EchoTool(BaseTool):
        name = "echo"
        description = "Echoes input."
        input_schema = EchoInput
        default_timeout = 5.0

        async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
            return ToolResult(success=True, output=inv.args)

    assert EchoTool.name == "echo"
    assert EchoTool.default_timeout == 5.0
    assert issubclass(EchoTool, BaseTool)


def test_concrete_tool_without_required_classvars_fails():
    class Broken(BaseTool):
        async def execute(self, inv, ctx):
            return ToolResult(success=True, output=None)

    # missing required ClassVars: name, description, input_schema
    # Note: Python doesn't enforce ClassVar presence at class-creation;
    # we instead rely on type-checker. We test that the class instantiates
    # but accessing the unset ClassVar raises AttributeError.
    t = Broken()
    with pytest.raises(AttributeError):
        _ = t.name
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_tool.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `tool.py`**

Create `src/meta_harney/abstractions/tool.py`:

```python
"""Tool abstraction: BaseTool ABC + ToolInvocation/ToolResult/ToolContext.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.2.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from meta_harney.abstractions.session import SessionStore
    from meta_harney.abstractions.trace import TraceSink


class ToolInvocation(BaseModel):
    """A single tool call request from the engine."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    invocation_id: str
    session_id: str  # tools load Session on demand via ctx.session_store


class ToolResult(BaseModel):
    """A single tool call result."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ToolContext:
    """Runtime services exposed to tools at execute() time.

    Business tools may subclass to inject additional services (e.g., DB session).
    The engine constructs ToolContext per invocation.
    """

    session_store: SessionStore
    trace_sink: TraceSink
    current_span_id: str
    new_span_id: Callable[[], str]


class BaseTool(ABC):
    """Base class for all tools.

    Subclasses declare `name`, `description`, `input_schema`, and optionally
    `default_timeout`, then implement `execute()`.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    default_timeout: ClassVar[float | None] = None

    @abstractmethod
    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult:
        """Execute the tool with the given invocation. Must be async."""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_tool.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/tool.py tests/unit/abstractions/test_tool.py
git commit -m "feat(abstractions): BaseTool, ToolInvocation, ToolResult, ToolContext

BaseTool is an ABC requiring async execute(inv, ctx). Subclasses declare
name/description/input_schema as ClassVar plus optional default_timeout.
ToolInvocation carries session_id (not Session) — tools load on demand.
ToolContext exposes session_store, trace_sink, current_span_id, new_span_id;
business may subclass to inject additional services.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: Implement `abstractions/hook.py`

**Files:**
- Create: `src/meta_harney/abstractions/hook.py`
- Test: `tests/unit/abstractions/test_hook.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_hook.py`:

```python
"""Tests for BaseHook, HookEvent, HookDecision."""
from __future__ import annotations
import pytest
from pydantic import ValidationError

from meta_harney.abstractions.hook import (
    BaseHook,
    HookDecision,
    HookEvent,
)


def test_hook_event_kinds():
    valid = [
        "pre_tool", "post_tool", "pre_llm", "post_llm",
        "session_start", "session_end", "turn_complete",
    ]
    for kind in valid:
        ev = HookEvent(kind=kind, session_id="s1", payload={})
        assert ev.kind == kind


def test_hook_event_invalid_kind():
    with pytest.raises(ValidationError):
        HookEvent(kind="bogus", session_id="s1", payload={})  # type: ignore


def test_hook_decision_defaults():
    d = HookDecision()
    assert d.allow is True
    assert d.transform is None
    assert d.reason is None


def test_hook_decision_deny():
    d = HookDecision(allow=False, reason="blocked")
    assert not d.allow
    assert d.reason == "blocked"


def test_hook_decision_with_transform():
    d = HookDecision(transform={"args": {"x": 99}})
    assert d.transform == {"args": {"x": 99}}


def test_base_hook_is_abstract():
    with pytest.raises(TypeError):
        BaseHook()  # type: ignore[abstract]


def test_concrete_hook_subclass():
    class LogHook(BaseHook):
        subscribed_events = {"pre_tool", "post_tool"}

        async def handle(self, event: HookEvent) -> HookDecision:
            return HookDecision(allow=True)

    h = LogHook()
    assert h.subscribed_events == {"pre_tool", "post_tool"}
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_hook.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `hook.py`**

Create `src/meta_harney/abstractions/hook.py`:

```python
"""Hook abstraction: BaseHook ABC + HookEvent + HookDecision.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.3.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field


HookEventKind = Literal[
    "pre_tool",
    "post_tool",
    "pre_llm",
    "post_llm",
    "session_start",
    "session_end",
    "turn_complete",
]


class HookEvent(BaseModel):
    """A lifecycle event delivered to subscribed hooks."""

    kind: HookEventKind
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class HookDecision(BaseModel):
    """Hook return value: allow/deny + optional in-flight transform.

    `transform` is only applied for pre_* events; engine ignores it for
    post_* events (and emits a warning trace).
    """

    allow: bool = True
    transform: dict[str, Any] | None = None
    reason: str | None = None


class BaseHook(ABC):
    """Base class for all hooks.

    Subclasses declare `subscribed_events` and implement `handle()`.
    """

    subscribed_events: ClassVar[set[HookEventKind]]

    @abstractmethod
    async def handle(self, event: HookEvent) -> HookDecision:
        """Handle a subscribed event. Must be async."""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_hook.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/hook.py tests/unit/abstractions/test_hook.py
git commit -m "feat(abstractions): BaseHook, HookEvent, HookDecision

7 lifecycle event kinds: pre_tool, post_tool, pre_llm, post_llm,
session_start, session_end, turn_complete. HookDecision provides
allow/deny + optional transform (engine enforces transform only on
pre_* events — post_* sees it and warns via trace).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: Implement `abstractions/permission.py`

**Files:**
- Create: `src/meta_harney/abstractions/permission.py`
- Test: `tests/unit/abstractions/test_permission.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_permission.py`:

```python
"""Tests for PermissionResolver Protocol + PermissionDecision."""
from __future__ import annotations
import pytest
from pydantic import ValidationError

from meta_harney.abstractions.permission import (
    PermissionDecision,
    PermissionResolver,
)
from meta_harney.abstractions.tool import ToolInvocation


def test_permission_decision_allow():
    d = PermissionDecision(verdict="allow")
    assert d.verdict == "allow"
    assert d.reason is None


def test_permission_decision_deny():
    d = PermissionDecision(verdict="deny", reason="path forbidden")
    assert d.verdict == "deny"
    assert d.reason == "path forbidden"


def test_permission_decision_ask():
    d = PermissionDecision(verdict="ask")
    assert d.verdict == "ask"


def test_permission_decision_invalid_verdict():
    with pytest.raises(ValidationError):
        PermissionDecision(verdict="maybe")  # type: ignore


async def test_protocol_is_satisfied_by_duck_typing():
    """PermissionResolver is a Protocol — any class with `resolve()` matches."""

    class AllowAll:
        async def resolve(self, invocation, session_id):
            return PermissionDecision(verdict="allow")

    resolver: PermissionResolver = AllowAll()
    inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
    d = await resolver.resolve(inv, "s")
    assert d.verdict == "allow"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_permission.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `permission.py`**

Create `src/meta_harney/abstractions/permission.py`:

```python
"""Permission abstraction: PermissionResolver Protocol + PermissionDecision.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.4.
"""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from meta_harney.abstractions.tool import ToolInvocation


class PermissionDecision(BaseModel):
    """Resolver verdict on a single tool invocation."""

    verdict: Literal["allow", "deny", "ask"]
    reason: str | None = None


class PermissionResolver(Protocol):
    """Decides whether a tool invocation is allowed.

    Implementations are duck-typed; no inheritance required. The framework
    ships `AllowAllPermissionResolver` and `DenyAllPermissionResolver` as
    defaults under `meta_harney.builtin.permission`.
    """

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_permission.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/permission.py tests/unit/abstractions/test_permission.py
git commit -m "feat(abstractions): PermissionResolver Protocol + PermissionDecision

Duck-typed Protocol with single async resolve(invocation, session_id)
returning allow/deny/ask + optional reason.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Implement `abstractions/prompt.py`

**Files:**
- Create: `src/meta_harney/abstractions/prompt.py`
- Test: `tests/unit/abstractions/test_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_prompt.py`:

```python
"""Tests for PromptBuilder Protocol."""
from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.prompt import PromptBuilder


async def test_protocol_satisfied_by_duck_typing():
    class Fake:
        async def build_system_prompt(self, session_id: str) -> str:
            return f"hi from {session_id}"

        async def build_context_messages(self, session_id: str) -> list[Message]:
            return [Message(role="user", content=[TextBlock(text="prior")])]

    builder: PromptBuilder = Fake()
    sp = await builder.build_system_prompt("s1")
    assert sp == "hi from s1"

    msgs = await builder.build_context_messages("s1")
    assert len(msgs) == 1
    assert msgs[0].content[0].text == "prior"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_prompt.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `prompt.py`**

Create `src/meta_harney/abstractions/prompt.py`:

```python
"""Prompt abstraction: PromptBuilder Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.5.
"""
from __future__ import annotations

from typing import Protocol

from meta_harney.abstractions._types import Message


class PromptBuilder(Protocol):
    """Builds the system prompt and context messages for a given session."""

    async def build_system_prompt(self, session_id: str) -> str: ...

    async def build_context_messages(self, session_id: str) -> list[Message]: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_prompt.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/prompt.py tests/unit/abstractions/test_prompt.py
git commit -m "feat(abstractions): PromptBuilder Protocol

Two async methods: build_system_prompt(session_id) -> str and
build_context_messages(session_id) -> list[Message]. No coding context
assumptions; business implementations decide what's in the system prompt
and how prior conversation is loaded.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 13: Implement `abstractions/task.py`

**Files:**
- Create: `src/meta_harney/abstractions/task.py`
- Test: `tests/unit/abstractions/test_task.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_task.py`:

```python
"""Tests for BaseTask ABC + TaskState."""
from __future__ import annotations

import pytest

from meta_harney.abstractions.task import BaseTask, TaskState


def test_task_state_values():
    assert TaskState.PENDING.value == "pending"
    assert TaskState.RUNNING.value == "running"
    assert TaskState.SUCCEEDED.value == "succeeded"
    assert TaskState.FAILED.value == "failed"
    assert TaskState.CANCELLED.value == "cancelled"


def test_base_task_is_abstract():
    with pytest.raises(TypeError):
        BaseTask()  # type: ignore[abstract]


async def test_concrete_task_subclass():
    class HelloTask(BaseTask):
        def __init__(self):
            self.task_id = "t1"
            self.state = TaskState.PENDING

        async def run(self) -> str:
            self.state = TaskState.RUNNING
            self.state = TaskState.SUCCEEDED
            return "done"

        async def cancel(self) -> None:
            self.state = TaskState.CANCELLED

    t = HelloTask()
    result = await t.run()
    assert result == "done"
    assert t.state == TaskState.SUCCEEDED
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_task.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `task.py`**

Create `src/meta_harney/abstractions/task.py`:

```python
"""Task abstraction: BaseTask ABC + TaskState enum.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.6.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BaseTask(ABC):
    """Base for background tasks managed by the runtime.

    Subclasses set `task_id` and `state` in __init__ and implement async
    `run()` and `cancel()`. The TaskManager (introduced in Phase 2) owns
    a registry of running tasks.
    """

    task_id: str
    state: TaskState

    @abstractmethod
    async def run(self) -> Any: ...

    @abstractmethod
    async def cancel(self) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_task.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/task.py tests/unit/abstractions/test_task.py
git commit -m "feat(abstractions): BaseTask ABC + TaskState enum

5 states: PENDING, RUNNING, SUCCEEDED, FAILED, CANCELLED. BaseTask
declares task_id, state attrs and async run()/cancel() methods.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 14: Implement `abstractions/session.py`

**Files:**
- Create: `src/meta_harney/abstractions/session.py`
- Test: `tests/unit/abstractions/test_session.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_session.py`:

```python
"""Tests for Session model + SessionStore Protocol."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session, SessionStore


def test_session_minimal():
    s = Session(id="s1", created_at=datetime.now(timezone.utc))
    assert s.id == "s1"
    assert s.tenant_id is None
    assert s.user_id is None
    assert s.parent_session_id is None
    assert s.version == 0
    assert s.messages == []
    assert s.attributes == {}
    assert s.metadata == {}


def test_session_full():
    now = datetime.now(timezone.utc)
    s = Session(
        id="s1",
        tenant_id="acme",
        user_id="u1",
        parent_session_id="parent-s",
        created_at=now,
        version=3,
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
        attributes={"customer_id": "C-001"},
        metadata={"app_version": "1.0"},
    )
    assert s.tenant_id == "acme"
    assert s.attributes["customer_id"] == "C-001"
    assert len(s.messages) == 1


def test_session_attributes_free_form():
    s = Session(id="s1", created_at=datetime.now(timezone.utc))
    s.attributes["nested"] = {"a": [1, 2, 3]}
    assert s.attributes["nested"]["a"] == [1, 2, 3]


async def test_protocol_satisfied_by_duck_typing():
    """SessionStore is a Protocol — duck typing suffices."""

    class FakeStore:
        def __init__(self):
            self._data: dict[str, Session] = {}

        async def load(self, session_id, *, tenant_id=None):
            s = self._data.get(session_id)
            if s and tenant_id and s.tenant_id != tenant_id:
                return None
            return s

        async def save(self, session):
            self._data[session.id] = session

        async def list(self, *, tenant_id=None, filter=None):
            results = list(self._data.values())
            if tenant_id is not None:
                results = [s for s in results if s.tenant_id == tenant_id]
            return results

        async def delete(self, session_id):
            self._data.pop(session_id, None)

    store: SessionStore = FakeStore()
    s = Session(id="s1", tenant_id="acme", created_at=datetime.now(timezone.utc))
    await store.save(s)
    assert (await store.load("s1")).id == "s1"
    assert (await store.load("s1", tenant_id="other")) is None
    assert len(await store.list(tenant_id="acme")) == 1
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_session.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `session.py`**

Create `src/meta_harney/abstractions/session.py`:

```python
"""Session abstraction: Session model + SessionStore Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.7.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from meta_harney.abstractions._types import Message


class Session(BaseModel):
    """Authoritative session state.

    `attributes` is the business self-service area: customer ids, order
    numbers, anything outside of message content. `version` is the
    optimistic-lock token enforced by SessionStore implementations.
    """

    id: str
    tenant_id: str | None = None
    user_id: str | None = None
    parent_session_id: str | None = None
    created_at: datetime
    version: int = 0
    messages: list[Message] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionStore(Protocol):
    """Persistence backend for Session.

    Implementations MUST:
    - Support tenant filtering on `load()` and `list()`.
    - Enforce optimistic locking on `save()` — raise `SessionConflictError`
      when the in-store version doesn't match the incoming session's version.
    - Increment `session.version` on every successful save.

    These contracts are validated by `SessionStoreContract` test suite.
    """

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None: ...

    async def save(self, session: Session) -> None: ...

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]: ...

    async def delete(self, session_id: str) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_session.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/session.py tests/unit/abstractions/test_session.py
git commit -m "feat(abstractions): Session + SessionStore Protocol

Session carries id, tenant_id, user_id, parent_session_id, created_at,
version (optimistic lock), messages, attributes (business KV), metadata.
SessionStore Protocol requires load(with tenant filter)/save(with lock)/
list/delete; contracts enforced by SessionStoreContract test suite (Task 22).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 15: Implement `abstractions/trace.py`

**Files:**
- Create: `src/meta_harney/abstractions/trace.py`
- Test: `tests/unit/abstractions/test_trace.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_trace.py`:

```python
"""Tests for TraceEvent + TraceSink Protocol."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def test_trace_event_minimal():
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="turn.started",
        span_id="span-a",
        payload={},
    )
    assert ev.parent_span_id is None
    assert ev.duration_ms is None


def test_trace_event_with_parent():
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="tool.completed",
        span_id="span-b",
        parent_span_id="span-a",
        payload={"success": True},
        duration_ms=123.4,
    )
    assert ev.parent_span_id == "span-a"
    assert ev.duration_ms == 123.4


async def test_protocol_satisfied_by_duck_typing():
    class CollectingSink:
        def __init__(self):
            self.events: list[TraceEvent] = []
            self.flushed = False

        async def emit(self, event: TraceEvent) -> None:
            self.events.append(event)

        async def flush(self) -> None:
            self.flushed = True

    sink: TraceSink = CollectingSink()
    ev = TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind="turn.started",
        span_id="x",
        payload={},
    )
    await sink.emit(ev)
    await sink.flush()
    assert len(sink.events) == 1
    assert sink.flushed
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_trace.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `trace.py`**

Create `src/meta_harney/abstractions/trace.py`:

```python
"""Trace abstraction: TraceEvent model + TraceSink Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.8.
Reserved kind vocabulary in Appendix A of the spec.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """A single observation event in the agent's life.

    `kind` is open-typed (str) for forward compatibility; the spec reserves
    a vocabulary (Appendix A) and recommends business prefixes (e.g., crm.*)
    for custom kinds. The framework does not enforce prefix validation —
    that is a TraceSink implementation decision.
    """

    ts: datetime
    session_id: str
    kind: str
    span_id: str
    parent_span_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class TraceSink(Protocol):
    """Receives all trace events emitted by the engine.

    Implementations MUST NOT raise to the engine: any exception is caught
    by the engine and logged to stderr, never propagated. This is the
    "observability shouldn't kill the system" rule.
    """

    async def emit(self, event: TraceEvent) -> None: ...

    async def flush(self) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_trace.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/trace.py tests/unit/abstractions/test_trace.py
git commit -m "feat(abstractions): TraceEvent + TraceSink Protocol

TraceEvent: ts, session_id, kind (str, open), span_id, parent_span_id,
payload, duration_ms. TraceSink Protocol: async emit() + flush().
Sink exceptions are isolated by the engine (never propagate).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 16: Implement `abstractions/multi_agent.py`

**Files:**
- Create: `src/meta_harney/abstractions/multi_agent.py`
- Test: `tests/unit/abstractions/test_multi_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_multi_agent.py`:

```python
"""Tests for AgentSpec, SpawnHandle, MultiAgentBackend Protocol."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from meta_harney.abstractions.multi_agent import (
    AgentSpec,
    MultiAgentBackend,
    SpawnHandle,
)
from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


def test_agent_spec_defaults():
    spec = AgentSpec(
        name="helper",
        instructions="You are helpful.",
        allowed_tools=["echo"],
    )
    assert spec.max_iters == 10


def test_spawn_handle_modes():
    h = SpawnHandle(child_session_id="child-1", mode="blocking")
    assert h.mode == "blocking"
    h2 = SpawnHandle(child_session_id="child-2", mode="detached")
    assert h2.mode == "detached"


def test_spawn_handle_invalid_mode():
    with pytest.raises(ValidationError):
        SpawnHandle(child_session_id="x", mode="async")  # type: ignore


async def test_protocol_satisfied_by_duck_typing():
    class FakeBackend:
        async def spawn(self, spec, initial_message, parent_session_id, mode="blocking"):
            return SpawnHandle(child_session_id="child", mode=mode)

        async def join(self, child_session_id, timeout=None):
            return ToolResult(success=True, output="child done")

        async def status(self, child_session_id):
            return TaskState.SUCCEEDED

        async def cancel(self, child_session_id):
            return None

    backend: MultiAgentBackend = FakeBackend()
    spec = AgentSpec(name="x", instructions="y", allowed_tools=[])
    h = await backend.spawn(spec, "hello", "parent")
    assert h.child_session_id == "child"
    r = await backend.join("child")
    assert r.success
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_multi_agent.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `multi_agent.py`**

Create `src/meta_harney/abstractions/multi_agent.py`:

```python
"""MultiAgent abstraction: AgentSpec + SpawnHandle + MultiAgentBackend Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.9.
"""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from meta_harney.abstractions.task import TaskState
from meta_harney.abstractions.tool import ToolResult


class AgentSpec(BaseModel):
    """Definition of a child agent to spawn."""

    name: str
    instructions: str  # the child's system prompt
    allowed_tools: list[str]
    max_iters: int = 10


class SpawnHandle(BaseModel):
    """Returned by spawn() — identifies the child session."""

    child_session_id: str
    mode: Literal["blocking", "detached"]


class MultiAgentBackend(Protocol):
    """Coordinates spawning, joining, status-checking and cancelling child agents.

    Concrete implementations (in-process, subprocess, remote RPC) plug in here.
    The Phase 1 plan only defines the Protocol; implementations land in Phase 3.
    """

    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: Literal["blocking", "detached"] = "blocking",
    ) -> SpawnHandle: ...

    async def join(
        self,
        child_session_id: str,
        timeout: float | None = None,
    ) -> ToolResult: ...

    async def status(self, child_session_id: str) -> TaskState: ...

    async def cancel(self, child_session_id: str) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_multi_agent.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/multi_agent.py tests/unit/abstractions/test_multi_agent.py
git commit -m "feat(abstractions): MultiAgentBackend Protocol + AgentSpec + SpawnHandle

AgentSpec(name, instructions, allowed_tools, max_iters=10).
SpawnHandle(child_session_id, mode). Protocol methods: spawn(mode=
blocking|detached) -> SpawnHandle, join(timeout) -> ToolResult, status,
cancel. Implementations land in Phase 3.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 17: Implement `abstractions/compaction.py`

**Files:**
- Create: `src/meta_harney/abstractions/compaction.py`
- Test: `tests/unit/abstractions/test_compaction.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/abstractions/test_compaction.py`:

```python
"""Tests for CompactionStrategy Protocol."""
from __future__ import annotations

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.compaction import CompactionStrategy


async def test_protocol_satisfied_by_duck_typing():
    class AlwaysCompact:
        async def should_compact(self, session_id, current_tokens, window_limit):
            return current_tokens > window_limit * 0.5

        async def compact(self, session_id):
            return [Message(role="system", content=[TextBlock(text="summary")])]

    strat: CompactionStrategy = AlwaysCompact()
    assert await strat.should_compact("s", 600, 1000)
    assert not await strat.should_compact("s", 400, 1000)
    msgs = await strat.compact("s")
    assert len(msgs) == 1
    assert msgs[0].content[0].text == "summary"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/abstractions/test_compaction.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `compaction.py`**

Create `src/meta_harney/abstractions/compaction.py`:

```python
"""Compaction abstraction: CompactionStrategy Protocol.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.10.
"""
from __future__ import annotations

from typing import Protocol

from meta_harney.abstractions._types import Message


class CompactionStrategy(Protocol):
    """Decides when to compact a session's messages and how.

    The engine asks `should_compact()` once per loop iteration when
    `current_tokens > window_limit * 0.8` (default heuristic, configurable).
    If True, the engine calls `compact()` and replaces session.messages
    with the returned list.
    """

    async def should_compact(
        self,
        session_id: str,
        current_tokens: int,
        window_limit: int,
    ) -> bool: ...

    async def compact(self, session_id: str) -> list[Message]:
        """Return the new compacted message list."""
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/abstractions/test_compaction.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/abstractions/compaction.py tests/unit/abstractions/test_compaction.py
git commit -m "feat(abstractions): CompactionStrategy Protocol

Two async methods: should_compact(session_id, current_tokens, window_limit)
-> bool and compact(session_id) -> list[Message]. Default implementation
SummarizationCompactor lands in Task 24.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 18: Builtin Permission Resolvers (allow_all, deny_all)

**Files:**
- Create: `src/meta_harney/builtin/permission/allow_all.py`
- Create: `src/meta_harney/builtin/permission/deny_all.py`
- Test: `tests/unit/builtin/test_allow_all.py`
- Test: `tests/unit/builtin/test_deny_all.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/builtin/test_allow_all.py`:

```python
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver


async def test_allow_all_returns_allow():
    r = AllowAllPermissionResolver()
    inv = ToolInvocation(name="any", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.verdict == "allow"
    assert d.reason is None
```

Create `tests/unit/builtin/test_deny_all.py`:

```python
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver


async def test_deny_all_returns_deny():
    r = DenyAllPermissionResolver()
    inv = ToolInvocation(name="any", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.verdict == "deny"
    assert "default deny" in d.reason.lower()


async def test_deny_all_custom_reason():
    r = DenyAllPermissionResolver(reason="policy: deny by default")
    inv = ToolInvocation(name="x", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.reason == "policy: deny by default"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/builtin/test_allow_all.py tests/unit/builtin/test_deny_all.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `allow_all.py`**

Create `src/meta_harney/builtin/permission/allow_all.py`:

```python
"""AllowAllPermissionResolver — the framework default.

WARNING: This resolver allows EVERY tool invocation. Business apps SHOULD
replace it with a policy-aware implementation before going to production.
"""
from __future__ import annotations

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation


class AllowAllPermissionResolver:
    """Allows every tool invocation unconditionally."""

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision:
        return PermissionDecision(verdict="allow")
```

- [ ] **Step 4: Write `deny_all.py`**

Create `src/meta_harney/builtin/permission/deny_all.py`:

```python
"""DenyAllPermissionResolver — secure-by-default option.

Useful in tests and as a starting point: deny everything, then allow
specific tools via custom resolver logic.
"""
from __future__ import annotations

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation


class DenyAllPermissionResolver:
    """Denies every tool invocation."""

    def __init__(self, reason: str = "default deny"):
        self._reason = reason

    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision:
        return PermissionDecision(verdict="deny", reason=self._reason)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/builtin/test_allow_all.py tests/unit/builtin/test_deny_all.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/builtin/permission/ tests/unit/builtin/test_allow_all.py tests/unit/builtin/test_deny_all.py
git commit -m "feat(builtin): AllowAllPermissionResolver + DenyAllPermissionResolver

AllowAllPermissionResolver: framework default — every invocation allowed.
DenyAllPermissionResolver: secure default — every invocation denied with
configurable reason.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 19: Builtin Trace Sinks (NullSink, JsonlSink)

**Files:**
- Create: `src/meta_harney/builtin/trace/null_sink.py`
- Create: `src/meta_harney/builtin/trace/jsonl_sink.py`
- Test: `tests/unit/builtin/test_null_sink.py`
- Test: `tests/unit/builtin/test_jsonl_sink.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/builtin/test_null_sink.py`:

```python
from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.builtin.trace.null_sink import NullSink


async def test_null_sink_noop():
    sink = NullSink()
    ev = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s",
        kind="any", span_id="x", payload={},
    )
    # Should not raise; should do nothing.
    await sink.emit(ev)
    await sink.flush()
```

Create `tests/unit/builtin/test_jsonl_sink.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.builtin.trace.jsonl_sink import JsonlSink


async def test_jsonl_sink_writes_after_flush(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s1",
        kind="tool.invoked", span_id="x", payload={"a": 1},
    )
    await sink.emit(ev)
    # Not yet written to disk (buffered)
    assert not log.exists() or log.read_text() == ""
    await sink.flush()
    assert log.exists()
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == "tool.invoked"
    assert parsed["payload"] == {"a": 1}


async def test_jsonl_sink_append_across_flushes(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    for i in range(3):
        await sink.emit(TraceEvent(
            ts=datetime.now(timezone.utc), session_id="s",
            kind="x.y", span_id=str(i), payload={},
        ))
    await sink.flush()
    # second batch
    for i in range(3, 5):
        await sink.emit(TraceEvent(
            ts=datetime.now(timezone.utc), session_id="s",
            kind="x.y", span_id=str(i), payload={},
        ))
    await sink.flush()
    assert len(log.read_text().splitlines()) == 5


async def test_jsonl_sink_flush_with_empty_buffer_noop(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    await sink.flush()  # nothing to write
    assert not log.exists()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/builtin/test_null_sink.py tests/unit/builtin/test_jsonl_sink.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `null_sink.py`**

Create `src/meta_harney/builtin/trace/null_sink.py`:

```python
"""NullSink — discards all events. The framework default."""
from __future__ import annotations

from meta_harney.abstractions.trace import TraceEvent


class NullSink:
    """No-op sink. Useful as default; tests use it when trace is irrelevant."""

    async def emit(self, event: TraceEvent) -> None:
        return None

    async def flush(self) -> None:
        return None
```

- [ ] **Step 4: Write `jsonl_sink.py`**

Create `src/meta_harney/builtin/trace/jsonl_sink.py`:

```python
"""JsonlSink — buffers events, writes JSON-Lines to disk on flush().

Suitable for development; production should use a buffered async sink
that ships to APM/Loki/etc.
"""
from __future__ import annotations

from pathlib import Path

from meta_harney.abstractions.trace import TraceEvent


class JsonlSink:
    """Append-only JSON-Lines sink."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._buf: list[str] = []

    async def emit(self, event: TraceEvent) -> None:
        self._buf.append(event.model_dump_json())

    async def flush(self) -> None:
        if not self._buf:
            return
        with self.path.open("a", encoding="utf-8") as f:
            for line in self._buf:
                f.write(line)
                f.write("\n")
        self._buf.clear()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/builtin/test_null_sink.py tests/unit/builtin/test_jsonl_sink.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/meta_harney/builtin/trace/ tests/unit/builtin/test_null_sink.py tests/unit/builtin/test_jsonl_sink.py
git commit -m "feat(builtin): NullSink + JsonlSink

NullSink discards everything (framework default).
JsonlSink buffers events and writes JSON-Lines to disk on flush();
auto-creates parent directories.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 20: Builtin SessionStores (MemorySessionStore + FileSessionStore)

**Files:**
- Create: `src/meta_harney/builtin/session/memory_store.py`
- Create: `src/meta_harney/builtin/session/file_store.py`

(Tests will use the contract suite written in Task 23; for now write basic smoke tests in Task 21 below.)

- [ ] **Step 1: Write `memory_store.py`**

Create `src/meta_harney/builtin/session/memory_store.py`:

```python
"""MemorySessionStore — in-process dict-backed store.

Suitable for tests, single-process demos, and as the default when no
persistent store is configured. NOT suitable for production: all state
lost on process exit.
"""
from __future__ import annotations

import asyncio
from typing import Any

from meta_harney.abstractions.session import Session
from meta_harney.errors import SessionConflictError


class MemorySessionStore:
    """In-memory SessionStore with optimistic locking and tenant filtering."""

    def __init__(self) -> None:
        self._data: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None:
        async with self._lock:
            s = self._data.get(session_id)
            if s is None:
                return None
            if tenant_id is not None and s.tenant_id != tenant_id:
                return None
            return s.model_copy(deep=True)

    async def save(self, session: Session) -> None:
        async with self._lock:
            existing = self._data.get(session.id)
            if existing is not None and existing.version != session.version:
                raise SessionConflictError(
                    session_id=session.id,
                    expected_version=session.version,
                    found_version=existing.version,
                )
            session.version += 1
            self._data[session.id] = session.model_copy(deep=True)

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]:
        async with self._lock:
            results = list(self._data.values())
        if tenant_id is not None:
            results = [s for s in results if s.tenant_id == tenant_id]
        if filter:
            for k, v in filter.items():
                results = [s for s in results if s.attributes.get(k) == v]
        return [s.model_copy(deep=True) for s in results]

    async def delete(self, session_id: str) -> None:
        async with self._lock:
            self._data.pop(session_id, None)
```

- [ ] **Step 2: Write `file_store.py`**

Create `src/meta_harney/builtin/session/file_store.py`:

```python
"""FileSessionStore — one JSON file per session.

Per-session asyncio.Lock prevents intra-process concurrent writes from
corrupting the same file. Cross-process safety is NOT guaranteed —
use a real database for that.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from meta_harney.abstractions.session import Session
from meta_harney.errors import SessionConflictError, SessionStoreError


class FileSessionStore:
    """File-backed SessionStore: one JSON file per session under `root`."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _path(self, session_id: str) -> Path:
        # Defensive: prevent traversal via session_id
        if "/" in session_id or ".." in session_id:
            raise SessionStoreError(f"invalid session_id: {session_id!r}")
        return self.root / f"{session_id}.json"

    async def load(
        self,
        session_id: str,
        *,
        tenant_id: str | None = None,
    ) -> Session | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            raise SessionStoreError(f"failed to read {path}: {e}") from e
        s = Session.model_validate_json(raw)
        if tenant_id is not None and s.tenant_id != tenant_id:
            return None
        return s

    async def save(self, session: Session) -> None:
        path = self._path(session.id)
        async with self._locks[session.id]:
            if path.exists():
                existing = Session.model_validate_json(path.read_text(encoding="utf-8"))
                if existing.version != session.version:
                    raise SessionConflictError(
                        session_id=session.id,
                        expected_version=session.version,
                        found_version=existing.version,
                    )
            session.version += 1
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(session.model_dump_json(), encoding="utf-8")
            tmp.replace(path)  # atomic on POSIX

    async def list(
        self,
        *,
        tenant_id: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> list[Session]:
        results: list[Session] = []
        for p in self.root.glob("*.json"):
            try:
                s = Session.model_validate_json(p.read_text(encoding="utf-8"))
            except Exception:
                continue  # skip corrupt
            if tenant_id is not None and s.tenant_id != tenant_id:
                continue
            if filter:
                if not all(s.attributes.get(k) == v for k, v in filter.items()):
                    continue
            results.append(s)
        return results

    async def delete(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
```

- [ ] **Step 3: Smoke-test the stores import**

```bash
python -c "from meta_harney.builtin.session.memory_store import MemorySessionStore; print('mem OK')"
python -c "from meta_harney.builtin.session.file_store import FileSessionStore; print('file OK')"
```
Expected: `mem OK` then `file OK`.

- [ ] **Step 4: Commit**

```bash
git add src/meta_harney/builtin/session/
git commit -m "feat(builtin): MemorySessionStore + FileSessionStore

MemorySessionStore: in-process dict with asyncio.Lock + optimistic
locking + tenant filtering + attribute filtering.
FileSessionStore: one JSON file per session under root dir;
per-session asyncio.Lock; atomic rename via .tmp; rejects path
traversal via session_id sanity check.

Contract tests follow in Task 23.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 21: Builtin Prompt Builder (MinimalPromptBuilder)

**Files:**
- Create: `src/meta_harney/builtin/prompt/minimal.py`
- Test: `tests/unit/builtin/test_minimal_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/builtin/test_minimal_prompt.py`:

```python
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore


async def test_default_system_prompt():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(session_store=store)
    sp = await builder.build_system_prompt("missing")
    assert "helpful AI assistant" in sp.lower()


async def test_custom_system_prompt():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(
        session_store=store,
        system_prompt="You are a billing specialist.",
    )
    sp = await builder.build_system_prompt("any")
    assert sp == "You are a billing specialist."


async def test_context_messages_from_session():
    store = MemorySessionStore()
    s = Session(
        id="s1",
        created_at=datetime.now(timezone.utc),
        messages=[
            Message(role="user", content=[TextBlock(text="hello")]),
            Message(role="assistant", content=[TextBlock(text="hi there")]),
        ],
    )
    await store.save(s)
    builder = MinimalPromptBuilder(session_store=store)
    msgs = await builder.build_context_messages("s1")
    assert len(msgs) == 2
    assert msgs[0].content[0].text == "hello"


async def test_context_messages_empty_for_missing_session():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(session_store=store)
    msgs = await builder.build_context_messages("nonexistent")
    assert msgs == []
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/builtin/test_minimal_prompt.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `minimal.py`**

Create `src/meta_harney/builtin/prompt/minimal.py`:

```python
"""MinimalPromptBuilder — domain-agnostic default.

System prompt is a single configurable string; context messages are
the session's full message history. No coding-context assumptions.
"""
from __future__ import annotations

from meta_harney.abstractions._types import Message
from meta_harney.abstractions.session import SessionStore


DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class MinimalPromptBuilder:
    """Minimal, domain-neutral PromptBuilder."""

    def __init__(
        self,
        session_store: SessionStore,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._session_store = session_store
        self._system_prompt = system_prompt

    async def build_system_prompt(self, session_id: str) -> str:
        return self._system_prompt

    async def build_context_messages(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None:
            return []
        return list(s.messages)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/builtin/test_minimal_prompt.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/builtin/prompt/ tests/unit/builtin/test_minimal_prompt.py
git commit -m "feat(builtin): MinimalPromptBuilder

Domain-agnostic prompt builder: single configurable system prompt
(default 'You are a helpful AI assistant.') + session.messages as
context. Loads session via injected SessionStore.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 22: Builtin Compactor (SummarizationCompactor)

**Files:**
- Create: `src/meta_harney/builtin/compaction/summarization.py`
- Test: `tests/unit/builtin/test_summarization.py`

**Design note:** SummarizationCompactor takes a `summarize_fn: Callable[[list[Message]], Awaitable[str]]` rather than an LLM provider directly. This keeps Phase 1 decoupled from the provider layer (which lands in Phase 2).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/builtin/test_summarization.py`:

```python
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.compaction.summarization import SummarizationCompactor
from meta_harney.builtin.session.memory_store import MemorySessionStore


def _msg(role, text):
    return Message(role=role, content=[TextBlock(text=text)])


async def _fake_summarize(messages):
    return f"Summary of {len(messages)} messages."


async def test_should_compact_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(session_store=store, summarize_fn=_fake_summarize)
    assert await c.should_compact("s", current_tokens=8001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=7999, window_limit=10000)


async def test_should_compact_custom_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        trigger_ratio=0.5,
    )
    assert await c.should_compact("s", current_tokens=5001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=4999, window_limit=10000)


async def test_compact_preserves_recent_and_system():
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS")] + [_msg("user", f"u-{i}") for i in range(20)]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        keep_recent=5,
    )
    new = await c.compact("s1")
    # system message preserved, summary message inserted, last 5 user msgs preserved
    assert new[0].role == "system"
    assert "SYS" in new[0].content[0].text
    # next is a summary message
    assert new[1].role == "system"
    assert "Summary" in new[1].content[0].text
    # then 5 recent
    assert len(new) == 1 + 1 + 5
    assert new[-1].content[0].text == "u-19"


async def test_compact_with_only_system_and_few_messages():
    """If history is short, no middle to summarize."""
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS"), _msg("user", "hello")]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store, summarize_fn=_fake_summarize, keep_recent=10,
    )
    new = await c.compact("s1")
    # Nothing to summarize — return as-is
    assert len(new) == 2
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/builtin/test_summarization.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write `summarization.py`**

Create `src/meta_harney/builtin/compaction/summarization.py`:

```python
"""SummarizationCompactor — preserves system + recent N, summarizes the middle.

Decoupled from the provider layer: caller injects a `summarize_fn` that
turns a list of messages into a summary string. In Phase 2, the runtime
will wire this fn to call the configured LLM provider.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import SessionStore


SummarizeFn = Callable[[list[Message]], Awaitable[str]]


class SummarizationCompactor:
    """Compacts the middle of session.messages into a single summary message.

    Algorithm:
      1. Compute (system_msgs, middle_msgs, recent_msgs) where recent_msgs
         is the last `keep_recent` messages and system_msgs are all role==system
         messages before middle.
      2. If middle_msgs is empty, return messages unchanged.
      3. Call summarize_fn(middle_msgs) -> str.
      4. Return system_msgs + [summary_msg] + recent_msgs.
    """

    def __init__(
        self,
        session_store: SessionStore,
        summarize_fn: SummarizeFn,
        keep_recent: int = 10,
        trigger_ratio: float = 0.8,
    ) -> None:
        self._session_store = session_store
        self._summarize_fn = summarize_fn
        self._keep_recent = keep_recent
        self._trigger_ratio = trigger_ratio

    async def should_compact(
        self,
        session_id: str,
        current_tokens: int,
        window_limit: int,
    ) -> bool:
        return current_tokens > window_limit * self._trigger_ratio

    async def compact(self, session_id: str) -> list[Message]:
        s = await self._session_store.load(session_id)
        if s is None or not s.messages:
            return []
        msgs = list(s.messages)

        # Partition: leading system, middle, recent
        system_msgs: list[Message] = []
        i = 0
        while i < len(msgs) and msgs[i].role == "system":
            system_msgs.append(msgs[i])
            i += 1
        rest = msgs[i:]

        if len(rest) <= self._keep_recent:
            return msgs  # nothing to summarize

        recent = rest[-self._keep_recent :]
        middle = rest[: -self._keep_recent]

        summary_text = await self._summarize_fn(middle)
        summary_msg = Message(
            role="system",
            content=[TextBlock(text=summary_text)],
        )
        return [*system_msgs, summary_msg, *recent]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/builtin/test_summarization.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/meta_harney/builtin/compaction/ tests/unit/builtin/test_summarization.py
git commit -m "feat(builtin): SummarizationCompactor

Preserves leading system messages + last keep_recent (default 10),
summarizes the middle into a single role=system message via injected
summarize_fn. trigger_ratio (default 0.8) controls should_compact
threshold. Decoupled from provider layer for Phase 1 isolation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 23: Contract Test Suite — SessionStore

**Files:**
- Create: `tests/contracts/session_store.py`
- Modify: `tests/unit/builtin/test_memory_store.py` (rename existing or create new)
- Modify: `tests/unit/builtin/test_file_store.py`

- [ ] **Step 1: Write the contract base class**

Create `tests/contracts/session_store.py`:

```python
"""Reusable contract test suite for SessionStore implementations.

Any concrete SessionStore (builtin or business-supplied) should subclass
this and provide `make_store()`. The subclass automatically inherits all
contract checks.
"""
from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import datetime, timezone

import pytest

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.errors import SessionConflictError


def _make_session(
    *,
    id: str = "s1",
    tenant_id: str | None = None,
    user_id: str | None = None,
    version: int = 0,
) -> Session:
    return Session(
        id=id,
        tenant_id=tenant_id,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        version=version,
    )


class SessionStoreContract:
    """Contract tests every SessionStore implementation must pass.

    Subclass and implement `make_store()`. Concrete subclasses must be
    valid pytest test classes (start with `Test...`).
    """

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    async def test_load_returns_none_for_missing(self):
        store = self.make_store()
        assert await store.load("does-not-exist") is None

    async def test_save_then_load_roundtrip(self):
        store = self.make_store()
        s = _make_session(id="s1", tenant_id="acme")
        s.attributes["customer_id"] = "C-1"
        await store.save(s)
        loaded = await store.load("s1")
        assert loaded is not None
        assert loaded.id == "s1"
        assert loaded.tenant_id == "acme"
        assert loaded.attributes["customer_id"] == "C-1"

    async def test_save_increments_version(self):
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)
        # The stored copy has version 1
        loaded = await store.load(s.id)
        assert loaded is not None
        assert loaded.version == 1

    async def test_save_with_stale_version_raises_conflict(self):
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)  # stored as version 1
        stale = _make_session(version=0)  # caller still thinks v0
        with pytest.raises(SessionConflictError):
            await store.save(stale)

    async def test_save_then_save_with_fresh_version_succeeds(self):
        store = self.make_store()
        s = _make_session(version=0)
        await store.save(s)  # version 1
        s2 = _make_session(version=1)  # caller knows current is v1
        s2.messages.append(Message(role="user", content=[TextBlock(text="hi")]))
        await store.save(s2)  # version 2
        loaded = await store.load("s1")
        assert loaded.version == 2
        assert len(loaded.messages) == 1

    async def test_tenant_filter_load_isolation(self):
        store = self.make_store()
        s = _make_session(id="s1", tenant_id="acme")
        await store.save(s)
        assert (await store.load("s1", tenant_id="acme")) is not None
        assert (await store.load("s1", tenant_id="other")) is None

    async def test_tenant_filter_list(self):
        store = self.make_store()
        await store.save(_make_session(id="a", tenant_id="acme"))
        await store.save(_make_session(id="b", tenant_id="other"))
        await store.save(_make_session(id="c", tenant_id="acme"))
        acme = await store.list(tenant_id="acme")
        ids = sorted(s.id for s in acme)
        assert ids == ["a", "c"]

    async def test_list_no_filter_returns_all(self):
        store = self.make_store()
        await store.save(_make_session(id="a"))
        await store.save(_make_session(id="b"))
        all_ = await store.list()
        assert len(all_) == 2

    async def test_delete_then_load_returns_none(self):
        store = self.make_store()
        await store.save(_make_session(id="s1"))
        await store.delete("s1")
        assert await store.load("s1") is None

    async def test_delete_missing_is_idempotent(self):
        store = self.make_store()
        await store.delete("never-existed")  # must not raise

    async def test_load_returns_independent_copy(self):
        """Mutating returned Session must not corrupt the stored copy."""
        store = self.make_store()
        s = _make_session(id="s1")
        await store.save(s)
        loaded = await store.load("s1")
        assert loaded is not None
        loaded.attributes["leak"] = "bad"
        loaded2 = await store.load("s1")
        assert "leak" not in loaded2.attributes
```

- [ ] **Step 2: Rewrite `test_memory_store.py` to use the contract**

Replace `tests/unit/builtin/test_memory_store.py` with:

```python
"""MemorySessionStore: contract conformance."""
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.session_store import SessionStoreContract


class TestMemorySessionStore(SessionStoreContract):
    def make_store(self):
        return MemorySessionStore()
```

(If `test_memory_store.py` already exists from earlier tasks, overwrite.)

- [ ] **Step 3: Write `test_file_store.py`**

Create `tests/unit/builtin/test_file_store.py`:

```python
"""FileSessionStore: contract conformance + file-specific behavior."""
import pytest

from meta_harney.builtin.session.file_store import FileSessionStore
from meta_harney.errors import SessionStoreError
from tests.contracts.session_store import SessionStoreContract


class TestFileSessionStore(SessionStoreContract):
    @pytest.fixture(autouse=True)
    def _tmp_path(self, tmp_path):
        self._root = tmp_path

    def make_store(self):
        return FileSessionStore(self._root)


async def test_file_store_rejects_path_traversal(tmp_path):
    store = FileSessionStore(tmp_path)
    with pytest.raises(SessionStoreError):
        await store.load("../etc/passwd")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/builtin/test_memory_store.py tests/unit/builtin/test_file_store.py -v
```
Expected: all PASS (both stores satisfy the contract; FileStore extra path-traversal check passes).

- [ ] **Step 5: Commit**

```bash
git add tests/contracts/session_store.py tests/unit/builtin/test_memory_store.py tests/unit/builtin/test_file_store.py
git commit -m "test: SessionStoreContract + apply to Memory/FileSessionStore

Reusable contract suite: load/save roundtrip, optimistic locking
(version increment + stale rejection), tenant isolation (load + list),
filter list, delete idempotence, independent-copy semantics.
Memory and File stores both pass — 10 contract checks each.

Business stores will get the same 10 checks for free by subclassing.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 24: Contract Test Suite — PermissionResolver

**Files:**
- Create: `tests/contracts/permission_resolver.py`
- Modify: `tests/unit/builtin/test_allow_all.py`
- Modify: `tests/unit/builtin/test_deny_all.py`

- [ ] **Step 1: Write the contract base class**

Create `tests/contracts/permission_resolver.py`:

```python
"""Contract tests for PermissionResolver implementations."""
from __future__ import annotations

from abc import abstractmethod
from typing import Literal

from meta_harney.abstractions.permission import PermissionResolver
from meta_harney.abstractions.tool import ToolInvocation


class PermissionResolverContract:
    """Contract tests every PermissionResolver must pass.

    `expected_verdict` lets the subclass declare which verdict the
    resolver should produce so we can write generic assertions.
    """

    @abstractmethod
    def make_resolver(self) -> PermissionResolver: ...

    @abstractmethod
    def expected_verdict(self) -> Literal["allow", "deny", "ask"]: ...

    async def test_returns_expected_verdict(self):
        resolver = self.make_resolver()
        inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
        d = await resolver.resolve(inv, "s")
        assert d.verdict == self.expected_verdict()

    async def test_verdict_is_consistent_across_calls(self):
        resolver = self.make_resolver()
        inv1 = ToolInvocation(name="a", args={"x": 1}, invocation_id="i1", session_id="s1")
        inv2 = ToolInvocation(name="b", args={"y": 2}, invocation_id="i2", session_id="s2")
        d1 = await resolver.resolve(inv1, "s1")
        d2 = await resolver.resolve(inv2, "s2")
        assert d1.verdict == d2.verdict == self.expected_verdict()
```

- [ ] **Step 2: Apply contract to AllowAll**

Replace `tests/unit/builtin/test_allow_all.py`:

```python
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
from tests.contracts.permission_resolver import PermissionResolverContract


class TestAllowAll(PermissionResolverContract):
    def make_resolver(self):
        return AllowAllPermissionResolver()

    def expected_verdict(self):
        return "allow"


async def test_allow_all_no_reason():
    r = AllowAllPermissionResolver()
    inv = ToolInvocation(name="t", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.reason is None
```

- [ ] **Step 3: Apply contract to DenyAll**

Replace `tests/unit/builtin/test_deny_all.py`:

```python
from meta_harney.abstractions.tool import ToolInvocation
from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
from tests.contracts.permission_resolver import PermissionResolverContract


class TestDenyAll(PermissionResolverContract):
    def make_resolver(self):
        return DenyAllPermissionResolver()

    def expected_verdict(self):
        return "deny"


async def test_deny_all_custom_reason():
    r = DenyAllPermissionResolver(reason="policy: deny by default")
    inv = ToolInvocation(name="x", args={}, invocation_id="i", session_id="s")
    d = await r.resolve(inv, "s")
    assert d.reason == "policy: deny by default"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/builtin/test_allow_all.py tests/unit/builtin/test_deny_all.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/contracts/permission_resolver.py tests/unit/builtin/test_allow_all.py tests/unit/builtin/test_deny_all.py
git commit -m "test: PermissionResolverContract + apply to AllowAll/DenyAll

Contract checks: returns_expected_verdict + verdict_is_consistent.
Subclass declares `expected_verdict()`; the suite uses it for assertions.
AllowAll/DenyAll both pass; reason-specific tests retained inline.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 25: Contract Test Suite — TraceSink

**Files:**
- Create: `tests/contracts/trace_sink.py`
- Modify: `tests/unit/builtin/test_null_sink.py`
- Modify: `tests/unit/builtin/test_jsonl_sink.py`

- [ ] **Step 1: Write the contract**

Create `tests/contracts/trace_sink.py`:

```python
"""Contract tests for TraceSink implementations."""
from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions.trace import TraceEvent, TraceSink


def _event(kind: str = "test.kind", span_id: str = "x") -> TraceEvent:
    return TraceEvent(
        ts=datetime.now(timezone.utc),
        session_id="s1",
        kind=kind,
        span_id=span_id,
        payload={},
    )


class TraceSinkContract:
    """Contract tests every TraceSink must pass."""

    @abstractmethod
    def make_sink(self) -> TraceSink: ...

    async def test_emit_does_not_raise(self):
        sink = self.make_sink()
        await sink.emit(_event())  # must complete without exception

    async def test_flush_does_not_raise(self):
        sink = self.make_sink()
        await sink.flush()  # idempotent with empty buffer

    async def test_emit_many_then_flush(self):
        sink = self.make_sink()
        for i in range(50):
            await sink.emit(_event(span_id=str(i)))
        await sink.flush()  # must not raise

    async def test_concurrent_emit_safe(self):
        sink = self.make_sink()

        async def burst():
            for i in range(10):
                await sink.emit(_event(span_id=f"burst-{i}"))

        await asyncio.gather(*(burst() for _ in range(5)))
        await sink.flush()
```

- [ ] **Step 2: Apply to NullSink**

Replace `tests/unit/builtin/test_null_sink.py`:

```python
from meta_harney.builtin.trace.null_sink import NullSink
from tests.contracts.trace_sink import TraceSinkContract


class TestNullSink(TraceSinkContract):
    def make_sink(self):
        return NullSink()
```

- [ ] **Step 3: Apply to JsonlSink**

Replace `tests/unit/builtin/test_jsonl_sink.py`:

```python
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta_harney.abstractions.trace import TraceEvent
from meta_harney.builtin.trace.jsonl_sink import JsonlSink
from tests.contracts.trace_sink import TraceSinkContract


class TestJsonlSink(TraceSinkContract):
    @pytest.fixture(autouse=True)
    def _tmp(self, tmp_path):
        self._path = tmp_path / "trace.jsonl"

    def make_sink(self):
        return JsonlSink(self._path)


# JsonlSink-specific behavior checks:

async def test_jsonl_writes_after_flush(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    ev = TraceEvent(
        ts=datetime.now(timezone.utc), session_id="s1",
        kind="tool.invoked", span_id="x", payload={"a": 1},
    )
    await sink.emit(ev)
    assert not log.exists() or log.read_text() == ""
    await sink.flush()
    assert log.exists()
    parsed = json.loads(log.read_text().strip())
    assert parsed["kind"] == "tool.invoked"
    assert parsed["payload"] == {"a": 1}


async def test_jsonl_appends_across_flushes(tmp_path: Path):
    log = tmp_path / "trace.jsonl"
    sink = JsonlSink(log)
    for i in range(3):
        await sink.emit(TraceEvent(
            ts=datetime.now(timezone.utc), session_id="s",
            kind="x.y", span_id=str(i), payload={},
        ))
    await sink.flush()
    for i in range(3, 5):
        await sink.emit(TraceEvent(
            ts=datetime.now(timezone.utc), session_id="s",
            kind="x.y", span_id=str(i), payload={},
        ))
    await sink.flush()
    assert len(log.read_text().splitlines()) == 5
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/builtin/test_null_sink.py tests/unit/builtin/test_jsonl_sink.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/contracts/trace_sink.py tests/unit/builtin/test_null_sink.py tests/unit/builtin/test_jsonl_sink.py
git commit -m "test: TraceSinkContract + apply to Null/JsonlSink

Contract checks: emit doesn't raise, flush idempotent on empty buffer,
50-event burst + flush, concurrent emit safety (5 concurrent bursts of 10).
JsonlSink retains specific assertions for buffering + appending.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 26: Contract Test Suite — PromptBuilder + CompactionStrategy

**Files:**
- Create: `tests/contracts/prompt_builder.py`
- Create: `tests/contracts/compaction_strategy.py`
- Modify: `tests/unit/builtin/test_minimal_prompt.py`
- Modify: `tests/unit/builtin/test_summarization.py`

- [ ] **Step 1: Write PromptBuilderContract**

Create `tests/contracts/prompt_builder.py`:

```python
"""Contract tests for PromptBuilder implementations."""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore


class PromptBuilderContract:
    """Contract tests every PromptBuilder must pass.

    Subclass provides:
      - make_builder(store) -> PromptBuilder
      - make_store() -> SessionStore
    """

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    @abstractmethod
    def make_builder(self, store: SessionStore) -> PromptBuilder: ...

    async def test_system_prompt_returns_string(self):
        builder = self.make_builder(self.make_store())
        sp = await builder.build_system_prompt("any-session-id")
        assert isinstance(sp, str)
        assert sp  # non-empty

    async def test_context_messages_empty_for_missing_session(self):
        builder = self.make_builder(self.make_store())
        msgs = await builder.build_context_messages("nonexistent")
        assert msgs == []

    async def test_context_messages_for_known_session(self):
        store = self.make_store()
        s = Session(
            id="s1",
            created_at=datetime.now(timezone.utc),
            messages=[Message(role="user", content=[TextBlock(text="hi")])],
        )
        await store.save(s)
        builder = self.make_builder(store)
        msgs = await builder.build_context_messages("s1")
        assert isinstance(msgs, list)
        assert all(isinstance(m, Message) for m in msgs)
```

- [ ] **Step 2: Write CompactionStrategyContract**

Create `tests/contracts/compaction_strategy.py`:

```python
"""Contract tests for CompactionStrategy implementations."""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.session import Session, SessionStore


class CompactionStrategyContract:
    """Contract tests every CompactionStrategy must pass."""

    @abstractmethod
    def make_store(self) -> SessionStore: ...

    @abstractmethod
    def make_strategy(self, store: SessionStore) -> CompactionStrategy: ...

    async def test_should_compact_returns_bool(self):
        strat = self.make_strategy(self.make_store())
        v = await strat.should_compact("s", current_tokens=100, window_limit=1000)
        assert isinstance(v, bool)

    async def test_compact_returns_list_of_messages(self):
        store = self.make_store()
        s = Session(
            id="s1",
            created_at=datetime.now(timezone.utc),
            messages=[Message(role="user", content=[TextBlock(text="x")])],
        )
        await store.save(s)
        strat = self.make_strategy(store)
        new = await strat.compact("s1")
        assert isinstance(new, list)
        assert all(isinstance(m, Message) for m in new)

    async def test_compact_missing_session_returns_empty(self):
        strat = self.make_strategy(self.make_store())
        new = await strat.compact("nonexistent")
        assert new == []
```

- [ ] **Step 3: Apply PromptBuilderContract to MinimalPromptBuilder**

Replace `tests/unit/builtin/test_minimal_prompt.py`:

```python
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.prompt_builder import PromptBuilderContract


class TestMinimalPromptBuilder(PromptBuilderContract):
    def make_store(self):
        return MemorySessionStore()

    def make_builder(self, store):
        return MinimalPromptBuilder(session_store=store)


# Builder-specific tests:

async def test_default_system_prompt_content():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(session_store=store)
    sp = await builder.build_system_prompt("any")
    assert "helpful AI assistant" in sp.lower()


async def test_custom_system_prompt_override():
    store = MemorySessionStore()
    builder = MinimalPromptBuilder(
        session_store=store,
        system_prompt="You are a billing specialist.",
    )
    sp = await builder.build_system_prompt("any")
    assert sp == "You are a billing specialist."
```

- [ ] **Step 4: Apply CompactionStrategyContract to SummarizationCompactor**

Replace `tests/unit/builtin/test_summarization.py`:

```python
from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.session import Session
from meta_harney.builtin.compaction.summarization import SummarizationCompactor
from meta_harney.builtin.session.memory_store import MemorySessionStore
from tests.contracts.compaction_strategy import CompactionStrategyContract


async def _fake_summarize(messages):
    return f"Summary of {len(messages)} messages."


class TestSummarizationCompactor(CompactionStrategyContract):
    def make_store(self):
        return MemorySessionStore()

    def make_strategy(self, store):
        return SummarizationCompactor(
            session_store=store,
            summarize_fn=_fake_summarize,
            keep_recent=10,
        )


# Strategy-specific tests:

def _msg(role, text):
    return Message(role=role, content=[TextBlock(text=text)])


async def test_should_compact_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(session_store=store, summarize_fn=_fake_summarize)
    assert await c.should_compact("s", current_tokens=8001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=7999, window_limit=10000)


async def test_should_compact_custom_threshold():
    store = MemorySessionStore()
    c = SummarizationCompactor(
        session_store=store,
        summarize_fn=_fake_summarize,
        trigger_ratio=0.5,
    )
    assert await c.should_compact("s", current_tokens=5001, window_limit=10000)
    assert not await c.should_compact("s", current_tokens=4999, window_limit=10000)


async def test_compact_preserves_recent_and_system():
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS")] + [_msg("user", f"u-{i}") for i in range(20)]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store, summarize_fn=_fake_summarize, keep_recent=5,
    )
    new = await c.compact("s1")
    assert new[0].role == "system"
    assert "SYS" in new[0].content[0].text
    assert new[1].role == "system"
    assert "Summary" in new[1].content[0].text
    assert len(new) == 1 + 1 + 5
    assert new[-1].content[0].text == "u-19"


async def test_compact_short_history_unchanged():
    store = MemorySessionStore()
    msgs = [_msg("system", "SYS"), _msg("user", "hello")]
    s = Session(id="s1", created_at=datetime.now(timezone.utc), messages=msgs)
    await store.save(s)
    c = SummarizationCompactor(
        session_store=store, summarize_fn=_fake_summarize, keep_recent=10,
    )
    new = await c.compact("s1")
    assert len(new) == 2
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/builtin/test_minimal_prompt.py tests/unit/builtin/test_summarization.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/contracts/prompt_builder.py tests/contracts/compaction_strategy.py tests/unit/builtin/test_minimal_prompt.py tests/unit/builtin/test_summarization.py
git commit -m "test: PromptBuilderContract + CompactionStrategyContract

PromptBuilderContract: system_prompt is string, context_messages empty
for missing session, context_messages returns list[Message] for known.
CompactionStrategyContract: should_compact returns bool, compact returns
list[Message], compact on missing session returns []. Both applied to
MinimalPromptBuilder and SummarizationCompactor respectively.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 27: Public API Surface (`__init__.py`)

**Files:**
- Modify: `src/meta_harney/__init__.py`
- Modify: `src/meta_harney/abstractions/__init__.py`
- Modify: `src/meta_harney/builtin/__init__.py`
- Test: `tests/unit/test_public_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_public_api.py`:

```python
"""Verify the public API surface from `meta_harney` package root."""


def test_public_api_exports():
    import meta_harney as mh

    # Data contracts
    assert mh.Message
    assert mh.TextBlock
    assert mh.ImageBlock
    assert mh.ToolCallBlock
    assert mh.ToolResultBlock

    # Tool abstraction
    assert mh.BaseTool
    assert mh.ToolInvocation
    assert mh.ToolResult
    assert mh.ToolContext

    # Hook
    assert mh.BaseHook
    assert mh.HookEvent
    assert mh.HookDecision

    # Permission
    assert mh.PermissionResolver
    assert mh.PermissionDecision

    # Prompt
    assert mh.PromptBuilder

    # Task
    assert mh.BaseTask
    assert mh.TaskState

    # Session
    assert mh.Session
    assert mh.SessionStore

    # Trace
    assert mh.TraceEvent
    assert mh.TraceSink

    # MultiAgent
    assert mh.MultiAgentBackend
    assert mh.AgentSpec
    assert mh.SpawnHandle

    # Compaction
    assert mh.CompactionStrategy

    # Errors (root only at top level; full hierarchy under meta_harney.errors)
    assert mh.MetaHarneyError


def test_builtin_namespace():
    from meta_harney.builtin.permission.allow_all import AllowAllPermissionResolver
    from meta_harney.builtin.permission.deny_all import DenyAllPermissionResolver
    from meta_harney.builtin.session.memory_store import MemorySessionStore
    from meta_harney.builtin.session.file_store import FileSessionStore
    from meta_harney.builtin.trace.null_sink import NullSink
    from meta_harney.builtin.trace.jsonl_sink import JsonlSink
    from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder
    from meta_harney.builtin.compaction.summarization import SummarizationCompactor

    # smoke
    assert AllowAllPermissionResolver
    assert DenyAllPermissionResolver
    assert MemorySessionStore
    assert FileSessionStore
    assert NullSink
    assert JsonlSink
    assert MinimalPromptBuilder
    assert SummarizationCompactor
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/unit/test_public_api.py -v
```
Expected: AttributeError on first `mh.Message` access.

- [ ] **Step 3: Write `src/meta_harney/abstractions/__init__.py`**

Replace contents:

```python
"""meta_harney abstractions: the 9 core protocol/ABC interfaces.

See docs/superpowers/specs/2026-05-13-meta-harney-design.md §4.
"""
from meta_harney.abstractions._types import (
    ContentBlock,
    ImageBlock,
    Message,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from meta_harney.abstractions.compaction import CompactionStrategy
from meta_harney.abstractions.hook import (
    BaseHook,
    HookDecision,
    HookEvent,
    HookEventKind,
)
from meta_harney.abstractions.multi_agent import (
    AgentSpec,
    MultiAgentBackend,
    SpawnHandle,
)
from meta_harney.abstractions.permission import (
    PermissionDecision,
    PermissionResolver,
)
from meta_harney.abstractions.prompt import PromptBuilder
from meta_harney.abstractions.session import Session, SessionStore
from meta_harney.abstractions.task import BaseTask, TaskState
from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)
from meta_harney.abstractions.trace import TraceEvent, TraceSink

__all__ = [
    # types
    "ContentBlock",
    "ImageBlock",
    "Message",
    "TextBlock",
    "ToolCallBlock",
    "ToolResultBlock",
    # tool
    "BaseTool",
    "ToolContext",
    "ToolInvocation",
    "ToolResult",
    # hook
    "BaseHook",
    "HookDecision",
    "HookEvent",
    "HookEventKind",
    # permission
    "PermissionDecision",
    "PermissionResolver",
    # prompt
    "PromptBuilder",
    # task
    "BaseTask",
    "TaskState",
    # session
    "Session",
    "SessionStore",
    # trace
    "TraceEvent",
    "TraceSink",
    # multi-agent
    "AgentSpec",
    "MultiAgentBackend",
    "SpawnHandle",
    # compaction
    "CompactionStrategy",
]
```

- [ ] **Step 4: Write `src/meta_harney/__init__.py`**

Replace contents:

```python
"""meta_harney — domain-agnostic agent runtime SDK.

Phase 1 status: abstractions and builtin defaults only. Engine, providers,
runtime, and multi-agent backends land in subsequent phases.
"""
from meta_harney.abstractions import (
    AgentSpec,
    BaseHook,
    BaseTask,
    BaseTool,
    CompactionStrategy,
    ContentBlock,
    HookDecision,
    HookEvent,
    HookEventKind,
    ImageBlock,
    Message,
    MultiAgentBackend,
    PermissionDecision,
    PermissionResolver,
    PromptBuilder,
    Session,
    SessionStore,
    SpawnHandle,
    TaskState,
    TextBlock,
    ToolCallBlock,
    ToolContext,
    ToolInvocation,
    ToolResult,
    ToolResultBlock,
    TraceEvent,
    TraceSink,
)
from meta_harney.errors import MetaHarneyError

__version__ = "0.0.1"

__all__ = [
    "__version__",
    # data contracts
    "ContentBlock",
    "ImageBlock",
    "Message",
    "TextBlock",
    "ToolCallBlock",
    "ToolResultBlock",
    # tool
    "BaseTool",
    "ToolContext",
    "ToolInvocation",
    "ToolResult",
    # hook
    "BaseHook",
    "HookDecision",
    "HookEvent",
    "HookEventKind",
    # permission
    "PermissionDecision",
    "PermissionResolver",
    # prompt
    "PromptBuilder",
    # task
    "BaseTask",
    "TaskState",
    # session
    "Session",
    "SessionStore",
    # trace
    "TraceEvent",
    "TraceSink",
    # multi-agent
    "AgentSpec",
    "MultiAgentBackend",
    "SpawnHandle",
    # compaction
    "CompactionStrategy",
    # errors
    "MetaHarneyError",
]
```

- [ ] **Step 5: Verify builtin/__init__.py stays minimal**

Replace `src/meta_harney/builtin/__init__.py` with:

```python
"""Builtin default implementations of meta_harney abstractions.

Import directly from sub-namespaces:
  - meta_harney.builtin.permission.{allow_all,deny_all}
  - meta_harney.builtin.session.{memory_store,file_store}
  - meta_harney.builtin.trace.{null_sink,jsonl_sink}
  - meta_harney.builtin.prompt.minimal
  - meta_harney.builtin.compaction.summarization
"""
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/unit/test_public_api.py -v
```
Expected: all PASS.

- [ ] **Step 7: Run full test suite to ensure nothing broke**

```bash
pytest -q
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/meta_harney/__init__.py src/meta_harney/abstractions/__init__.py src/meta_harney/builtin/__init__.py tests/unit/test_public_api.py
git commit -m "feat: expose public API at package root

Top-level meta_harney exports all 9 abstractions + data contracts +
MetaHarneyError. Builtin namespace deliberately not re-exported at
top — users import builtin defaults explicitly from sub-namespaces.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 28: Type Check + Final Lint Pass

**Files:**
- Modify: `pyproject.toml` (if needed for excludes)
- Run: `mypy`, `ruff check`, full pytest

- [ ] **Step 1: Run mypy across the package**

```bash
mypy src/meta_harney
```
Expected: 0 errors. If errors surface, fix them before continuing.

- [ ] **Step 2: Run ruff lint check**

```bash
ruff check src/meta_harney tests
```
Expected: 0 errors. Fix any reported issues by running `ruff check --fix` and re-running.

- [ ] **Step 3: Run ruff format check**

```bash
ruff format --check src/meta_harney tests
```
Expected: 0 differences. If differences exist, run `ruff format src/meta_harney tests` and re-stage.

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```
Expected: ALL tests pass; count should be roughly 60+ (abstractions: ~25, builtin: ~30, contracts via subclasses: ~25, public API: ~2). Specific number doesn't matter — what matters is 0 failures.

- [ ] **Step 5: If any fixes were made above, commit them**

```bash
git status
git add -A
git commit -m "chore: mypy strict + ruff clean

Final Phase 1 verification: package and tests pass mypy --strict and
ruff check + format. All tests green.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

(If nothing changed, skip the commit.)

---

## Phase 1 Completion Checklist

After all 28 tasks pass:

- [ ] `meta_harney` package imports cleanly: `python -c "import meta_harney; print(meta_harney.__version__)"`
- [ ] `pytest` reports 0 failures
- [ ] `mypy src/meta_harney` reports 0 errors
- [ ] `ruff check src/meta_harney tests` reports 0 issues
- [ ] `git log --oneline` on `feature/meta-harney` shows ~28 task commits + initial design commits
- [ ] All 9 abstractions exist under `src/meta_harney/abstractions/` with corresponding tests
- [ ] All builtin defaults exist under `src/meta_harney/builtin/`
- [ ] All 5 contract suites exist under `tests/contracts/` and are applied to builtin implementations

**What's NOT included (intentional — Phase 2+):**
- No `AgentRuntime` (Phase 3)
- No `engine/` (Phase 2)
- No `providers/` (Phase 2)
- No `MultiAgentBackend` concrete implementations (Phase 3)
- No `testing/` helpers (Phase 4)
- No integration tests (Phase 4)
- No CRM example (Phase 5)

Return to brainstorming or writing-plans for Phase 2.

---

## Self-Review

**Spec coverage:**
- §3 Repository layout: covered (Task 6 scaffold + Tasks 8-22 file creation)
- §4.1 Data contracts: Task 8
- §4.2-4.10 nine abstractions: Tasks 9-17
- §7.1 Exception hierarchy: Task 7
- §8.2 Contract tests: Tasks 23-26
- §9.1 Deletion: Tasks 2-4
- Public API: Task 27
- Type+lint discipline: Task 28

Not covered in Phase 1 (deferred by design): engine (§5), providers, runtime assembly, multi-agent impls, integration tests (§8.4), testing module (§8.5), CRM example. These are explicit non-goals of Phase 1.

**Placeholder scan:** No "TBD" / "TODO" / "later" found in steps. All code blocks contain complete implementations.

**Type consistency:**
- `ToolInvocation` uses `session_id: str` everywhere ✓
- `ToolContext` is a `@dataclass` with `session_store`, `trace_sink`, `current_span_id`, `new_span_id` — consistent across Tasks 9, 21, 22 ✓
- `Session.version` lock semantics: `expected_version` / `found_version` naming matches between `errors.py` (Task 7) and the two store implementations (Task 20) and the contract test (Task 23) ✓
- `HookDecision.transform` is `dict[str, Any] | None` — engine enforcement (pre_* only) is documented but not yet implemented (engine is Phase 2) ✓
- `SummarizeFn = Callable[[list[Message]], Awaitable[str]]` matches usage in tests and impl ✓
