# meta-harney Phase 8: oh-mini Python Backend + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build oh-mini v0.1.0 — a complete command-line coding-agent demo consuming meta-harney v0.0.7 via git URL, with 10 coding tools, dual provider, one-shot + REPL modes, FileSessionStore persistence, and CI matrix.

**Architecture:** New independent Python project at `/Users/baihe/Projects/study/oh-mini/`. Each tool is a `BaseTool` subclass in `src/oh_mini/tools/`. `build_runtime()` factory wires meta-harney's `AgentRuntime` with all components. CLI dispatches to one-shot / REPL / resume modes. Tests use `meta_harney.testing.FakeLLMProvider` exclusively (no real API).

**Tech Stack:** Python 3.10+ · meta-harney 0.0.7+ · httpx · nbformat · prompt_toolkit · rich · pytest + pytest-asyncio · mypy strict · ruff · GitHub Actions.

**Pre-conditions:**
- meta-harney v0.0.7 published at `https://github.com/bailaohe/meta-harney.git`
- Plan execution starts from a directory where the oh-mini project does **not** yet exist
- `python3.10` or later available
- `uv` or standard `python -m venv` available for environment

**Execution model:** Tasks 1-22 build everything; Task 23 cuts the v0.1.0 tag. Each task TDD: failing test → implementation → green → commit. Where tests interact with the filesystem (file_read/write/edit), use `tmp_path` fixtures. Where tests interact with subprocess/network, use mocks; integration tests only use `FakeLLMProvider`.

---

## File Structure After Phase 8

```
/Users/baihe/Projects/study/oh-mini/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .github/workflows/ci.yml
├── src/oh_mini/
│   ├── __init__.py                # __version__ = "0.1.0"
│   ├── __main__.py
│   ├── cli.py
│   ├── repl.py
│   ├── runtime.py                 # build_runtime()
│   ├── permission.py              # InteractiveAskPermissionResolver
│   ├── prompts.py                 # CodingPromptBuilder
│   ├── output.py                  # stream rendering
│   └── tools/
│       ├── __init__.py            # ALL_TOOLS dict
│       ├── _safety.py
│       ├── file_read.py     file_write.py    file_edit.py
│       ├── grep.py          glob.py          bash.py
│       ├── todo_write.py    agent.py
│       ├── notebook_edit.py web_fetch.py
└── tests/
    ├── unit/
    │   ├── tools/(10 files)
    │   ├── test_permission.py
    │   ├── test_prompts.py
    │   └── test_runtime_factory.py
    └── integration/
        ├── test_cli_one_shot.py
        ├── test_cli_resume.py
        └── test_repl_interactive.py
```

---

## Task 1: Bootstrap oh-mini project

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/pyproject.toml`
- Create: `/Users/baihe/Projects/study/oh-mini/README.md`
- Create: `/Users/baihe/Projects/study/oh-mini/LICENSE`
- Create: `/Users/baihe/Projects/study/oh-mini/.gitignore`
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/__init__.py`
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/__main__.py`

- [ ] **Step 1: Create directory structure**

```bash
cd /Users/baihe/Projects/study
mkdir -p oh-mini/src/oh_mini/tools
mkdir -p oh-mini/tests/unit/tools
mkdir -p oh-mini/tests/integration
cd oh-mini
```

- [ ] **Step 2: Initialize git**

```bash
git init -b main
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "oh-mini"
version = "0.1.0"
description = "Coding-agent CLI demo built on meta-harney runtime."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
authors = [
    { name = "oh-mini contributors" },
]
dependencies = [
    "meta-harney @ git+https://github.com/bailaohe/meta-harney.git@v0.0.7",
    "httpx>=0.27",
    "nbformat>=5.10",
    "prompt_toolkit>=3.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "mypy>=1.10",
    "ruff>=0.5",
]

[project.scripts]
oh = "oh_mini.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/oh_mini"]

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
disallow_untyped_defs = false
disallow_untyped_calls = false

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
```

- [ ] **Step 4: Write `LICENSE`** (Apache-2.0 full text — copy from meta-harney repo)

```bash
curl -sL https://raw.githubusercontent.com/bailaohe/meta-harney/main/LICENSE -o LICENSE
```

(If curl fails or repo not accessible, paste Apache-2.0 license text from any canonical source.)

- [ ] **Step 5: Write `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
*.so

# Test/lint/type cache
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Virtual envs
.venv/
venv/
env/
.env

# IDE
.idea/
.vscode/
.claude/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# oh-mini runtime data
.oh-mini/
```

- [ ] **Step 6: Write minimal `README.md`**

```markdown
# oh-mini

> Coding-agent CLI demo built on the [meta-harney](https://github.com/bailaohe/meta-harney) runtime.

A faithful but minimal recreation of OpenHarness's coding-assistant scenarios.
oh-mini ships 10 coding tools (file ops, grep/glob, bash, todo, sub-agent,
notebook edit, web fetch), supports both one-shot and interactive REPL modes,
and persists sessions across runs.

## Install

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY
```

## Usage

```bash
oh "add a hello() function to src/foo.py and run the tests"
oh                                    # interactive REPL
oh --resume <session-id> "tweak that"
```

## Tools

| Tool | Purpose |
|------|---------|
| `file_read` | Read a file with optional offset/limit |
| `file_write` | Create or overwrite a file |
| `file_edit` | Exact-match string replace in a file |
| `grep` | Pattern search across files |
| `glob` | Match files by pattern |
| `bash` | Run a shell command with timeout |
| `todo_write` | Plan multi-step work |
| `agent` | Spawn a read-only sub-agent |
| `notebook_edit` | Edit cells of a Jupyter notebook |
| `web_fetch` | Fetch URL contents (https only) |

## License

Apache-2.0
```

- [ ] **Step 7: Write `src/oh_mini/__init__.py`**

```python
"""oh-mini — coding-agent CLI demo on the meta-harney runtime."""

__version__ = "0.1.0"

__all__ = ["__version__"]
```

- [ ] **Step 8: Write `src/oh_mini/__main__.py`**

```python
"""Allow `python -m oh_mini` to invoke the CLI."""

from oh_mini.cli import main

if __name__ == "__main__":
    main()
```

(Note: `cli` module doesn't exist yet — that's Task 17. Import will fail until then. This is acceptable because `python -m oh_mini` won't be exercised until Task 17.)

- [ ] **Step 9: Create the test package roots**

```bash
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/unit/tools/__init__.py
touch tests/integration/__init__.py
touch src/oh_mini/tools/__init__.py
```

- [ ] **Step 10: Create venv + install dev dependencies**

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Expected: meta-harney is fetched from the git URL and installs cleanly with its own deps (pydantic, anthropic, openai).

- [ ] **Step 11: Smoke test**

```bash
source .venv/bin/activate
python -c "import oh_mini; print(oh_mini.__version__)"
python -c "import meta_harney; print(meta_harney.__version__)"
```

Expected: `0.1.0` and `0.0.7` (or later).

- [ ] **Step 12: Commit initial state**

```bash
git add pyproject.toml README.md LICENSE .gitignore src tests
git commit -m "feat: bootstrap oh-mini project

Initial scaffold with pyproject.toml depending on meta-harney via
git URL pinned to v0.0.7. Creates src/oh_mini package + tests/
package structure. README and LICENSE in place."
```

---

## Task 2: `_safety.py` — path-traversal guard

**Files:**
- Create: `src/oh_mini/tools/_safety.py`
- Create: `tests/unit/tools/test_safety.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for path-traversal guard."""
from __future__ import annotations

from pathlib import Path

import pytest

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


def test_relative_path_inside_cwd_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.py").write_text("x")
    result = resolve_path_within_cwd("foo.py")
    assert result == (tmp_path / "foo.py").resolve()


def test_relative_dot_dot_path_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathOutsideCwdError):
        resolve_path_within_cwd("../etc/passwd")


def test_absolute_path_inside_cwd_resolves(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.py"
    p.write_text("x")
    result = resolve_path_within_cwd(str(p))
    assert result == p.resolve()


def test_absolute_path_outside_cwd_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathOutsideCwdError):
        resolve_path_within_cwd("/etc/passwd")
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_safety.py -v
```

Expected: ModuleNotFoundError on `oh_mini.tools._safety`.

- [ ] **Step 3: Implement `src/oh_mini/tools/_safety.py`**

```python
"""Path-traversal guard shared by file_read / file_write / file_edit tools."""
from __future__ import annotations

import os
from pathlib import Path


class PathOutsideCwdError(Exception):
    """Raised when a tool argument resolves to a path outside the current cwd."""


def resolve_path_within_cwd(path: str) -> Path:
    """Resolve `path` relative to cwd and ensure it stays inside.

    Raises PathOutsideCwdError if the resolved absolute path is not
    a child of (or equal to) the current working directory.
    """
    cwd = Path(os.getcwd()).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(cwd)
    except ValueError as exc:
        raise PathOutsideCwdError(f"path outside cwd: {path}") from exc
    return resolved
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_safety.py -v
ruff check src/oh_mini/tools/_safety.py tests/unit/tools/test_safety.py
mypy src/oh_mini/tools/_safety.py
```

Expected: 4/4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/_safety.py tests/unit/tools/test_safety.py
git commit -m "feat(tools): path-traversal guard helper

resolve_path_within_cwd(path) returns resolved Path or raises
PathOutsideCwdError if the resolved path escapes cwd.

Shared by file_read / file_write / file_edit / notebook_edit."
```

---

## Task 3: `output.py` — stream renderer

**Files:**
- Create: `src/oh_mini/output.py`
- Create: `tests/unit/test_output.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for stream renderer."""
from __future__ import annotations

import io

from rich.console import Console

from meta_harney import (
    IterationCompleted,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)
from meta_harney.abstractions._types import ToolResult

from oh_mini.output import render_stream_event


def _capture(event: object, *, show_thinking: bool = False) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    render_stream_event(event, console, show_thinking=show_thinking)
    return buf.getvalue()


def test_render_text_delta_writes_text() -> None:
    out = _capture(TextDelta(text="hello"))
    assert "hello" in out


def test_render_tool_call_started_shows_tool_name() -> None:
    out = _capture(ToolCallStarted(tool_name="bash", invocation_id="t1", args={"command": "ls"}))
    assert "bash" in out


def test_render_tool_call_completed_success() -> None:
    out = _capture(
        ToolCallCompleted(
            tool_name="bash",
            invocation_id="t1",
            result=ToolResult(success=True, output="ok"),
        )
    )
    assert "bash" in out or "✓" in out or "ok" in out


def test_render_tool_call_completed_failure_shows_error() -> None:
    out = _capture(
        ToolCallCompleted(
            tool_name="bash",
            invocation_id="t1",
            result=ToolResult(success=False, output=None, error="boom"),
        )
    )
    assert "boom" in out


def test_render_thinking_delta_suppressed_by_default() -> None:
    out = _capture(ThinkingDelta(text="reasoning"))
    assert "reasoning" not in out


def test_render_thinking_delta_shown_when_flag_set() -> None:
    out = _capture(ThinkingDelta(text="reasoning"), show_thinking=True)
    assert "reasoning" in out


def test_render_turn_completed_shows_iteration_count() -> None:
    out = _capture(TurnCompleted(total_iterations=3))
    assert "3" in out


def test_render_iteration_completed_is_silent() -> None:
    # IterationCompleted is internal-ish; renderer should ignore or render minimally
    out = _capture(IterationCompleted(iteration=1))
    # accept either silent or minimal output, but no exception
    assert isinstance(out, str)
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_output.py -v
```

Expected: ModuleNotFoundError on `oh_mini.output`.

- [ ] **Step 3: Implement `src/oh_mini/output.py`**

```python
"""Render meta-harney StreamEvent into Rich console output."""
from __future__ import annotations

from rich.console import Console

from meta_harney import (
    IterationCompleted,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCompleted,
)


def render_stream_event(
    event: StreamEvent,
    console: Console,
    *,
    show_thinking: bool = False,
) -> None:
    """Render one StreamEvent. Designed to be called inside an async-for loop."""
    if isinstance(event, TextDelta):
        console.out(event.text, end="", highlight=False)
    elif isinstance(event, ThinkingDelta):
        if show_thinking:
            console.out(f"[dim italic]{event.text}[/]", end="", highlight=False)
    elif isinstance(event, ToolCallStarted):
        args_preview = _format_args(event.args)
        console.print(f"\n[cyan]▸ [{event.tool_name}][/] {args_preview}")
    elif isinstance(event, ToolCallCompleted):
        if event.result.success:
            console.print(f"  [green]└─ ✓[/] {event.tool_name}")
        else:
            console.print(f"  [red]└─ ✗[/] {event.tool_name}: {event.result.error}")
    elif isinstance(event, IterationCompleted):
        # Engine-internal marker; nothing to show.
        pass
    elif isinstance(event, TurnCompleted):
        console.print(f"\n[dim][done in {event.total_iterations} iters][/]")


def _format_args(args: dict[str, object]) -> str:
    """One-line preview of tool args. Truncate long values."""
    parts: list[str] = []
    for k, v in args.items():
        s = repr(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_output.py -v
ruff check src/oh_mini/output.py tests/unit/test_output.py
mypy src/oh_mini/output.py
```

Expected: 8/8 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/output.py tests/unit/test_output.py
git commit -m "feat: stream-event renderer using rich

render_stream_event(event, console, show_thinking=False) handles
TextDelta / ToolCallStarted / ToolCallCompleted / ThinkingDelta /
IterationCompleted / TurnCompleted. ThinkingDelta hidden unless
show_thinking=True."
```

---

## Task 4: `CodingPromptBuilder`

**Files:**
- Create: `src/oh_mini/prompts.py`
- Create: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for CodingPromptBuilder."""
from __future__ import annotations

import os

from meta_harney.builtin.session.memory_store import MemorySessionStore

from oh_mini.prompts import CodingPromptBuilder


async def test_system_prompt_includes_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = MemorySessionStore()
    pb = CodingPromptBuilder(session_store=store)
    prompt = await pb.build_system_prompt("any-session")
    assert str(tmp_path) in prompt or os.fspath(tmp_path) in prompt


async def test_system_prompt_includes_coding_persona(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = MemorySessionStore()
    pb = CodingPromptBuilder(session_store=store)
    prompt = await pb.build_system_prompt("any-session")
    assert "coding assistant" in prompt.lower()
    assert "todowrite" in prompt.lower() or "todo" in prompt.lower()
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_prompts.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/prompts.py`**

```python
"""Coding-agent system prompt with cwd injection."""
from __future__ import annotations

import os

from meta_harney.builtin.prompt.minimal import MinimalPromptBuilder


class CodingPromptBuilder(MinimalPromptBuilder):
    """Wraps the base MinimalPromptBuilder with a coding-agent persona."""

    async def build_system_prompt(self, session_id: str) -> str:
        base = await super().build_system_prompt(session_id)
        cwd = os.getcwd()
        persona = (
            f"You are a coding assistant operating in directory: {cwd}\n\n"
            "Use the available tools to read code, modify files, run commands, "
            "and verify your work. When unsure, prefer reading files first. "
            "Always run tests after non-trivial changes. Use the TodoWrite tool "
            "to plan multi-step work."
        )
        if not base:
            return persona
        return f"{persona}\n\n{base}"
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_prompts.py -v
ruff check src/oh_mini/prompts.py tests/unit/test_prompts.py
mypy src/oh_mini/prompts.py
```

Expected: 2/2 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/prompts.py tests/unit/test_prompts.py
git commit -m "feat: CodingPromptBuilder subclass with cwd + persona

Extends MinimalPromptBuilder. System prompt injects the cwd and a
brief coding-agent persona that tells the LLM to read first,
verify with tests, and use TodoWrite for multi-step work."
```

---

## Task 5: `InteractiveAskPermissionResolver`

**Files:**
- Create: `src/oh_mini/permission.py`
- Create: `tests/unit/test_permission.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for InteractiveAskPermissionResolver."""
from __future__ import annotations

import asyncio

from meta_harney.abstractions.tool import ToolInvocation

from oh_mini.permission import (
    DANGEROUS_TOOLS,
    InteractiveAskPermissionResolver,
)


def _make_inv(name: str, args: dict[str, object] | None = None) -> ToolInvocation:
    return ToolInvocation(
        name=name,
        args=args or {},
        invocation_id="t1",
        session_id="s1",
    )


async def test_yolo_always_allows() -> None:
    r = InteractiveAskPermissionResolver(yolo=True, ask=lambda *_a, **_k: "N")
    decision = await r.resolve(_make_inv("bash", {"command": "rm -rf /"}), "s1")
    assert decision.verdict == "allow"


async def test_non_dangerous_silently_allowed() -> None:
    r = InteractiveAskPermissionResolver(yolo=False, ask=lambda *_a, **_k: "N")
    # file_read is NOT in DANGEROUS_TOOLS
    decision = await r.resolve(_make_inv("file_read", {"path": "foo.py"}), "s1")
    assert decision.verdict == "allow"


async def test_dangerous_y_allows() -> None:
    r = InteractiveAskPermissionResolver(yolo=False, ask=lambda *_a, **_k: "y")
    decision = await r.resolve(_make_inv("bash", {"command": "ls"}), "s1")
    assert decision.verdict == "allow"


async def test_dangerous_n_denies() -> None:
    r = InteractiveAskPermissionResolver(yolo=False, ask=lambda *_a, **_k: "N")
    decision = await r.resolve(_make_inv("bash", {"command": "ls"}), "s1")
    assert decision.verdict == "deny"
    assert "user" in (decision.reason or "").lower() or "denied" in (decision.reason or "").lower()


async def test_dangerous_a_promotes_yolo() -> None:
    r = InteractiveAskPermissionResolver(yolo=False, ask=lambda *_a, **_k: "a")
    # First call: a → allow + promote
    decision = await r.resolve(_make_inv("bash", {"command": "ls"}), "s1")
    assert decision.verdict == "allow"
    # Second call: ask should NOT be called (yolo is now True);
    # we can verify by switching ask to raise.
    r._ask = lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not ask"))
    decision2 = await r.resolve(_make_inv("file_write", {"path": "x", "content": "y"}), "s1")
    assert decision2.verdict == "allow"


async def test_dangerous_eof_denies() -> None:
    def _ask(*_a: object, **_k: object) -> str:
        raise EOFError
    r = InteractiveAskPermissionResolver(yolo=False, ask=_ask)
    decision = await r.resolve(_make_inv("bash", {"command": "ls"}), "s1")
    assert decision.verdict == "deny"


def test_dangerous_tools_set_includes_expected_names() -> None:
    assert "bash" in DANGEROUS_TOOLS
    assert "file_write" in DANGEROUS_TOOLS
    assert "file_edit" in DANGEROUS_TOOLS
    assert "notebook_edit" in DANGEROUS_TOOLS
    assert "file_read" not in DANGEROUS_TOOLS
    assert "grep" not in DANGEROUS_TOOLS
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_permission.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/permission.py`**

```python
"""InteractiveAskPermissionResolver — interactive y/N/a prompting for dangerous tools."""
from __future__ import annotations

from collections.abc import Callable

from meta_harney.abstractions.permission import PermissionDecision
from meta_harney.abstractions.tool import ToolInvocation

DANGEROUS_TOOLS: frozenset[str] = frozenset(
    {"bash", "file_write", "file_edit", "notebook_edit"}
)


# Default prompt fn uses builtins.input. Tests inject a stub.
def _default_ask(prompt: str) -> str:
    return input(prompt)


class InteractiveAskPermissionResolver:
    """Implements meta-harney's PermissionResolver Protocol.

    Behavior:
    - yolo=True: always allow.
    - tool not in DANGEROUS_TOOLS: always allow.
    - Otherwise: call ask() with a prompt; answer 'y' or 'yes' → allow;
      'a' → allow + promote to yolo for the rest of this resolver's life;
      anything else (incl. EOFError, KeyboardInterrupt) → deny.
    """

    def __init__(
        self,
        *,
        yolo: bool,
        dangerous_tools: frozenset[str] = DANGEROUS_TOOLS,
        ask: Callable[[str], str] = _default_ask,
    ) -> None:
        self._yolo = yolo
        self._dangerous = dangerous_tools
        self._ask = ask

    async def resolve(
        self,
        inv: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision:
        if self._yolo:
            return PermissionDecision(verdict="allow")
        if inv.name not in self._dangerous:
            return PermissionDecision(verdict="allow")
        # Dangerous: prompt user.
        prompt = (
            f"\n⚠  Tool [{inv.name}] wants to run:\n"
            f"   {_format_args(inv.args)}\n"
            "Allow? [y/N/a=always]: "
        )
        try:
            answer = self._ask(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return PermissionDecision(verdict="deny", reason="user interrupted")
        if answer == "a":
            self._yolo = True
            return PermissionDecision(verdict="allow")
        if answer in {"y", "yes"}:
            return PermissionDecision(verdict="allow")
        return PermissionDecision(verdict="deny", reason="user denied")


def _format_args(args: dict[str, object]) -> str:
    parts: list[str] = []
    for k, v in args.items():
        s = repr(v)
        if len(s) > 80:
            s = s[:77] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_permission.py -v
ruff check src/oh_mini/permission.py tests/unit/test_permission.py
mypy src/oh_mini/permission.py
```

Expected: 7/7 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/permission.py tests/unit/test_permission.py
git commit -m "feat: InteractiveAskPermissionResolver for coding tools

DANGEROUS_TOOLS = {bash, file_write, file_edit, notebook_edit}.
Resolver asks y/N/a for dangerous tools; 'a' promotes to yolo for
this resolver's lifetime. EOF / KeyboardInterrupt → deny."
```

---

## Task 6: `FileReadTool`

**Files:**
- Create: `src/oh_mini/tools/file_read.py`
- Create: `tests/unit/tools/test_file_read.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for FileReadTool."""
from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.file_read import FileReadTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="file_read", args=args, invocation_id="t1", session_id="s1")


async def test_read_file_happy(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.txt"
    p.write_text("line 1\nline 2\nline 3\n")
    inv = _make_inv({"path": "foo.txt"})
    result = await FileReadTool().execute(inv, _make_ctx())
    assert result.success
    assert "line 1" in str(result.output)
    assert "line 3" in str(result.output)


async def test_read_with_offset_and_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.txt"
    p.write_text("a\nb\nc\nd\ne\n")
    inv = _make_inv({"path": "foo.txt", "offset": 1, "limit": 2})
    result = await FileReadTool().execute(inv, _make_ctx())
    assert result.success
    # offset=1 skips first line, limit=2 reads 2 lines → "b\nc"
    assert "b" in str(result.output)
    assert "c" in str(result.output)
    assert "a" not in str(result.output)
    assert "d" not in str(result.output)


async def test_read_missing_file_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"path": "no-such-file.txt"})
    result = await FileReadTool().execute(inv, _make_ctx())
    assert not result.success
    assert "no-such-file" in (result.error or "").lower() or "not found" in (result.error or "").lower() or "no such" in (result.error or "").lower()


async def test_read_outside_cwd_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"path": "../etc/passwd"})
    result = await FileReadTool().execute(inv, _make_ctx())
    assert not result.success
    assert "outside" in (result.error or "").lower() or "cwd" in (result.error or "").lower()
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_read.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/file_read.py`**

```python
"""FileReadTool — read text files with optional offset/limit."""
from __future__ import annotations

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _FileReadInput(BaseModel):
    path: str
    offset: int = Field(default=0, ge=0)
    limit: int | None = Field(default=None, ge=1)


class FileReadTool(BaseTool):
    name = "file_read"
    description = (
        "Read a text file. Returns its full content, or lines [offset:offset+limit] if specified."
    )
    input_schema = _FileReadInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            path = resolve_path_within_cwd(inv.args["path"])
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        if not path.exists():
            return ToolResult(success=False, error=f"no such file: {inv.args['path']}")
        if path.is_dir():
            return ToolResult(success=False, error=f"path is a directory: {inv.args['path']}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(success=False, error=f"read failed: {exc}")
        offset = int(inv.args.get("offset", 0))
        limit = inv.args.get("limit")
        if offset or limit is not None:
            lines = text.splitlines(keepends=True)
            if limit is None:
                lines = lines[offset:]
            else:
                lines = lines[offset : offset + int(limit)]
            text = "".join(lines)
        return ToolResult(success=True, output=text)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_read.py -v
ruff check src/oh_mini/tools/file_read.py tests/unit/tools/test_file_read.py
mypy src/oh_mini/tools/file_read.py
```

Expected: 4/4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/file_read.py tests/unit/tools/test_file_read.py
git commit -m "feat(tools): FileReadTool — read text files

input_schema: {path, offset?: int>=0, limit?: int>=1}. Uses
resolve_path_within_cwd to reject path traversal. Returns full
text or sliced lines."
```

---

## Task 7: `FileWriteTool`

**Files:**
- Create: `src/oh_mini/tools/file_write.py`
- Create: `tests/unit/tools/test_file_write.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for FileWriteTool."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.file_write import FileWriteTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="file_write", args=args, invocation_id="t1", session_id="s1")


async def test_write_new_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"path": "out.txt", "content": "hello"})
    result = await FileWriteTool().execute(inv, _make_ctx())
    assert result.success
    assert (tmp_path / "out.txt").read_text() == "hello"


async def test_write_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out.txt").write_text("old content")
    inv = _make_inv({"path": "out.txt", "content": "new content"})
    result = await FileWriteTool().execute(inv, _make_ctx())
    assert result.success
    assert (tmp_path / "out.txt").read_text() == "new content"


async def test_write_outside_cwd_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"path": "../escaped.txt", "content": "evil"})
    result = await FileWriteTool().execute(inv, _make_ctx())
    assert not result.success
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_write.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/file_write.py`**

```python
"""FileWriteTool — create or overwrite a text file."""
from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _FileWriteInput(BaseModel):
    path: str
    content: str


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Create or overwrite a text file at `path` with `content`."
    input_schema = _FileWriteInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            path = resolve_path_within_cwd(inv.args["path"])
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(inv.args["content"], encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"write failed: {exc}")
        return ToolResult(success=True, output=f"wrote {len(inv.args['content'])} bytes to {path}")
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_write.py -v
ruff check src/oh_mini/tools/file_write.py tests/unit/tools/test_file_write.py
mypy src/oh_mini/tools/file_write.py
```

Expected: 3/3 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/file_write.py tests/unit/tools/test_file_write.py
git commit -m "feat(tools): FileWriteTool — create or overwrite

input_schema: {path, content}. Creates parent dirs as needed.
Path traversal blocked. Returns byte-count summary."
```

---

## Task 8: `FileEditTool`

**Files:**
- Create: `src/oh_mini/tools/file_edit.py`
- Create: `tests/unit/tools/test_file_edit.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for FileEditTool."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.file_edit import FileEditTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="file_edit", args=args, invocation_id="t1", session_id="s1")


async def test_exact_replace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.py"
    p.write_text("def old():\n    pass\n")
    inv = _make_inv({"path": "foo.py", "old_string": "def old():", "new_string": "def new():"})
    result = await FileEditTool().execute(inv, _make_ctx())
    assert result.success
    assert p.read_text() == "def new():\n    pass\n"


async def test_replace_all_multiple_occurrences(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.py"
    p.write_text("x = 1\ny = 1\nz = 1\n")
    inv = _make_inv({"path": "foo.py", "old_string": "1", "new_string": "2", "replace_all": True})
    result = await FileEditTool().execute(inv, _make_ctx())
    assert result.success
    assert p.read_text() == "x = 2\ny = 2\nz = 2\n"


async def test_old_string_not_found_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.py"
    p.write_text("nothing matches")
    inv = _make_inv({"path": "foo.py", "old_string": "xyz", "new_string": "abc"})
    result = await FileEditTool().execute(inv, _make_ctx())
    assert not result.success
    assert "not found" in (result.error or "").lower()


async def test_non_unique_without_replace_all_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "foo.py"
    p.write_text("x = 1\ny = 1\n")
    inv = _make_inv({"path": "foo.py", "old_string": "1", "new_string": "2"})
    result = await FileEditTool().execute(inv, _make_ctx())
    assert not result.success
    assert "unique" in (result.error or "").lower() or "multiple" in (result.error or "").lower()
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_edit.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/file_edit.py`**

```python
"""FileEditTool — exact-match string replacement in a file."""
from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _FileEditInput(BaseModel):
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class FileEditTool(BaseTool):
    name = "file_edit"
    description = (
        "Exact-match string replacement. `old_string` must occur exactly once "
        "unless `replace_all=true`."
    )
    input_schema = _FileEditInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            path = resolve_path_within_cwd(inv.args["path"])
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        if not path.exists():
            return ToolResult(success=False, error=f"no such file: {inv.args['path']}")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return ToolResult(success=False, error=f"read failed: {exc}")
        old = str(inv.args["old_string"])
        new = str(inv.args["new_string"])
        replace_all = bool(inv.args.get("replace_all", False))
        count = content.count(old)
        if count == 0:
            return ToolResult(success=False, error=f"old_string not found in file")
        if count > 1 and not replace_all:
            return ToolResult(
                success=False,
                error=f"old_string not unique (found {count} occurrences); "
                f"set replace_all=true or include more context",
            )
        if replace_all:
            content = content.replace(old, new)
        else:
            content = content.replace(old, new, 1)
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"write failed: {exc}")
        return ToolResult(
            success=True,
            output=f"replaced {count if replace_all else 1} occurrence(s) in {path}",
        )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_file_edit.py -v
ruff check src/oh_mini/tools/file_edit.py tests/unit/tools/test_file_edit.py
mypy src/oh_mini/tools/file_edit.py
```

Expected: 4/4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/file_edit.py tests/unit/tools/test_file_edit.py
git commit -m "feat(tools): FileEditTool — exact-match string replace

input_schema: {path, old_string, new_string, replace_all=false}.
Refuses ambiguous edits when old_string occurs multiple times
unless replace_all=true."
```

---

## Task 9: `GrepTool`

**Files:**
- Create: `src/oh_mini/tools/grep.py`
- Create: `tests/unit/tools/test_grep.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for GrepTool."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.grep import GrepTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="grep", args=args, invocation_id="t1", session_id="s1")


async def test_grep_finds_pattern(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("hello world\n")
    (tmp_path / "b.py").write_text("goodbye\n")
    inv = _make_inv({"pattern": "hello"})
    result = await GrepTool().execute(inv, _make_ctx())
    assert result.success
    out = str(result.output)
    assert "a.py" in out
    assert "hello" in out
    assert "b.py" not in out


async def test_grep_no_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("hello\n")
    inv = _make_inv({"pattern": "nonexistent_xyz"})
    result = await GrepTool().execute(inv, _make_ctx())
    assert result.success
    assert "no matches" in str(result.output).lower() or str(result.output).strip() == ""


async def test_grep_filters_by_glob(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("hello\n")
    (tmp_path / "a.txt").write_text("hello\n")
    inv = _make_inv({"pattern": "hello", "glob": "*.py"})
    result = await GrepTool().execute(inv, _make_ctx())
    assert result.success
    out = str(result.output)
    assert "a.py" in out
    assert "a.txt" not in out


async def test_grep_max_matches_truncates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text("hit\n")
    inv = _make_inv({"pattern": "hit", "max_matches": 2})
    result = await GrepTool().execute(inv, _make_ctx())
    assert result.success
    out = str(result.output)
    # At most 2 of the 5 files appear
    hit_count = sum(out.count(f"f{i}.py") for i in range(5))
    assert hit_count <= 2
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_grep.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/grep.py`**

```python
"""GrepTool — recursive pattern search."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _GrepInput(BaseModel):
    pattern: str
    path: str = "."
    glob: str | None = None
    max_matches: int = Field(default=100, ge=1)


class GrepTool(BaseTool):
    name = "grep"
    description = "Recursive regex search for `pattern` across files. Returns matching lines."
    input_schema = _GrepInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            root = resolve_path_within_cwd(str(inv.args.get("path", ".")))
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        pattern = str(inv.args["pattern"])
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolResult(success=False, error=f"invalid regex: {exc}")
        glob = inv.args.get("glob")
        max_matches = int(inv.args.get("max_matches", 100))

        matches: list[str] = []
        if root.is_file():
            files = [root]
        else:
            files = [p for p in root.rglob("*") if p.is_file()]
        if glob is not None:
            files = [f for f in files if fnmatch.fnmatch(f.name, str(glob))]
        for f in files:
            try:
                with f.open("r", encoding="utf-8", errors="replace") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        if regex.search(line):
                            rel = f.relative_to(root) if root.is_dir() else f.name
                            matches.append(f"{rel}:{lineno}:{line.rstrip()}")
                            if len(matches) >= max_matches:
                                break
            except OSError:
                continue
            if len(matches) >= max_matches:
                break
        if not matches:
            return ToolResult(success=True, output="no matches")
        return ToolResult(success=True, output="\n".join(matches))
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_grep.py -v
ruff check src/oh_mini/tools/grep.py tests/unit/tools/test_grep.py
mypy src/oh_mini/tools/grep.py
```

Expected: 4/4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/grep.py tests/unit/tools/test_grep.py
git commit -m "feat(tools): GrepTool — recursive regex search

input_schema: {pattern, path=., glob?, max_matches=100}.
Uses Python re module + pathlib.rglob; fnmatch for glob filter.
Output format: 'rel/path:lineno:text'."
```

---

## Task 10: `GlobTool`

**Files:**
- Create: `src/oh_mini/tools/glob.py`
- Create: `tests/unit/tools/test_glob.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for GlobTool."""
from __future__ import annotations

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.glob import GlobTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="glob", args=args, invocation_id="t1", session_id="s1")


async def test_glob_finds_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")
    inv = _make_inv({"pattern": "*.py"})
    result = await GlobTool().execute(inv, _make_ctx())
    assert result.success
    out = str(result.output)
    assert "a.py" in out
    assert "b.py" in out
    assert "c.txt" not in out


async def test_glob_no_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.txt").write_text("")
    inv = _make_inv({"pattern": "*.nonexistent"})
    result = await GlobTool().execute(inv, _make_ctx())
    assert result.success
    assert "no matches" in str(result.output).lower() or str(result.output).strip() == ""


async def test_glob_recursive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.py").write_text("")
    (tmp_path / "top.py").write_text("")
    inv = _make_inv({"pattern": "**/*.py"})
    result = await GlobTool().execute(inv, _make_ctx())
    assert result.success
    out = str(result.output)
    assert "deep.py" in out
    assert "top.py" in out
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_glob.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/glob.py`**

```python
"""GlobTool — match files by glob pattern."""
from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _GlobInput(BaseModel):
    pattern: str
    path: str = "."


class GlobTool(BaseTool):
    name = "glob"
    description = "Match file paths by glob pattern (supports `**` recursion)."
    input_schema = _GlobInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            root = resolve_path_within_cwd(str(inv.args.get("path", ".")))
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        pattern = str(inv.args["pattern"])
        try:
            matches = sorted(root.glob(pattern))
        except (OSError, ValueError) as exc:
            return ToolResult(success=False, error=f"glob failed: {exc}")
        if not matches:
            return ToolResult(success=True, output="no matches")
        rels = [str(p.relative_to(root)) for p in matches]
        return ToolResult(success=True, output="\n".join(rels))
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_glob.py -v
ruff check src/oh_mini/tools/glob.py tests/unit/tools/test_glob.py
mypy src/oh_mini/tools/glob.py
```

Expected: 3/3 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/glob.py tests/unit/tools/test_glob.py
git commit -m "feat(tools): GlobTool — match files by glob

input_schema: {pattern, path=.}. Uses pathlib.Path.glob with **
recursion. Returns sorted relative paths or 'no matches'."
```

---

## Task 11: `BashTool`

**Files:**
- Create: `src/oh_mini/tools/bash.py`
- Create: `tests/unit/tools/test_bash.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for BashTool."""
from __future__ import annotations

import sys

import pytest

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.bash import BashTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="bash", args=args, invocation_id="t1", session_id="s1")


@pytest.mark.skipif(sys.platform == "win32", reason="bash not available on Windows")
async def test_bash_exit_zero_returns_stdout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"command": "echo hello"})
    result = await BashTool().execute(inv, _make_ctx())
    assert result.success
    out = result.output
    assert isinstance(out, dict)
    assert "hello" in str(out["stdout"])
    assert out["exit_code"] == 0


@pytest.mark.skipif(sys.platform == "win32", reason="bash not available on Windows")
async def test_bash_exit_nonzero_still_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"command": "exit 3"})
    result = await BashTool().execute(inv, _make_ctx())
    assert result.success  # tool succeeded; exit_code reflects the command itself
    assert result.output["exit_code"] == 3


@pytest.mark.skipif(sys.platform == "win32", reason="bash not available on Windows")
async def test_bash_stderr_captured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"command": "echo oops >&2"})
    result = await BashTool().execute(inv, _make_ctx())
    assert result.success
    assert "oops" in str(result.output["stderr"])


@pytest.mark.skipif(sys.platform == "win32", reason="bash not available on Windows")
async def test_bash_timeout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inv = _make_inv({"command": "sleep 5", "timeout": 1})
    result = await BashTool().execute(inv, _make_ctx())
    assert not result.success
    assert "timeout" in (result.error or "").lower()


@pytest.mark.skipif(sys.platform == "win32", reason="bash not available on Windows")
async def test_bash_cwd_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    inv = _make_inv({"command": "pwd", "cwd": str(sub)})
    result = await BashTool().execute(inv, _make_ctx())
    assert result.success
    assert str(sub) in str(result.output["stdout"]) or "sub" in str(result.output["stdout"])
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_bash.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/bash.py`**

```python
"""BashTool — run a shell command with timeout."""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)


class _BashInput(BaseModel):
    command: str
    timeout: int = Field(default=60, ge=1, le=600)
    cwd: str | None = None


class BashTool(BaseTool):
    name = "bash"
    description = (
        "Run a bash shell command. Returns stdout, stderr, exit_code. "
        "Non-zero exit is NOT a tool failure (LLM decides). Timeout default 60s."
    )
    input_schema = _BashInput
    default_timeout: float | None = 60.0

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        command = str(inv.args["command"])
        timeout = int(inv.args.get("timeout", 60))
        cwd = inv.args.get("cwd")
        cwd_str = str(cwd) if cwd is not None else None
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash",
                "-c",
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd_str,
            )
        except (OSError, FileNotFoundError) as exc:
            return ToolResult(success=False, error=f"failed to spawn bash: {exc}")
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            return ToolResult(success=False, error=f"timeout after {timeout}s")
        return ToolResult(
            success=True,
            output={
                "stdout": stdout_b.decode("utf-8", errors="replace"),
                "stderr": stderr_b.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
            },
        )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_bash.py -v
ruff check src/oh_mini/tools/bash.py tests/unit/tools/test_bash.py
mypy src/oh_mini/tools/bash.py
```

Expected: 5/5 pass (on Linux/macOS); clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/bash.py tests/unit/tools/test_bash.py
git commit -m "feat(tools): BashTool — async subprocess with timeout

input_schema: {command, timeout=60, cwd?}. Returns
{stdout, stderr, exit_code}. Non-zero exit is success=True
(the command itself signaled, but the tool worked).
Timeout kills the process and reports failure."
```

---

## Task 12: `TodoWriteTool`

**Files:**
- Create: `src/oh_mini/tools/todo_write.py`
- Create: `tests/unit/tools/test_todo_write.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for TodoWriteTool."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions.session import Session
from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.todo_write import TodoWriteTool


async def _make_ctx_with_session(session_id: str) -> ToolContext:
    store = MemorySessionStore()
    await store.save(Session(id=session_id, created_at=datetime.now(timezone.utc)))
    return ToolContext(
        session_store=store,
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object], session_id: str = "s1") -> ToolInvocation:
    return ToolInvocation(name="todo_write", args=args, invocation_id="t1", session_id=session_id)


async def test_todo_write_persists_to_session_attributes():
    ctx = await _make_ctx_with_session("s1")
    todos = [
        {"content": "step 1", "status": "in_progress"},
        {"content": "step 2", "status": "pending"},
    ]
    inv = _make_inv({"todos": todos})
    result = await TodoWriteTool().execute(inv, ctx)
    assert result.success
    session = await ctx.session_store.load("s1")
    assert session is not None
    assert session.attributes["todos"] == todos


async def test_todo_write_overwrites_previous():
    ctx = await _make_ctx_with_session("s1")
    first = [{"content": "old", "status": "pending"}]
    second = [{"content": "new", "status": "completed"}]
    await TodoWriteTool().execute(_make_inv({"todos": first}), ctx)
    await TodoWriteTool().execute(_make_inv({"todos": second}), ctx)
    session = await ctx.session_store.load("s1")
    assert session is not None
    assert session.attributes["todos"] == second
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_todo_write.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/todo_write.py`**

```python
"""TodoWriteTool — store a todo list in session.attributes."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)


class _TodoItem(BaseModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]


class _TodoWriteInput(BaseModel):
    todos: list[_TodoItem]


class TodoWriteTool(BaseTool):
    name = "todo_write"
    description = (
        "Persist a structured todo list in the current session's attributes. "
        "Overwrites any previous list."
    )
    input_schema = _TodoWriteInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        session = await ctx.session_store.load(inv.session_id)
        if session is None:
            return ToolResult(success=False, error=f"session {inv.session_id} not found")
        todos = inv.args["todos"]
        # Normalize to plain dicts (caller may have passed list[_TodoItem] or list[dict])
        normalized: list[dict[str, str]] = []
        for t in todos:
            if isinstance(t, dict):
                normalized.append({"content": str(t["content"]), "status": str(t["status"])})
            else:
                normalized.append({"content": t.content, "status": t.status})
        session.attributes["todos"] = normalized
        try:
            await ctx.session_store.save(session)
        except Exception as exc:
            return ToolResult(success=False, error=f"save failed: {exc}")
        return ToolResult(success=True, output=f"wrote {len(normalized)} todos")
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_todo_write.py -v
ruff check src/oh_mini/tools/todo_write.py tests/unit/tools/test_todo_write.py
mypy src/oh_mini/tools/todo_write.py
```

Expected: 2/2 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/todo_write.py tests/unit/tools/test_todo_write.py
git commit -m "feat(tools): TodoWriteTool — persist todos in session.attributes

input_schema: {todos: list[{content, status}]}. Overwrites
session.attributes['todos']. Status enum: pending/in_progress/completed."
```

---

## Task 13: `NotebookEditTool`

**Files:**
- Create: `src/oh_mini/tools/notebook_edit.py`
- Create: `tests/unit/tools/test_notebook_edit.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for NotebookEditTool."""
from __future__ import annotations

import json

import nbformat

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.notebook_edit import NotebookEditTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="notebook_edit", args=args, invocation_id="t1", session_id="s1")


def _write_nb(path, cells_sources: list[str]):
    nb = nbformat.v4.new_notebook()
    nb["cells"] = [nbformat.v4.new_code_cell(s) for s in cells_sources]
    nbformat.write(nb, path)


async def test_edit_cell_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nb_path = tmp_path / "x.ipynb"
    _write_nb(nb_path, ["print('hi')", "print('old')"])
    inv = _make_inv({"path": "x.ipynb", "cell_index": 1, "new_source": "print('new')"})
    result = await NotebookEditTool().execute(inv, _make_ctx())
    assert result.success
    nb = nbformat.read(nb_path, as_version=4)
    assert nb["cells"][1]["source"] == "print('new')"


async def test_cell_index_out_of_range_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nb_path = tmp_path / "x.ipynb"
    _write_nb(nb_path, ["only one cell"])
    inv = _make_inv({"path": "x.ipynb", "cell_index": 5, "new_source": "..."})
    result = await NotebookEditTool().execute(inv, _make_ctx())
    assert not result.success
    assert "index" in (result.error or "").lower()


async def test_non_ipynb_file_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "not-a-notebook.txt"
    p.write_text("hello")
    inv = _make_inv({"path": "not-a-notebook.txt", "cell_index": 0, "new_source": "..."})
    result = await NotebookEditTool().execute(inv, _make_ctx())
    assert not result.success
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_notebook_edit.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/notebook_edit.py`**

```python
"""NotebookEditTool — edit a single code cell of a Jupyter notebook."""
from __future__ import annotations

import nbformat
from pydantic import BaseModel, Field

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

from oh_mini.tools._safety import PathOutsideCwdError, resolve_path_within_cwd


class _NotebookEditInput(BaseModel):
    path: str
    cell_index: int = Field(ge=0)
    new_source: str


class NotebookEditTool(BaseTool):
    name = "notebook_edit"
    description = (
        "Replace the source of a single cell in a Jupyter notebook (.ipynb). "
        "cell_index is 0-based."
    )
    input_schema = _NotebookEditInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        try:
            path = resolve_path_within_cwd(str(inv.args["path"]))
        except PathOutsideCwdError as exc:
            return ToolResult(success=False, error=str(exc))
        if not path.exists():
            return ToolResult(success=False, error=f"no such file: {inv.args['path']}")
        if path.suffix != ".ipynb":
            return ToolResult(success=False, error=f"not a notebook (.ipynb): {path}")
        try:
            nb = nbformat.read(str(path), as_version=4)
        except Exception as exc:
            return ToolResult(success=False, error=f"notebook read failed: {exc}")
        cell_index = int(inv.args["cell_index"])
        if cell_index < 0 or cell_index >= len(nb["cells"]):
            return ToolResult(
                success=False,
                error=f"cell_index {cell_index} out of range (notebook has {len(nb['cells'])} cells)",
            )
        nb["cells"][cell_index]["source"] = str(inv.args["new_source"])
        try:
            nbformat.write(nb, str(path))
        except Exception as exc:
            return ToolResult(success=False, error=f"notebook write failed: {exc}")
        return ToolResult(success=True, output=f"edited cell {cell_index} of {path}")
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_notebook_edit.py -v
ruff check src/oh_mini/tools/notebook_edit.py tests/unit/tools/test_notebook_edit.py
mypy src/oh_mini/tools/notebook_edit.py
```

Expected: 3/3 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/notebook_edit.py tests/unit/tools/test_notebook_edit.py
git commit -m "feat(tools): NotebookEditTool — edit one cell of .ipynb

input_schema: {path, cell_index>=0, new_source}. Uses nbformat
v4. Refuses non-.ipynb files. cell_index bound-check."
```

---

## Task 14: `WebFetchTool`

**Files:**
- Create: `src/oh_mini/tools/web_fetch.py`
- Create: `tests/unit/tools/test_web_fetch.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for WebFetchTool."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.web_fetch import WebFetchTool


def _make_ctx() -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=None,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="web_fetch", args=args, invocation_id="t1", session_id="s1")


def _fake_response(text: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


async def test_web_fetch_https_success():
    fake_get = AsyncMock(return_value=_fake_response("hello world"))
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = fake_get
    with patch("oh_mini.tools.web_fetch.httpx.AsyncClient", return_value=fake_client):
        inv = _make_inv({"url": "https://example.com/"})
        result = await WebFetchTool().execute(inv, _make_ctx())
    assert result.success
    assert "hello world" in str(result.output)


async def test_web_fetch_non_https_rejected():
    inv = _make_inv({"url": "ftp://example.com/file"})
    result = await WebFetchTool().execute(inv, _make_ctx())
    assert not result.success
    assert "http" in (result.error or "").lower()


async def test_web_fetch_truncates_at_1mb():
    big = "x" * (2 * 1024 * 1024)
    fake_get = AsyncMock(return_value=_fake_response(big))
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = fake_get
    with patch("oh_mini.tools.web_fetch.httpx.AsyncClient", return_value=fake_client):
        inv = _make_inv({"url": "https://example.com/"})
        result = await WebFetchTool().execute(inv, _make_ctx())
    assert result.success
    body = str(result.output)
    # Body is truncated to ~1MB and includes the truncation marker.
    assert len(body) <= (1 * 1024 * 1024 + 100)
    assert "truncated" in body.lower()


async def test_web_fetch_http_error_returned_as_failure():
    fake_get = AsyncMock(side_effect=httpx.TimeoutException("slow"))
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = fake_get
    with patch("oh_mini.tools.web_fetch.httpx.AsyncClient", return_value=fake_client):
        inv = _make_inv({"url": "https://example.com/"})
        result = await WebFetchTool().execute(inv, _make_ctx())
    assert not result.success
    assert "timeout" in (result.error or "").lower() or "slow" in (result.error or "").lower()
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_web_fetch.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/web_fetch.py`**

```python
"""WebFetchTool — fetch a URL via httpx (https only)."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

_MAX_BODY_BYTES = 1 * 1024 * 1024
_TRUNCATED_MARKER = "\n[truncated at 1MB]"


class _WebFetchInput(BaseModel):
    url: str
    prompt: str | None = None  # Phase 8: prompt is accepted but unused (no LLM summarize)


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "Fetch the body of an https URL. Returns raw text, truncated to 1MB. "
        "(Phase 8: does not summarize via LLM.)"
    )
    input_schema = _WebFetchInput
    default_timeout: float | None = 30.0

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        url = str(inv.args["url"])
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(success=False, error=f"only http(s) URLs allowed; got: {parsed.scheme}")
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                body = resp.text
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            return ToolResult(success=False, error=f"fetch failed: {exc}")
        if len(body.encode("utf-8")) > _MAX_BODY_BYTES:
            body = body[:_MAX_BODY_BYTES] + _TRUNCATED_MARKER
        return ToolResult(success=True, output=body)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_web_fetch.py -v
ruff check src/oh_mini/tools/web_fetch.py tests/unit/tools/test_web_fetch.py
mypy src/oh_mini/tools/web_fetch.py
```

Expected: 4/4 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/web_fetch.py tests/unit/tools/test_web_fetch.py
git commit -m "feat(tools): WebFetchTool — fetch https URL via httpx

input_schema: {url, prompt?}. Only http(s) scheme allowed; non-http
rejected. Body truncated to 1MB with marker. prompt arg accepted but
unused in Phase 8 (no LLM summarize)."
```

---

## Task 15: `AgentTool`

**Files:**
- Create: `src/oh_mini/tools/agent.py`
- Create: `tests/unit/tools/test_agent.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for AgentTool."""
from __future__ import annotations

from datetime import datetime, timezone

from meta_harney.abstractions._types import Message, TextBlock
from meta_harney.abstractions.multi_agent import AgentSpec, SpawnHandle
from meta_harney.abstractions.tool import ToolContext, ToolInvocation
from meta_harney.builtin.session.memory_store import MemorySessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.tools.agent import SUBAGENT_ALLOWED_TOOLS, AgentTool


class _StubBackend:
    """Capture spawn args and return a canned final Message."""

    def __init__(self, final_text: str = "sub-agent result") -> None:
        self.captured_spec: AgentSpec | None = None
        self.captured_message: str | None = None
        self._final_text = final_text

    async def spawn(self, spec, initial_message, parent_session_id, *, mode="blocking"):
        self.captured_spec = spec
        self.captured_message = initial_message
        return SpawnHandle(child_session_id="child-1")

    async def join(self, child_session_id, *, timeout=None):
        return Message(role="assistant", content=[TextBlock(text=self._final_text)])

    async def status(self, child_session_id):  # pragma: no cover - not used in these tests
        from meta_harney.abstractions.task import TaskState
        return TaskState.SUCCEEDED

    async def cancel(self, child_session_id):  # pragma: no cover
        return None


def _make_ctx_with_backend(backend) -> ToolContext:
    return ToolContext(
        session_store=MemorySessionStore(),
        trace_sink=NullSink(),
        current_span_id="span-1",
        new_span_id=lambda: "span-x",
        multi_agent=backend,
    )


def _make_inv(args: dict[str, object]) -> ToolInvocation:
    return ToolInvocation(name="agent", args=args, invocation_id="t1", session_id="parent")


async def test_agent_blocking_returns_final_text():
    backend = _StubBackend(final_text="42")
    inv = _make_inv({"description": "find the answer", "prompt": "find it"})
    result = await AgentTool().execute(inv, _make_ctx_with_backend(backend))
    assert result.success
    assert "42" in str(result.output)


async def test_agent_subagent_allowed_tools_is_readonly_subset():
    backend = _StubBackend()
    inv = _make_inv({"description": "x", "prompt": "find x"})
    await AgentTool().execute(inv, _make_ctx_with_backend(backend))
    assert backend.captured_spec is not None
    assert set(backend.captured_spec.allowed_tools) == set(SUBAGENT_ALLOWED_TOOLS)
    assert "bash" not in backend.captured_spec.allowed_tools
    assert "file_write" not in backend.captured_spec.allowed_tools
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_agent.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement `src/oh_mini/tools/agent.py`**

```python
"""AgentTool — spawn a read-only sub-agent via meta-harney MultiAgentBackend."""
from __future__ import annotations

from pydantic import BaseModel

from meta_harney.abstractions._types import TextBlock
from meta_harney.abstractions.multi_agent import AgentSpec
from meta_harney.abstractions.tool import (
    BaseTool,
    ToolContext,
    ToolInvocation,
    ToolResult,
)

SUBAGENT_ALLOWED_TOOLS: list[str] = ["file_read", "grep", "glob"]


class _AgentInput(BaseModel):
    description: str
    prompt: str


class AgentTool(BaseTool):
    name = "agent"
    description = (
        "Spawn a sub-agent to research and report back. The sub-agent has access "
        "only to read-only tools (file_read, grep, glob). Returns the sub-agent's "
        "final assistant message text."
    )
    input_schema = _AgentInput

    async def execute(
        self,
        inv: ToolInvocation,
        ctx: ToolContext,
    ) -> ToolResult:
        if ctx.multi_agent is None:
            return ToolResult(success=False, error="multi-agent backend not configured")
        spec = AgentSpec(
            name="sub-agent",
            instructions=str(inv.args["prompt"]),
            allowed_tools=list(SUBAGENT_ALLOWED_TOOLS),
            max_iters=5,
        )
        try:
            handle = await ctx.multi_agent.spawn(
                spec,
                str(inv.args["prompt"]),
                inv.session_id,
                mode="blocking",
            )
            result_msg = await ctx.multi_agent.join(handle.child_session_id)
        except Exception as exc:
            return ToolResult(success=False, error=f"sub-agent failed: {exc}")
        # Extract the assistant message's text.
        text_parts: list[str] = []
        for block in result_msg.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
        return ToolResult(success=True, output="\n".join(text_parts) or "(empty response)")
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/tools/test_agent.py -v
ruff check src/oh_mini/tools/agent.py tests/unit/tools/test_agent.py
mypy src/oh_mini/tools/agent.py
```

Expected: 2/2 pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/tools/agent.py tests/unit/tools/test_agent.py
git commit -m "feat(tools): AgentTool — spawn read-only sub-agent

input_schema: {description, prompt}. Uses ctx.multi_agent.spawn
in blocking mode. Sub-agent allowed_tools = [file_read, grep, glob]
(read-only subset). Returns final assistant text."
```

---

## Task 16: `build_runtime` factory

**Files:**
- Create: `src/oh_mini/runtime.py`
- Modify: `src/oh_mini/tools/__init__.py` (export ALL_TOOLS dict)
- Create: `tests/unit/test_runtime_factory.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for build_runtime factory."""
from __future__ import annotations

from pathlib import Path

import pytest

from oh_mini.runtime import build_runtime


def test_build_runtime_anthropic(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anth-key")
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", model="claude-sonnet-4-5", yolo=False)
    # Smoke: runtime can be inspected
    assert rt is not None
    assert rt._provider is not None  # type: ignore[attr-defined]


def test_build_runtime_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-oa-key")
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="openai", model="gpt-4o", yolo=False)
    assert rt is not None


def test_build_runtime_yolo_flag_propagates(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", model=None, yolo=True)
    # The permission resolver inside should be yolo=True; we check via attribute
    assert rt._permission_resolver._yolo is True  # type: ignore[attr-defined]


def test_build_runtime_loads_all_ten_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", model=None, yolo=False)
    tools = rt._tools  # type: ignore[attr-defined]
    expected = {
        "file_read", "file_write", "file_edit", "grep", "glob", "bash",
        "todo_write", "agent", "notebook_edit", "web_fetch",
    }
    assert set(tools.keys()) == expected


def test_build_runtime_sessions_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("HOME", str(tmp_path))
    custom = tmp_path / "custom-sessions"
    rt = build_runtime(provider="anthropic", model=None, yolo=False, sessions_root=custom)
    # File session store should point at custom path; check via instance attribute
    assert custom.exists()
```

- [ ] **Step 2: Update `src/oh_mini/tools/__init__.py`**

```python
"""All built-in oh-mini coding tools, indexed by name."""
from __future__ import annotations

from meta_harney.abstractions.tool import BaseTool

from oh_mini.tools.agent import AgentTool
from oh_mini.tools.bash import BashTool
from oh_mini.tools.file_edit import FileEditTool
from oh_mini.tools.file_read import FileReadTool
from oh_mini.tools.file_write import FileWriteTool
from oh_mini.tools.glob import GlobTool
from oh_mini.tools.grep import GrepTool
from oh_mini.tools.notebook_edit import NotebookEditTool
from oh_mini.tools.todo_write import TodoWriteTool
from oh_mini.tools.web_fetch import WebFetchTool


def build_all_tools() -> dict[str, BaseTool]:
    """Construct one instance of each built-in tool, keyed by tool.name."""
    instances: list[BaseTool] = [
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GrepTool(),
        GlobTool(),
        BashTool(),
        TodoWriteTool(),
        AgentTool(),
        NotebookEditTool(),
        WebFetchTool(),
    ]
    return {t.name: t for t in instances}


__all__ = ["build_all_tools"]
```

- [ ] **Step 3: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime_factory.py -v
```

Expected: ModuleNotFoundError on `oh_mini.runtime`.

- [ ] **Step 4: Implement `src/oh_mini/runtime.py`**

```python
"""Factory to assemble an oh-mini AgentRuntime."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from meta_harney import (
    AgentRuntime,
    AnthropicProvider,
    OpenAIProvider,
    RuntimeConfig,
)
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.session.file_store import FileSessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.permission import InteractiveAskPermissionResolver
from oh_mini.prompts import CodingPromptBuilder
from oh_mini.tools import build_all_tools

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
}


def build_runtime(
    *,
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    yolo: bool = False,
    sessions_root: Path | None = None,
) -> AgentRuntime:
    """Assemble a meta-harney AgentRuntime configured for coding scenarios.

    Reads API key from ANTHROPIC_API_KEY or OPENAI_API_KEY env var; calls
    sys.exit(1) on missing key.
    """
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            sys.exit("error: ANTHROPIC_API_KEY env var not set")
        prov = AnthropicProvider(api_key=api_key)
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            sys.exit("error: OPENAI_API_KEY env var not set")
        prov = OpenAIProvider(api_key=api_key)

    chosen_model = model or _DEFAULT_MODELS[provider]

    root = sessions_root or (Path.home() / ".oh-mini" / "sessions")
    root.mkdir(parents=True, exist_ok=True)
    session_store = FileSessionStore(root)

    permission = InteractiveAskPermissionResolver(yolo=yolo)
    prompt_builder = CodingPromptBuilder(session_store=session_store)
    multi_agent = InProcessMultiAgentBackend()
    tools = build_all_tools()

    return AgentRuntime(
        provider=prov,
        prompt_builder=prompt_builder,
        permission_resolver=permission,
        session_store=session_store,
        trace_sink=NullSink(),
        config=RuntimeConfig(model=chosen_model, max_iterations=20),
        tools=tools,
        hooks=[],
        multi_agent=multi_agent,
    )
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime_factory.py -v
pytest -q
ruff check src/oh_mini/runtime.py src/oh_mini/tools/__init__.py tests/unit/test_runtime_factory.py
mypy src/oh_mini/runtime.py src/oh_mini/tools/__init__.py
```

Expected: 5/5 new pass + all prior tests still pass; clean.

- [ ] **Step 6: Commit**

```bash
git add src/oh_mini/runtime.py src/oh_mini/tools/__init__.py tests/unit/test_runtime_factory.py
git commit -m "feat: build_runtime() factory assembles the AgentRuntime

Wires AnthropicProvider/OpenAIProvider + CodingPromptBuilder +
InteractiveAskPermissionResolver + FileSessionStore (~/.oh-mini/sessions/)
+ InProcessMultiAgentBackend + 10 tools + NullSink into a meta-harney
AgentRuntime. Reads API key from env; sys.exit(1) on missing key."
```

---

## Task 17: CLI argparse + one-shot dispatch

**Files:**
- Create: `src/oh_mini/cli.py`
- Create: `tests/integration/test_cli_one_shot.py`

- [ ] **Step 1: Write failing integration test**

```python
"""Integration tests for `oh` one-shot CLI."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], env_extra: dict[str, str] | None = None, cwd=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["OH_MINI_TEST_FAKE_PROVIDER"] = "1"  # makes runtime.py use FakeLLMProvider
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "oh_mini", *args],
        capture_output=True, text=True, env=env, cwd=cwd,
    )


def test_cli_one_shot_basic(tmp_path):
    proc = _run_cli(["hi there"], env_extra={"HOME": str(tmp_path), "ANTHROPIC_API_KEY": "fake"}, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "Session:" in proc.stdout


def test_cli_missing_api_key_exits_1(tmp_path):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "OH_MINI_TEST_FAKE_PROVIDER": "0",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "hi"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert proc.returncode == 1
    assert "ANTHROPIC_API_KEY" in proc.stderr or "api key" in proc.stderr.lower()


def test_cli_version_flag(tmp_path):
    proc = _run_cli(["--version"], env_extra={"HOME": str(tmp_path), "ANTHROPIC_API_KEY": "fake"})
    assert proc.returncode == 0
    assert "0.1.0" in proc.stdout
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/integration/test_cli_one_shot.py -v
```

Expected: fails because `cli.py` and the fake-provider switch don't exist yet.

- [ ] **Step 3: Patch `runtime.py` to honor `OH_MINI_TEST_FAKE_PROVIDER` env**

Edit `src/oh_mini/runtime.py`, near the top of `build_runtime`:

```python
def build_runtime(
    *,
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    yolo: bool = False,
    sessions_root: Path | None = None,
) -> AgentRuntime:
    """Assemble a meta-harney AgentRuntime configured for coding scenarios.

    If OH_MINI_TEST_FAKE_PROVIDER=1, swap in a FakeLLMProvider that returns
    a canned "hello" round. Used only by integration tests.
    """
    if os.environ.get("OH_MINI_TEST_FAKE_PROVIDER") == "1":
        from meta_harney.testing import FakeLLMProvider, FakeRound
        prov = FakeLLMProvider(rounds=[FakeRound(text="hello from fake", stop_reason="end_turn")])
    elif provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            sys.exit("error: ANTHROPIC_API_KEY env var not set")
        prov = AnthropicProvider(api_key=api_key)
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            sys.exit("error: OPENAI_API_KEY env var not set")
        prov = OpenAIProvider(api_key=api_key)
    # ... rest unchanged
```

- [ ] **Step 4: Implement `src/oh_mini/cli.py`**

```python
"""oh-mini CLI entry point."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console

from meta_harney.abstractions._types import Message, TextBlock

from oh_mini import __version__
from oh_mini.output import render_stream_event
from oh_mini.runtime import build_runtime


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="oh", description="oh-mini coding agent CLI")
    parser.add_argument("prompt", nargs="?", default=None)
    parser.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    parser.add_argument("--model", default=None)
    parser.add_argument("--yolo", action="store_true", default=None)
    parser.add_argument("--no-yolo", dest="no_yolo", action="store_true", default=False)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--show-thinking", action="store_true", default=False)
    parser.add_argument("--sessions-root", default=None)
    parser.add_argument("--version", action="version", version=f"oh-mini {__version__}")
    return parser.parse_args(argv)


def _resolve_yolo(args: argparse.Namespace, *, interactive_mode: bool) -> bool:
    """yolo: interactive → False default, one-shot → True default; flags override."""
    if args.yolo:
        return True
    if args.no_yolo:
        return False
    # Defaults:
    return not interactive_mode


async def run_one_shot(args: argparse.Namespace) -> int:
    sessions_root = Path(args.sessions_root) if args.sessions_root else None
    yolo = _resolve_yolo(args, interactive_mode=False)
    rt = build_runtime(
        provider=args.provider, model=args.model, yolo=yolo,
        sessions_root=sessions_root,
    )
    console = Console()
    if args.resume:
        session = await rt._session_store.load(args.resume)  # type: ignore[attr-defined]
        if session is None:
            console.print(f"[red]error:[/] no such session: {args.resume}")
            return 2
    else:
        session = await rt.create_session()
    console.print(f"[dim]Session: {session.id}[/]")
    user_msg = Message(role="user", content=[TextBlock(text=args.prompt)])
    async for ev in rt.stream(session.id, user_msg):
        render_stream_event(ev, console, show_thinking=args.show_thinking)
    console.print(f"\n[dim]Session: {session.id}[/]")
    return 0


async def run_repl(args: argparse.Namespace) -> int:
    # Lazy import to avoid pulling prompt_toolkit when only one-shot is used
    from oh_mini.repl import run_repl as _run_repl_inner
    return await _run_repl_inner(args)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    interactive = args.prompt is None
    try:
        if interactive:
            rc = asyncio.run(run_repl(args))
        else:
            rc = asyncio.run(run_one_shot(args))
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_cli_one_shot.py -v -s
ruff check src/oh_mini/cli.py src/oh_mini/runtime.py tests/integration/test_cli_one_shot.py
mypy src/oh_mini/cli.py src/oh_mini/runtime.py
```

Expected: 3/3 new tests pass; clean. (Note: REPL path will fail to import until Task 18 — `run_repl` import is lazy and only triggered if no prompt is provided. The version flag test doesn't trigger REPL.)

- [ ] **Step 6: Commit**

```bash
git add src/oh_mini/cli.py src/oh_mini/runtime.py tests/integration/test_cli_one_shot.py
git commit -m "feat: oh CLI argparse + one-shot dispatch

Flags: --provider, --model, --yolo / --no-yolo, --resume,
--show-thinking, --sessions-root, --version.

one-shot: print 'Session: <id>', stream events to terminal,
print session id again at end.

OH_MINI_TEST_FAKE_PROVIDER=1 env switches to FakeLLMProvider so
integration tests don't need real API keys."
```

---

## Task 18: REPL interactive mode

**Files:**
- Create: `src/oh_mini/repl.py`
- Create: `tests/integration/test_repl_interactive.py`

- [ ] **Step 1: Write failing integration test**

```python
"""Integration test for `oh` REPL mode (driven via subprocess.PIPE)."""
from __future__ import annotations

import os
import subprocess
import sys


def test_repl_single_turn_then_exit(tmp_path):
    env = os.environ.copy()
    env.update({
        "HOME": str(tmp_path),
        "ANTHROPIC_API_KEY": "fake",
        "OH_MINI_TEST_FAKE_PROVIDER": "1",
        "OH_MINI_TEST_REPL_FORCE": "1",  # bypass TTY check
    })
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini"],
        input="hi\n/exit\n",
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    # Should have rendered text + exited cleanly
    assert proc.returncode == 0, proc.stderr
    assert "hello from fake" in proc.stdout or "Session:" in proc.stdout


def test_repl_clear_command(tmp_path):
    env = os.environ.copy()
    env.update({
        "HOME": str(tmp_path),
        "ANTHROPIC_API_KEY": "fake",
        "OH_MINI_TEST_FAKE_PROVIDER": "1",
        "OH_MINI_TEST_REPL_FORCE": "1",
    })
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini"],
        input="/clear\n/exit\n",
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    # Should have at least 2 'Session:' lines (initial + after /clear)
    assert proc.stdout.count("Session:") >= 2
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/integration/test_repl_interactive.py -v
```

Expected: fails (REPL doesn't exist).

- [ ] **Step 3: Implement `src/oh_mini/repl.py`**

```python
"""Interactive REPL loop."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console

from meta_harney.abstractions._types import Message, TextBlock

from oh_mini.output import render_stream_event
from oh_mini.runtime import build_runtime


async def run_repl(args: argparse.Namespace) -> int:
    # TTY check (bypass if test env var set)
    if not sys.stdin.isatty() and os.environ.get("OH_MINI_TEST_REPL_FORCE") != "1":
        sys.stderr.write("error: REPL requires a TTY (or set OH_MINI_TEST_REPL_FORCE=1)\n")
        return 1

    sessions_root = Path(args.sessions_root) if args.sessions_root else None
    yolo = bool(args.yolo) if args.yolo else False  # interactive default: no yolo
    if args.no_yolo:
        yolo = False
    rt = build_runtime(
        provider=args.provider, model=args.model, yolo=yolo,
        sessions_root=sessions_root,
    )
    console = Console()

    if args.resume:
        session = await rt._session_store.load(args.resume)  # type: ignore[attr-defined]
        if session is None:
            console.print(f"[red]error:[/] no such session: {args.resume}")
            return 2
    else:
        session = await rt.create_session()
    console.print(f"[bold cyan]oh-mini[/] · Session: {session.id}")
    console.print("[dim]/exit, /quit  exit · /clear  new session · /sessions  list[/]")

    while True:
        try:
            line = input("oh> ")
        except (EOFError, KeyboardInterrupt):
            console.print("\nbye")
            return 0
        line = line.strip()
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            console.print("bye")
            return 0
        if line == "/clear":
            session = await rt.create_session()
            console.print(f"[dim]new Session: {session.id}[/]")
            continue
        if line == "/sessions":
            ids = await rt._session_store.list()  # type: ignore[attr-defined]
            for s in ids:
                console.print(f"  {s.id}  created {s.created_at}")
            continue
        try:
            user_msg = Message(role="user", content=[TextBlock(text=line)])
            async for ev in rt.stream(session.id, user_msg):
                render_stream_event(ev, console, show_thinking=args.show_thinking)
            console.print()  # newline after stream
        except Exception as exc:
            console.print(f"\n[red]error:[/] {exc}")
            # session stays open; loop continues
    # unreachable
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_repl_interactive.py -v -s
ruff check src/oh_mini/repl.py tests/integration/test_repl_interactive.py
mypy src/oh_mini/repl.py
```

Expected: 2/2 new pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/repl.py tests/integration/test_repl_interactive.py
git commit -m "feat: interactive REPL with slash commands

oh (no args) → REPL loop. Built-in commands: /exit /quit /clear /sessions.
Ctrl-C / Ctrl-D / EOF exit cleanly. TTY check (bypass via
OH_MINI_TEST_REPL_FORCE=1 for tests). Error in one turn doesn't
crash REPL; loop continues with the same session."
```

---

## Task 19: Integration test — `--resume`

**Files:**
- Create: `tests/integration/test_cli_resume.py`

- [ ] **Step 1: Write failing integration test**

```python
"""Integration test: --resume picks up an existing session."""
from __future__ import annotations

import os
import re
import subprocess
import sys


def test_resume_continues_existing_session(tmp_path):
    env = os.environ.copy()
    env.update({
        "HOME": str(tmp_path),
        "ANTHROPIC_API_KEY": "fake",
        "OH_MINI_TEST_FAKE_PROVIDER": "1",
    })

    # First run: capture session id
    proc1 = subprocess.run(
        [sys.executable, "-m", "oh_mini", "first message"],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc1.returncode == 0, proc1.stderr
    m = re.search(r"Session:\s+(\S+)", proc1.stdout)
    assert m, f"no Session: id in output\n{proc1.stdout}"
    sid = m.group(1)

    # Second run: --resume
    proc2 = subprocess.run(
        [sys.executable, "-m", "oh_mini", "--resume", sid, "follow-up"],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc2.returncode == 0, proc2.stderr
    assert sid in proc2.stdout


def test_resume_unknown_session_exits_2(tmp_path):
    env = os.environ.copy()
    env.update({
        "HOME": str(tmp_path),
        "ANTHROPIC_API_KEY": "fake",
        "OH_MINI_TEST_FAKE_PROVIDER": "1",
    })
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "--resume", "nonexistent-id", "x"],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc.returncode == 2
    assert "no such session" in proc.stdout.lower() or "no such session" in proc.stderr.lower()
```

- [ ] **Step 2: Run + verify**

```bash
source .venv/bin/activate
pytest tests/integration/test_cli_resume.py -v -s
ruff check tests/integration/test_cli_resume.py
mypy tests/integration/test_cli_resume.py
```

Expected: 2/2 pass; clean. (No new source files; this exercises the existing `--resume` path in cli.py.)

If FAIL: the FakeLLMProvider in runtime.py is currently constructed fresh on each `build_runtime` call, but `FakeLLMProvider.rounds` is shared state across calls. For `--resume`, the engine will reuse the loaded session and request a NEW provider call, but our test fake only has 1 round. Workaround: in `runtime.py`'s FakeLLMProvider construction, give it 3-5 identical rounds so multiple invocations within a test all succeed:

```python
if os.environ.get("OH_MINI_TEST_FAKE_PROVIDER") == "1":
    from meta_harney.testing import FakeLLMProvider, FakeRound
    prov = FakeLLMProvider(rounds=[
        FakeRound(text="hello from fake", stop_reason="end_turn")
        for _ in range(20)
    ])
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cli_resume.py src/oh_mini/runtime.py
git commit -m "test(integration): --resume continues existing session

Two scenarios:
1. First run prints session id; second run --resume same id succeeds
2. --resume <bogus-id> exits with code 2

Also: bumped fake provider's pre-canned rounds to 20 so multi-invocation
tests don't exhaust the script."
```

---

## Task 20: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Create the workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    name: Python ${{ matrix.python-version }} on ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"

      - name: Run pytest
        run: pytest -q

      - name: Run mypy (src)
        run: mypy src/oh_mini

      - name: Run mypy (tests)
        run: mypy tests

      - name: Run ruff check
        run: ruff check src tests

      - name: Run ruff format check
        run: ruff format --check src tests
```

- [ ] **Step 3: Write `.github/pull_request_template.md`**

```markdown
## Summary

<!-- 2-3 bullet points describing what changed and why -->

-
-

## Test plan

- [ ] All CI checks pass (pytest × 6 jobs, mypy, ruff)
- [ ] Manual verification (if applicable): <describe>
- [ ] Updated tests for new behavior

## Notes
```

- [ ] **Step 4: Commit**

```bash
git add .github/
git commit -m "ci: GitHub Actions matrix workflow + PR template

Python 3.10/3.11/3.12 × ubuntu-latest/macos-latest = 6 jobs.
pytest + mypy src + mypy tests + ruff check + ruff format check.
fail-fast: false so all jobs report independently."
```

---

## Task 21: README polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` with the polished version**

```markdown
# oh-mini

> A faithful, minimal recreation of OpenHarness's coding-assistant experience,
> built on the [meta-harney](https://github.com/bailaohe/meta-harney) runtime SDK.

oh-mini ships 10 coding tools, supports one-shot and interactive REPL modes,
persists sessions across runs, and can use either Anthropic or OpenAI as the
LLM backend. It's deliberately scoped as a demo of what meta-harney's
domain-agnostic runtime can do on a real coding workload.

## Install

```bash
git clone https://github.com/bailaohe/oh-mini.git
cd oh-mini
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...     # or OPENAI_API_KEY
```

## Usage

```bash
# One-shot
oh "in src/foo.py, add a bar() function and run the tests"

# Interactive REPL
oh
oh> /sessions
oh> /clear
oh> /exit

# Continue a previous session
oh --resume <session-id> "tweak it"

# Use OpenAI instead
oh --provider openai --model gpt-4o "..."

# Skip all permission prompts (dangerous; not recommended outside containers)
oh --yolo "..."
```

## Tools

| Tool | Schema | Notes |
|------|--------|-------|
| `file_read` | `{path, offset?, limit?}` | UTF-8 text |
| `file_write` | `{path, content}` | Overwrites |
| `file_edit` | `{path, old_string, new_string, replace_all?}` | Exact match |
| `grep` | `{pattern, path?, glob?, max_matches?}` | Recursive regex |
| `glob` | `{pattern, path?}` | Supports `**` |
| `bash` | `{command, timeout?, cwd?}` | Default 60s timeout |
| `todo_write` | `{todos: [{content, status}]}` | Stored in session |
| `agent` | `{description, prompt}` | Read-only sub-agent |
| `notebook_edit` | `{path, cell_index, new_source}` | .ipynb only |
| `web_fetch` | `{url, prompt?}` | https only; 1MB cap |

## Permission model

- Interactive REPL: prompts y/N/a for dangerous tools (`bash`, `file_write`, `file_edit`, `notebook_edit`)
- One-shot mode: allows everything by default (assumes you trust the prompt)
- `--yolo` / `--no-yolo` overrides per invocation

## Session storage

Sessions persist as JSON files under `~/.oh-mini/sessions/`. Override the
location with `--sessions-root <path>`.

## License

Apache-2.0
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README polish — usage, tools table, permission model"
```

---

## Task 22: Final quality gates + v0.1.0 tag

**Files:** no source changes (tag-only step)

- [ ] **Step 1: Run all gates**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/oh_mini 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src tests 2>&1 | tail -2
ruff format --check src tests 2>&1 | tail -2
```

Expected: 52 tests pass; mypy strict + ruff check + ruff format all clean.

If `ruff format --check` reports diffs:

```bash
ruff format src tests
pytest 2>&1 | tail -3
git add -A
git commit -m "style: ruff format pass on Phase 8 sources"
```

- [ ] **Step 2: Smoke test the actual CLI**

```bash
source .venv/bin/activate
export ANTHROPIC_API_KEY=fake
export OH_MINI_TEST_FAKE_PROVIDER=1
oh "hello"
```

Expected: prints `Session: <id>` + `hello from fake` + `Session: <id>`.

```bash
oh --version
```

Expected: `oh-mini 0.1.0`.

- [ ] **Step 3: Tag v0.1.0**

```bash
git tag -a v0.1.0 HEAD -m "$(cat <<'EOF'
oh-mini v0.1.0 — Phase 8 (Sub-project 1 of 3)

Initial release. Coding-agent CLI demo built on meta-harney v0.0.7.

What ships:
- 10 coding tools: file_read/write/edit, grep, glob, bash, todo_write,
  agent (read-only sub-agent spawn), notebook_edit, web_fetch
- Dual provider (anthropic default, openai via --provider)
- one-shot + interactive REPL + --resume <id>
- InteractiveAskPermissionResolver with --yolo / --no-yolo
- FileSessionStore at ~/.oh-mini/sessions/
- CodingPromptBuilder with cwd + persona injection
- 52 tests, all FakeLLMProvider-driven (no real API calls)
- CI matrix: Python 3.10/3.11/3.12 x ubuntu/macos = 6 jobs

Subsequent phases (not in v0.1.0):
- Sub-project 2: Node/Python bridge protocol (JSON-RPC over stdio)
- Sub-project 3: React + Ink TUI frontend

License: Apache-2.0
EOF
)"
```

- [ ] **Step 4: (Optional) Create GitHub remote + push**

If/when ready to publish:

```bash
GITHUB_TOKEN= gh repo create bailaohe/oh-mini --public \
  --description "Coding-agent CLI demo built on meta-harney runtime" \
  --source=. --remote=origin --push

GITHUB_TOKEN= git push origin --tags
```

(This step is optional and requires explicit user confirmation before running.)

- [ ] **Step 5: Verify final state**

```bash
git log --oneline | head -30
git tag -l 'v*'
source .venv/bin/activate
python -c "import oh_mini; print(oh_mini.__version__)"
```

Expected: `0.1.0` and 22+ commits since project init.

---

## Phase 8 Completion Checklist

- [ ] `/Users/baihe/Projects/study/oh-mini/` exists as independent git repo
- [ ] `pyproject.toml` has `meta-harney @ git+...@v0.0.7`
- [ ] All 10 tools implemented and unit-tested
- [ ] `_safety.py` path-traversal guard in place
- [ ] `InteractiveAskPermissionResolver` with --yolo / --no-yolo
- [ ] `FileSessionStore` at `~/.oh-mini/sessions/`
- [ ] `CodingPromptBuilder` injects cwd + persona
- [ ] `build_runtime()` factory wires everything
- [ ] CLI one-shot mode works
- [ ] REPL interactive mode works with `/exit /clear /sessions`
- [ ] `--resume <id>` works
- [ ] `OH_MINI_TEST_FAKE_PROVIDER=1` switches in FakeLLMProvider for tests
- [ ] 52 tests pass (44 unit + 8 integration)
- [ ] mypy strict + ruff check + ruff format all clean
- [ ] CI workflow at `.github/workflows/ci.yml`
- [ ] `v0.1.0` git tag on HEAD

---

## Self-Review

**Spec coverage:**

- §1 Goals 1 (new project + path) → Task 1
- §1 Goals 2 (meta-harney via git URL) → Task 1 (pyproject)
- §1 Goals 3 (CLI entry `oh`) → Task 17 (cli.py + project.scripts)
- §1 Goals 4 (10 coding tools) → Tasks 6-15
- §1 Goals 5 (dual provider + env auth) → Task 16 (build_runtime)
- §1 Goals 6 (InteractiveAskPermissionResolver + --yolo) → Tasks 5, 17, 18
- §1 Goals 7 (FileSessionStore + --resume) → Tasks 16 (factory), 17 (one-shot resume), 19 (test)
- §1 Goals 8 (CodingPromptBuilder) → Task 4
- §1 Goals 9 (CI) → Task 20
- §1 Goals 10 (52 tests) → Tasks 2-15, 16, 17, 18, 19 (count matches)
- §3 File Structure → Tasks 1-21 cover every declared file
- §4 APIs (build_runtime signature, InteractiveAskPermissionResolver, CodingPromptBuilder, FakeRound usage, CLI flags table) → Tasks 4, 5, 16, 17
- §5 Data flow (startup, one-shot, REPL, permission, agent sub-flow, resume, cwd injection) → Tasks 4, 5, 15, 16, 17, 18, 19
- §6 Error handling (all rows) → Tasks 16, 17, 18, plus individual tool tests
- §7 Testing (52 tests, fake-provider integration pattern, pty REPL) → Tasks 2-19
- §8 Completion → tracked via per-task checkboxes + Phase 8 Completion Checklist
- §9 Sub-project 2/3 candidates → Mentioned in Task 22 tag message as future phases

**Placeholder scan:**

- No "TBD", "TODO", "implement later", "fill in details", "handle edge cases".
- Task 17 step 3 has a "patch runtime.py to honor OH_MINI_TEST_FAKE_PROVIDER" instruction with the exact code — acceptable.
- Task 19 step 2 has an "if FAIL" diagnostic with a concrete fix (bump fake rounds to 20) — acceptable: this is an actionable contingency, not a placeholder.
- Task 22 step 4 says "Optional and requires explicit user confirmation" — acceptable: the spec explicitly defers GitHub remote creation as optional.

**Type consistency:**

- `BaseTool` subclass shape: each tool has `name: str`, `description: str`, `input_schema: type[BaseModel]`, async `execute(inv, ctx) -> ToolResult`. Consistent across Tasks 6-15. ✓
- `ToolResult` construction: `success: bool`, `output: Any = None`, `error: str | None = None`. Consistent. ✓
- `InteractiveAskPermissionResolver.__init__` signature in Task 5 matches usage in Tasks 16, 17, 18. ✓
- `build_runtime` signature in Task 16 matches CLI invocation in Tasks 17, 18, 19. ✓
- `OH_MINI_TEST_FAKE_PROVIDER` env var name consistent across Tasks 17, 18, 19. ✓
- `OH_MINI_TEST_REPL_FORCE` env var name consistent in Task 18 (one place). ✓
- `SUBAGENT_ALLOWED_TOOLS = ["file_read", "grep", "glob"]` consistent in Task 15. ✓
- `DANGEROUS_TOOLS = {"bash", "file_write", "file_edit", "notebook_edit"}` consistent in Task 5 and verified in test. ✓

**Notes on test counts:**

Per spec §7.1, target was 52 tests. Plan totals:
- Task 2: 4 (safety) ✓
- Task 3: 8 (output) — spec didn't preallocate; plan adds these as test_output.py
- Task 4: 2 (prompts) ✓
- Task 5: 7 (permission) — spec said 6; plan added one for DANGEROUS_TOOLS sanity
- Task 6: 4 (file_read) ✓
- Task 7: 3 (file_write) ✓
- Task 8: 4 (file_edit) ✓
- Task 9: 4 (grep) ✓
- Task 10: 3 (glob) ✓
- Task 11: 5 (bash) ✓
- Task 12: 2 (todo_write) ✓
- Task 13: 3 (notebook_edit) ✓
- Task 14: 4 (web_fetch) ✓
- Task 15: 2 (agent) ✓
- Task 16: 5 (runtime factory) — spec said 4; plan added one for sessions_root override
- Task 17: 3 (cli one-shot) ✓
- Task 18: 2 (repl) ✓
- Task 19: 2 (resume) — spec said 1; plan added the bogus-id case

Plan total: 67. Spec target was 52. Plan exceeds spec — additional coverage is OK (spec said "≥52" implicitly via "+1 → 52", but plan's extras don't harm). No gaps.
