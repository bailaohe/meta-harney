# meta-harney Phase 9b — oh-mini Credentials + Config System 设计

**日期：** 2026-05-14
**目标产物：** oh-mini v0.2.0
**前置：** meta-harney v0.0.8（Provider Catalog 已发布）+ oh-mini v0.1.0

## 1. 目标与非目标

### 目标

Phase 9b 是 Phase 9 的下半段。目标是把 oh-mini 升级为一个**有完整凭证 + 配置系统**
的 CLI，镜像 OpenHarness 原版的 auth/config 体系。

具体交付：

1. **依赖升级**：`meta-harney @ git+...@v0.0.8`（使用新的 Provider Catalog）
2. **删除硬编码**：`runtime.py` 中的 `provider == "anthropic"` if/else 和 `_DEFAULT_MODELS`
   字典；改用 `meta_harney.BUILT_IN_PROVIDERS` + `provider_from_spec`
3. **新增凭证层** `src/oh_mini/auth/`：
   - `CredentialBackend` Protocol + `KeyringBackend` + `FileBackend`
   - `default_backend()` 自动探测（keyring 优先，file fallback）
   - `CredentialResolver` 按优先级解析：CLI flag > env > storage > 报错
4. **新增配置层** `src/oh_mini/config.py`：
   - 读写 `~/.oh-mini/settings.json`
   - `default_provider` / `default_profile`
   - `custom_providers` → 启动时 `register_provider()` 到 catalog
5. **CLI 子命令组**：argparse subparser 改造
   - `oh <prompt>` / `oh` REPL（保留 Phase 8 行为）
   - `oh auth login/list/remove/show --provider X [--profile Y]`
   - `oh providers list`
6. **新增 `--api-key` flag**：CLI 直接传 key（最高优先级）
7. **30 个新测试**（6+5+5+6+2+4+2，全部 Mock，无真 API 调用）
8. **可选依赖 `keyring`**：放在 `[project.optional-dependencies].full` 或主依赖里
9. **v0.2.0 release**：bump + tag + push + CI 6/6 全绿
10. **向后兼容**：v0.1.0 用户用 `ANTHROPIC_API_KEY` env var 继续可用（resolver 第 2 级）

### 非目标

- 凭证加密（明文文件 + keyring 已够）
- 远程同步
- Migration script（env var 兼容性已经覆盖了无缝迁移）
- 自定义 provider 的图形 UI（编辑 settings.json 即可）
- File lock（CLI short-lived，原子 rename 即可）
- 多用户共享凭证
- API key 轮换 / 过期管理
- 不修改任何 meta-harney 代码

## 2. 总体架构

```
┌─── 启动期 ─────────────────────────────────────┐
│ cli.main()                                       │
│   ↓                                              │
│ settings = load_settings()                       │
│   ↓ 读 ~/.oh-mini/settings.json                 │
│   ↓ 对每个 custom_providers 调 register_provider │
│   ↓ catalog 现含 9 内置 + N 自定义              │
│                                                  │
│ dispatch:                                        │
│   ├─ oh auth ... → auth.cli.handle_auth         │
│   ├─ oh providers list → list catalog            │
│   ├─ oh "task" → run_one_shot                    │
│   └─ oh → run_repl                               │
└──────────────────────────────────────────────────┘

┌─── prompt 路径 ────────────────────────────────┐
│ provider_name = args.provider or settings.default│
│ spec = BUILT_IN_PROVIDERS[provider_name]         │
│ api_key = resolver.resolve(provider_name, profile,│
│             cli_api_key=args.api_key)            │
│ ↓ 1. CLI flag                                    │
│ ↓ 2. env var <PROVIDER>_API_KEY                  │
│ ↓ 3. storage.get(CredentialKey(provider,profile))│
│ ↓ 4. NoCredentialError → CLI 友好退出            │
│ prov = provider_from_spec(spec, api_key=...)     │
│ rt = AgentRuntime(provider=prov, ...)            │
└──────────────────────────────────────────────────┘
```

**核心设计原则：**
- catalog（meta-harney v0.0.8）是 provider 元数据的**唯一权威源**
- resolver（oh-mini）是凭证查找的**唯一权威源**
- storage backend 互换（keyring ↔ file）不影响 resolver
- settings.json 是用户级配置，**不**存凭证

## 3. 文件结构

```
oh-mini/
├── src/oh_mini/
│   ├── __init__.py                # MOD — __version__ = "0.2.0"
│   ├── cli.py                     # MOD — subparser dispatch
│   ├── runtime.py                 # MOD — 用 catalog + resolver
│   ├── repl.py                    # MOD — 传递 resolver 给 runtime（如果需要）
│   ├── auth/                      # NEW
│   │   ├── __init__.py            # 公开 API + 异常
│   │   ├── storage.py             # Backend Protocol + 2 实现 + 探测
│   │   ├── resolver.py            # CredentialResolver
│   │   └── cli.py                 # auth login/list/remove/show
│   └── config.py                  # NEW — settings.json
│
├── pyproject.toml                 # MOD — version + meta-harney v0.0.8 + keyring dep
├── README.md                      # MOD — auth + 多 provider 用法
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

## 4. 关键 API 与契约

### 4.1 CredentialKey + CredentialBackend Protocol

```python
# src/oh_mini/auth/storage.py
@dataclass(frozen=True)
class CredentialKey:
    provider: str
    profile: str = "default"


class CredentialBackend(Protocol):
    def get(self, key: CredentialKey) -> str | None: ...
    def put(self, key: CredentialKey, secret: str) -> None: ...
    def delete(self, key: CredentialKey) -> bool: ...  # True if existed
    def list(self) -> list[CredentialKey]: ...


def default_backend() -> CredentialBackend:
    """Keyring if available, else FileBackend at ~/.oh-mini/credentials.json."""
    if _keyring_available():
        return KeyringBackend()
    return FileBackend(_default_credentials_path())


def _keyring_available() -> bool:
    """Probe + cache. Returns True if a system keyring backend is usable."""
    ...
```

### 4.2 KeyringBackend

```python
class KeyringBackend:
    """Uses the `keyring` library. Service name = 'oh-mini'.

    Encoding: username = f"{provider}:{profile}". Listing requires the
    keyring backend to support iteration (most do; if not we maintain a
    sidecar index file).
    """

    _SERVICE_NAME = "oh-mini"
    # Sidecar index lives at ~/.oh-mini/keyring-index.json — flat list of
    # CredentialKey shapes. We update it on put/delete to support list().

    def get(self, key: CredentialKey) -> str | None: ...
    def put(self, key: CredentialKey, secret: str) -> None: ...
    def delete(self, key: CredentialKey) -> bool: ...
    def list(self) -> list[CredentialKey]: ...
```

### 4.3 FileBackend

```python
class FileBackend:
    """Plain-text JSON at <path> with mode 0600."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, key: CredentialKey) -> str | None: ...
    def put(self, key: CredentialKey, secret: str) -> None:
        # mkdir -p parent
        # atomic: write to tmp file with mode 0600, then rename
        ...
    def delete(self, key: CredentialKey) -> bool: ...
    def list(self) -> list[CredentialKey]: ...
```

JSON schema:

```json
{
  "version": 1,
  "credentials": {
    "<provider>": {
      "<profile>": "<api_key>"
    }
  }
}
```

### 4.4 CredentialResolver

```python
class CredentialResolver:
    def __init__(self, backend: CredentialBackend) -> None:
        self._backend = backend

    def resolve(
        self,
        provider: str,
        profile: str = "default",
        *,
        cli_api_key: str | None = None,
    ) -> str:
        """Returns non-empty key or raises NoCredentialError.

        Priority:
        1. cli_api_key (if not None and non-empty)
        2. env var <PROVIDER>_API_KEY (if non-empty)
        3. self._backend.get(CredentialKey(provider, profile))
        4. raise NoCredentialError(provider, profile)
        """
        if cli_api_key:
            return cli_api_key
        env = os.environ.get(f"{provider.upper()}_API_KEY", "")
        if env:
            return env
        stored = self._backend.get(CredentialKey(provider, profile))
        if stored:
            return stored
        raise NoCredentialError(provider, profile)


class NoCredentialError(Exception):
    def __init__(self, provider: str, profile: str) -> None:
        super().__init__(f"no credential for {provider}/{profile}")
        self.provider = provider
        self.profile = profile
```

### 4.5 Config / Settings

```python
# src/oh_mini/config.py
@dataclass
class Settings:
    default_provider: str = "anthropic"
    default_profile: str = "default"


_DEFAULT_PATH = Path.home() / ".oh-mini" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Read settings.json if it exists; register custom_providers; return Settings.

    Errors:
    - Missing file → return Settings() (defaults)
    - Corrupt JSON → log warning to stderr, return Settings() (soft fail)
    - One bad custom_providers entry → log warning, skip that entry, continue
    """
    ...


def save_settings(s: Settings, path: Path | None = None) -> None:
    """Atomic write. Used by future `oh config set` (not in v0.2.0)."""
    ...


class ConfigError(Exception):
    """Raised on settings.json parse failures (catch + soft fallback at top level)."""
```

settings.json schema:

```json
{
  "default_provider": "deepseek",
  "default_profile": "default",
  "custom_providers": [
    {
      "name": "my-llama",
      "kind": "openai",
      "base_url": "http://192.168.1.100:8080/v1",
      "default_model": "llama-3.1-8b"
    }
  ]
}
```

加载时 `custom_providers` 中的每一项调用 `meta_harney.register_provider(ProviderSpec(...), overwrite=True)`。

### 4.6 runtime.build_runtime 改造

```python
# src/oh_mini/runtime.py 重写
def build_runtime(
    *,
    provider: str = "anthropic",          # ← 现在接受 catalog 任意 name
    model: str | None = None,
    api_key: str,                          # ← 调用方解析后传入
    yolo: bool = False,
    sessions_root: Path | None = None,
) -> AgentRuntime:
    if os.environ.get("OH_MINI_TEST_FAKE_PROVIDER") == "1":
        # 同 v0.1.0 路径
        prov = FakeLLMProvider(rounds=[FakeRound(text="hello from fake", stop_reason="end_turn") for _ in range(20)])
        chosen_model = model or "fake-model"
    else:
        if provider not in BUILT_IN_PROVIDERS:
            sys.exit(f"error: unknown provider {provider!r}. Try: oh providers list")
        spec = BUILT_IN_PROVIDERS[provider]
        prov = provider_from_spec(spec, api_key=api_key)
        chosen_model = model or spec.default_model

    # rest: same as v0.1.0
```

调用方（cli.py）负责 resolver.resolve()，把 api_key 传进来。

### 4.7 CLI subparser 改造

```python
# src/oh_mini/cli.py（结构示意）
def _build_parser():
    parser = argparse.ArgumentParser(prog="oh")
    sub = parser.add_subparsers(dest="cmd", required=False)

    # default prompt subcommand (no name; uses positional)
    parser.add_argument("prompt", nargs="?", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--no-yolo", dest="no_yolo", action="store_true")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--show-thinking", action="store_true")
    parser.add_argument("--sessions-root", default=None)
    parser.add_argument("--version", action="version", version=...)

    # auth subcommand group
    auth_parser = sub.add_parser("auth", help="manage credentials")
    auth_sub = auth_parser.add_subparsers(dest="auth_cmd", required=True)
    for name in ("login", "list", "remove", "show"):
        ap = auth_sub.add_parser(name)
        if name != "list":
            ap.add_argument("--provider", required=(name == "login"))
            ap.add_argument("--profile", default="default")

    # providers subcommand group
    prov_parser = sub.add_parser("providers", help="inspect provider catalog")
    prov_sub = prov_parser.add_subparsers(dest="prov_cmd", required=True)
    prov_sub.add_parser("list")

    return parser
```

Note: argparse 的 subparser 与 positional `prompt` 共存有些 tricky；细节在 plan 里处理。

## 5. Data flow

### 启动期：load settings → register custom providers

```
cli.main()
  → settings = load_settings()
       → JSON parse
       → for each custom_providers entry: register_provider(ProviderSpec(**entry), overwrite=True)
       → return Settings(default_provider, default_profile)
  → dispatch based on args.cmd
```

### 默认 prompt 路径

```
oh "task" --provider deepseek
  → settings 已加载
  → resolver = CredentialResolver(default_backend())
  → api_key = resolver.resolve("deepseek", "default", cli_api_key=args.api_key)
       → CLI → env → storage → NoCredentialError
  → rt = build_runtime(provider="deepseek", api_key=api_key, ...)
       → spec = BUILT_IN_PROVIDERS["deepseek"]
       → prov = provider_from_spec(spec, api_key)
  → 之后跟 v0.1.0 完全一样
```

### auth login

```
oh auth login --provider deepseek [--profile work]
  → 验证 provider 在 BUILT_IN_PROVIDERS 里
  → api_key = getpass.getpass(...)
  → backend = default_backend()
  → backend.put(CredentialKey("deepseek", "work"), api_key)
  → 打印 "saved deepseek/work → KeyringBackend"
```

### auth list

```
oh auth list
  → backend = default_backend()
  → keys = backend.list()
  → print table: provider, profile, backend, masked key
```

### auth remove

```
oh auth remove --provider deepseek [--profile work]
  → existed = backend.delete(CredentialKey("deepseek", "work"))
  → if existed: print "removed"
  → else: print "not found"  (idempotent, exit 0)
```

### auth show

```
oh auth show --provider deepseek
  → for profile in backend.list_profiles_for("deepseek"):
        print f"{profile}: {masked_key}"
```

### providers list

```
oh providers list
  → for name, spec in sorted(BUILT_IN_PROVIDERS.items()):
        print f"{name:<12} {spec.kind:<10} {spec.default_model:<25} {spec.base_url or '(default)':<40} {spec.description}"
```

## 6. Error handling

| 路径 | 行为 |
|---|---|
| `--provider <unknown>` | `sys.exit(2, "unknown provider: X. Try: oh providers list")` |
| 缺凭证 | `NoCredentialError` → CLI `sys.exit(1, "no credential for X/Y. Try: oh auth login --provider X")` |
| `oh auth login` 空 key | `sys.exit(1, "empty key, aborted")` |
| `oh auth remove` 不存在 | print "not found"; `sys.exit(0)` (idempotent) |
| `oh auth show` 无凭证 | print "no credentials for X"; `sys.exit(0)` |
| keyring 探测异常 | catch + fallback FileBackend；不暴露 keyring 内部错 |
| keyring 单次操作失败 | `CredentialStorageError`；CLI 打印 + 提示 |
| `credentials.json` 损坏 | `CredentialStorageError("corrupted: ...")` → CLI `sys.exit(1)` |
| `credentials.json` 权限不是 0600 | 启动时**警告** stderr，不阻塞读；写时强制 0600 |
| `credentials.json` 父目录不存在 | put 时 `mkdir -p` |
| `settings.json` 损坏 | `ConfigError`，warn 后 fall back to `Settings()`（软失败） |
| `custom_providers` 单项坏 | warn 跳过；其它项继续 |
| `custom_providers` name 冲突 | `register_provider(overwrite=True)` 强制替换 |
| `settings.default_provider` 未知 | 不在 load 时报错；prompt 时 `sys.exit(2)` |
| env var 空串 | resolver 跳过该级 |
| `--api-key` 空串 | resolver 跳过 |
| 并发写 credentials.json | 原子 rename，无 file lock |

**核心不变量：**

- `default_backend()` 永远返回有效 backend
- `resolver.resolve()` 要么返回非空字符串，要么抛 `NoCredentialError`
- 写凭证文件 → 永远 mode 0600
- `register_provider` 错误 **不能** 让启动失败

## 7. Testing

### 7.1 用例分布

| 文件 | 类型 | 用例数 |
|---|---|---|
| `tests/unit/auth/test_file_backend.py` | 新建 | 6 |
| `tests/unit/auth/test_keyring_backend.py` | 新建 | 5 |
| `tests/unit/auth/test_resolver.py` | 新建 | 5 |
| `tests/unit/test_config.py` | 新建 | 6 |
| `tests/unit/test_runtime_factory.py` | 修改 | +2 |
| `tests/integration/test_auth_cli.py` | 新建 | 4 |
| `tests/integration/test_cli_provider_catalog.py` | 新建 | 2 |
| 合计 | | **30** |

总测试数 67（v0.1.0）→ **97**（v0.2.0）

### 7.2 测试技术

- **不打真 API**：沿用 `OH_MINI_TEST_FAKE_PROVIDER=1`
- **keyring 全 mock**：`unittest.mock.patch`
- **FileBackend 用 `tmp_path`**：每测试隔离
- **Resolver 用 `InMemoryBackend` test fixture**
- **CLI 集成测试设 `HOME=tmp_path`**：隔离 `~/.oh-mini/`

### 7.3 主要测试点

详见 design 文档的 §7（Testing 节）—— 6 大测试模式：mode 0600、keyring 调用 mock、
resolver 优先级、config 加载 + register、auth login subprocess、`--provider deepseek` 走 catalog。

## 8. 版本号与发布

- `pyproject.toml`:
  - `version = "0.1.0"` → `"0.2.0"`
  - `meta-harney @ git+https://github.com/bailaohe/meta-harney.git@v0.0.8` （升 v0.0.7→v0.0.8）
  - 主依赖加 `keyring>=24`（强依赖；不可用则 fall back）
- `src/oh_mini/__init__.py`: `__version__ = "0.2.0"`
- README 更新 auth + 多 provider 部分
- git tag `v0.2.0`
- 不要求 push 到 GitHub remote（本 phase 范围）

## 9. 完成标准

- [ ] meta-harney 依赖升至 v0.0.8
- [ ] runtime.py 不再硬编码 provider；用 `BUILT_IN_PROVIDERS` + `provider_from_spec`
- [ ] `src/oh_mini/auth/` 子包存在，3 个模块 + `__init__.py`
- [ ] `KeyringBackend` + `FileBackend` 实现 `CredentialBackend` Protocol
- [ ] `default_backend()` 探测 keyring，fallback 到 FileBackend
- [ ] `CredentialResolver.resolve` 实现 4 级优先级
- [ ] `src/oh_mini/config.py` 读 settings.json + register custom_providers
- [ ] CLI subparser：`oh auth login/list/remove/show` + `oh providers list`
- [ ] `--api-key` 顶层 flag
- [ ] FileBackend 写文件 mode 0600
- [ ] settings.json 损坏 → 软失败（默认值继续）
- [ ] 30 个新测试通过
- [ ] 总测试 97/97 全绿
- [ ] mypy strict + ruff check + ruff format 全绿
- [ ] 版本号 0.2.0
- [ ] v0.2.0 git tag 本地

## 10. Phase 9c+ 候选

- `oh config set / show` 配置 CLI（修改 default_provider 等）
- 多用户共享 / 团队凭证
- 凭证加密（额外密码层）
- File lock（如确实需要并发安全）
- `oh providers add/remove`（动态修改 custom_providers）
- migration script v0.1.x → v0.2.x
