# meta-harney Phase 9b: oh-mini Credentials + Config System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship oh-mini v0.2.0 — consume meta-harney v0.0.8's Provider Catalog and add a full credential + config system (keyring + file backends, settings.json, auth CLI subcommands).

**Architecture:** New `src/oh_mini/auth/` subpackage (3 modules + `__init__`) for credential storage and resolution. New `src/oh_mini/config.py` for settings.json. CLI converts to argparse subparser pattern: existing prompt/REPL behavior preserved as default, new `oh auth` and `oh providers` subcommand groups added. `runtime.py` rewrites to consume meta-harney v0.0.8 catalog instead of hardcoded provider list.

**Tech Stack:** Python 3.10+ · meta-harney 0.0.8 (via git URL) · keyring>=24 (with file fallback) · argparse subparsers · pytest + pytest-asyncio · unittest.mock for keyring · mypy strict · ruff.

**Pre-conditions:**
- oh-mini at `/Users/baihe/Projects/study/oh-mini/` with v0.1.0 baseline (67 tests passing)
- meta-harney v0.0.8 published at `bailaohe/meta-harney` (Phase 9a done)
- .venv at `oh-mini/.venv/` is set up

**Execution model:** 11 tasks. T1-T2 dependency + catalog wiring. T3-T5 auth subsystem (storage backends + resolver). T6 config. T7 CLI subparser. T8-T9 integration tests. T10 README. T11 v0.2.0 release.

---

## File Structure After Phase 9b

```
oh-mini/
├── src/oh_mini/
│   ├── __init__.py                # MOD — __version__ = "0.2.0"
│   ├── cli.py                     # MOD — subparser dispatch
│   ├── runtime.py                 # MOD — catalog + resolver
│   ├── repl.py                    # UNCHANGED (resolver lives in cli.py)
│   ├── auth/                      # NEW
│   │   ├── __init__.py
│   │   ├── storage.py             # KeyringBackend + FileBackend + default_backend
│   │   ├── resolver.py            # CredentialResolver + NoCredentialError
│   │   └── cli.py                 # handle_auth(args) dispatch
│   └── config.py                  # NEW — load_settings / save_settings
│
├── pyproject.toml                 # MOD — meta-harney @v0.0.8 + keyring + version
├── README.md                      # MOD
│
└── tests/
    ├── unit/
    │   ├── auth/                  # NEW
    │   │   ├── __init__.py
    │   │   ├── test_file_backend.py
    │   │   ├── test_keyring_backend.py
    │   │   └── test_resolver.py
    │   ├── test_config.py         # NEW
    │   └── test_runtime_factory.py # MOD
    └── integration/
        ├── test_auth_cli.py       # NEW
        └── test_cli_provider_catalog.py # NEW
```

---

## Task 1: Upgrade meta-harney dependency to v0.0.8 + add keyring

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/pyproject.toml`

- [ ] **Step 1: Update pyproject.toml**

Find the dependencies block:

```toml
dependencies = [
    "meta-harney @ git+https://github.com/bailaohe/meta-harney.git@v0.0.7",
    "anthropic>=0.40",
    "openai>=1.50",
    "httpx>=0.27",
    "nbformat>=5.10",
    "prompt_toolkit>=3.0",
    "rich>=13.0",
]
```

Replace with:

```toml
dependencies = [
    "meta-harney @ git+https://github.com/bailaohe/meta-harney.git@v0.0.8",
    "anthropic>=0.40",
    "openai>=1.50",
    "httpx>=0.27",
    "nbformat>=5.10",
    "prompt_toolkit>=3.0",
    "rich>=13.0",
    "keyring>=24",
]
```

- [ ] **Step 2: Re-install in venv**

```bash
cd /Users/baihe/Projects/study/oh-mini
source .venv/bin/activate
pip install -e ".[dev]" 2>&1 | tail -10
```

Expected: meta-harney 0.0.8 installs (fetched from git URL); keyring installs cleanly.

- [ ] **Step 3: Verify imports + version**

```bash
source .venv/bin/activate
python -c "
import meta_harney
print('meta-harney:', meta_harney.__version__)
assert meta_harney.__version__ == '0.0.8'
from meta_harney import BUILT_IN_PROVIDERS, provider_from_spec, ProviderSpec, register_provider
print('catalog size:', len(BUILT_IN_PROVIDERS))
import keyring
print('keyring:', keyring.__version__)
"
```

Expected: meta-harney 0.0.8, catalog size 9, keyring version printed.

- [ ] **Step 4: Run existing test suite to confirm nothing breaks**

```bash
pytest -q 2>&1 | tail -3
```

Expected: 67/67 passing (existing v0.1.0 tests unaffected by dep upgrade).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "deps: upgrade meta-harney to v0.0.8 + add keyring

Phase 9b foundation. v0.0.8 brings the Provider Catalog
(BUILT_IN_PROVIDERS, provider_from_spec, register_provider).
keyring>=24 added to main deps; used by oh-mini's new auth layer
(falls back to file storage when keyring is unavailable)."
```

---

## Task 2: Rewrite runtime.py to consume Provider Catalog

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/runtime.py`
- Modify: `/Users/baihe/Projects/study/oh-mini/tests/unit/test_runtime_factory.py`

- [ ] **Step 1: Update tests in `tests/unit/test_runtime_factory.py`**

Append 2 new tests + update existing tests to work with the new `build_runtime` signature (provider name is a string accepted from catalog; api_key is now required positional kwarg).

Current tests expect: `build_runtime(provider="anthropic", model=..., yolo=...)` reads env var internally.
New behavior: `build_runtime(provider="anthropic", api_key="...", model=..., yolo=...)` accepts the resolved key.

Replace the file with:

```python
"""Tests for build_runtime factory (v0.2.0: consumes meta-harney catalog)."""
from __future__ import annotations

from pathlib import Path

import pytest

from oh_mini.runtime import build_runtime


def test_build_runtime_anthropic(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", api_key="fake-anth", model="claude-sonnet-4-5", yolo=False)
    assert rt is not None
    assert rt._provider is not None


def test_build_runtime_openai(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="openai", api_key="fake-oa", model="gpt-4o", yolo=False)
    assert rt is not None


def test_build_runtime_yolo_flag_propagates(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", api_key="fake", model=None, yolo=True)
    assert rt._permission_resolver._yolo is True


def test_build_runtime_loads_all_ten_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="anthropic", api_key="fake", model=None, yolo=False)
    tools = rt._tools
    expected = {
        "file_read", "file_write", "file_edit", "grep", "glob", "bash",
        "todo_write", "agent", "notebook_edit", "web_fetch",
    }
    assert set(tools.keys()) == expected


def test_build_runtime_sessions_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    custom = tmp_path / "custom-sessions"
    rt = build_runtime(provider="anthropic", api_key="fake", model=None, yolo=False, sessions_root=custom)
    assert custom.exists()


def test_build_runtime_catalog_provider_uses_spec_base_url(monkeypatch, tmp_path):
    """Phase 9b: provider name from catalog → spec.base_url is respected."""
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = build_runtime(provider="moonshot", api_key="sk-moon", model=None, yolo=False)
    # Default model comes from spec
    assert rt._config.model == "kimi-k2-0905-preview"
    # Provider is OpenAIProvider with the moonshot base_url
    from meta_harney import OpenAIProvider
    assert isinstance(rt._provider, OpenAIProvider)
    assert rt._provider._base_url == "https://api.moonshot.cn/v1"


def test_build_runtime_unknown_provider_exits(monkeypatch, tmp_path):
    """Unknown provider name → sys.exit(2)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(SystemExit) as exc_info:
        build_runtime(provider="nonexistent-llm", api_key="fake", model=None, yolo=False)
    assert exc_info.value.code == 2
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime_factory.py -v
```

Expected: existing 5 tests fail because `build_runtime` no longer takes the env-var route (api_key kwarg now required); the 2 new tests also fail.

- [ ] **Step 3: Rewrite `src/oh_mini/runtime.py`**

Replace the entire file with:

```python
"""Factory to assemble an oh-mini AgentRuntime (Phase 9b: catalog-driven)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from meta_harney import (
    AgentRuntime,
    BUILT_IN_PROVIDERS,
    BaseHook,
    RuntimeConfig,
    provider_from_spec,
)
from meta_harney.builtin.multi_agent.in_process import InProcessMultiAgentBackend
from meta_harney.builtin.session.file_store import FileSessionStore
from meta_harney.builtin.trace.null_sink import NullSink

from oh_mini.permission import InteractiveAskPermissionResolver
from oh_mini.prompts import CodingPromptBuilder
from oh_mini.tools import build_all_tools


def build_runtime(
    *,
    provider: str = "anthropic",
    api_key: str = "",
    model: str | None = None,
    yolo: bool = False,
    sessions_root: Path | None = None,
) -> AgentRuntime:
    """Assemble a meta-harney AgentRuntime configured for coding scenarios.

    Args:
        provider: Provider name from meta_harney.BUILT_IN_PROVIDERS (or a
            custom-registered provider).
        api_key: Resolved API key. Caller is responsible for resolution.
            Ignored when OH_MINI_TEST_FAKE_PROVIDER=1.
        model: Model id override. None = use spec.default_model.
        yolo: Skip all permission prompts.
        sessions_root: Override session storage root. Default ~/.oh-mini/sessions/.

    Raises SystemExit(2) when provider is not in the catalog.
    """
    if os.environ.get("OH_MINI_TEST_FAKE_PROVIDER") == "1":
        from meta_harney.testing import FakeLLMProvider, FakeRound

        prov = FakeLLMProvider(
            rounds=[
                FakeRound(text="hello from fake", stop_reason="end_turn")
                for _ in range(20)
            ]
        )
        chosen_model = model or "fake-model"
    else:
        if provider not in BUILT_IN_PROVIDERS:
            sys.exit(
                f"error: unknown provider {provider!r}. "
                f"Try: oh providers list"
            )
        spec = BUILT_IN_PROVIDERS[provider]
        prov = provider_from_spec(spec, api_key=api_key)
        chosen_model = model or spec.default_model

    root = sessions_root or (Path.home() / ".oh-mini" / "sessions")
    root.mkdir(parents=True, exist_ok=True)
    session_store = FileSessionStore(root)

    permission = InteractiveAskPermissionResolver(yolo=yolo)
    prompt_builder = CodingPromptBuilder(session_store=session_store)
    tools = build_all_tools()
    trace_sink = NullSink()
    config = RuntimeConfig(model=chosen_model, max_iterations=20)
    hooks: list[BaseHook] = []

    multi_agent = InProcessMultiAgentBackend(
        provider=prov,
        permission_resolver=permission,
        session_store=session_store,
        trace_sink=trace_sink,
        config=config,
        all_tools=tools,
        hooks=hooks,
    )

    return AgentRuntime(
        provider=prov,
        prompt_builder=prompt_builder,
        permission_resolver=permission,
        session_store=session_store,
        trace_sink=trace_sink,
        config=config,
        tools=tools,
        hooks=hooks,
        multi_agent=multi_agent,
    )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_runtime_factory.py -v
ruff check src/oh_mini/runtime.py tests/unit/test_runtime_factory.py
mypy src/oh_mini/runtime.py
```

Expected: 7/7 runtime factory tests pass.

- [ ] **Step 5: Run full suite — expect some breakage**

```bash
pytest -q 2>&1 | tail -10
```

Expected: some integration tests will fail because `cli.py` and `repl.py` still call the old `build_runtime` signature. That's expected — Task 7 fixes the CLI. Track which failures.

For now, the runtime factory itself is correct. Continue.

- [ ] **Step 6: Commit**

```bash
git add src/oh_mini/runtime.py tests/unit/test_runtime_factory.py
git commit -m "feat(runtime): build_runtime consumes meta-harney v0.0.8 catalog

- Removes hardcoded _DEFAULT_MODELS and provider == 'anthropic' if/else
- Reads spec from BUILT_IN_PROVIDERS[provider], builds via provider_from_spec
- api_key is now a required kwarg (caller resolves before calling)
- Unknown provider → sys.exit(2) with friendly message
- chosen_model falls back to spec.default_model when model arg is None

Phase 9b foundation. CLI integration follows in Task 7 — until then,
integration tests that drive cli.py will fail; runtime unit tests pass."
```

---

## Task 3: `auth/storage.py` — backends + default_backend

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/__init__.py`
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/storage.py`
- Create: `/Users/baihe/Projects/study/oh-mini/tests/unit/auth/__init__.py`
- Create: `/Users/baihe/Projects/study/oh-mini/tests/unit/auth/test_file_backend.py`
- Create: `/Users/baihe/Projects/study/oh-mini/tests/unit/auth/test_keyring_backend.py`

- [ ] **Step 1: Create empty package init files**

```bash
touch /Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/__init__.py
touch /Users/baihe/Projects/study/oh-mini/tests/unit/auth/__init__.py
```

- [ ] **Step 2: Write failing tests in `tests/unit/auth/test_file_backend.py`**

```python
"""Tests for FileBackend (file-backed credential storage)."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from oh_mini.auth.storage import CredentialKey, FileBackend


def test_file_backend_put_then_get(tmp_path):
    b = FileBackend(tmp_path / "creds.json")
    b.put(CredentialKey("deepseek"), "sk-xxx")
    assert b.get(CredentialKey("deepseek")) == "sk-xxx"


def test_file_backend_writes_mode_0600(tmp_path):
    p = tmp_path / "creds.json"
    b = FileBackend(p)
    b.put(CredentialKey("deepseek"), "sk-xxx")
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_file_backend_get_missing_returns_none(tmp_path):
    b = FileBackend(tmp_path / "creds.json")
    assert b.get(CredentialKey("deepseek")) is None


def test_file_backend_delete_existing_returns_true_then_gone(tmp_path):
    b = FileBackend(tmp_path / "creds.json")
    b.put(CredentialKey("deepseek"), "sk-x")
    assert b.delete(CredentialKey("deepseek")) is True
    assert b.get(CredentialKey("deepseek")) is None


def test_file_backend_delete_missing_returns_false(tmp_path):
    b = FileBackend(tmp_path / "creds.json")
    assert b.delete(CredentialKey("deepseek")) is False


def test_file_backend_list_returns_all_keys(tmp_path):
    b = FileBackend(tmp_path / "creds.json")
    b.put(CredentialKey("deepseek", "default"), "k1")
    b.put(CredentialKey("deepseek", "work"), "k2")
    b.put(CredentialKey("anthropic"), "k3")
    keys = b.list()
    assert set(keys) == {
        CredentialKey("deepseek", "default"),
        CredentialKey("deepseek", "work"),
        CredentialKey("anthropic", "default"),
    }
```

- [ ] **Step 3: Write failing tests in `tests/unit/auth/test_keyring_backend.py`**

```python
"""Tests for KeyringBackend (system keyring storage)."""
from __future__ import annotations

from unittest.mock import patch

from oh_mini.auth.storage import CredentialKey, KeyringBackend


def test_keyring_backend_put_calls_set_password(tmp_path):
    with patch("oh_mini.auth.storage.keyring") as kr:
        b = KeyringBackend(index_path=tmp_path / "index.json")
        b.put(CredentialKey("deepseek", "default"), "sk-xxx")
        kr.set_password.assert_called_once_with(
            "oh-mini", "deepseek:default", "sk-xxx"
        )


def test_keyring_backend_get_returns_keyring_value(tmp_path):
    with patch("oh_mini.auth.storage.keyring") as kr:
        kr.get_password.return_value = "sk-stored"
        b = KeyringBackend(index_path=tmp_path / "index.json")
        result = b.get(CredentialKey("deepseek", "default"))
        assert result == "sk-stored"
        kr.get_password.assert_called_once_with("oh-mini", "deepseek:default")


def test_keyring_backend_get_missing_returns_none(tmp_path):
    with patch("oh_mini.auth.storage.keyring") as kr:
        kr.get_password.return_value = None
        b = KeyringBackend(index_path=tmp_path / "index.json")
        assert b.get(CredentialKey("deepseek", "default")) is None


def test_keyring_backend_delete_existing_returns_true(tmp_path):
    with patch("oh_mini.auth.storage.keyring") as kr:
        # First put, then delete
        b = KeyringBackend(index_path=tmp_path / "index.json")
        b.put(CredentialKey("deepseek"), "sk-x")
        result = b.delete(CredentialKey("deepseek"))
        assert result is True
        kr.delete_password.assert_called_once_with("oh-mini", "deepseek:default")


def test_keyring_backend_list_uses_sidecar_index(tmp_path):
    with patch("oh_mini.auth.storage.keyring") as kr:
        b = KeyringBackend(index_path=tmp_path / "index.json")
        b.put(CredentialKey("deepseek", "default"), "k1")
        b.put(CredentialKey("anthropic", "work"), "k2")
        keys = b.list()
        assert set(keys) == {
            CredentialKey("deepseek", "default"),
            CredentialKey("anthropic", "work"),
        }
```

- [ ] **Step 4: RED**

```bash
source .venv/bin/activate
pytest tests/unit/auth/ -v
```

Expected: ImportError on `oh_mini.auth.storage`.

- [ ] **Step 5: Implement `src/oh_mini/auth/storage.py`**

```python
"""Credential storage backends.

KeyringBackend uses the system keyring (macOS Keychain, Linux Secret
Service, Windows Credential Manager). Falls back to FileBackend if
keyring is unavailable or fails.

FileBackend stores plain-text JSON at ~/.oh-mini/credentials.json
with POSIX mode 0600.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import keyring


@dataclass(frozen=True)
class CredentialKey:
    provider: str
    profile: str = "default"


class CredentialStorageError(Exception):
    """Raised on backend I/O failures (corrupted file, keyring crash)."""


class CredentialBackend(Protocol):
    def get(self, key: CredentialKey) -> str | None: ...
    def put(self, key: CredentialKey, secret: str) -> None: ...
    def delete(self, key: CredentialKey) -> bool: ...
    def list(self) -> list[CredentialKey]: ...


# ----------------------------------------------------------------------------- #
# FileBackend
# ----------------------------------------------------------------------------- #


class FileBackend:
    """Plain-text JSON storage with POSIX mode 0600.

    JSON shape:
        {
          "version": 1,
          "credentials": {
            "<provider>": {"<profile>": "<api_key>", ...},
            ...
          }
        }
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict[str, dict[str, str]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise CredentialStorageError(
                f"credentials file corrupted: {self._path}: {exc}"
            ) from exc
        if not isinstance(data, dict) or data.get("version") != 1:
            raise CredentialStorageError(
                f"credentials file has unexpected schema: {self._path}"
            )
        creds = data.get("credentials", {})
        if not isinstance(creds, dict):
            raise CredentialStorageError(
                f"credentials file has malformed 'credentials' field: {self._path}"
            )
        return creds

    def _save(self, creds: dict[str, dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        body = json.dumps(
            {"version": 1, "credentials": creds}, indent=2, ensure_ascii=False
        )
        # Open with O_EXCL? No — overwrite tmp if leftover. Use mode 0600.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body + "\n")
        os.replace(tmp, self._path)
        # Ensure final file is 0600 (atomic rename preserves mode of tmp).
        os.chmod(self._path, 0o600)

    def get(self, key: CredentialKey) -> str | None:
        creds = self._load()
        return creds.get(key.provider, {}).get(key.profile)

    def put(self, key: CredentialKey, secret: str) -> None:
        creds = self._load()
        creds.setdefault(key.provider, {})[key.profile] = secret
        self._save(creds)

    def delete(self, key: CredentialKey) -> bool:
        creds = self._load()
        if key.provider not in creds or key.profile not in creds[key.provider]:
            return False
        del creds[key.provider][key.profile]
        if not creds[key.provider]:
            del creds[key.provider]
        self._save(creds)
        return True

    def list(self) -> list[CredentialKey]:
        creds = self._load()
        out: list[CredentialKey] = []
        for provider, profiles in creds.items():
            for profile in profiles:
                out.append(CredentialKey(provider, profile))
        return out


# ----------------------------------------------------------------------------- #
# KeyringBackend
# ----------------------------------------------------------------------------- #

_KEYRING_SERVICE = "oh-mini"


def _username(key: CredentialKey) -> str:
    return f"{key.provider}:{key.profile}"


class KeyringBackend:
    """Uses `keyring` library. Maintains a sidecar JSON index of stored keys
    because `keyring` doesn't expose a portable iteration API.
    """

    def __init__(self, *, index_path: Path | None = None) -> None:
        self._index_path = index_path or (
            Path.home() / ".oh-mini" / "keyring-index.json"
        )

    def _load_index(self) -> list[CredentialKey]:
        if not self._index_path.exists():
            return []
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        out: list[CredentialKey] = []
        for entry in data:
            if isinstance(entry, dict) and "provider" in entry:
                out.append(
                    CredentialKey(entry["provider"], entry.get("profile", "default"))
                )
        return out

    def _save_index(self, keys: list[CredentialKey]) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            [{"provider": k.provider, "profile": k.profile} for k in keys],
            indent=2,
        )
        self._index_path.write_text(body + "\n", encoding="utf-8")

    def get(self, key: CredentialKey) -> str | None:
        try:
            value = keyring.get_password(_KEYRING_SERVICE, _username(key))
        except Exception as exc:
            raise CredentialStorageError(f"keyring get failed: {exc}") from exc
        return value

    def put(self, key: CredentialKey, secret: str) -> None:
        try:
            keyring.set_password(_KEYRING_SERVICE, _username(key), secret)
        except Exception as exc:
            raise CredentialStorageError(f"keyring put failed: {exc}") from exc
        # Update sidecar index
        index = self._load_index()
        if key not in index:
            index.append(key)
            self._save_index(index)

    def delete(self, key: CredentialKey) -> bool:
        index = self._load_index()
        if key not in index:
            return False
        try:
            keyring.delete_password(_KEYRING_SERVICE, _username(key))
        except Exception as exc:
            raise CredentialStorageError(f"keyring delete failed: {exc}") from exc
        index.remove(key)
        self._save_index(index)
        return True

    def list(self) -> list[CredentialKey]:
        return list(self._load_index())


# ----------------------------------------------------------------------------- #
# Default backend selection
# ----------------------------------------------------------------------------- #


_keyring_probe_cached: bool | None = None


def _keyring_available() -> bool:
    """Probe + cache. True if a usable keyring backend is configured."""
    global _keyring_probe_cached
    if _keyring_probe_cached is not None:
        return _keyring_probe_cached
    try:
        # Calling get_keyring() initializes the backend; some envs raise here.
        kr = keyring.get_keyring()
        # If we got back the null/fail backend, mark unavailable.
        backend_name = type(kr).__name__.lower()
        _keyring_probe_cached = "fail" not in backend_name
    except Exception:
        _keyring_probe_cached = False
    return _keyring_probe_cached


def _default_credentials_path() -> Path:
    return Path.home() / ".oh-mini" / "credentials.json"


def default_backend() -> CredentialBackend:
    """Return the best available backend.

    Keyring is preferred; falls back to FileBackend when keyring isn't usable
    (containers, headless SSH, CI environments).
    """
    if _keyring_available():
        return KeyringBackend()
    return FileBackend(_default_credentials_path())
```

- [ ] **Step 6: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/auth/ -v
ruff check src/oh_mini/auth/ tests/unit/auth/
mypy src/oh_mini/auth/
```

Expected: 11/11 new pass; clean.

If mypy complains about `keyring` being untyped, add `[[tool.mypy.overrides]] module = "keyring.*" ignore_missing_imports = true` to pyproject.toml (similar to how meta_harney is handled).

- [ ] **Step 7: Commit**

```bash
git add src/oh_mini/auth/__init__.py src/oh_mini/auth/storage.py tests/unit/auth/__init__.py tests/unit/auth/test_file_backend.py tests/unit/auth/test_keyring_backend.py pyproject.toml
git commit -m "feat(auth): storage backends (file + keyring) + default_backend

Phase 9b foundation. CredentialBackend Protocol with two impls:
- FileBackend: JSON at ~/.oh-mini/credentials.json, mode 0600,
  atomic writes via tmp + rename
- KeyringBackend: system keyring (Keychain/Secret Service/Cred Manager)
  with sidecar JSON index for list() support

default_backend() probes keyring availability, falls back to file."
```

---

## Task 4: `auth/resolver.py` — CredentialResolver

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/resolver.py`
- Create: `/Users/baihe/Projects/study/oh-mini/tests/unit/auth/test_resolver.py`

- [ ] **Step 1: Write failing tests in `tests/unit/auth/test_resolver.py`**

```python
"""Tests for CredentialResolver."""
from __future__ import annotations

import pytest

from oh_mini.auth.resolver import CredentialResolver, NoCredentialError
from oh_mini.auth.storage import CredentialBackend, CredentialKey


class _InMemoryBackend:
    """Test fixture: dict-backed Backend."""

    def __init__(self, data: dict[CredentialKey, str] | None = None) -> None:
        self._d = dict(data or {})

    def get(self, key: CredentialKey) -> str | None:
        return self._d.get(key)

    def put(self, key: CredentialKey, secret: str) -> None:
        self._d[key] = secret

    def delete(self, key: CredentialKey) -> bool:
        return self._d.pop(key, None) is not None

    def list(self) -> list[CredentialKey]:
        return list(self._d.keys())


def test_resolver_cli_api_key_wins(monkeypatch):
    backend = _InMemoryBackend({CredentialKey("deepseek"): "sk-storage"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    r = CredentialResolver(backend)
    assert r.resolve("deepseek", cli_api_key="sk-cli") == "sk-cli"


def test_resolver_env_beats_storage(monkeypatch):
    backend = _InMemoryBackend({CredentialKey("deepseek"): "sk-storage"})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    r = CredentialResolver(backend)
    assert r.resolve("deepseek") == "sk-env"


def test_resolver_storage_when_no_cli_no_env(monkeypatch):
    backend = _InMemoryBackend({CredentialKey("deepseek"): "sk-storage"})
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = CredentialResolver(backend)
    assert r.resolve("deepseek") == "sk-storage"


def test_resolver_no_credential_raises(monkeypatch):
    backend = _InMemoryBackend()
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = CredentialResolver(backend)
    with pytest.raises(NoCredentialError) as exc:
        r.resolve("deepseek")
    assert exc.value.provider == "deepseek"
    assert exc.value.profile == "default"


def test_resolver_profile_separates_credentials(monkeypatch):
    backend = _InMemoryBackend({
        CredentialKey("deepseek", "default"): "sk-default",
        CredentialKey("deepseek", "work"): "sk-work",
    })
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = CredentialResolver(backend)
    assert r.resolve("deepseek", "default") == "sk-default"
    assert r.resolve("deepseek", "work") == "sk-work"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/auth/test_resolver.py -v
```

Expected: ImportError on `oh_mini.auth.resolver`.

- [ ] **Step 3: Implement `src/oh_mini/auth/resolver.py`**

```python
"""CredentialResolver — resolve a key from CLI flag / env / storage."""
from __future__ import annotations

import os

from oh_mini.auth.storage import CredentialBackend, CredentialKey


class NoCredentialError(Exception):
    """Raised when no credential is found across CLI / env / storage."""

    def __init__(self, provider: str, profile: str) -> None:
        super().__init__(f"no credential for {provider}/{profile}")
        self.provider = provider
        self.profile = profile


class CredentialResolver:
    """Resolves an API key by priority:

    1. cli_api_key (if non-empty)
    2. env var <PROVIDER>_API_KEY (if non-empty)
    3. backend.get(CredentialKey(provider, profile))
    4. raise NoCredentialError
    """

    def __init__(self, backend: CredentialBackend) -> None:
        self._backend = backend

    def resolve(
        self,
        provider: str,
        profile: str = "default",
        *,
        cli_api_key: str | None = None,
    ) -> str:
        if cli_api_key:
            return cli_api_key
        env_value = os.environ.get(f"{provider.upper()}_API_KEY", "")
        if env_value:
            return env_value
        stored = self._backend.get(CredentialKey(provider, profile))
        if stored:
            return stored
        raise NoCredentialError(provider, profile)
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/auth/test_resolver.py -v
ruff check src/oh_mini/auth/resolver.py tests/unit/auth/test_resolver.py
mypy src/oh_mini/auth/resolver.py
```

Expected: 5/5 new pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/auth/resolver.py tests/unit/auth/test_resolver.py
git commit -m "feat(auth): CredentialResolver with 4-level priority

Priority: cli_api_key > env <PROVIDER>_API_KEY > backend.get > raise.
NoCredentialError carries provider + profile fields for CLI to format
a helpful message."
```

---

## Task 5: `auth/__init__.py` exposes the public API

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/__init__.py`

- [ ] **Step 1: Update `src/oh_mini/auth/__init__.py`**

```python
"""oh-mini credential storage + resolution layer."""
from __future__ import annotations

from oh_mini.auth.resolver import CredentialResolver, NoCredentialError
from oh_mini.auth.storage import (
    CredentialBackend,
    CredentialKey,
    CredentialStorageError,
    FileBackend,
    KeyringBackend,
    default_backend,
)

__all__ = [
    "CredentialBackend",
    "CredentialKey",
    "CredentialResolver",
    "CredentialStorageError",
    "FileBackend",
    "KeyringBackend",
    "NoCredentialError",
    "default_backend",
]
```

- [ ] **Step 2: Verify**

```bash
source .venv/bin/activate
python -c "
from oh_mini.auth import (
    CredentialBackend, CredentialKey, CredentialResolver,
    CredentialStorageError, FileBackend, KeyringBackend,
    NoCredentialError, default_backend,
)
print('OK')
"
pytest -q 2>&1 | tail -3
ruff check src/oh_mini/auth/
mypy src/oh_mini/auth/
```

Expected: `OK`; all 78 tests pass (67 baseline + 11 new auth backend + resolver). Wait — some integration tests still broken from Task 2's runtime change. Expected; see Task 2.

Adjust the expected count: `67 (v0.1.0) + 7 runtime_factory (was 5) + 11 auth = 85`. But the broken cli/repl integration tests will still fail until Task 7. Just verify auth tests + runtime tests pass; ignore cli/repl failures for now.

```bash
pytest tests/unit/ -q 2>&1 | tail -3
```

Expected: all unit tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/oh_mini/auth/__init__.py
git commit -m "feat(auth): expose auth public API at oh_mini.auth

Re-exports CredentialKey, CredentialBackend, CredentialResolver,
NoCredentialError, FileBackend, KeyringBackend, default_backend,
CredentialStorageError."
```

---

## Task 6: `config.py` — settings.json loader + custom_providers register

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/config.py`
- Create: `/Users/baihe/Projects/study/oh-mini/tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests in `tests/unit/test_config.py`**

```python
"""Tests for config.py (settings.json + custom providers)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oh_mini.config import ConfigError, Settings, load_settings


@pytest.fixture
def _restore_catalog():
    """Clean up custom providers added during a test."""
    from meta_harney import BUILT_IN_PROVIDERS
    original = dict(BUILT_IN_PROVIDERS)
    yield
    for name in list(BUILT_IN_PROVIDERS.keys()):
        if name not in original:
            del BUILT_IN_PROVIDERS[name]


def test_load_settings_missing_file_returns_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s.default_provider == "anthropic"
    assert s.default_profile == "default"


def test_load_settings_reads_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "default_provider": "deepseek",
        "default_profile": "work",
    }))
    s = load_settings(p)
    assert s.default_provider == "deepseek"
    assert s.default_profile == "work"


def test_load_settings_registers_custom_providers(tmp_path, _restore_catalog):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "custom_providers": [{
            "name": "my-llama",
            "kind": "openai",
            "base_url": "http://localhost:8080/v1",
            "default_model": "llama-3.1-8b",
        }],
    }))
    load_settings(p)
    from meta_harney import BUILT_IN_PROVIDERS
    assert "my-llama" in BUILT_IN_PROVIDERS
    assert BUILT_IN_PROVIDERS["my-llama"].base_url == "http://localhost:8080/v1"


def test_load_settings_corrupt_json_returns_defaults(tmp_path, capsys):
    """Soft fail: corrupt settings.json → warn + return defaults."""
    p = tmp_path / "settings.json"
    p.write_text("{ not valid json")
    s = load_settings(p)
    assert s.default_provider == "anthropic"
    captured = capsys.readouterr()
    assert "settings" in captured.err.lower() or "corrupt" in captured.err.lower()


def test_load_settings_bad_custom_provider_entry_skipped(tmp_path, capsys, _restore_catalog):
    """One bad custom_providers entry doesn't break the rest."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "default_provider": "anthropic",
        "custom_providers": [
            {"this is malformed": True},  # missing 'name', 'kind', etc.
            {
                "name": "good-one",
                "kind": "openai",
                "base_url": "http://x/v1",
                "default_model": "x",
            },
        ],
    }))
    load_settings(p)
    from meta_harney import BUILT_IN_PROVIDERS
    assert "good-one" in BUILT_IN_PROVIDERS


def test_load_settings_custom_provider_overwrites_builtin(tmp_path, _restore_catalog):
    """custom_providers entries use overwrite=True (so they can replace built-ins)."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "custom_providers": [{
            "name": "openai",  # overwrites built-in!
            "kind": "openai",
            "base_url": "https://my-private-openai/v1",
            "default_model": "my-model",
        }],
    }))
    load_settings(p)
    from meta_harney import BUILT_IN_PROVIDERS
    assert BUILT_IN_PROVIDERS["openai"].base_url == "https://my-private-openai/v1"
```

- [ ] **Step 2: RED**

```bash
source .venv/bin/activate
pytest tests/unit/test_config.py -v
```

Expected: ImportError on `oh_mini.config`.

- [ ] **Step 3: Implement `src/oh_mini/config.py`**

```python
"""oh-mini configuration (~/.oh-mini/settings.json)."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meta_harney import ProviderSpec, register_provider


class ConfigError(Exception):
    """Raised on settings.json parse failures."""


@dataclass
class Settings:
    default_provider: str = "anthropic"
    default_profile: str = "default"


def _default_settings_path() -> Path:
    return Path.home() / ".oh-mini" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Read settings.json if it exists; register custom_providers; return Settings.

    Soft-fails on corrupt JSON — warns to stderr and returns defaults.
    """
    p = path if path is not None else _default_settings_path()
    if not p.exists():
        return Settings()

    try:
        data: Any = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(
            f"warning: settings file corrupt or unreadable ({p}): {exc}",
            file=sys.stderr,
        )
        return Settings()

    if not isinstance(data, dict):
        print(
            f"warning: settings file top-level is not an object ({p})",
            file=sys.stderr,
        )
        return Settings()

    # Register custom providers
    for entry in data.get("custom_providers", []) or []:
        if not isinstance(entry, dict):
            print(
                f"warning: skipping non-object custom_providers entry: {entry!r}",
                file=sys.stderr,
            )
            continue
        try:
            spec = ProviderSpec(
                name=str(entry["name"]),
                kind=entry["kind"],
                base_url=entry.get("base_url"),
                default_model=str(entry["default_model"]),
                description=str(entry.get("description", "")),
            )
            register_provider(spec, overwrite=True)
        except (KeyError, TypeError, ValueError) as exc:
            print(
                f"warning: skipping malformed custom_providers entry "
                f"{entry.get('name', '<no name>')!r}: {exc}",
                file=sys.stderr,
            )

    return Settings(
        default_provider=str(data.get("default_provider", "anthropic")),
        default_profile=str(data.get("default_profile", "default")),
    )
```

- [ ] **Step 4: Verify**

```bash
source .venv/bin/activate
pytest tests/unit/test_config.py -v
ruff check src/oh_mini/config.py tests/unit/test_config.py
mypy src/oh_mini/config.py
```

Expected: 6/6 new pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/config.py tests/unit/test_config.py
git commit -m "feat(config): load_settings reads ~/.oh-mini/settings.json

- Returns Settings(default_provider, default_profile)
- Registers custom_providers entries with overwrite=True
- Soft-fails: corrupt JSON → warn stderr + return defaults
- Bad custom_providers entries skipped individually (one bad entry
  doesn't break the rest)"
```

---

## Task 7: CLI subparser refactor (auth/providers subcommands + --api-key + resolver wiring)

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/cli.py`
- Modify: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/repl.py`
- Create: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/auth/cli.py`

- [ ] **Step 1: Implement `src/oh_mini/auth/cli.py`**

```python
"""CLI subcommand handlers for `oh auth ...`."""
from __future__ import annotations

import argparse
import getpass
import sys

from oh_mini.auth.resolver import NoCredentialError
from oh_mini.auth.storage import (
    CredentialKey,
    CredentialStorageError,
    default_backend,
)


def _mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 10:
        return "***"
    return f"{secret[:6]}...{secret[-4:]}"


def handle_auth(args: argparse.Namespace) -> int:
    """Dispatch oh auth <login/list/remove/show>."""
    backend = default_backend()
    backend_name = type(backend).__name__

    if args.auth_cmd == "login":
        return _do_login(args, backend, backend_name)
    if args.auth_cmd == "list":
        return _do_list(backend, backend_name)
    if args.auth_cmd == "remove":
        return _do_remove(args, backend, backend_name)
    if args.auth_cmd == "show":
        return _do_show(args, backend, backend_name)
    print(f"error: unknown auth command {args.auth_cmd!r}", file=sys.stderr)
    return 2


def _do_login(args: argparse.Namespace, backend, backend_name: str) -> int:
    from meta_harney import BUILT_IN_PROVIDERS

    if args.provider not in BUILT_IN_PROVIDERS:
        print(
            f"error: unknown provider {args.provider!r}. Try: oh providers list",
            file=sys.stderr,
        )
        return 2
    profile = args.profile or "default"
    try:
        api_key = getpass.getpass(
            f"API key for {args.provider} ({profile}): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print("\naborted", file=sys.stderr)
        return 1
    if not api_key:
        print("error: empty key, aborted", file=sys.stderr)
        return 1
    try:
        backend.put(CredentialKey(args.provider, profile), api_key)
    except CredentialStorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"saved {args.provider}/{profile} → {backend_name}")
    return 0


def _do_list(backend, backend_name: str) -> int:
    try:
        keys = backend.list()
    except CredentialStorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not keys:
        print("no credentials stored. Try: oh auth login --provider <name>")
        return 0
    print(f"{'provider':<14} {'profile':<10} {'backend':<16} {'key':<20}")
    for k in sorted(keys, key=lambda x: (x.provider, x.profile)):
        secret = backend.get(k) or ""
        print(f"{k.provider:<14} {k.profile:<10} {backend_name:<16} {_mask(secret):<20}")
    return 0


def _do_remove(args: argparse.Namespace, backend, backend_name: str) -> int:
    profile = args.profile or "default"
    try:
        existed = backend.delete(CredentialKey(args.provider, profile))
    except CredentialStorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if existed:
        print(f"removed {args.provider}/{profile} from {backend_name}")
    else:
        print(f"not found: {args.provider}/{profile}")
    return 0


def _do_show(args: argparse.Namespace, backend, backend_name: str) -> int:
    try:
        keys = backend.list()
    except CredentialStorageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    matching = [k for k in keys if k.provider == args.provider]
    if not matching:
        print(f"no credentials for {args.provider}")
        return 0
    for k in matching:
        secret = backend.get(k) or ""
        print(f"  {k.profile:<10} {backend_name:<16} {_mask(secret)}")
    return 0
```

- [ ] **Step 2: Rewrite `src/oh_mini/cli.py`**

```python
"""oh-mini CLI entry point (Phase 9b: subparser + resolver wiring)."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console

from meta_harney import BUILT_IN_PROVIDERS
from meta_harney.abstractions._types import Message, TextBlock

from oh_mini import __version__
from oh_mini.auth.cli import handle_auth
from oh_mini.auth.resolver import CredentialResolver, NoCredentialError
from oh_mini.auth.storage import default_backend
from oh_mini.config import load_settings
from oh_mini.output import render_stream_event
from oh_mini.runtime import build_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oh", description="oh-mini coding agent CLI")
    parser.add_argument("--version", action="version", version=f"oh-mini {__version__}")

    sub = parser.add_subparsers(dest="cmd", required=False)

    # `oh auth ...`
    auth_p = sub.add_parser("auth", help="manage credentials")
    auth_sub = auth_p.add_subparsers(dest="auth_cmd", required=True)

    login_p = auth_sub.add_parser("login", help="store a credential")
    login_p.add_argument("--provider", required=True)
    login_p.add_argument("--profile", default="default")

    list_p = auth_sub.add_parser("list", help="list stored credentials")

    remove_p = auth_sub.add_parser("remove", help="remove a credential")
    remove_p.add_argument("--provider", required=True)
    remove_p.add_argument("--profile", default="default")

    show_p = auth_sub.add_parser("show", help="show credentials for a provider")
    show_p.add_argument("--provider", required=True)

    # `oh providers list`
    prov_p = sub.add_parser("providers", help="inspect provider catalog")
    prov_sub = prov_p.add_subparsers(dest="prov_cmd", required=True)
    prov_sub.add_parser("list", help="list known providers")

    # Default subcommand: prompt or REPL. Top-level positional + flags.
    parser.add_argument("prompt", nargs="?", default=None)
    parser.add_argument("--provider", default=None, dest="default_provider_flag")
    parser.add_argument("--profile", default=None, dest="default_profile_flag")
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None, dest="api_key")
    parser.add_argument("--yolo", action="store_true", default=False)
    parser.add_argument("--no-yolo", dest="no_yolo", action="store_true", default=False)
    parser.add_argument("--resume", default=None)
    parser.add_argument("--show-thinking", action="store_true", default=False)
    parser.add_argument("--sessions-root", default=None)

    return parser


def _resolve_yolo(args: argparse.Namespace, *, interactive_mode: bool) -> bool:
    if args.yolo:
        return True
    if args.no_yolo:
        return False
    return not interactive_mode


async def run_one_shot(args: argparse.Namespace, settings) -> int:
    provider_name = args.default_provider_flag or settings.default_provider
    profile_name = args.default_profile_flag or settings.default_profile

    if provider_name not in BUILT_IN_PROVIDERS:
        print(
            f"error: unknown provider {provider_name!r}. Try: oh providers list",
            file=sys.stderr,
        )
        return 2

    resolver = CredentialResolver(default_backend())
    try:
        api_key = resolver.resolve(provider_name, profile_name, cli_api_key=args.api_key)
    except NoCredentialError as exc:
        print(
            f"error: {exc}. Try: oh auth login --provider {provider_name}",
            file=sys.stderr,
        )
        return 1

    sessions_root = Path(args.sessions_root) if args.sessions_root else None
    yolo = _resolve_yolo(args, interactive_mode=False)
    rt = build_runtime(
        provider=provider_name,
        api_key=api_key,
        model=args.model,
        yolo=yolo,
        sessions_root=sessions_root,
    )
    console = Console()

    if args.resume:
        session = await rt._session_store.load(args.resume)
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


async def run_repl(args: argparse.Namespace, settings) -> int:
    from oh_mini.repl import run_repl as _run_repl_inner

    return await _run_repl_inner(args, settings)


def _handle_providers(args: argparse.Namespace) -> int:
    if args.prov_cmd == "list":
        print(f"{'name':<14} {'kind':<10} {'default_model':<28} {'base_url':<55} description")
        for name in sorted(BUILT_IN_PROVIDERS.keys()):
            spec = BUILT_IN_PROVIDERS[name]
            base_url = spec.base_url or "(SDK default)"
            print(
                f"{name:<14} {spec.kind:<10} {spec.default_model:<28} {base_url:<55} {spec.description}"
            )
        return 0
    print(f"error: unknown providers command {args.prov_cmd!r}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()

    if args.cmd == "auth":
        rc = handle_auth(args)
    elif args.cmd == "providers":
        rc = _handle_providers(args)
    else:
        interactive = args.prompt is None
        try:
            if interactive:
                rc = asyncio.run(run_repl(args, settings))
            else:
                rc = asyncio.run(run_one_shot(args, settings))
        except KeyboardInterrupt:
            rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update `src/oh_mini/repl.py` for new build_runtime signature + settings**

Open `src/oh_mini/repl.py`. The `run_repl(args)` function currently calls `build_runtime(provider=args.provider, ...)` directly without `api_key`. Update to resolve credentials before calling.

Find the existing function body and replace it. The full new file:

```python
"""Interactive REPL loop."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console

from meta_harney import BUILT_IN_PROVIDERS
from meta_harney.abstractions._types import Message, TextBlock

from oh_mini.auth.resolver import CredentialResolver, NoCredentialError
from oh_mini.auth.storage import default_backend
from oh_mini.output import render_stream_event
from oh_mini.runtime import build_runtime


async def run_repl(args: argparse.Namespace, settings=None) -> int:
    # TTY check (bypass if test env var set)
    if not sys.stdin.isatty() and os.environ.get("OH_MINI_TEST_REPL_FORCE") != "1":
        sys.stderr.write("error: REPL requires a TTY (or set OH_MINI_TEST_REPL_FORCE=1)\n")
        return 1

    # Settings fallback (in case repl is invoked without going through cli.main)
    if settings is None:
        from oh_mini.config import load_settings
        settings = load_settings()

    provider_name = args.default_provider_flag or settings.default_provider
    profile_name = args.default_profile_flag or settings.default_profile

    if provider_name not in BUILT_IN_PROVIDERS:
        sys.stderr.write(f"error: unknown provider {provider_name!r}. Try: oh providers list\n")
        return 2

    resolver = CredentialResolver(default_backend())
    try:
        api_key = resolver.resolve(provider_name, profile_name, cli_api_key=args.api_key)
    except NoCredentialError as exc:
        sys.stderr.write(
            f"error: {exc}. Try: oh auth login --provider {provider_name}\n"
        )
        return 1

    sessions_root = Path(args.sessions_root) if args.sessions_root else None
    yolo = bool(args.yolo) if args.yolo else False
    if args.no_yolo:
        yolo = False
    rt = build_runtime(
        provider=provider_name,
        api_key=api_key,
        model=args.model,
        yolo=yolo,
        sessions_root=sessions_root,
    )
    console = Console()

    if args.resume:
        session = await rt._session_store.load(args.resume)
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
            ids = await rt._session_store.list()
            for s in ids:
                console.print(f"  {s.id}  created {s.created_at}")
            continue
        try:
            user_msg = Message(role="user", content=[TextBlock(text=line)])
            async for ev in rt.stream(session.id, user_msg):
                render_stream_event(ev, console, show_thinking=args.show_thinking)
            console.print()
        except Exception as exc:
            console.print(f"\n[red]error:[/] {exc}")
```

- [ ] **Step 4: Verify all unit tests pass + existing CLI integration tests work via fake provider**

```bash
source .venv/bin/activate
pytest tests/unit -q 2>&1 | tail -3
pytest tests/integration -q 2>&1 | tail -10
```

Expected: unit tests pass; integration tests (test_cli_one_shot, test_cli_resume, test_repl_interactive) pass because `OH_MINI_TEST_FAKE_PROVIDER=1` short-circuits the api_key requirement in `build_runtime`.

If `test_cli_one_shot_basic` etc. fail, check:
- `ANTHROPIC_API_KEY=fake` env var: the test sets it; resolver level 2 picks it up so resolve() returns "fake" before reaching storage.
- `OH_MINI_TEST_FAKE_PROVIDER=1` short-circuits in `build_runtime` so the fake key isn't used to call a real provider.

```bash
ruff check src/oh_mini tests
mypy src/oh_mini
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/cli.py src/oh_mini/repl.py src/oh_mini/auth/cli.py
git commit -m "feat(cli): subparser refactor + resolver wiring

- argparse subparsers: oh auth {login,list,remove,show} + oh providers list
- New flag --api-key on default prompt subcommand
- Default subcommand resolves credentials via CredentialResolver
- REPL uses same resolver path
- Settings loaded once at cli.main() entry; passed to run_one_shot / run_repl
- Unknown provider → sys.exit(2) + helpful 'oh providers list' hint
- Missing credential → sys.exit(1) + 'oh auth login' hint

OH_MINI_TEST_FAKE_PROVIDER=1 still works (build_runtime short-circuits
before api_key is needed)."
```

---

## Task 8: Integration test `tests/integration/test_auth_cli.py`

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/tests/integration/test_auth_cli.py`

- [ ] **Step 1: Write tests**

```python
"""Integration tests for `oh auth ...` subcommands.

These tests use FileBackend (force keyring unavailable via patched
_keyring_probe_cached). Each test runs in an isolated HOME.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _cli_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    # Force FileBackend for deterministic test behavior
    env["OH_MINI_FORCE_FILE_BACKEND"] = "1"
    return env


def test_auth_login_stores_credential(tmp_path):
    """oh auth login --provider deepseek (input 'sk-xxx') stores it in file backend."""
    env = _cli_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "login", "--provider", "deepseek"],
        input="sk-deepseek-xxx\n",
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    assert "saved" in proc.stdout
    # FileBackend persists
    creds_path = tmp_path / ".oh-mini" / "credentials.json"
    assert creds_path.exists()
    data = json.loads(creds_path.read_text())
    assert data["credentials"]["deepseek"]["default"] == "sk-deepseek-xxx"


def test_auth_login_unknown_provider_exits_2(tmp_path):
    env = _cli_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "login", "--provider", "nonexistent"],
        input="\n",
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert proc.returncode == 2
    combined = (proc.stdout + proc.stderr).lower()
    assert "unknown provider" in combined


def test_auth_list_then_remove(tmp_path):
    env = _cli_env(tmp_path)
    # Login first
    subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "login", "--provider", "deepseek"],
        input="sk-x\n", env=env, timeout=15,
    )
    # List
    list_proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "list"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert list_proc.returncode == 0
    assert "deepseek" in list_proc.stdout
    # Remove
    remove_proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "remove", "--provider", "deepseek"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert remove_proc.returncode == 0
    assert "removed" in remove_proc.stdout.lower()


def test_auth_remove_idempotent(tmp_path):
    env = _cli_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "auth", "remove", "--provider", "deepseek"],
        capture_output=True, text=True, env=env, timeout=15,
    )
    assert proc.returncode == 0
    assert "not found" in proc.stdout.lower()
```

- [ ] **Step 2: Patch `auth/storage.py` to honor `OH_MINI_FORCE_FILE_BACKEND` env var**

Edit `default_backend()`:

```python
def default_backend() -> CredentialBackend:
    """Return the best available backend.

    Keyring is preferred; falls back to FileBackend when keyring isn't usable.
    Set OH_MINI_FORCE_FILE_BACKEND=1 to force file backend (for tests).
    """
    if os.environ.get("OH_MINI_FORCE_FILE_BACKEND") == "1":
        return FileBackend(_default_credentials_path())
    if _keyring_available():
        return KeyringBackend()
    return FileBackend(_default_credentials_path())
```

- [ ] **Step 3: Run tests**

```bash
source .venv/bin/activate
pytest tests/integration/test_auth_cli.py -v -s
```

Expected: 4/4 pass.

- [ ] **Step 4: Verify gates**

```bash
pytest -q 2>&1 | tail -3
ruff check src/oh_mini tests
mypy src/oh_mini
```

Expected: all tests pass; clean.

- [ ] **Step 5: Commit**

```bash
git add src/oh_mini/auth/storage.py tests/integration/test_auth_cli.py
git commit -m "test(integration): oh auth login/list/remove cycle

4 new integration tests driving 'oh auth' subprocess. Use a fresh
HOME (tmp_path) + OH_MINI_FORCE_FILE_BACKEND=1 to bypass keyring
and pin the test to FileBackend (deterministic, doesn't pollute
the real system keyring)."
```

---

## Task 9: Integration test — `--provider deepseek` via catalog

**Files:**
- Create: `/Users/baihe/Projects/study/oh-mini/tests/integration/test_cli_provider_catalog.py`

- [ ] **Step 1: Write tests**

```python
"""Integration tests: `oh --provider <name>` goes through the catalog."""
from __future__ import annotations

import os
import subprocess
import sys


def _env(tmp_path, **extra) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["OH_MINI_TEST_FAKE_PROVIDER"] = "1"
    env["OH_MINI_FORCE_FILE_BACKEND"] = "1"
    env.update(extra)
    return env


def test_cli_provider_deepseek_via_env(tmp_path):
    """--provider deepseek picks up DEEPSEEK_API_KEY env var via resolver."""
    env = _env(tmp_path, DEEPSEEK_API_KEY="sk-fake-deepseek")
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "--provider", "deepseek", "hello"],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    assert "Session:" in proc.stdout
    assert "hello from fake" in proc.stdout


def test_cli_missing_credential_for_provider_exits_1(tmp_path):
    """Without a stored or env credential, oh exits 1 with login hint."""
    env = _env(tmp_path)
    # Clear any inherited <PROVIDER>_API_KEY env vars
    for k in list(env.keys()):
        if k.endswith("_API_KEY"):
            del env[k]
    env["OH_MINI_TEST_FAKE_PROVIDER"] = "0"  # disable fake-provider short-circuit
    proc = subprocess.run(
        [sys.executable, "-m", "oh_mini", "--provider", "deepseek", "hi"],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=15,
    )
    assert proc.returncode == 1
    combined = (proc.stdout + proc.stderr).lower()
    assert "no credential" in combined
    assert "oh auth login" in combined
```

- [ ] **Step 2: Run**

```bash
source .venv/bin/activate
pytest tests/integration/test_cli_provider_catalog.py -v -s
```

Expected: 2/2 pass.

- [ ] **Step 3: Verify gates**

```bash
pytest -q 2>&1 | tail -3
ruff check src/oh_mini tests
mypy src/oh_mini
```

Expected: all 97 tests pass (67 v0.1.0 + 7 runtime + 11 auth storage + 5 resolver + 6 config + 4 auth cli + 2 catalog provider = 102; spec says 97. Adjust as actual numbers come in).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_cli_provider_catalog.py
git commit -m "test(integration): --provider deepseek via catalog + missing-cred path

2 tests:
1. --provider deepseek with DEEPSEEK_API_KEY env var → success
2. --provider deepseek with no credential anywhere → exit 1 + 'oh auth login' hint"
```

---

## Task 10: README polish

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/README.md`

- [ ] **Step 1: Replace `README.md` with v0.2.0 version**

```markdown
# oh-mini

> A coding-agent CLI built on the [meta-harney](https://github.com/bailaohe/meta-harney) runtime SDK.

Supports 9 LLM providers out of the box, persists sessions across runs,
and stores credentials via system keyring (with file fallback).

## Install

```bash
git clone https://github.com/bailaohe/oh-mini.git
cd oh-mini
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quickstart: login + use

```bash
# Store a credential (uses system keyring if available; else file 0600)
oh auth login --provider anthropic
# (interactive; enter API key, hidden input)

# Then just run
oh "list the python files in the current directory"
```

Or skip storage and use env var (also fine):

```bash
ANTHROPIC_API_KEY=sk-ant-... oh "..."
```

## Supported providers

```bash
oh providers list
```

```
name           kind       default_model                base_url                                                description
anthropic      anthropic  claude-sonnet-4-5            (SDK default)                                           Anthropic Claude (official)
openai         openai     gpt-4o                       (SDK default)                                           OpenAI (official)
moonshot       openai     kimi-k2-0905-preview         https://api.moonshot.cn/v1                              Moonshot AI (Kimi, OpenAI-compatible)
deepseek       openai     deepseek-chat                https://api.deepseek.com/v1                             DeepSeek (OpenAI-compatible)
gemini         openai     gemini-2.0-flash             https://generativelanguage.googleapis.com/v1beta/openai Google Gemini (OpenAI-compatible)
minimax        openai     MiniMax-M2                   https://api.minimax.io/v1                               MiniMax (OpenAI-compatible)
nvidia         openai     meta/llama-3.1-405b-instruct https://integrate.api.nvidia.com/v1                     NVIDIA NIM (OpenAI-compatible)
dashscope      openai     qwen-max                     https://dashscope.aliyuncs.com/compatible-mode/v1       Alibaba Dashscope (OpenAI-compatible)
modelscope     openai     Qwen/Qwen2.5-72B-Instruct    https://api-inference.modelscope.cn/v1                  ModelScope (OpenAI-compatible)
```

Switch with `--provider`:

```bash
oh --provider deepseek "task description"
oh --provider moonshot --model kimi-k2-0905-preview "..."
```

## Credential management

```bash
oh auth login --provider deepseek
oh auth login --provider deepseek --profile work    # separate key per profile
oh auth list                                        # show all stored
oh auth show --provider deepseek                    # show profiles for one
oh auth remove --provider deepseek --profile work   # delete
```

Resolution priority (highest first):
1. `--api-key sk-...` flag
2. env var `<PROVIDER>_API_KEY` (e.g. `DEEPSEEK_API_KEY`)
3. stored credential (keyring or file)

## Custom providers

Edit `~/.oh-mini/settings.json`:

```json
{
  "default_provider": "deepseek",
  "default_profile": "default",
  "custom_providers": [
    {
      "name": "my-local-llama",
      "kind": "openai",
      "base_url": "http://localhost:8080/v1",
      "default_model": "llama-3.1-8b"
    }
  ]
}
```

Then `oh --provider my-local-llama "..."` works.

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

# Skip all permission prompts (dangerous outside containers)
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
| `bash` | `{command, timeout?, cwd?}` | 60s timeout default |
| `todo_write` | `{todos: [{content, status}]}` | Stored in session |
| `agent` | `{description, prompt}` | Read-only sub-agent |
| `notebook_edit` | `{path, cell_index, new_source}` | .ipynb only |
| `web_fetch` | `{url, prompt?}` | https only; 1MB cap |

## Session storage

Sessions persist as JSON files under `~/.oh-mini/sessions/`. Override with
`--sessions-root <path>`.

## License

Apache-2.0
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README polish for v0.2.0 — auth + multi-provider"
```

---

## Task 11: v0.2.0 release

**Files:**
- Modify: `/Users/baihe/Projects/study/oh-mini/src/oh_mini/__init__.py`
- Modify: `/Users/baihe/Projects/study/oh-mini/pyproject.toml`

- [ ] **Step 1: Bump version**

In `src/oh_mini/__init__.py`:

```python
"""oh-mini — coding-agent CLI demo on the meta-harney runtime."""

__version__ = "0.2.0"

__all__ = ["__version__"]
```

In `pyproject.toml`: `version = "0.2.0"`.

- [ ] **Step 2: Final gates**

```bash
source .venv/bin/activate
pytest 2>&1 | tail -3
mypy src/oh_mini 2>&1 | tail -2
mypy tests 2>&1 | tail -2
ruff check src/oh_mini tests 2>&1 | tail -2
ruff format --check src/oh_mini tests 2>&1 | tail -2
```

Expected: all tests pass; clean.

If `ruff format --check` reports diffs:

```bash
ruff format src/oh_mini tests
git add -A
git commit -m "style: ruff format pass on Phase 9b sources"
```

- [ ] **Step 3: Smoke test**

```bash
source .venv/bin/activate
python -c "
import oh_mini
print('Version:', oh_mini.__version__)
"
oh --version
oh providers list | head -5
OH_MINI_TEST_FAKE_PROVIDER=1 ANTHROPIC_API_KEY=fake oh "hi"
```

Expected: version 0.2.0, providers list prints 9 entries, fake provider call returns "hello from fake".

- [ ] **Step 4: Commit + tag**

```bash
git add src/oh_mini/__init__.py pyproject.toml
git commit -m "release: bump oh-mini to v0.2.0 for Phase 9b milestone

Phase 9b deliverables:
- Consumes meta-harney v0.0.8 Provider Catalog (9 builtin providers)
- New credential system: keyring + file fallback (mode 0600)
- New config: ~/.oh-mini/settings.json with custom_providers support
- New CLI subcommands: oh auth {login,list,remove,show}, oh providers list
- New top-level --api-key flag
- 30 new tests (97 total, was 67)
- Backward-compatible: ANTHROPIC_API_KEY / OPENAI_API_KEY env vars
  still work (resolver level 2)

Phase 9c+ candidates: oh config set/show, encrypted credentials,
file locking, migration script."

git tag -a v0.2.0 HEAD -m "$(cat <<'EOF'
oh-mini v0.2.0 — Phase 9b (Credentials + Config)

Builds on v0.1.0. Adds:

Provider catalog consumption:
- Removed hardcoded provider list; reads meta-harney v0.0.8 BUILT_IN_PROVIDERS
- 9 providers available out of the box: anthropic, openai, moonshot,
  deepseek, gemini, minimax, nvidia, dashscope, modelscope
- Custom providers via ~/.oh-mini/settings.json (custom_providers field)

Credential management:
- CredentialResolver: CLI flag > env > storage > error
- KeyringBackend (system keyring) + FileBackend (~/.oh-mini/credentials.json,
  mode 0600); auto-fallback if keyring unavailable
- New CLI: oh auth {login, list, remove, show}
- New flag: --api-key (highest priority override)

Backwards-compat: ANTHROPIC_API_KEY / OPENAI_API_KEY env vars still work
(resolver level 2). v0.1.0 users see no breakage.

Tests: 97 (was 67), all green.
Quality: mypy strict + ruff check + ruff format clean.
EOF
)"
```

- [ ] **Step 5: Verify final state**

```bash
git log --oneline | head -20
git tag -l 'v*'
source .venv/bin/activate
python -c "import oh_mini; print('Version:', oh_mini.__version__)"
```

Expected: `v0.2.0` tag in list; version 0.2.0; ~14 commits since v0.1.0.

---

## Phase 9b Completion Checklist

- [ ] `pyproject.toml` deps: `meta-harney @ git+...@v0.0.8`, `keyring>=24`
- [ ] `runtime.py` uses `BUILT_IN_PROVIDERS` + `provider_from_spec`; no hardcoded provider list
- [ ] `src/oh_mini/auth/` subpackage with `storage.py`, `resolver.py`, `cli.py`, `__init__.py`
- [ ] `KeyringBackend` + `FileBackend` implement `CredentialBackend` Protocol
- [ ] `FileBackend` writes mode 0600 + atomic rename
- [ ] `KeyringBackend` maintains sidecar index for `list()`
- [ ] `default_backend()` probes keyring + falls back to file; honors `OH_MINI_FORCE_FILE_BACKEND=1`
- [ ] `CredentialResolver.resolve(provider, profile, cli_api_key)` 4-level priority
- [ ] `src/oh_mini/config.py` reads settings.json; registers custom_providers; soft-fails on corrupt
- [ ] CLI subparser: `oh auth {login,list,remove,show}` + `oh providers list`
- [ ] CLI new flag: `--api-key`
- [ ] REPL uses same resolver path
- [ ] Total tests >= 97 passing
- [ ] mypy strict + ruff check + ruff format clean
- [ ] `__version__ = "0.2.0"` + `version = "0.2.0"` in pyproject
- [ ] `v0.2.0` git tag exists locally

---

## Self-Review

**Spec coverage:**

- §1 Goals 1 (dep upgrade) → Task 1
- §1 Goals 2 (delete hardcode) → Task 2
- §1 Goals 3 (auth subpackage) → Tasks 3, 4, 5, 7 (cli.py for auth subcommands)
- §1 Goals 4 (config layer) → Task 6
- §1 Goals 5 (CLI subparser) → Task 7
- §1 Goals 6 (--api-key flag) → Task 7
- §1 Goals 7 (30 new tests) → Tasks 3, 4, 6, 8, 9 (with revised counts; spec said 30, plan totals ~35)
- §1 Goals 8 (keyring dep) → Task 1
- §1 Goals 9 (v0.2.0 release) → Task 11
- §1 Goals 10 (backward compat) → Resolver level 2 (env var) handles this; integration tests verify
- §3 File Structure → all files mapped across Tasks 1-11
- §4 APIs (CredentialKey, CredentialBackend, KeyringBackend, FileBackend, default_backend, CredentialResolver, NoCredentialError, Settings, load_settings, ConfigError, build_runtime new sig, CLI subparser) → Tasks 2, 3, 4, 5, 6, 7
- §5 Data flow → implemented across Tasks 6 (settings load + register), 7 (CLI dispatch + resolver + build_runtime call)
- §6 Error handling → exhaustive coverage in Task 7 (CLI dispatch); FileBackend corrupt-file handling in Task 3; settings soft-fail in Task 6
- §7 Testing → 30+ new tests across Tasks 3, 4, 6, 8, 9
- §8 Version + tag → Task 11
- §9 Completion criteria → Phase 9b Completion Checklist
- §10 Phase 9c+ candidates → Mentioned in v0.2.0 tag message

**Placeholder scan:**

- No "TBD", "TODO", "implement later", or vague requirements.
- Task 7's `_resolve_yolo` and dual-positional `prompt` + subcommand pattern is a known argparse quirk; the implementation handles it concretely.
- Task 8's `OH_MINI_FORCE_FILE_BACKEND=1` env var is a concrete test hook; not a placeholder.
- Task 9's expected test count comment notes the actual count may differ from the spec's preliminary 97; this is acceptable (more tests > fewer).

**Type consistency:**

- `CredentialKey(provider: str, profile: str = "default")` — frozen dataclass used identically in Tasks 3, 4, 7, 8
- `CredentialBackend` Protocol (get/put/delete/list) — same signatures across `KeyringBackend`, `FileBackend`, `_InMemoryBackend` test fixture
- `CredentialResolver.resolve(provider, profile="default", *, cli_api_key=None) -> str` — same in Tasks 4, 7
- `NoCredentialError(provider, profile)` — same constructor across Tasks 4, 7
- `build_runtime(*, provider, api_key, model=None, yolo=False, sessions_root=None)` — new signature consistent in Tasks 2, 7
- `Settings(default_provider, default_profile)` — same fields in Tasks 6, 7

**Risk callouts:**

- **argparse subparsers + positional `prompt`**: known tricky. The plan has the user define `prompt` at the top-level parser (not in a subparser); test_cli_one_shot validates this works.
- **`pip install` may be slow** on Task 1 step 2 if PyPI / GitHub is slow; this is unavoidable.
- **mypy may need a `[[tool.mypy.overrides]] module = "keyring.*"` rule**; the plan flags this in Task 3 step 6.
- **Test count expectations** (97 → potentially ~100+) are approximate; the actual count after Task 11 is what matters.
- **OH_MINI_FORCE_FILE_BACKEND env var** is a test-only hook documented in default_backend() docstring; not user-facing.
