# meta-harney Phase 6 — Stabilize 设计

**日期：** 2026-05-14
**版本目标：** v0.0.6
**前置：** v0.0.5（Phase 5 — OpenAIProvider + 文档）

## 1. 目标与非目标

### 目标

Phase 6 是 v0.0.5 的稳定化收尾：补齐设计文档 §8.4 列出但尚未实现的两条集成场景，接入 `ThinkingDelta`
让 Anthropic extended thinking 能被 SDK 消费者实时观察，修复一处 provider 序列化 bug，并补一条注释防回归。

具体 5 项工作：

1. **`ToolResult.output` 序列化修复**
   - 抽公共 helper `_serialize_tool_output(output: Any) -> str`
   - 两个 provider 改用同一 helper，消除当前的 `str(None)→"None"` 与 dict Python repr 行为
2. **OpenAI `RateLimitError` catch 顺序注释**
3. **`ThinkingDelta` 实时流事件接入**（仅 Anthropic）
4. **集成测试：`tool-error-recovery`**（spec §8.4 #2）
5. **集成测试：`multi-turn-session`**（spec §8.4 #4）

### 非目标

- Anthropic `redacted_thinking` 的完整呈现（静默跳过即可）
- thinking 配合 tool_use 多轮的完整支持（需要把 thinking block 作为 ContentBlock 入 session.messages，本阶段不做）
- OpenAI 的 thinking 概念（OpenAI Chat Completions 没有这个概念）
- CI 矩阵（推迟，按用户决策）

## 2. 总体架构

5 项工作相互独立，无内部强依赖。按风险从小到大执行：

1. helper + 两个 provider 改用（最小、最安全）
2. RateLimitError 注释（一行）
3. ThinkingDelta（新增公开 API 面）
4. tool-error-recovery 集成测试
5. multi-turn-session 集成测试

## 3. 文件结构

| 文件 | 改动 | 说明 |
|---|---|---|
| `src/meta_harney/abstractions/_serialize.py` | **新建** | `_serialize_tool_output(output: Any) -> str` |
| `src/meta_harney/providers/base.py` | 修改 | 加 `ProviderThinkingDelta(text: str)` 类；加入 `ProviderStreamEvent` 联合 |
| `src/meta_harney/providers/anthropic.py` | 修改 | thinking_budget 构造参数；API 请求注入 thinking；解析 `thinking_delta` SSE；ToolResult 改用 helper |
| `src/meta_harney/providers/openai.py` | 修改 | ToolResult 改用 helper；`RateLimitError` catch 注释 |
| `src/meta_harney/engine/loop.py` | 修改 | `ProviderThinkingDelta` 透传成 `StreamEvent.ThinkingDelta`（不入 session） |
| `src/meta_harney/__init__.py` | 修改 | 导出 `ProviderThinkingDelta`；版本号 `0.0.6` |
| `pyproject.toml` | 修改 | 版本号 `0.0.6` |
| `src/meta_harney/testing/fake_provider.py` | 修改 | `FakeRound` 加可选 `thinking: str | None = None` |
| `tests/unit/abstractions/test_serialize.py` | **新建** | helper 单元 7+ 用例 |
| `tests/unit/providers/test_anthropic.py` | 修改 | 4 新用例：thinking_budget API、thinking_delta 解析、redacted_thinking 静默、dict 序列化 |
| `tests/unit/providers/test_openai.py` | 修改 | 1 新用例：dict 序列化 |
| `tests/integration/test_engine_e2e.py` | 修改 | 3 新场景（含 ThinkingDelta 透传 + 不入 history） |

## 4. 关键 API 与契约

### 4.1 `_serialize_tool_output` helper

```python
# src/meta_harney/abstractions/_serialize.py
from __future__ import annotations

import json
from typing import Any


def _serialize_tool_output(output: Any) -> str:
    """Serialize a ToolResult.output to a string for LLM consumption.

    - None      → ""
    - str       → unchanged
    - other     → json.dumps(output, default=str, ensure_ascii=False)
    - 循环引用   → repr(output) 兜底，不抛
    """
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, default=str, ensure_ascii=False)
    except (ValueError, TypeError):
        return repr(output)
```

调用点：

- `AnthropicProvider._block_to_anthropic` 中处理 `ToolResultBlock` 的内容
- `OpenAIProvider._convert_messages_to_openai` 中处理 `ToolResultBlock` 的内容
- 两处 `block.error` 也走 helper（虽然 `error: str | None` 时是 no-op，但保持"内容总是字符串"的单点保证）

### 4.2 `ProviderThinkingDelta`

```python
# src/meta_harney/providers/base.py 中追加
class ProviderThinkingDelta(BaseModel):
    """Streaming chunk of Anthropic extended-thinking text."""
    kind: Literal["thinking_delta"] = "thinking_delta"
    text: str

# ProviderStreamEvent 联合追加 ProviderThinkingDelta
```

### 4.3 `AnthropicProvider` 改动

构造参数：

```python
def __init__(
    self,
    *,
    api_key: str,
    base_url: str | None = None,
    default_max_tokens: int = 4096,
    thinking_budget: int | None = None,  # 新增
) -> None:
```

`stream()` 内部：

- 若 `self._thinking_budget is not None`，请求 `kwargs` 加入：
  `thinking={"type": "enabled", "budget_tokens": self._thinking_budget}`
- 在 `content_block_start` 时记录当前 block 是否为 `thinking` 类型（block index → "thinking"/"text"/"tool_use"）
- `content_block_delta` 路径上，若 delta 是 `thinking_delta`（含 `thinking` 字段），yield `ProviderThinkingDelta(text=delta.thinking)`
- `redacted_thinking` 类型 block 不解析、不发事件、不报错

### 4.4 engine 透传

`engine/loop.py` 中，遍历 provider stream 事件时新增分支：

```python
elif isinstance(event, ProviderThinkingDelta):
    yield ThinkingDelta(text=event.text)
    # 注意：不追加到 _assistant_text / _assistant_blocks，不入 session.messages
```

### 4.5 `FakeRound` 扩展

`tests` + `meta_harney.testing.fake_provider`：

```python
@dataclass
class FakeRound:
    text: str | None = None
    tool_calls: list[ProviderToolCall] = field(default_factory=list)
    thinking: str | None = None       # 新增（None ⇒ 不发 thinking_delta）
    stop_reason: str = "end_turn"
    raise_error: Exception | None = None
    split_on: str | None = None
```

`FakeLLMProvider.stream()` 当 round 含 `thinking` 时先 yield `ProviderThinkingDelta(text=round.thinking)`，再走 text/tool_call 路径。

## 5. Data flow

### ThinkingDelta 路径

```
Anthropic SSE
  └→ content_block_delta(delta.type="thinking_delta", thinking="…")
       └→ AnthropicProvider yields ProviderThinkingDelta(text=…)
            └→ engine yields StreamEvent.ThinkingDelta(text=…)
                 └→ runtime.stream() consumer
                ✗ 不进 assistant_text / _assistant_blocks
                ✗ 不进 session.messages
```

### ToolResult 序列化路径

```
BaseTool.execute() → ToolResult(success=True, output=<Any>)
  └→ engine 包装为 ToolResultBlock 加入 session.messages
       └→ 下一轮 PromptBuilder 加载 history
            └→ AnthropicProvider._block_to_anthropic
                 └→ _serialize_tool_output(content) → str
            └→ OpenAIProvider._convert_messages_to_openai
                 └→ _serialize_tool_output(block.output) → str
```

### Multi-turn session

```
invoke(session_id, "Q1") → session = [user(Q1), assistant(A1)]
invoke(session_id, "Q2") → load → append user(Q2)
                              → PromptBuilder 返回 [Q1, A1, Q2]
                              → provider.calls[1].messages 含 Q1+A1
                              → session = [user(Q1), assistant(A1), user(Q2), assistant(A2)]
```

## 6. Error handling

| 路径 | 行为 |
|---|---|
| `json.dumps` 循环引用 / TypeError | helper 内 try/except → `repr(output)` 降级，不抛 |
| Anthropic `redacted_thinking` block | provider 静默跳过，stream 正常完成 |
| `thinking_budget` 不合法（<1024） | 不前置校验，API 返回 400 → 现有 `NonRetryableProviderError` 路径 |
| Tool 抛异常（集成测试场景 4） | engine 现有 dispatch 已包装为 `ToolResult(success=False, error=str(exc))` |
| 多轮 session（场景 5） | 现有路径，无新错误 |

## 7. Testing

### 7.1 新增 / 修改用例

| 测试文件 | 类型 | 新增用例数 |
|---|---|---|
| `tests/unit/abstractions/test_serialize.py` | 新建 | 7 |
| `tests/unit/providers/test_anthropic.py` | 修改 | 4 |
| `tests/unit/providers/test_openai.py` | 修改 | 1 |
| `tests/integration/test_engine_e2e.py` | 修改 | 3 |
| 合计 | | **15** |

### 7.2 `_serialize_tool_output` 用例

1. `None` → `""`
2. `"hi"` → `"hi"`
3. `{"a": 1, "b": "x"}` → `'{"a": 1, "b": "x"}'`
4. `[1, 2, 3]` → `'[1, 2, 3]'`
5. `42` → `'42'`
6. `datetime(2026,1,1)` → 含 ISO 串（default=str 兜底）
7. 循环引用 dict → 不抛，返回字符串

### 7.3 thinking 相关用例

- `AnthropicProvider(api_key="…", thinking_budget=4096)` 调用 SDK 时 `kwargs` 含 `thinking={"type":"enabled","budget_tokens":4096}`
- Fake stream 中含 `thinking_delta` chunk → provider yield `ProviderThinkingDelta(text="…")`
- Fake stream 中含 `redacted_thinking` block → provider 不抛、不 yield ThinkingDelta、StreamDone 正常
- engine + FakeRound 包含 `thinking="…"`，跑完一轮：
  - 消费 `StreamEvent.ThinkingDelta`
  - `session.messages` 不含 thinking 文本
  - assistant content 不含 thinking 文本

### 7.4 集成场景

**tool-error-recovery（场景 4）：**

- Round 1: assistant tool_call("query_db", args={...})
- Tool 抛 `RuntimeError("DB unreachable")`
- engine 转 `ToolResult(success=False, error="DB unreachable")`
- Round 2: assistant text "DB connection failed, please retry later."
- 断言 session.messages role 序列 `[user, assistant, tool, assistant]`
- 断言最后一条 assistant content 含 "retry later"

**multi-turn-session（场景 5）：**

- `invoke(session.id, "What's 2+2?")` → assistant "4"
- `invoke(session.id, "And then double it?")` → assistant "8"
- 断言 session.messages role 序列 `[user, assistant, user, assistant]`
- 断言 `provider.calls[1].messages` 含第一轮的 user+assistant

### 7.5 测试总数

268（v0.0.5 末） + 15 = **283**

## 8. 版本号与发布

- `pyproject.toml`: `0.0.5` → `0.0.6`
- `src/meta_harney/__init__.py`:
  - `__version__ = "0.0.6"`
  - 模块 docstring 更新为 Phase 6 状态
  - 导出列表追加 `"ProviderThinkingDelta"`
- 创建 git tag `v0.0.6`

## 9. 完成标准

- [ ] `_serialize_tool_output` 在 `abstractions/_serialize.py`
- [ ] 两个 provider 的 ToolResult 路径改用 helper
- [ ] OpenAIProvider `RateLimitError` catch 注释到位
- [ ] `ProviderThinkingDelta` 公开导出
- [ ] `AnthropicProvider.thinking_budget` 构造参数 + API 请求注入
- [ ] AnthropicProvider 解析 `thinking_delta` SSE → ProviderThinkingDelta
- [ ] AnthropicProvider 不解析 `redacted_thinking`（静默跳过）
- [ ] engine 透传 `ProviderThinkingDelta` → `StreamEvent.ThinkingDelta`
- [ ] ThinkingDelta 不入 `session.messages`
- [ ] `FakeRound` 加 `thinking: str | None = None` 字段
- [ ] tool-error-recovery 集成测试通过
- [ ] multi-turn-session 集成测试通过
- [ ] 总测试数 ≥ 283，全部通过
- [ ] mypy strict + ruff check + ruff format 全绿
- [ ] 版本号升至 0.0.6 + tag

## 10. Phase 7+ 候选

- ThinkingDelta 完整模式（thinking 入 ContentBlock，支持 thinking + tool_use 多轮，含 signature/redacted 处理）
- CI 矩阵（spec §8.6）
- `__init__.py` 导出整理（如果 Provider* 事件类型导出层级值得重组）
