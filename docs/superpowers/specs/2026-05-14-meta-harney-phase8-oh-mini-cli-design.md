# meta-harney Phase 8 — oh-mini Python Backend + CLI 设计

**日期：** 2026-05-14
**目标产物：** `/Users/baihe/Projects/study/oh-mini/` 独立项目，版本 v0.1.0
**meta-harney 依赖：** v0.0.7+（git URL 锁版本）

## 1. 目标与非目标

### 目标

Phase 8 是 OpenHarness 编程场景 demo 的第一个子项目（Sub-project 1 of 3）。交付一个**完整可用的命令行编程助手** `oh-mini`，作为独立 Python 项目存在；用 meta-harney runtime 装配，10 个 coding 工具，one-shot + interactive REPL 两种 CLI 形态。

**Phase 8 完成后即可独立体验和测试**——能跑 "查代码 → 改代码 → 跑测试 → 修复" 的真实编程闭环。Sub-project 2（Bridge 协议）和 Sub-project 3（React+Ink TUI）是后续 phase，不在 Phase 8 范围。

具体交付：

1. **新独立项目** `oh-mini`（路径 `/Users/baihe/Projects/study/oh-mini/`，包名 `oh-mini`，初版 0.1.0）
2. **依赖** meta-harney via `git+https://github.com/bailaohe/meta-harney.git@v0.0.7`
3. **CLI 入口** `oh` 命令（pyproject `[project.scripts]`）+ `python -m oh_mini`
4. **10 个 coding 工具**：file_read / file_write / file_edit / grep / glob / bash / todo_write / agent / notebook_edit / web_fetch
5. **双 provider** anthropic（默认） + openai，env 变量 + `--provider` flag
6. **InteractiveAskPermissionResolver** with `--yolo` / `--no-yolo` 覆盖；interactive 默认 Ask；one-shot 默认 AllowAll
7. **FileSessionStore** 根目录 `~/.oh-mini/sessions/`；`--resume <id>` 续接
8. **`CodingPromptBuilder`** 含 coding persona + cwd 注入
9. **CI** Python 3.10/3.11/3.12 × ubuntu/macos = 6 jobs；pytest + mypy strict + ruff check + ruff format check
10. **52 个测试**（44 unit + 8 integration），全部用 `FakeLLMProvider` 不打真 API

### 非目标

- **不**做 React+Ink TUI（Sub-project 3）
- **不**定义 Node ↔ Python Bridge 协议（Sub-project 2）
- **不**实现 OpenHarness 的其它 30+ 工具（cron、autopilot、send_message、channels、voice、vim…）
- **不**还原 OpenHarness 的 subscription forwarding（spawn 本地 Claude Code/Codex 子进程）
- **不**做 PyPI 发包（Phase X+）
- **不**做 Markdown 渲染、stream-json 输出（留 Sub-project 3）
- **不**做 MCP 集成
- **不**做 web_fetch 的 "fetch + summarize via LLM" 第二跳（仅 return body）
- **不**做 Windows 矩阵（与 meta-harney CI 一致）
- **不**做 sandbox（bash 不进 chroot/firejail；依赖 permission gate）
- **不**改 meta-harney（Phase 8 完全是消费方）

## 2. 总体架构

```
/Users/baihe/Projects/study/oh-mini/    （独立 git repo，独立版本号 0.1.0）
  └─ 依赖 meta-harney v0.0.7 (git URL)

入口分发：
  oh "task"              → one-shot
  oh                     → interactive REPL
  oh --resume <id> "..." → 加载老 session 再 one-shot
  oh --resume <id>       → 加载老 session 再 REPL

build_runtime() 工厂集成：
  AnthropicProvider/OpenAIProvider + CodingPromptBuilder
  + InteractiveAskPermissionResolver + FileSessionStore
  + InProcessMultiAgentBackend + NullSink + 10 个 BaseTool
  → AgentRuntime（meta-harney facade）

CLI 渲染：
  消费 StreamEvent → TextDelta 流式 print，ToolCallStarted/Completed
  打状态行，TurnCompleted 打总结。
```

子项目切分（roadmap 视图）：

```
Sub-project 1 (本 Phase 8): Python backend + CLI
Sub-project 2 (Phase 9):    Bridge 协议 (Node ↔ Python IPC)
Sub-project 3 (Phase 10):   React + Ink TUI 前端
```

Phase 8 完成后，oh-mini 已经是一个可用的编程助手 CLI；Sub-project 2/3 是用户体验增强，不做也不影响 Phase 8 的价值。

## 3. 文件结构

```
oh-mini/
├── pyproject.toml                    # 包元数据 + meta-harney 依赖
├── README.md                         # 快速上手 + 工具列表
├── LICENSE                           # Apache-2.0
├── .gitignore                        # Python 标准
├── .github/workflows/ci.yml          # Python 3.10/3.11/3.12 × ubuntu/macos
│
├── src/oh_mini/
│   ├── __init__.py                   # __version__ = "0.1.0", 导出 build_runtime
│   ├── __main__.py                   # `python -m oh_mini` → cli.main()
│   ├── cli.py                        # argparse + dispatch
│   ├── repl.py                       # interactive REPL
│   ├── runtime.py                    # build_runtime() 工厂
│   ├── permission.py                 # InteractiveAskPermissionResolver
│   ├── prompts.py                    # CodingPromptBuilder
│   ├── output.py                     # stream 渲染
│   │
│   └── tools/
│       ├── __init__.py               # ALL_TOOLS dict
│       ├── _safety.py                # resolve_path_within_cwd
│       ├── file_read.py
│       ├── file_write.py
│       ├── file_edit.py
│       ├── grep.py
│       ├── glob.py
│       ├── bash.py
│       ├── todo_write.py
│       ├── agent.py
│       ├── notebook_edit.py
│       └── web_fetch.py
│
└── tests/
    ├── unit/
    │   ├── tools/
    │   │   ├── test_file_read.py     test_file_write.py    test_file_edit.py
    │   │   ├── test_grep.py          test_glob.py          test_bash.py
    │   │   ├── test_todo_write.py    test_agent.py
    │   │   ├── test_notebook_edit.py test_web_fetch.py
    │   ├── test_permission.py
    │   ├── test_prompts.py
    │   └── test_runtime_factory.py
    └── integration/
        ├── test_cli_one_shot.py
        ├── test_cli_resume.py
        └── test_repl_interactive.py
```

## 4. 关键 API 与契约

### 4.1 `pyproject.toml` 关键字段

```toml
[project]
name = "oh-mini"
version = "0.1.0"
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
description = "Coding-agent CLI demo built on meta-harney runtime."
dependencies = [
    "meta-harney @ git+https://github.com/bailaohe/meta-harney.git@v0.0.7",
    "httpx>=0.27",
    "nbformat>=5.10",
    "prompt_toolkit>=3.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "mypy>=1.10", "ruff>=0.5"]

[project.scripts]
oh = "oh_mini.cli:main"
```

### 4.2 `build_runtime` 工厂签名

```python
# src/oh_mini/runtime.py
def build_runtime(
    *,
    provider: Literal["anthropic", "openai"] = "anthropic",
    model: str | None = None,
    yolo: bool = False,
    sessions_root: Path | None = None,  # 默认 ~/.oh-mini/sessions/
) -> AgentRuntime:
    """Assemble a meta-harney AgentRuntime configured for coding scenarios."""
```

### 4.3 `InteractiveAskPermissionResolver` Protocol 实现

```python
# src/oh_mini/permission.py
DANGEROUS_TOOLS = frozenset({"bash", "file_write", "file_edit", "notebook_edit"})

class InteractiveAskPermissionResolver:
    """Implements meta-harney's PermissionResolver Protocol."""

    def __init__(self, *, yolo: bool, dangerous_tools: frozenset[str] = DANGEROUS_TOOLS):
        self._yolo = yolo
        self._dangerous = dangerous_tools

    async def resolve(self, inv: ToolInvocation, session_id: str) -> PermissionDecision:
        if self._yolo or inv.name not in self._dangerous:
            return PermissionDecision(verdict="allow")
        # Interactive ask via prompt_toolkit; "y"/"yes"/"a"=always → allow.
        # "a" promotes to yolo for the rest of the session.
        # Ctrl-C / EOF / anything else → deny.
        ...
```

### 4.4 `CodingPromptBuilder`

```python
# src/oh_mini/prompts.py
class CodingPromptBuilder(MinimalPromptBuilder):
    async def build_system_prompt(self, session_id: str) -> str:
        base = await super().build_system_prompt(session_id)
        return (
            f"You are a coding assistant operating in directory: {os.getcwd()}\n\n"
            "Use the available tools to read code, modify files, run commands, "
            "and verify your work. When unsure, prefer reading files first. "
            "Always run tests after non-trivial changes. Use the TodoWrite tool "
            "to plan multi-step work.\n\n"
            f"{base}"
        )
```

### 4.5 CLI flags（argparse）

| Flag | Type | Default | 说明 |
|---|---|---|---|
| `prompt` | positional `str?` | None | 任务描述；缺省进 REPL |
| `--provider` | choices | `anthropic` | `anthropic` / `openai` |
| `--model` | str | provider 默认 | 覆盖 model |
| `--yolo` / `--no-yolo` | flag | None | 覆盖 permission 行为 |
| `--resume` | str | None | session id |
| `--show-thinking` | flag | False | 显示 ThinkingDelta（灰色 italic） |
| `--show-tool-calls` | flag | True | 显示 tool call 状态行（默认开） |
| `--sessions-root` | str | `~/.oh-mini/sessions/` | session 存储根目录 |
| `--version` | flag | — | print 版本退出 |

### 4.6 工具 input_schema 总览

| 工具 | input_schema |
|---|---|
| FileReadTool | `{path: str, offset?: int, limit?: int}` |
| FileWriteTool | `{path: str, content: str}` |
| FileEditTool | `{path: str, old_string: str, new_string: str, replace_all?: bool=false}` |
| GrepTool | `{pattern: str, path?: str=".", glob?: str, max_matches?: int=100}` |
| GlobTool | `{pattern: str, path?: str="."}` |
| BashTool | `{command: str, timeout?: int=60, cwd?: str}` |
| TodoWriteTool | `{todos: list[{content: str, status: "pending"\|"in_progress"\|"completed"}]}` |
| AgentTool | `{description: str, prompt: str}` |
| NotebookEditTool | `{path: str, cell_index: int, new_source: str}` |
| WebFetchTool | `{url: str, prompt?: str}` |

### 4.7 Default timeouts

- `BashTool.default_timeout = 60.0`
- `WebFetchTool.default_timeout = 30.0`
- 其它工具不设（meta-harney global 300s 兜底）

### 4.8 Agent tool 子-agent 工具集

```python
# src/oh_mini/tools/agent.py
SUBAGENT_ALLOWED_TOOLS = ["file_read", "grep", "glob"]  # 只读子集
```

子 agent 用 blocking 模式，AgentSpec 的 `instructions` 即调用方传入的 prompt。

## 5. Data flow

### 启动 + 装配

```
oh "task" / oh / oh --resume <id> "..."
  ↓ argparse
  ↓ env API key 检查（缺则 sys.exit(1)）
  ↓ build_runtime() → AgentRuntime
  ↓ 分发
       one-shot   → run_one_shot(rt, prompt)
       REPL       → run_repl(rt)
       resume     → run_one_shot/run_repl with session_id
```

### one-shot 数据流

```
session = await rt.create_session() [or already-existing if --resume]
console.print(f"Session: {session.id}")
async for ev in rt.stream(session.id, prompt):
    render_stream_event(ev, console)
    # TextDelta         → print(text, end="", flush=True)
    # ToolCallStarted   → "\n▸ [tool] starting..."
    # ToolCallCompleted → "  └─ {success ? ✓ : ✗ error}"
    # ThinkingDelta     → 灰色 italic（如 --show-thinking）
    # TurnCompleted     → "[done in N iters]"
console.print(f"\nSession: {session.id}")
```

### REPL 数据流

```
while True:
    line = await prompt_async("oh> ")
    if /exit /quit → break
    if /clear → new session
    if /sessions → list_sessions
    else: async for ev in rt.stream(session.id, line): render(ev)
```

### Permission 流（在 engine 内部触发）

```
LLM 决定调 bash → engine.permission_resolver.resolve(inv, session_id)
  InteractiveAskPermissionResolver.resolve():
    if yolo or inv.name not in DANGEROUS_TOOLS: allow
    else:
      console.print 工具名 + args
      ans = await prompt_async("Allow? [y/N/a]: ")
      if a → self._yolo = True; allow
      if y → allow
      else → deny (含 Ctrl-C / EOF)
```

deny → engine 生成 `ToolResult(success=False, error="permission denied")` 喂回 LLM；ToolCallStarted **不**发；engine loop 继续。

### Agent tool 子流

```
AgentTool.execute(inv, ctx):
  spec = AgentSpec(
    name="sub-agent",
    instructions=inv.args["prompt"],
    allowed_tools=SUBAGENT_ALLOWED_TOOLS,
    max_iters=5,
  )
  handle = await ctx.multi_agent.spawn(spec, inv.args["prompt"], inv.session_id, mode="blocking")
  result = await ctx.multi_agent.join(handle.child_session_id)
  return ToolResult(success=True, output=extract_text(result.content))
```

### Resume 流

```
oh --resume abc "..."
  session = await rt._session_store.load("abc")
  if not session: sys.exit(2)
  # PromptBuilder.build_context_messages() 自然加载 session.messages
  rt.stream("abc", prompt) → 与新 session 一致
```

## 6. Error handling

| 路径 | 行为 |
|---|---|
| 缺 API key | `sys.exit(1)` + 友好提示 |
| `--resume` 找不到 session | `sys.exit(2)` + `"no such session"` |
| Permission Ask 时 Ctrl-C | deny；engine 把 tool call 标 fail 喂回 LLM；REPL/one-shot 继续 |
| REPL 顶层 Ctrl-C / Ctrl-D | 优雅退出；session 由 engine `finally` 保住 |
| 工具 timeout | meta-harney 已包装 ToolResult(success=False, error="timeout"); loop 继续 |
| 工具内部抛 | `_execute_after_permission` 已 catch → ToolResult(success=False); loop 继续 |
| 路径 traversal | `_safety.resolve_path_within_cwd` 抛 → 工具 catch → ToolResult fail |
| Bash exit ≠ 0 | **不**算工具失败：ToolResult(success=True, output={stdout, stderr, exit_code}) |
| web_fetch 非 http(s) | ToolResult fail |
| web_fetch body > 1MB | 截断 + `"[truncated at 1MB]"` 后缀；success=True |
| Agent 子 agent 抛 | join 返回 final Message（错误反映在内容）；AgentTool return success=True with that text |
| Provider 429 / 5xx | meta-harney retry_with_backoff；耗尽 → RetryableProviderError 冒到 CLI |
| Provider 4xx | NonRetryableProviderError 冒到 CLI |
| `--yolo` interactive | 完全 bypass Ask |
| `--no-yolo` one-shot 无 TTY | input EOF → deny |
| 无 TTY 启动 REPL | 拒绝："REPL requires a TTY" |
| Session 文件破损 / version 冲突 | FileSessionStore 抛 → CLI catch + 友好提示 |
| meta-harney 不可用 | `ModuleNotFoundError` → `"pip install -e ."` |
| Windows | 不支持，CI 不跑 |

**核心不变量：**
- 任何工具失败不能让 turn 中止
- 任何 Permission deny 不能让 turn 中止
- 任何 Ctrl-C 必须保住 session
- Provider 错误由 meta-harney 重试；冒出来时清晰报错

## 7. Testing

### 7.1 用例分布

| 测试文件 | 类型 | 用例数 |
|---|---|---|
| `tests/unit/tools/test_file_read.py` | 新建 | 4 |
| `tests/unit/tools/test_file_write.py` | 新建 | 3 |
| `tests/unit/tools/test_file_edit.py` | 新建 | 4 |
| `tests/unit/tools/test_grep.py` | 新建 | 4 |
| `tests/unit/tools/test_glob.py` | 新建 | 3 |
| `tests/unit/tools/test_bash.py` | 新建 | 5 |
| `tests/unit/tools/test_todo_write.py` | 新建 | 2 |
| `tests/unit/tools/test_agent.py` | 新建 | 2 |
| `tests/unit/tools/test_notebook_edit.py` | 新建 | 3 |
| `tests/unit/tools/test_web_fetch.py` | 新建 | 4 |
| `tests/unit/test_permission.py` | 新建 | 6 |
| `tests/unit/test_prompts.py` | 新建 | 2 |
| `tests/unit/test_runtime_factory.py` | 新建 | 4 |
| `tests/integration/test_cli_one_shot.py` | 新建 | 3 |
| `tests/integration/test_cli_resume.py` | 新建 | 1 |
| `tests/integration/test_repl_interactive.py` | 新建 | 2 |
| **合计** | | **52** |

### 7.2 测试技术

- **不打真 API**：所有测试用 `meta_harney.testing.FakeLLMProvider` + `FakeRound`
- **工具单元**：实例化 `ToolContext` helper（NullSink + new_span helper），构造 `ToolInvocation`，await `tool.execute()`
- **permission 单元**：monkeypatch `input()` 或 `prompt_async()` 返回值
- **CLI 集成**：`subprocess.run(["python", "-m", "oh_mini", ...])`，通过 env var 注入 fake provider 模式（runtime.py 检测 `OH_MINI_TEST_MODE=1` 时用 FakeLLMProvider 替换 provider）
- **REPL 集成**：用 `pty` + asyncio.create_subprocess_exec 模拟 TTY 输入

### 7.3 CI（`.github/workflows/ci.yml`）

```yaml
matrix: Python 3.10/3.11/3.12 × ubuntu-latest/macos-latest = 6 jobs
steps:
  - actions/checkout
  - actions/setup-python with cache=pip
  - pip install -e ".[dev]"        # 包含 meta-harney from git URL
  - pytest -q
  - mypy src/oh_mini
  - mypy tests
  - ruff check src tests
  - ruff format --check src tests
```

## 8. 完成标准

- [ ] `/Users/baihe/Projects/study/oh-mini/` 独立 git repo 初始化
- [ ] `pyproject.toml` 含 meta-harney git URL 依赖 + 4 个二级依赖（httpx, nbformat, prompt_toolkit, rich）
- [ ] `oh "hi"` 命令能跑通（接 anthropic API 或 fake provider 都可）
- [ ] `oh` 进 REPL，能多轮对话
- [ ] `oh --resume <id> "..."` 能加载老 session 续接
- [ ] 10 个工具全部实现 + 单测通过
- [ ] InteractiveAskPermissionResolver 在交互/one-shot/yolo 三种场景下行为正确
- [ ] FileSessionStore 在 `~/.oh-mini/sessions/` 创建并 roundtrip 多种 ContentBlock
- [ ] CodingPromptBuilder 注入 cwd + persona
- [ ] 52 个测试全部通过；mypy strict + ruff check + ruff format 全绿
- [ ] CI 在 GitHub 上 6 个 job 全部 success（如 oh-mini 也建 remote）
- [ ] `v0.1.0` git tag（本地，可选 push 到 oh-mini 的 GitHub repo）

## 9. Sub-project 2 / 3 候选

- **Sub-project 2 (Phase 9)：Bridge 协议**
  - JSON-RPC over stdio：Python backend 暴露 `start-session` / `send-message` / `subscribe-stream` / `answer-permission` / `list-sessions` 等方法
  - 把 StreamEvent / Permission Ask 序列化为 JSONL 行
  - 配套 `oh-server` 子命令启动 backend 守护

- **Sub-project 3 (Phase 10)：React + Ink TUI**
  - Node.js 项目 + Ink JSX
  - 通过 Sub-project 2 协议跟 Python backend 通信
  - 实现 OpenHarness 原版的 streaming UI、permission modal、session sidebar 等
