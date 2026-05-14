# meta-harney Phase 9a — Provider Catalog 设计

**日期：** 2026-05-14
**版本目标：** v0.0.8
**前置：** v0.0.7

## 1. 目标与非目标

### 目标

Phase 9a 给 meta-harney 加入**通用的 LLM provider catalog**，让所有 SDK 消费者
（oh-mini、未来的 bridge、其它应用）都能直接复用 8+ 个已知 provider（Anthropic、
OpenAI、Moonshot、DeepSeek、Gemini、MiniMax、NVIDIA、Dashscope、ModelScope），
而不必各自硬编码 base_url。

这是 Phase 9 拆出来的第一步：

```
Phase 9a (本 spec)  →  meta-harney v0.0.8  (Provider Catalog)
Phase 9b (下一步)   →  oh-mini v0.2.0      (消费 catalog + 凭证 + config 系统)
```

Phase 9a 不包含任何凭证存储、配置文件、CLI 子命令 —— 那些是 oh-mini 的应用层
关注点，Phase 9b 才做。

### 交付

1. **新模块** `src/meta_harney/providers/catalog.py`
2. **新公开 API**（加入 `meta_harney.__all__`）：
   - `ProviderSpec` (frozen dataclass)
   - `BUILT_IN_PROVIDERS: dict[str, ProviderSpec]`（9 个内置）
   - `provider_from_spec(spec, *, api_key, model=None) -> LLMProvider`（工厂）
   - `register_provider(spec, *, overwrite=False) -> None`（应用扩展入口）
3. **10 个单测** 在 `tests/unit/providers/test_catalog.py`
4. **v0.0.8 release** + tag

### 非目标

- 凭证存储 / keyring（Phase 9b）
- 配置文件 (`~/.oh-mini/settings.json`)（Phase 9b）
- CLI 子命令（Phase 9b）
- 凭证解析优先级（Phase 9b）
- profile 支持（Phase 9b）
- runtime URL 校验
- catalog 与 base_url 的健康检查
- Custom provider 持久化到磁盘（runtime register 即可，重启失效）

## 2. 总体架构

Catalog = **元数据字典 + 工厂函数**。零侵入式叠加在现有 Provider 类之上：

```
现有 v0.0.7 API（不动）：
  AnthropicProvider(api_key=..., base_url=..., default_max_tokens=...)
  OpenAIProvider(api_key=..., base_url=..., default_max_tokens=...)

新增 v0.0.8 API：
  ProviderSpec(name, kind, base_url, default_model, description)  ← 不可变数据
  BUILT_IN_PROVIDERS: dict[str, ProviderSpec]                      ← 模块级字典
  provider_from_spec(spec, api_key=...) -> LLMProvider             ← 工厂
  register_provider(spec, overwrite=False)                         ← 扩展入口
```

零 breaking change：v0.0.7 用户代码原样跑。

## 3. 文件结构

```
src/meta_harney/
├── __init__.py                                 # MODIFIED — 4 个新公开 API + 版本 0.0.8
└── providers/
    └── catalog.py                              # NEW

tests/
└── unit/providers/
    └── test_catalog.py                         # NEW

pyproject.toml                                  # MODIFIED — version 0.0.7 → 0.0.8
```

## 4. 关键 API 与契约

### 4.1 ProviderSpec

```python
@dataclass(frozen=True)
class ProviderSpec:
    name: str                                       # 唯一 id："anthropic", "moonshot"
    kind: Literal["anthropic", "openai"]            # 用哪个 Provider 类
    base_url: str | None                            # None = SDK 默认 endpoint
    default_model: str                              # 推荐 model id
    description: str = ""                           # 人读注释
```

`frozen=True`：实例字段不可改。要换 base_url 必须用 `register_provider` 重新注册。

### 4.2 BUILT_IN_PROVIDERS（9 个 spec）

```python
BUILT_IN_PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic":  ProviderSpec("anthropic",  "anthropic", None,                                             "claude-sonnet-4-5",            "Anthropic Claude (official)"),
    "openai":     ProviderSpec("openai",     "openai",    None,                                             "gpt-4o",                       "OpenAI (official)"),
    "moonshot":   ProviderSpec("moonshot",   "openai",    "https://api.moonshot.cn/v1",                     "kimi-k2-0905-preview",         "Moonshot AI (Kimi, OpenAI-compatible)"),
    "deepseek":   ProviderSpec("deepseek",   "openai",    "https://api.deepseek.com/v1",                    "deepseek-chat",                "DeepSeek (OpenAI-compatible)"),
    "gemini":     ProviderSpec("gemini",     "openai",    "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash",   "Google Gemini (OpenAI-compatible)"),
    "minimax":    ProviderSpec("minimax",    "openai",    "https://api.minimax.io/v1",                      "MiniMax-M2",                   "MiniMax (OpenAI-compatible)"),
    "nvidia":     ProviderSpec("nvidia",     "openai",    "https://integrate.api.nvidia.com/v1",            "meta/llama-3.1-405b-instruct", "NVIDIA NIM (OpenAI-compatible)"),
    "dashscope":  ProviderSpec("dashscope",  "openai",    "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-max",                  "Alibaba Dashscope (OpenAI-compatible)"),
    "modelscope": ProviderSpec("modelscope", "openai",    "https://api-inference.modelscope.cn/v1",         "Qwen/Qwen2.5-72B-Instruct",    "ModelScope (OpenAI-compatible)"),
}
```

字典是模块级，应用代码可直接读写（通过 `register_provider`）。

### 4.3 provider_from_spec

```python
def provider_from_spec(
    spec: ProviderSpec,
    *,
    api_key: str,
    model: str | None = None,
) -> LLMProvider:
    """Build an LLMProvider from a spec + api_key.

    `model` parameter is accepted for API symmetry but unused here;
    the engine consumes model via RuntimeConfig. Higher-level
    callers can use spec.default_model as their default.
    """
    if spec.kind == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=spec.base_url)
    if spec.kind == "openai":
        return OpenAIProvider(api_key=api_key, base_url=spec.base_url)
    raise ValueError(f"unknown provider kind: {spec.kind!r}")
```

### 4.4 register_provider

```python
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

### 4.5 公开导出

`src/meta_harney/__init__.py` 新增导出：

```python
from meta_harney.providers.catalog import (
    BUILT_IN_PROVIDERS,
    ProviderSpec,
    provider_from_spec,
    register_provider,
)
```

并加入 `__all__`（按字母顺序）。

## 5. Data flow

### 启动期

```
import meta_harney
  → providers/catalog.py 加载
  → BUILT_IN_PROVIDERS = {...}  (9 frozen specs)

应用可选：
  register_provider(ProviderSpec(name="my-local", ...))
  → BUILT_IN_PROVIDERS["my-local"] = spec
```

### 查询期

```
caller has provider name "deepseek" + api_key
  ↓
spec = BUILT_IN_PROVIDERS["deepseek"]  # raises KeyError if absent
  ↓
provider = provider_from_spec(spec, api_key="sk-...")
  ↓ kind == "anthropic" → AnthropicProvider(api_key=..., base_url=spec.base_url)
  ↓ kind == "openai"    → OpenAIProvider(api_key=..., base_url=spec.base_url)
  ↓ else                → ValueError
  ↓
provider ready for AgentRuntime
```

### base_url=None 的语义

- `AnthropicProvider(base_url=None)` → anthropic SDK 用默认 `https://api.anthropic.com`
- `OpenAIProvider(base_url=None)` → openai SDK fallback 到 `OPENAI_BASE_URL` env var → 没有则 `https://api.openai.com/v1`

## 6. Error handling

| 路径 | 行为 |
|---|---|
| `BUILT_IN_PROVIDERS[unknown_name]` | Python `KeyError`（不包装） |
| `provider_from_spec(spec, api_key="")` | 现有 `AnthropicProvider`/`OpenAIProvider` 抛 `ConfigurationError` |
| `register_provider(spec)` 名字冲突 + `overwrite=False` | `ValueError(f"provider {name!r} already registered")` |
| `register_provider(spec, overwrite=True)` | 静默替换 |
| `ProviderSpec(...)` 非法 kind（mypy 没拦到） | `ProviderSpec` 构造期不验证；`provider_from_spec` 时抛 `ValueError("unknown provider kind: ...")` |
| `spec.base_url = "..."` 改 frozen 实例 | `FrozenInstanceError` |
| 并发 `register_provider` | 不加锁（startup-time 操作；文档警告） |
| 非法 `base_url`（如 typo URL） | 不在 catalog 层校验；落到 SDK 请求时由 `httpx.ConnectError` → `RetryableProviderError` |

**核心不变量：**
- `BUILT_IN_PROVIDERS` 永远 truthy（至少含 anthropic + openai）
- `provider_from_spec(spec, api_key=非空)` 在 spec.kind ∈ {anthropic, openai} 时永不抛
- frozen ProviderSpec 字段不可变

## 7. Testing

### 7.1 用例分布

| 文件 | 类型 | 用例数 |
|---|---|---|
| `tests/unit/providers/test_catalog.py` | 新建 | 10 |

### 7.2 用例清单

1. `test_provider_spec_construction` — 构造 + 字段值正确
2. `test_provider_spec_is_frozen` — 修改字段抛 `FrozenInstanceError`
3. `test_provider_spec_with_invalid_kind_caught_by_mypy_not_runtime` — 构造非法 kind 不抛（mypy 拦截）
4. `test_built_in_providers_contains_all_nine` — 9 个 name 都在；spec.name 与 dict key 一致
5. `test_built_in_providers_anthropic_and_openai_have_none_base_url` — 这俩用 SDK 默认；其它 7 个有 https URL
6. `test_provider_from_spec_anthropic_constructs_anthropic_provider` — kind=anthropic → AnthropicProvider 实例
7. `test_provider_from_spec_openai_constructs_openai_provider` — kind=openai (moonshot) → OpenAIProvider；base_url 透传
8. `test_provider_from_spec_unknown_kind_raises` — cast 绕过 mypy 传 kind="vertex" → ValueError
9. `test_register_provider_adds_new_spec` — 注册新 name 成功；fixture teardown 清理
10. `test_register_provider_existing_name_without_overwrite_raises` — 同名 + overwrite=False → ValueError；overwrite=True → 成功覆盖

### 7.3 测试技术

- **不**打真 API；catalog 只做实例化，不发请求
- 用 `pytest` fixture (`_clean_register`) 在用例 9/10 之后清理 `BUILT_IN_PROVIDERS` 中非内置的条目，防污染后续测试
- 用 `typing.cast` 在用例 8 中绕过 mypy 的 `Literal` 检查

### 7.4 测试总数

305 (v0.0.7) → **315** (v0.0.8)

## 8. 版本号与发布

- `pyproject.toml`: `0.0.7` → `0.0.8`
- `src/meta_harney/__init__.py`:
  - `__version__ = "0.0.8"`
  - module docstring 更新提到 provider catalog
  - 4 个新公开 API 入 `__all__`
- 创建 git tag `v0.0.8`
- Push to GitHub remote（已建立的 `bailaohe/meta-harney`）
- 等 CI 6/6 job 全绿

## 9. 完成标准

- [ ] `src/meta_harney/providers/catalog.py` 存在
- [ ] `ProviderSpec` frozen dataclass
- [ ] `BUILT_IN_PROVIDERS` 含 9 个 spec
- [ ] `provider_from_spec` 工厂支持 anthropic + openai，未知 kind 抛 ValueError
- [ ] `register_provider` 支持 overwrite=False/True
- [ ] 4 个新 API 在 `meta_harney.__all__`
- [ ] 10 个新单测通过
- [ ] 全套测试 315/315 通过
- [ ] mypy strict + ruff check + ruff format 全绿
- [ ] 版本号升至 0.0.8
- [ ] `v0.0.8` git tag 推到 origin
- [ ] GHA CI 6 job 全绿

## 10. Phase 9b 衔接

oh-mini v0.2.0（下一个 phase，独立 brainstorm）会：

1. 升 meta-harney 依赖到 `v0.0.8`
2. 删掉 oh-mini 自己的 hardcode provider 列表
3. 用 `meta_harney.BUILT_IN_PROVIDERS` 做 provider name → spec 映射
4. 加凭证存储（keyring + ~/.oh-mini/credentials.json）
5. 加 `~/.oh-mini/settings.json` 配置文件
6. 加 `oh auth login/list/remove/show --provider` + `--profile`
7. 解析优先级：CLI flag > env > keyring > file > 报错
