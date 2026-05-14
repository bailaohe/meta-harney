# meta-harney: 通用 Agent 运行时设计

| Field | Value |
|-------|-------|
| Date | 2026-05-13 |
| Status | Approved Design |
| Branch | `feature/meta-harney` (forked from OpenHarness main @ `1929ad8`) |
| Package | distribution `meta-harney` / import `meta_harney` |
| Strategy | Hard fork — no merge-back to OpenHarness |

---

## 1. 动机与上下文

OpenHarness 名义为通用 Agent harness，实质是 Claude Code 的开源复刻——通用性评分 4/10。要基于它做面向业务的 Agent 应用（如 CRM Agent），需要先把"编程辅助"语境从核心引擎里彻底剥离。

本设计描述一次**硬分叉式重构**：保留 OpenHarness 已验证的 engine 内核（agent loop、stream、retry、compaction），删除所有编程相关代码与默认行为，引入 9 个干净的抽象接口，使框架成为**与领域无关的通用 Agent 运行时 SDK**。

未来若需重新实现"编程 Agent"，将作为该运行时之上的应用包独立交付。

## 2. 目标与非目标

### 目标

- **G1**：核心引擎对工具、提示词、权限、记忆、文件系统**零硬编码假设**
- **G2**：5 个已有模块（Tool/Hook/Permission/Prompt/Task）抽象为可插拔接口
- **G3**：新增 4 个一等公民原语：Session、Trace/Audit、MultiAgent、Compaction
- **G4**：交付形态为 Python SDK，业务通过 `from meta_harney import AgentRuntime` 集成
- **G5**：提供契约测试基础设施，业务自实现 Protocol 即获得 30+ 项规范化测试

### 非目标

- **不**保留任何编程语境的工具/skill/prompt
- **不**保证对 OpenHarness 现有 CLI / `ohmo` 子项目的向下兼容
- **不**引入 Workflow/State-Machine 原语（YAGNI；业务用 Hook + Tool 组合实现）
- **不**在此次重构内提供 RBAC、审计落库、租户管理等业务实现（基础设施由 Hook + Session.tenant_id + TraceSink 提供，业务自实现）

## 3. 仓库结构

```
meta-harney/
├── pyproject.toml                          # 分发名 meta-harney
├── README.md
├── CHANGELOG.md
├── docs/
│   ├── architecture.md
│   ├── abstractions.md
│   ├── providers.md
│   └── testing.md
│
├── src/meta_harney/
│   ├── __init__.py                         # 公开 API
│   ├── runtime.py                          # AgentRuntime 主入口
│   │
│   ├── engine/                             # 核心 agent loop
│   │   ├── loop.py                         # run_turn：tool-name-agnostic
│   │   ├── messages.py                     # Text/Image/ToolCall/ToolResult
│   │   ├── stream_events.py                # 流式事件
│   │   ├── compaction.py                   # 压缩调度
│   │   └── retry.py                        # 重试与退避
│   │
│   ├── abstractions/                       # ★ 9 个抽象接口
│   │   ├── tool.py                         # BaseTool (ABC) + ToolInvocation
│   │   ├── hook.py                         # BaseHook (ABC) + HookEvent
│   │   ├── permission.py                   # PermissionResolver (Protocol)
│   │   ├── prompt.py                       # PromptBuilder (Protocol)
│   │   ├── task.py                         # BaseTask (ABC)
│   │   ├── session.py                      # Session + SessionStore (Protocol)
│   │   ├── trace.py                        # TraceEvent + TraceSink (Protocol)
│   │   ├── multi_agent.py                  # MultiAgentBackend (Protocol)
│   │   └── compaction.py                   # CompactionStrategy (Protocol)
│   │
│   ├── providers/                          # LLM 适配
│   │   ├── base.py                         # LLMProvider Protocol
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   └── ...
│   │
│   ├── builtin/                            # 默认实现
│   │   ├── permission/{allow_all,deny_all}.py
│   │   ├── prompt/minimal.py
│   │   ├── session/{memory_store,file_store}.py
│   │   ├── trace/{null_sink,jsonl_sink}.py
│   │   └── compaction/summarization.py
│   │
│   ├── tracing/
│   │   └── contextvars.py                  # 可选的 contextvar 工具
│   │
│   ├── testing/                            # 一等公民测试支持
│   │   ├── fake_provider.py
│   │   └── runtime_helpers.py
│   │
│   ├── mcp/                                # MCP 客户端（保留）
│   ├── config/                             # Settings
│   ├── auth/                               # LLM provider auth
│   └── errors.py                           # 异常体系
│
└── tests/
    ├── unit/
    ├── integration/                        # 使用 FakeLLMProvider
    └── contracts/                          # 协议契约测试套
```

### 删除清单（相对当前 main）

- `ohmo/`
- `frontend/`
- `src/openharness/ui/`
- `src/openharness/tools/*_tool.py`（42 个）
- `src/openharness/commands/`（54 个 slash commands）
- `src/openharness/skills/bundled/`
- `src/openharness/coordinator/` 与 `swarm/` 中 coding-flavor 实现（保留 `MultiAgentBackend` 抽象，重写 in-process / subprocess backend）
- `src/openharness/services/autodream*`、`token_counting*` 等附属
- `src/openharness/prompts/system_prompt.py` 内容（保留组装机制）

## 4. 核心抽象

### 4.1 共享数据契约

```python
class ToolInvocation(BaseModel):
    name: str
    args: dict[str, Any]
    invocation_id: str
    session_id: str                          # 工具自己 load Session

class ToolResult(BaseModel):
    success: bool
    output: Any
    error: str | None = None
    metadata: dict[str, Any] = {}

class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]   # wire role
    author: str | None = None                              # 业务标签
    name: str | None = None                                # OpenAI 兼容
    content: list[ContentBlock]
```

**Message.role / Message.author 二分**：
- `role` 是发给 LLM 厂商的 wire 字段，受厂商 schema 限制
- `author` 是业务自由标签（"sales"、"customer" 等）
- Provider 适配器把 `author` 映射到厂商支持的形式（OpenAI 用 `name` 字段；Anthropic 在 text 前缀注入）

### 4.2 BaseTool

```python
class BaseTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    default_timeout: ClassVar[float | None] = None         # 工具自报默认超时（秒）

    @abstractmethod
    async def execute(self, inv: ToolInvocation, ctx: ToolContext) -> ToolResult: ...

@dataclass
class ToolContext:
    session_store: SessionStore
    trace_sink: TraceSink
    current_span_id: str
    new_span_id: Callable[[], str]
    # 业务可通过子类化扩展
```

### 4.3 BaseHook

```python
HookEventKind = Literal[
    "pre_tool", "post_tool",
    "pre_llm", "post_llm",
    "session_start", "session_end",
    "turn_complete",
]

class HookEvent(BaseModel):
    kind: HookEventKind
    session_id: str
    payload: dict[str, Any]

class HookDecision(BaseModel):
    allow: bool = True
    transform: dict | None = None    # 仅在 pre_* 事件中生效（engine 强制）
    reason: str | None = None

class BaseHook(ABC):
    subscribed_events: ClassVar[set[HookEventKind]]

    @abstractmethod
    async def handle(self, event: HookEvent) -> HookDecision: ...
```

### 4.4 PermissionResolver

```python
class PermissionDecision(BaseModel):
    verdict: Literal["allow", "deny", "ask"]
    reason: str | None = None

class PermissionResolver(Protocol):
    async def resolve(
        self,
        invocation: ToolInvocation,
        session_id: str,
    ) -> PermissionDecision: ...
```

### 4.5 PromptBuilder

```python
class PromptBuilder(Protocol):
    async def build_system_prompt(self, session_id: str) -> str: ...
    async def build_context_messages(self, session_id: str) -> list[Message]: ...
```

### 4.6 BaseTask

```python
class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

class BaseTask(ABC):
    task_id: str
    state: TaskState

    @abstractmethod
    async def run(self) -> Any: ...

    @abstractmethod
    async def cancel(self) -> None: ...
```

### 4.7 Session + SessionStore

```python
class Session(BaseModel):
    id: str
    tenant_id: str | None = None
    user_id: str | None = None
    parent_session_id: str | None = None     # sub-agent 派生关系
    created_at: datetime
    version: int = 0                         # 强制乐观锁字段
    messages: list[Message] = []
    attributes: dict[str, Any] = {}          # 业务自留地
    metadata: dict[str, Any] = {}

class SessionStore(Protocol):
    async def load(
        self, session_id: str, *, tenant_id: str | None = None
    ) -> Session | None:
        """若提供 tenant_id 且 session 归属其他 tenant，返回 None（防探测）"""

    async def save(self, session: Session) -> None:
        """必须实现乐观锁：检测 version 冲突时抛 SessionConflictError"""

    async def list(
        self, *, tenant_id: str | None = None, filter: dict | None = None
    ) -> list[Session]: ...

    async def delete(self, session_id: str) -> None: ...
```

**强制契约**：所有实现必须支持乐观锁与租户过滤——`SessionStoreContract` 契约测试会强制检查。

### 4.8 TraceEvent + TraceSink

```python
class TraceEvent(BaseModel):
    ts: datetime
    session_id: str
    kind: str                                # 见附录 A
    span_id: str
    parent_span_id: str | None = None
    payload: dict[str, Any]
    duration_ms: float | None = None

class TraceSink(Protocol):
    async def emit(self, event: TraceEvent) -> None: ...
    async def flush(self) -> None: ...
```

**Span 树**：engine 显式注入 `current_span_id` 到 `ToolContext`，业务想发自定义子 span 时手动 `new_span_id()`。框架另外提供可选的 `meta_harney.tracing.contextvars` 工具供 asyncio 用户使用，不在 Protocol 中——避免对业务并发模型做假设。

### 4.9 MultiAgentBackend

```python
class AgentSpec(BaseModel):
    name: str
    instructions: str
    allowed_tools: list[str]
    max_iters: int = 10

class SpawnHandle(BaseModel):
    child_session_id: str
    mode: Literal["blocking", "detached"]

class MultiAgentBackend(Protocol):
    async def spawn(
        self,
        spec: AgentSpec,
        initial_message: str,
        parent_session_id: str,
        mode: Literal["blocking", "detached"] = "blocking",
    ) -> SpawnHandle: ...

    async def join(
        self, child_session_id: str, timeout: float | None = None
    ) -> ToolResult: ...

    async def status(self, child_session_id: str) -> TaskState: ...
    async def cancel(self, child_session_id: str) -> None: ...
```

### 4.10 CompactionStrategy

```python
class CompactionStrategy(Protocol):
    async def should_compact(
        self,
        session_id: str,
        current_tokens: int,
        window_limit: int,
    ) -> bool: ...

    async def compact(self, session_id: str) -> list[Message]:
        """返回压缩后的新消息列表"""

# 默认实现：builtin/compaction/summarization.py
class SummarizationCompactor(CompactionStrategy):
    """保留 system + 最近 N 条，中间消息用 LLM 摘要为一条"""
```

## 5. Engine 数据流

### 5.1 一个 turn 的执行序列

```
runtime.invoke(session_id, user_message)
  │
  ├─ store.load(session_id)
  ├─ session.messages.append(user_message)
  ├─ trace.emit("turn.started")
  │
  └─ ITERATION LOOP:
       │
       ├─ prompt = prompt_builder.build(session_id)
       │  trace.emit("prompt.built")
       │
       ├─ pre_llm hooks（HookDecision.transform 可改写 prompt）
       │
       ├─ TRY:
       │    provider.stream(prompt) → yield StreamEvents
       │    trace.emit("llm.completed")
       │  EXCEPT RetryableProviderError:
       │    trace.emit("retry.attempted")
       │    指数退避后重试；超限 trace("retry.exhausted") + raise
       │
       ├─ post_llm hooks
       │
       ├─ session.messages.append(llm_response)
       │
       ├─ if llm_response 无 tool_calls: BREAK（turn 结束）
       │
       ├─ FOR EACH tool_call:
       │    inv = ToolInvocation(name, args, invocation_id, session_id)
       │
       │    perm = permission_resolver.resolve(inv, session_id)
       │    trace.emit("permission.resolved")
       │    if deny: ToolResult(success=False, error=reason)
       │             trace.emit("tool.denied")
       │             continue → 喂回 LLM
       │
       │    pre_tool hooks
       │
       │    timeout = (settings.overrides[name]
       │               or tool.default_timeout
       │               or settings.global_default_timeout)
       │
       │    TRY:
       │      result = asyncio.wait_for(tool.execute(inv, ctx), timeout)
       │      trace.emit("tool.completed")
       │    EXCEPT asyncio.TimeoutError:
       │      result = ToolResult(success=False, error="timed out after Xs")
       │      trace.emit("tool.timed_out")
       │    EXCEPT Exception:
       │      result = ToolResult(success=False, error=str(e))
       │      trace.emit("error.raised")
       │
       │    post_tool hooks
       │    session.messages.append(ToolResultMessage(result))
       │
       ├─ if total_tokens > window_limit:
       │    if compactor.should_compact(...):
       │       trace.emit("compaction.triggered")
       │       session.messages = compactor.compact(...)
       │
       └─ continue loop
  │
  ├─ session_end hooks
  ├─ store.save(session)        # ★ end-of-turn write-through
  ├─ trace.emit("turn.completed")
  ├─ trace.flush()
  └─ return final_assistant_message
```

### 5.2 StreamEvent vs TraceEvent

| 维度 | StreamEvent | TraceEvent |
|------|------------|------------|
| 用途 | 业务消费数据流 | 业务观测系统 |
| 接口 | `AgentRuntime.stream()` 的 AsyncIterator | `TraceSink.emit()` |
| 类型数 | 6（少而稳） | 20+ kind（见附录 A） |
| 关注点 | 对话内容（text delta、tool call） | 系统行为（permission、retry、compaction） |
| 关系 | 完全独立 | 完全独立 |

```python
StreamEventKind = Literal[
    "text_delta", "thinking_delta",
    "tool_call_started", "tool_call_completed",
    "iteration_completed", "turn_completed",
]
```

### 5.3 重试归一化

Provider 实现者负责把厂商错误归一化为：
- `RetryableProviderError`（429、5xx、网络抖动）→ engine 自动重试
- `NonRetryableProviderError`（auth、invalid request）→ 立即上抛

Engine 自身不感知厂商细节。

### 5.4 Compaction

调度由 engine 触发，决策与执行由 `CompactionStrategy` 接管。默认 `SummarizationCompactor`，业务可换。

## 6. Session & Trace 模型

### 6.1 Session 生命周期

- **创建**：必须显式 `runtime.create_session(tenant_id=..., user_id=..., attributes=...)`，禁止隐式创建
- **持久化**：end-of-turn write-through——每个 turn 结束 `store.save()`
- **并发**：强制乐观锁（`Session.version`）；store 实现自决 retry 策略（默认 3 次），超限抛 `SessionConflictError`
- **取消**：caller 取消 invoke task → engine 在 `finally` 中**照样保存**当前 session（含半成品消息）+ flush trace，调用方自决要不要 retry/丢弃

### 6.2 多租户隔离

- `Session.tenant_id` 一等公民
- `SessionStore.load(session_id, tenant_id=...)`：tenant 不匹配返回 `None`（不报错防探测）
- `SessionStore.list(tenant_id=...)`：必须支持按 tenant 过滤
- **框架不做** tenant 校验逻辑——business 责任；但**框架强制** store 实现支持这两个签名

### 6.3 Span 树

- engine 在进入嵌套作用域时生成新 `span_id`、记录 `parent_span_id`
- 业务工具/钩子从 `ToolContext.current_span_id` 读取父 span
- `ToolContext.new_span_id()` 提供生成 helper
- 不强制 contextvars——业务自决并发模型

### 6.4 TraceEvent 词汇表

见附录 A。约定（非强制）：业务自定义 kind 采用业务前缀命名（如 `crm.lead.created`），避免与附录 A 中保留名冲突。框架不主动校验前缀，但 `TraceSink` 实现可选择校验。

### 6.5 TraceSink 写入策略

- 默认 `NullSink`（不记录）/ `JsonlSink`（开发用）
- 生产：建议 buffered async write
- **失败永不阻断**：TraceSink 抛任何异常 → engine 捕获 + stderr log + 继续

## 7. 错误处理

### 7.1 异常分层

```
MetaHarneyError
├── ConfigurationError                    [fail-fast at runtime construction]
├── ProviderError
│   ├── RetryableProviderError
│   └── NonRetryableProviderError
├── ToolError
│   ├── ToolNotFoundError
│   ├── ToolInvalidArgsError
│   ├── ToolExecutionError
│   └── ToolTimeoutError
├── PermissionDeniedError
├── HookError
│   ├── HookHaltError                     [业务显式中断]
│   └── HookExecutionError                [fail-open]
├── SessionError
│   ├── SessionNotFoundError
│   ├── SessionConflictError
│   └── SessionStoreError
├── CompactionError
└── MultiAgentError
    ├── SpawnError
    └── ChildTimeoutError
```

### 7.2 处理矩阵

| 错误类 | 行为 | LLM 感知 | 终止 loop |
|--------|------|---------|----------|
| ConfigurationError | 构造 runtime 时抛 | ❌ | ✅ |
| RetryableProviderError | retry.py 自动重试，超限上抛 | ❌ | ✅ |
| NonRetryableProviderError | 立即上抛 | ❌ | ✅ |
| ToolError（任何子类） | 转 ToolResult 喂回 | ✅ | ❌ |
| ToolTimeoutError | 转 ToolResult + `trace("tool.timed_out")` | ✅ | ❌ |
| PermissionDeniedError | 转 ToolResult + `trace("tool.denied")` | ✅ | ❌ |
| HookHaltError | 上抛到 caller | ❌ | ✅ |
| HookExecutionError | 记录到 trace，继续 | ❌ | ❌ |
| SessionStoreError（load） | 上抛 | ❌ | ✅ |
| SessionConflictError（save） | store 内部 retry，超限上抛 | ❌ | ✅ |
| CompactionError | 记录到 trace，跳过本次压缩 | ❌ | ❌ |
| MultiAgentError | 转 ToolResult 喂回 | ✅ | ❌ |
| TraceSink 任何异常 | 捕获 + stderr log，永不阻断 | ❌ | ❌ |

### 7.3 三条核心规则

1. **工具/钩子/权限失败"喂回 LLM"**，让 agent 自适应
2. **观测组件失败永不阻断业务**——TraceSink 故障对系统透明
3. **业务想强制中断 → 用 `HookHaltError`**——这是唯一支持的中断方式

### 7.4 取消（Cancellation）

asyncio 原生。caller 取消 Task → `CancelledError` 沿 engine 传播。Engine 在 `finally` 中：
- `store.save(session)` 保留进度（可能是半成品 turn）
- `trace_sink.flush()`

工具必须 cancellation-aware（在 `await` 点自然响应）。Engine 不强杀。

### 7.5 工具超时

每个 BaseTool 子类可声明 `default_timeout: ClassVar[float | None]`；`RuntimeSettings.tool_timeout_overrides[tool_name]` 可覆盖；`global_default_timeout` 兜底（默认 300s）。

解析顺序：**overrides → tool.default_timeout → global_default → None（不限）**

超时 → `asyncio.TimeoutError` → 转 `ToolResult(success=False, error="...timed out")` → `trace("tool.timed_out")` → 喂回 LLM。

## 8. 测试策略

### 8.1 三层金字塔

```
              integration/       ← 5-10 个端到端场景（FakeLLMProvider）
              contracts/         ← 每个 Protocol 一套契约（所有实现必过）
              unit/              ← per-module/per-class 内部逻辑
```

### 8.2 契约测试

每个 Protocol 一套 abstract `XContract` 测试类。任何实现（含 `builtin/` 与未来业务实现）只需继承并提供 `make_X()` 工厂，即自动获得 30+ 项规范化测试。

需要契约测试的 Protocol：
- `SessionStoreContract`（强制乐观锁、租户隔离）
- `PermissionResolverContract`
- `TraceSinkContract`（强制异常隔离）
- `CompactionStrategyContract`
- `MultiAgentBackendContract`
- `PromptBuilderContract`

业务侧实现 `PostgresSessionStore`？继承 `SessionStoreContract` + 提供 `make_store()` = 自动具备 30+ 测试覆盖。

### 8.3 单元测试范围

- `test_engine_loop.py`、`test_retry.py`、`test_compaction_summarization.py`
- `test_permission_*.py`、`test_hook_decision_transform.py`
- `test_trace_event_validation.py`、`test_tool_timeout.py`
- 等等，per-module 覆盖

### 8.4 集成测试场景

使用 `FakeLLMProvider`（脚本化响应），覆盖：

1. happy-path
2. tool-error-recovery
3. permission-denied
4. multi-turn-session
5. hook-halt
6. multi-agent-blocking
7. multi-agent-detached
8. cancellation（含半成品 session 保留）
9. compaction（含 SummarizationCompactor 触发）
10. trace-sink-failure-isolation

### 8.5 业务测试支持

提供 `meta_harney.testing` 一等公民模块：

```python
from meta_harney.testing import FakeLLMProvider, runtime_for_testing

async def test_my_crm_tool():
    runtime = runtime_for_testing(
        tools=[MyLeadCreateTool()],
        scripted_llm=[...],
    )
    session = await runtime.create_session(tenant_id="acme")
    result = await runtime.invoke(session.id, "...")
    assert ...
```

### 8.6 CI 矩阵

- Python 3.10 / 3.11 / 3.12
- Linux + macOS
- `mypy --strict` 必过
- 覆盖率门槛：unit + contract 合计 ≥ 80%
- 完全 fake LLM，**不打真 API**（业务侧自行做真 LLM smoke test）

## 9. 迁移与删除计划（高层）

### 9.1 删除（一次性）

`ohmo/` · `frontend/` · `src/openharness/ui/` · `tools/*_tool.py`(42) · `commands/`(54) · `skills/bundled/` · `services/autodream*` · `prompts/system_prompt.py` 文案

### 9.2 保留并重构

- `engine/query.py` → `engine/loop.py`：去除硬编码工具名（`read_file`/`bash`/`grep`/`image_to_text`）、重写 tool-call 分支为基于 ToolRegistry 的泛化派发
- `permissions/checker.py` → 拆分为 `abstractions/permission.py`（协议）+ `builtin/permission/allow_all.py`（默认）；删除 SSH/AWS 路径列表
- `prompts/system_prompt.py` → 净化为 `builtin/prompt/minimal.py`
- `memory/` → 收编到 `abstractions/session.py` + `builtin/session/file_store.py`
- `tools/base.py` → 改造 `BaseTool` 与 `ToolInvocation`（去 cwd:Path）
- `hooks/executor.py` → 改造为基于 `HookDecision` 的派发
- `coordinator/` + `swarm/` → 抽象为 `MultiAgentBackend` Protocol，重写 in-process / subprocess backend

### 9.3 实施顺序

详细实施计划由 writing-plans skill 在批准本设计后产出。高层节奏：

1. **清理**：批量删除编程模块，包名重命名 `openharness` → `meta_harney`
2. **抽象层**：写出 9 个 abstraction 文件 + builtin 默认
3. **引擎重构**：改造 `engine/loop.py` 解除硬编码
4. **契约测试**：写各 Protocol 的 Contract 测试套
5. **集成测试**：FakeLLMProvider + 10 个 e2e 场景

## 10. 关键 Open Questions

无——所有重大设计决策已在 brainstorming 中明确。

实施过程中可能浮现的细节问题（如 SummarizationCompactor 的具体摘要 prompt 模板、provider 适配器对 `author` 字段的具体映射规则、契约测试的具体测试用例数），属于实施层面而非设计层面，将在 writing-plans 与执行阶段就地决定。

## 附录 A — TraceEvent 词汇表

| kind | 触发时机 | payload 关键字段 |
|------|---------|----------------|
| `session.created` | runtime.create_session() | `tenant_id`, `user_id` |
| `turn.started` | invoke() 开始 | `user_message_id` |
| `turn.completed` | invoke() 结束 | `assistant_message_id`, `total_tokens` |
| `prompt.built` | PromptBuilder 完成 | `system_prompt_len`, `n_messages` |
| `llm.requested` | 调 provider 之前 | `model`, `n_input_tokens` |
| `llm.completed` | provider 返回 | `n_output_tokens`, `stop_reason` |
| `retry.attempted` | 检测到 RetryableError | `attempt`, `delay_s`, `exc_type` |
| `retry.exhausted` | 重试次数耗尽 | `attempts`, `last_exc` |
| `tool.invoked` | 工具开始执行 | `tool_name`, `args` (truncated) |
| `tool.completed` | 工具返回 | `success`, `output_size` |
| `tool.denied` | permission deny | `tool_name`, `reason` |
| `tool.timed_out` | tool execution timeout | `tool_name`, `timeout_s` |
| `permission.resolved` | resolver 返回 | `verdict`, `reason` |
| `hook.fired` | hook handle() 完成 | `hook_name`, `event_kind`, `decision` |
| `compaction.triggered` | engine 调 compact | `before_tokens`, `after_tokens`, `before_msgs`, `after_msgs` |
| `agent.spawned` | MultiAgentBackend.spawn() | `child_session_id`, `mode`, `agent_name` |
| `agent.joined` | MultiAgentBackend.join() 返回 | `child_session_id`, `success` |
| `error.raised` | engine 捕获到非致命异常 | `exc_type`, `message`, `traceback_snippet` |

**约定**：业务自定义 kind 采用业务前缀命名（如 `crm.*`、`hr.*`），避免与上表保留名冲突。框架不强制校验——这是文档约定，业务可在自己的 `TraceSink` 实现中加校验逻辑。

## 附录 B — Tool Timeout 解析顺序

```
timeout = (
    settings.tool_timeout_overrides.get(tool.name)
    or tool.default_timeout
    or settings.global_default_timeout   # default 300s
    or None                              # None ⇒ no timeout
)
```
