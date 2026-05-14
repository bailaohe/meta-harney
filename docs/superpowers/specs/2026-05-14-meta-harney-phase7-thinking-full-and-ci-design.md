# meta-harney Phase 7 — ThinkingDelta 完整模式 + GitHub Remote/CI 设计

**日期：** 2026-05-14
**版本目标：** v0.0.7
**前置：** v0.0.6（Phase 6 — Stabilize）

## 1. 目标与非目标

### 目标

Phase 7 包含两条相互独立的工作流，**目标统一发布 v0.0.7**：

**A. ThinkingDelta 完整模式（Anthropic extended thinking 持久化）**

1. 新增 `ThinkingBlock(text: str, signature: str)` 与 `RedactedThinkingBlock(data: str)` 进 ContentBlock 体系
2. `AnthropicProvider` 在 stream 期间发新事件 `ProviderThinkingBlock` / `ProviderRedactedThinking`
3. Engine 把新事件追加到 `assistant_blocks`，进 `session.messages`
4. `_convert_messages_to_anthropic` 回传时识别新 block 类型并发回 Anthropic wire format（含 signature/data）
5. `OpenAIProvider._convert_messages_to_openai` 见到新 block 类型时跳过（OpenAI 不接受）
6. 保留 Phase 6 的实时流 `ProviderThinkingDelta` → `StreamEvent.ThinkingDelta`（双路径并存）
7. SessionStore（Memory + File）自动支持新 block 类型（Pydantic discriminated union）

**B. GitHub Remote + CI Matrix**

1. 在 GitHub 新建 **public** 仓库 `meta-harney`
2. 配置 `origin` remote、首次 push 主线 + tags
3. 新建 `.github/workflows/ci.yml`：Python 3.10/3.11/3.12 × ubuntu-latest/macos-latest = 6 个 job
4. 每个 job 跑 `pytest -q` + `mypy src tests` + `ruff check` + `ruff format --check`
5. Coverage 测量但**不强制阈值**（先收集基线，spec §8.6 的 80% 留后续 Phase）
6. 新建 `.github/pull_request_template.md`
7. README 替换占位 badges 为实际 GHA badge + license badge

### 非目标

- **Coverage 阈值绝对值**（先建立基线、后续 Phase 定）
- **PyPI 发包**（后续 Phase）
- **Windows 矩阵**（spec §8.6 只列 Linux + macOS）
- **release.yml workflow**（v0.0.7 仍走本地打 tag 流程）
- **`__init__.py` 导出层级重组**（YAGNI，按用户决策）
- **ThinkingBlock 在 OpenAI 路径上的等价处理**（OpenAI 没有这个概念，跳过即可）
- **redacted_thinking 内容的解密展示**（data 字段保持 opaque）

## 2. 总体架构

两条工作流互相独立、无内部依赖。**执行顺序：A 先做，B 后做**（A 是纯代码改动可回滚；B 涉及不可逆动作 — repo 创建）。

```
工作流 A：ThinkingDelta 完整模式（代码改动）
  ↓ A 全绿后
工作流 B：GitHub Remote + CI（仓库创建 + CI 配置）
  ↓
v0.0.7 release + tag（本地 + push）
```

## 3. 文件结构

### 工作流 A

```
src/meta_harney/
├── __init__.py                                # MODIFIED — 导出 4 个新类型 + 版本 0.0.7
├── abstractions/
│   ├── __init__.py                            # MODIFIED — 重新导出 ThinkingBlock + RedactedThinkingBlock
│   └── _types.py                              # MODIFIED — 新增两个 block + 加入 ContentBlock union
├── providers/
│   ├── base.py                                # MODIFIED — ProviderThinkingBlock + ProviderRedactedThinking
│   ├── anthropic.py                           # MODIFIED — emit + round-trip
│   ├── openai.py                              # MODIFIED — 跳过新 block
│   └── fake.py                                # MODIFIED — FakeRound.thinking_blocks 字段
└── engine/
    └── loop.py                                # MODIFIED — 处理新 provider events

pyproject.toml                                 # MODIFIED — 版本 0.0.7

tests/
├── unit/
│   ├── abstractions/test_types.py             # MODIFIED — 4 新用例
│   └── providers/
│       ├── test_anthropic.py                  # MODIFIED — 5 新用例
│       ├── test_openai.py                     # MODIFIED — 1 新用例
│       └── test_fake.py（如存在）              # MODIFIED — 1 新用例
└── integration/
    └── test_engine_e2e.py                     # MODIFIED — 1 新场景
```

### 工作流 B

```
.github/
├── workflows/
│   └── ci.yml                                 # NEW — Python 3.10/3.11/3.12 × ubuntu/macos
└── pull_request_template.md                   # NEW — Summary / Test plan / Checklist

README.md                                      # MODIFIED — badges (workflow + license)
pyproject.toml                                 # MODIFIED — [project.urls] 加 Homepage/Repository/Issues
```

## 4. 关键 API 与契约

### 4.1 新 ContentBlock 类型

```python
# src/meta_harney/abstractions/_types.py 新增
class ThinkingBlock(BaseModel):
    """Anthropic extended-thinking content block, fully persisted.

    Carried in assistant Message.content to round-trip back to the provider
    on subsequent turns. Required for Anthropic's thinking-continuity check
    when extended thinking + tool_use is enabled.
    """
    type: Literal["thinking"] = "thinking"
    text: str
    signature: str


class RedactedThinkingBlock(BaseModel):
    """Opaque encrypted thinking payload from Anthropic.

    `data` is treated as a black box: we never decrypt, only round-trip.
    """
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


ContentBlock = Annotated[
    TextBlock | ImageBlock | ToolCallBlock | ToolResultBlock
    | ThinkingBlock | RedactedThinkingBlock,
    Field(discriminator="type"),
]
```

### 4.2 新 Provider Stream Events

```python
# src/meta_harney/providers/base.py 新增（位于 ProviderToolCall 之后、ProviderStreamDone 之前）

class ProviderThinkingBlock(_ProviderStreamEventBase):
    """Complete thinking content block emitted at content_block_stop.

    Engine appends a ThinkingBlock to assistant message content. Distinct
    from ProviderThinkingDelta (which is the live-stream variant emitted
    incrementally and never persisted).
    """
    type: Literal["thinking_block"] = "thinking_block"
    text: str
    signature: str


class ProviderRedactedThinking(_ProviderStreamEventBase):
    """Opaque redacted-thinking block from Anthropic."""
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str


ProviderStreamEvent = (
    ProviderTextDelta | ProviderToolCall | ProviderThinkingDelta
    | ProviderThinkingBlock | ProviderRedactedThinking | ProviderStreamDone
)
```

### 4.3 AnthropicProvider stream() 改动

在现有 SSE 事件循环里：

- `content_block_start(type="thinking")`：buffer[idx] = `{"text_chunks": [], "signature_chunks": []}`
- `content_block_delta(delta.type="thinking_delta")`：现有 ProviderThinkingDelta yield 不变 + buffer[idx]["text_chunks"].append(delta.thinking)
- `content_block_delta(delta.type="signature_delta")`：buffer[idx]["signature_chunks"].append(delta.signature)（新增分支）
- `content_block_stop` 见到 buffer entry：yield `ProviderThinkingBlock(text="".join(buffer[idx]["text_chunks"]), signature="".join(buffer[idx]["signature_chunks"]))`
- `content_block_start(type="redacted_thinking", data=<blob>)`：立刻 yield `ProviderRedactedThinking(data=blob)`

### 4.4 AnthropicProvider 回传

`_convert_messages_to_anthropic._convert_block` 新增分支：

```python
if isinstance(block, ThinkingBlock):
    return {"type": "thinking", "thinking": block.text, "signature": block.signature}
if isinstance(block, RedactedThinkingBlock):
    return {"type": "redacted_thinking", "data": block.data}
```

### 4.5 OpenAIProvider 跳过

`_convert_messages_to_openai` 在 user/assistant 消息的 block 遍历中，对 `ThinkingBlock` / `RedactedThinkingBlock` 直接 `continue`，不产出任何 wire 内容。

### 4.6 Engine 事件分支

```python
elif isinstance(ev, ProviderThinkingBlock):
    assistant_blocks.append(
        ThinkingBlock(text=ev.text, signature=ev.signature)
    )
elif isinstance(ev, ProviderRedactedThinking):
    assistant_blocks.append(RedactedThinkingBlock(data=ev.data))
```

ProviderThinkingDelta passthrough（Phase 6 已实现）不动。

### 4.7 FakeRound 扩展

```python
class FakeRound(BaseModel):
    text: str = ""
    split_on: str | None = None
    thinking: str | None = None                      # Phase 6 - 简便语法糖（live stream only）
    thinking_blocks: list[ThinkingBlock] = []         # Phase 7 NEW - 完整持久化
    tool_calls: list[ProviderToolCall] = []
    stop_reason: Literal[...] = "end_turn"
    input_tokens: int | None = None
    output_tokens: int | None = None
```

`FakeLLMProvider.stream()`：thinking 先发（Phase 6 live-stream 路径），然后对每个 thinking_block 发 `ProviderThinkingBlock`，再发 text，再发 tool_calls。

**互斥校验**：`@model_validator` 确保 `thinking` 与 `thinking_blocks` 不同时设置；若同时设置抛 `ValueError`。

### 4.8 CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev,anthropic,openai]"
      - run: pytest -q
      - run: mypy src/meta_harney
      - run: mypy tests
      - run: ruff check src tests
      - run: ruff format --check src tests
```

### 4.9 pyproject.toml URLs

```toml
[project.urls]
Homepage = "https://github.com/<user>/meta-harney"
Repository = "https://github.com/<user>/meta-harney"
Issues = "https://github.com/<user>/meta-harney/issues"
```

`<user>` 由执行阶段从 `gh auth status` 读取并填充。

## 5. Data flow

### ThinkingBlock 持久化

```
Anthropic SSE (extended thinking on)
  content_block_start(type="thinking")
    → buffer[idx] = {text_chunks=[], signature_chunks=[]}
  content_block_delta(type="thinking_delta", thinking="…")
    → yield ProviderThinkingDelta (live)
    → buffer[idx]["text_chunks"].append("…")
  content_block_delta(type="signature_delta", signature="…")
    → buffer[idx]["signature_chunks"].append("…")
  content_block_stop
    → yield ProviderThinkingBlock(text=join, signature=join)

Engine: ProviderThinkingBlock → assistant_blocks.append(ThinkingBlock)
SessionStore: serialize via Pydantic discriminated union

Turn N+1:
  PromptBuilder loads history
  _convert_messages_to_anthropic 把 ThinkingBlock 转回
    {"type":"thinking","thinking":text,"signature":sig}
  Anthropic API 接受 → 满足 continuity
```

### RedactedThinkingBlock 路径

```
Anthropic SSE: content_block_start(type="redacted_thinking", data="<blob>")
  → ProviderRedactedThinking(data="<blob>") 立刻发
  → engine appends RedactedThinkingBlock(data="<blob>")
Turn N+1: _convert_messages_to_anthropic 转回
    {"type":"redacted_thinking","data":"<blob>"}
```

### OpenAI 路径上 ThinkingBlock 处理

```
ToolResultBlock / TextBlock / ImageBlock / ToolCallBlock → 原有 wire 转换
ThinkingBlock → continue (跳过)
RedactedThinkingBlock → continue (跳过)
```

### CI 触发

```
git push origin main / PR 创建 / PR 更新
  → workflow trigger
  → 6 jobs (3.10/3.11/3.12 × ubuntu/macos) 并行
  → 每个 job: setup → install → pytest → mypy(2x) → ruff(2x)
  → fail-fast=false：所有 job 都跑完
  → 总体状态：全绿才是 pass
```

## 6. Error handling

| 路径 | 行为 |
|---|---|
| Anthropic 返回 thinking 但缺 signature_delta | `signature=""`；下一轮回传时大概率 Anthropic 400 → `NonRetryableProviderError`（已存在） |
| Pydantic discriminated union 解析未知 type | `ValidationError`，意味着代码与 wire/disk 格式版本不匹配，不兜底 |
| OpenAI 调用看到 ThinkingBlock | 静默跳过；不抛、不警告 |
| `thinking_budget` 不合法 | API 400 → 现有错误路径 |
| ThinkingBlock signature 字段为空 | 不前置校验；让 Anthropic 自行判定 |
| `FakeRound.thinking` 和 `thinking_blocks` 同时设置 | `model_validator` 抛 `ValueError`（构造期捕获，避免运行时混乱） |
| CI 某 job 失败 | `fail-fast: false`，其他 job 继续；整体 status fail |
| `gh auth status` 未登录 | 执行阶段停下来提示 `gh auth login`；不自动尝试 |
| `gh repo create` 失败（名字占用） | 报错给用户；不主动 force |
| 首次 push 失败 | repo 已建但本地未 push；提示手动 `git push -u origin main` |

## 7. Testing

### 7.1 用例分布

| 测试文件 | 新增用例 |
|---|---|
| `tests/unit/abstractions/test_types.py` | 4（ThinkingBlock 构造、RedactedThinkingBlock 构造、Message JSON round-trip、Pydantic discriminator 解析） |
| `tests/unit/providers/test_anthropic.py` | 5（thinking_block emit、signature 累积、redacted_thinking emit、ThinkingBlock 回传 wire、RedactedThinkingBlock 回传 wire） |
| `tests/unit/providers/test_openai.py` | 1（ThinkingBlock / RedactedThinkingBlock 在转换器中被跳过） |
| `tests/unit/providers/test_fake.py`（新建或在现有 anthropic test 加） | 1（FakeRound.thinking_blocks emit ProviderThinkingBlock） |
| `tests/integration/test_engine_e2e.py` | 1（thinking + tool_use multi-turn 持久化端到端） |
| 合计 | **12** |

补充：FakeRound 互斥校验 1 个 unit test，归在 fake 测试里。**最终 +13**。

### 7.2 测试总数

289（v0.0.6） + 13 = **302**

### 7.3 CI workflow 验证

不为 CI workflow 单独写测试；workflow 第一次跑过即视为验证通过。

## 8. 版本号与发布

- `pyproject.toml`: `0.0.6` → `0.0.7`
- `src/meta_harney/__init__.py`:
  - `__version__ = "0.0.7"`
  - 模块 docstring 更新为 Phase 7 状态
  - `__all__` 追加：`"ThinkingBlock"`、`"RedactedThinkingBlock"`、`"ProviderThinkingBlock"`、`"ProviderRedactedThinking"`
- 创建 git tag `v0.0.7`（本地 + push 到 remote）

## 9. 完成标准

- [ ] `ThinkingBlock`、`RedactedThinkingBlock` 在 `abstractions/_types.py`
- [ ] `ContentBlock` discriminated union 包含两个新类型
- [ ] `ProviderThinkingBlock`、`ProviderRedactedThinking` 在 `providers/base.py`
- [ ] AnthropicProvider 缓冲 thinking_delta + signature_delta 并在 content_block_stop emit ProviderThinkingBlock
- [ ] AnthropicProvider 在 content_block_start 见到 redacted_thinking 立刻 emit ProviderRedactedThinking
- [ ] AnthropicProvider `_convert_messages_to_anthropic` 回传两类新 block 的 wire 格式
- [ ] OpenAIProvider 在转换 messages 时跳过两类新 block
- [ ] Engine `run_turn` 把两类新 provider event 写入 `assistant_blocks` → `session.messages`
- [ ] `FakeRound.thinking_blocks` 字段 + `thinking` vs `thinking_blocks` 互斥校验
- [ ] FakeLLMProvider 根据 `thinking_blocks` emit ProviderThinkingBlock
- [ ] 4 个新类型在 `meta_harney.__all__`
- [ ] 总测试数 = 302（289 + 13）
- [ ] mypy strict + ruff check + ruff format 全绿
- [ ] 版本号升至 0.0.7
- [ ] GitHub repo `meta-harney`（public）创建
- [ ] `origin` remote 配好，main + tags 已 push
- [ ] `.github/workflows/ci.yml` 落盘，首次 push 触发 6 job CI 全绿
- [ ] `.github/pull_request_template.md` 落盘
- [ ] README badges 替换为实际 GitHub workflow + license
- [ ] `pyproject.toml [project.urls]` 含 Homepage / Repository / Issues
- [ ] `v0.0.7` git tag 本地 + push

## 10. Phase 8+ 候选

- CI coverage 阈值（采集 v0.0.7 基线数据后定）
- PyPI 发包流程
- release.yml 自动化发布
- Windows 矩阵（如有需求）
- ChangeLog 自动化
