现在项目支持ChatBackEnd和 Exec Backend, Exec BackEnd 包括codex和claude,你可以先阅读一下这部分内容。
我希望能将一个新的BackEnd：Jiuwen,项目目录位于桌面的agent-core-rust文件夹，请你看看使用它做新BackEnd的可行性

---

## 可行性分析：将 agent-core-rust (Jiuwen) 作为 SkillOpt 新 Backend

### 两种集成路径

| 路径 | 类型 | 集成方式 | 工作量 | 推荐度 |
|------|------|----------|--------|--------|
| **A. Python 绑定 (PyO3)** | ExecBackend | 通过 `maturin` 编译 Python 扩展，在 `codex_harness.py` 中直接调用 | 中 | 推荐 |
| **B. A2A HTTP 服务** | ExecBackend | 启动 agent-core-rust 的 A2A HTTP 服务，SkillOpt 通过 JSON-RPC 调用 | 中高 | 可行但偏重 |
| **C. 纯 ChatBackend** | ChatBackend | 只用 agent-core-rust 的 LLM 客户端层，当作 chat API | 低 | 不推荐（浪费其 Agent 能力） |

### 推荐路径 A：作为 ExecBackend（与 codex_exec / claude_code_exec 同级）

**理由**：agent-core-rust 本质是一个 ReAct Agent 运行时（带工具调用循环），与 SkillOpt 现有的 `codex_exec`、`claude_code_exec` 定位完全一致。

### 关键对齐点

| SkillOpt ExecBackend 契约 | agent-core-rust 对应能力 |
|---------------------------|--------------------------|
| `work_dir` 工作目录 | `LocalWorkConfig(work_dir=...)` |
| `prompt` 任务提示 | `inputs = {"query": prompt}` |
| `model` 模型名 | `ReActAgentConfig.configure_model_client(model_name=model)` |
| `data_dirs` 文档目录 | 通过 `CallbackTool` 注册 glob/read/grep 工具 |
| `timeout` 超时 | 外层 asyncio.wait_for 包裹 |
| 返回 `(response, raw_trace)` | `invoke()` 返回 dict + 流式 chunk 拼接 trace |
| 需要 `<answer>` 标签提取 | 通过 prompt 约束 + 后处理提取 |

---

## 具体集成代码方案

### 架构总览

```
SkillOpt officeqa/rollout.py
  └─ is_target_exec_backend() → True
  └─ run_target_exec(work_dir, prompt, model, timeout, data_dirs)
      └─ codex_harness.run_target_exec()
          ├─ backend == "codex_exec"      → run_codex_exec(...)
          ├─ backend == "claude_code_exec" → run_claude_code_exec(...)
          ├─ backend == "cursor_exec"     → run_cursor_exec(...)
          ├─ backend == "copilot_exec"    → run_copilot_exec(...)
          └─ backend == "jiuwen_exec"     → run_jiuwen_exec(...)   ← 新增
```

### 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `skillopt/model/jiuwen_backend.py` | **新建** | 核心：ReActAgent 执行器 |
| 2 | `skillopt/model/codex_harness.py` | 修改 | `run_target_exec` 分派链加分支 |
| 3 | `skillopt/model/backend_config.py` | 修改 | 白名单 + 配置函数 |
| 4 | `skillopt/model/common.py` | 修改 | 别名 + 默认模型 |
| 5 | `skillopt/model/__init__.py` | 修改 | legacy `set_backend` + `get_backend_name` |
| 6 | `configs/officeqa/default.yaml` | 可选 | 添加 jiuwen_exec 专属配置 |

---

### 1. 新建 `skillopt/model/jiuwen_backend.py`

```python
"""Jiuwen (agent-core-rust) exec backend for SkillOpt.

This module wraps the openjiuwenrust PyO3 extension to run a ReActAgent
with local file tools (glob/read/grep) in a workspace directory, mirroring
the pattern of run_codex_exec / run_claude_code_exec.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import Any

# ---------------------------------------------------------------------------
# Workspace helpers (reuse shared utilities from codex_harness)
# ---------------------------------------------------------------------------
from skillopt.model.codex_harness import (
    ANSWER_SCHEMA,
    prepare_workspace,
    render_skill_md,
    _retry_prompt,
    _validate_exec_path,
)

# ---------------------------------------------------------------------------
# Jiuwen configuration globals
# ---------------------------------------------------------------------------
_JIUWEN_EXEC_CONFIG: dict[str, Any] = {
    "provider": os.environ.get("JIUWEN_MODEL_PROVIDER", "openai"),
    "api_key": os.environ.get("JIUWEN_API_KEY", ""),
    "api_base": os.environ.get("JIUWEN_API_BASE", "https://api.openai.com/v1"),
    "verify_ssl": True,
    "max_iterations": 24,
    "empty_response_retries": 0,
}


def configure_jiuwen_exec(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    verify_ssl: bool | None = None,
    max_iterations: int | None = None,
) -> None:
    """Configure the Jiuwen exec backend at runtime."""
    if provider is not None:
        _JIUWEN_EXEC_CONFIG["provider"] = provider
    if api_key is not None:
        _JIUWEN_EXEC_CONFIG["api_key"] = api_key
    if api_base is not None:
        _JIUWEN_EXEC_CONFIG["api_base"] = api_base
    if verify_ssl is not None:
        _JIUWEN_EXEC_CONFIG["verify_ssl"] = verify_ssl
    if max_iterations is not None:
        _JIUWEN_EXEC_CONFIG["max_iterations"] = int(max_iterations)


def get_jiuwen_exec_config() -> dict[str, Any]:
    return dict(_JIUWEN_EXEC_CONFIG)


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format, same as officeqa rollout)
# ---------------------------------------------------------------------------
_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "List files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '*.txt' or '**/*.json'",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Default: workspace root.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file and return its text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read."},
                    "offset": {"type": "integer", "description": "Start line (1-based). Default: 1."},
                    "limit": {"type": "integer", "description": "Max lines to read. Default: all."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search file contents with a regex pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search."},
                    "path": {"type": "string", "description": "Directory or file to search in."},
                },
                "required": ["pattern"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Local tool implementations
# ---------------------------------------------------------------------------
import fnmatch
import glob as _glob_mod


def _tool_glob(args: dict, roots: list[str]) -> str:
    pattern = args.get("pattern", "*")
    search_path = args.get("path", "")
    results: list[str] = []
    search_roots = [search_path] if search_path else roots
    for root in search_roots:
        full_pattern = os.path.join(root, pattern)
        results.extend(sorted(_glob_mod.glob(full_pattern, recursive=True)))
    if not results:
        return "No files found."
    return "\n".join(results[:200])


def _tool_read(args: dict, roots: list[str]) -> str:
    path = args.get("path", "")
    offset = int(args.get("offset", 1) or 1)
    limit = int(args.get("limit", 0) or 0)

    # Resolve path relative to roots if not absolute
    resolved = path
    if not os.path.isabs(path):
        for root in roots:
            candidate = os.path.join(root, path)
            if os.path.exists(candidate):
                resolved = candidate
                break

    if not os.path.exists(resolved):
        return f"File not found: {path}"

    try:
        with open(resolved, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as exc:
        return f"Error reading file: {exc}"

    start = max(0, offset - 1)
    end = start + limit if limit > 0 else len(lines)
    selected = lines[start:end]
    return "".join(selected)


def _tool_grep(args: dict, roots: list[str]) -> str:
    pattern = args.get("pattern", "")
    search_path = args.get("path", "")
    if not pattern:
        return "No pattern provided."

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex: {exc}"

    search_roots = [search_path] if search_path else roots
    results: list[str] = []

    for root in search_roots:
        if os.path.isfile(root):
            files = [root]
        else:
            files = []
            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    files.append(os.path.join(dirpath, fname))

        for fpath in files:
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{fpath}:{lineno}:{line.rstrip()}")
            except Exception:
                continue

        if len(results) >= 500:
            break

    if not results:
        return "No matches found."
    return "\n".join(results[:500])


_TOOL_DISPATCH = {
    "glob": _tool_glob,
    "read": _tool_read,
    "grep": _tool_grep,
}


def _make_tool_callback(tool_name: str, roots: list[str]):
    """Create a Python callable for CallbackTool."""
    def callback(inputs: dict) -> str:
        tool_fn = _TOOL_DISPATCH.get(tool_name)
        if tool_fn is None:
            return f"Unknown tool: {tool_name}"
        return tool_fn(inputs, roots)
    return callback


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------
def _persist_jiuwen_artifacts(work_dir: str, raw: str, response: str) -> None:
    raw_path = os.path.join(work_dir, "jiuwen_raw.txt")
    resp_path = os.path.join(work_dir, "jiuwen_response.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw)
    with open(resp_path, "w", encoding="utf-8") as f:
        f.write(response)


# ---------------------------------------------------------------------------
# Answer extraction
# ---------------------------------------------------------------------------
_ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL | re.IGNORECASE)


def _extract_answer(text: str) -> str:
    match = _ANSWER_RE.search(text or "")
    if match:
        return match.group(1).strip()
    return (text or "").strip()


# ---------------------------------------------------------------------------
# Core: run_jiuwen_exec
# ---------------------------------------------------------------------------
def run_jiuwen_exec(
    *,
    work_dir: str,
    prompt: str,
    model: str,
    timeout: int,
    images: list[str] | None = None,
    data_dirs: list[str] | None = None,
    allow_file_edits: bool = False,
) -> tuple[str, str]:
    """Run a Jiuwen ReActAgent in the workspace and return (response, raw_trace).

    Mirrors the signature of run_codex_exec / run_claude_code_exec.
    """
    config = get_jiuwen_exec_config()
    retries = int(config.get("empty_response_retries", 0) or 0)
    last_response = ""
    all_raw: list[str] = []

    for attempt in range(retries + 1):
        attempt_prompt = _retry_prompt(prompt, attempt)
        response, raw = _run_jiuwen_once(
            work_dir=work_dir,
            prompt=attempt_prompt,
            model=model,
            timeout=timeout,
            data_dirs=data_dirs,
            config=config,
        )
        all_raw.append(f"===== JIUWEN ATTEMPT {attempt + 1} =====\n{raw}")
        last_response = response
        if response.strip():
            combined = "\n\n".join(all_raw)
            _persist_jiuwen_artifacts(work_dir, combined, response)
            return response, combined

    combined = "\n\n".join(all_raw)
    _persist_jiuwen_artifacts(work_dir, combined, last_response)
    return last_response, combined


def _run_jiuwen_once(
    *,
    work_dir: str,
    prompt: str,
    model: str,
    timeout: int,
    data_dirs: list[str] | None,
    config: dict[str, Any],
) -> tuple[str, str]:
    """Single Jiuwen execution attempt."""
    try:
        return asyncio.run(_run_jiuwen_async(
            work_dir=work_dir,
            prompt=prompt,
            model=model,
            timeout=timeout,
            data_dirs=data_dirs,
            config=config,
        ))
    except RuntimeError as exc:
        # asyncio.run already called → re-enter with fresh loop
        if "This event loop is already running" in str(exc) or "asyncio.run() cannot be called from a running event loop" in str(exc):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_run_jiuwen_async(
                    work_dir=work_dir,
                    prompt=prompt,
                    model=model,
                    timeout=timeout,
                    data_dirs=data_dirs,
                    config=config,
                ))
            finally:
                loop.close()
        raise


async def _run_jiuwen_async(
    *,
    work_dir: str,
    prompt: str,
    model: str,
    timeout: int,
    data_dirs: list[str] | None,
    config: dict[str, Any],
) -> tuple[str, str]:
    """Async core: build ReActAgent, run, collect trace chunks."""
    from openjiuwenrust._rust import (
        AgentCard,
        ReActAgent,
        ReActAgentConfig,
        ToolCard,
        CallbackTool,
        SysOperationCard,
        OperationMode,
        LocalWorkConfig,
        Runner,
        RunnerConfig,
        CheckpointerConfig,
    )

    # Validate data dirs
    roots: list[str] = [work_dir]
    for d in data_dirs or []:
        roots.append(_validate_exec_path(d))

    # 1. Configure SysOperation (file system access scoped to work_dir)
    sysop_card = SysOperationCard(
        mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(work_dir=work_dir),
    )
    Runner.resource_mgr.add_sys_operation(sysop_card)
    sysop_id = sysop_card.id

    # 2. Configure Runner (in-memory checkpointer, no persistence needed)
    runner_config = RunnerConfig(
        distributed_mode=True,
        checkpointer_config=CheckpointerConfig(type_="in_memory", conf=None),
    )
    Runner.set_config(runner_config)
    Runner.start()

    # 3. Build ReActAgent
    agent_card = AgentCard(id="skillopt-jiuwen", name="skillopt-target", description="SkillOpt target agent")
    agent = ReActAgent(agent_card)

    # 4. Configure model client
    api_key = config.get("api_key", "") or os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
    api_base = config.get("api_base", "") or os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "")
    provider = config.get("provider", "openai")

    react_config = ReActAgentConfig()
    react_config = react_config.configure_model_client(
        provider=provider,
        api_key=api_key,
        api_base=api_base,
        model_name=model,
        verify_ssl=config.get("verify_ssl", True),
    )
    react_config = react_config.configure_max_iterations(config.get("max_iterations", 24))

    # 5. System prompt: skill + tool instructions + answer format
    system_prompt = (
        "You are an expert agent working over local Treasury bulletin text files.\n"
        "You have three tools: glob, read, grep.\n"
        "- Use glob to find files matching a pattern.\n"
        "- Use read to read file contents (supports offset/limit for large files).\n"
        "- Use grep to search file contents with regex.\n"
        "Always search and verify evidence before answering.\n"
        "Return the final answer inside <answer>...</answer> tags.\n"
        "The answer should be concise and factual.\n"
    )
    react_config = react_config.configure_prompt_template([
        {"role": "system", "content": system_prompt},
    ])

    # 6. Set workspace + sys_operation
    react_config.sys_operation_id = sysop_id

    agent.configure(react_config)

    # 7. Register tools via CallbackTool
    ability_mgr = agent.ability_manager
    for schema in _TOOL_SCHEMAS:
        fn = schema["function"]
        tool_card = ToolCard(
            id=f"tool_{fn['name']}",
            name=fn["name"],
            description=fn["description"],
            input_params=fn["parameters"],
        )
        cb = CallbackTool(tool_card, _make_tool_callback(fn["name"], roots))
        ability_mgr.add_callback_tool(cb)

    # 8. Run the agent
    inputs = {"query": prompt}
    trace_chunks: list[str] = []

    try:
        result = await asyncio.wait_for(
            agent.invoke(inputs),
            timeout=timeout,
        )
        # result is a dict: {"output": "...", "result_type": "answer"|"error"}
        output_text = result.get("output", "") if isinstance(result, dict) else str(result)
        result_type = result.get("result_type", "") if isinstance(result, dict) else ""
        trace_chunks.append(f"[result_type={result_type}]")
        trace_chunks.append(output_text)
        response = output_text

    except asyncio.TimeoutError:
        trace_chunks.append(f"[TIMEOUT after {timeout}s]")
        response = ""

    except Exception as exc:
        trace_chunks.append(f"[ERROR] {exc}")
        response = ""

    raw = "\n".join(trace_chunks)
    return response, raw
```

---

### 2. 修改 `skillopt/model/codex_harness.py`

在 `run_target_exec` 函数的分派链末尾、`raise ValueError` 之前插入：

```python
# --- 在 run_target_exec 函数中，copilot_exec 分支之后添加 ---

    if backend == "jiuwen_exec":
        from skillopt.model.jiuwen_backend import run_jiuwen_exec
        return run_jiuwen_exec(
            work_dir=work_dir,
            prompt=prompt,
            model=model,
            timeout=timeout,
            images=images,
            data_dirs=data_dirs,
            allow_file_edits=allow_file_edits,
        )
```

完整上下文（展示修改位置）：

```python
def run_target_exec(
    *,
    work_dir: str,
    prompt: str,
    model: str,
    timeout: int,
    images: list[str] | None = None,
    data_dirs: list[str] | None = None,
    allowed_tools: list[str] | str | None = None,
    permission_mode: str | None = None,
    sandbox: str | None = None,
    full_auto: bool | None = None,
    allow_file_edits: bool = False,
) -> tuple[str, str]:
    backend = get_target_backend()
    if backend == "codex_exec":
        return run_codex_exec(...)
    if backend == "claude_code_exec":
        return run_claude_code_exec(...)
    if backend == "cursor_exec":
        return run_cursor_exec(...)
    if backend == "copilot_exec":
        return run_copilot_exec(...)

    # ↓↓↓ 新增分支 ↓↓↓
    if backend == "jiuwen_exec":
        from skillopt.model.jiuwen_backend import run_jiuwen_exec
        return run_jiuwen_exec(
            work_dir=work_dir,
            prompt=prompt,
            model=model,
            timeout=timeout,
            images=images,
            data_dirs=data_dirs,
            allow_file_edits=allow_file_edits,
        )
    # ↑↑↑ 新增分支 ↑↑↑

    raise ValueError(f"Unsupported exec backend: {backend}")
```

---

### 3. 修改 `skillopt/model/backend_config.py`

#### 3a. `set_target_backend` 白名单加 `"jiuwen_exec"`

```python
# 修改前 (第 152 行):
if TARGET_BACKEND not in {"openai_chat", "claude_chat", "qwen_chat", "minimax_chat", "openai_compatible", "copilot_chat", "codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec"}:

# 修改后:
if TARGET_BACKEND not in {"openai_chat", "claude_chat", "qwen_chat", "minimax_chat", "openai_compatible", "copilot_chat", "codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec", "jiuwen_exec"}:
```

#### 3b. `is_target_exec_backend()` 集合加 `"jiuwen_exec"`

```python
# 修改前 (第 166-167 行):
def is_target_exec_backend() -> bool:
    return TARGET_BACKEND in {"codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec"}

# 修改后:
def is_target_exec_backend() -> bool:
    return TARGET_BACKEND in {"codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec", "jiuwen_exec"}
```

#### 3c. 新增配置函数（文件末尾追加）

```python
# ---------------------------------------------------------------------------
# Jiuwen (agent-core-rust) exec backend configuration
# ---------------------------------------------------------------------------
_JIUWEN_EXEC_CONFIG: dict[str, str] = {
    "provider": os.environ.get("JIUWEN_MODEL_PROVIDER", "openai"),
    "api_key": os.environ.get("JIUWEN_API_KEY", ""),
    "api_base": os.environ.get("JIUWEN_API_BASE", ""),
    "max_iterations": "24",
}


def configure_jiuwen_exec(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    max_iterations: int | None = None,
) -> None:
    """Configure the Jiuwen (agent-core-rust) exec backend."""
    global _JIUWEN_EXEC_CONFIG
    cfg = dict(_JIUWEN_EXEC_CONFIG)
    if provider is not None:
        cfg["provider"] = str(provider).strip()
        os.environ["JIUWEN_MODEL_PROVIDER"] = cfg["provider"]
    if api_key is not None:
        cfg["api_key"] = str(api_key).strip()
        os.environ["JIUWEN_API_KEY"] = cfg["api_key"]
    if api_base is not None:
        cfg["api_base"] = str(api_base).strip()
        os.environ["JIUWEN_API_BASE"] = cfg["api_base"]
    if max_iterations is not None:
        cfg["max_iterations"] = str(int(max_iterations))
    _JIUWEN_EXEC_CONFIG = cfg
    # 同步到 jiuwen_backend 模块
    try:
        from skillopt.model.jiuwen_backend import configure_jiuwen_exec as _configure
        _configure(
            provider=cfg.get("provider"),
            api_key=cfg.get("api_key"),
            api_base=cfg.get("api_base"),
            max_iterations=int(cfg.get("max_iterations", 24)),
        )
    except ImportError:
        pass


def get_jiuwen_exec_config() -> dict[str, str]:
    return dict(_JIUWEN_EXEC_CONFIG)
```

---

### 4. 修改 `skillopt/model/common.py`

#### 4a. `_BACKEND_DEFAULT_MODELS` 加默认模型

```python
# 在 _BACKEND_DEFAULT_MODELS 字典中追加:
_BACKEND_DEFAULT_MODELS = {
    # ... 现有项 ...
    "openai_compatible": "gpt-4o-mini",
    "jiuwen_exec": "gpt-4o",          # ← 新增
}
```

#### 4b. `_BACKEND_ALIASES` 加别名

```python
# 在 _BACKEND_ALIASES 字典中追加:
_BACKEND_ALIASES = {
    # ... 现有项 ...
    "compat": "openai_compatible",
    "jiuwen": "jiuwen_exec",          # ← 新增
    "jiuwen_exec": "jiuwen_exec",     # ← 新增
}
```

---

### 5. 修改 `skillopt/model/__init__.py`

#### 5a. `set_backend` legacy 入口加分支

```python
# 在 set_backend 函数中，copilot_exec 分支之后添加:
    if normalized == "jiuwen_exec":
        set_optimizer_backend("openai_chat")  # optimizer 仍用 chat 后端
        set_target_backend("jiuwen_exec")
        return "jiuwen_exec"
```

#### 5b. `get_backend_name` 加分支

```python
def get_backend_name() -> str:
    optimizer = get_optimizer_backend()
    target = get_target_backend()
    if optimizer == target:
        return optimizer
    # exec backends with openai_chat optimizer
    if target in {"codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec", "jiuwen_exec"}:
        return target  # ← "jiuwen_exec" 自动包含
    return f"{optimizer}/{target}"
```

---

### 6. 可选：`configs/officeqa/default.yaml` 添加 jiuwen_exec 配置

```yaml
# 在 env 段添加 jiuwen_exec 专属配置（仅当 target_backend=jiuwen_exec 时生效）
env:
  # ... 现有配置 ...

  # Jiuwen exec backend 配置
  jiuwen_provider: openai                    # openai | deepseek | dashscope 等
  jiuwen_api_key: ""                         # 留空则回退到 OPENAI_COMPATIBLE_API_KEY
  jiuwen_api_base: ""                        # 留空则回退到 OPENAI_COMPATIBLE_BASE_URL
  jiuwen_max_iterations: 24
```

---

### 7. 构建与安装

#### 7a. 安装 maturin 并编译 Python 扩展

```bash
# 在 SkillOpt venv 中安装 maturin
cd ~/桌面/SkillOpt
.venv/bin/pip install maturin

# 编译 agent-core-rust 的 Python 扩展到当前 venv
cd ~/桌面/agent-core-rust
~/桌面/SkillOpt/.venv/bin/maturin develop -m crates/openjiuwen-py/Cargo.toml --release

# 验证
~/桌面/SkillOpt/.venv/bin/python -c "from openjiuwenrust._rust import ReActAgent; print('Jiuwen binding OK')"
```

#### 7b. 配置环境变量（.env 或 shell）

```bash
# Jiuwen exec backend 配置
export JIUWEN_MODEL_PROVIDER=openai
export JIUWEN_API_KEY=sk-your-api-key
export JIUWEN_API_BASE=https://yibuapi.com/v1/
```

#### 7c. 运行测试

```bash
# 使用 jiuwen_exec 后端运行 officeqa eval
cd ~/桌面/SkillOpt
.venv/bin/python scripts/eval_only.py \
    --config configs/officeqa/default.yaml \
    --skill ckpt/officeqa/gpt5.5_skill.md \
    --split valid_unseen \
    --target_backend jiuwen_exec \
    --out_root output/officeqa_jiuwen_eval
```

---

### 8. 数据流图

```
                    ┌─────────────────────────────────────────┐
                    │  officeqa/rollout.py: process_one()     │
                    │  is_target_exec_backend() → True        │
                    │  调用 run_target_exec(work_dir, prompt, │
                    │    model, timeout, data_dirs)           │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │  codex_harness.py: run_target_exec()    │
                    │  backend == "jiuwen_exec"               │
                    │  → jiuwen_backend.run_jiuwen_exec()    │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │  jiuwen_backend.py: _run_jiuwen_async() │
                    │                                         │
                    │  1. SysOperationCard(work_dir=...)      │
                    │  2. ReActAgent + configure_model_client  │
                    │  3. CallbackTool: glob/read/grep        │
                    │  4. agent.invoke({"query": prompt})     │
                    │  5. 提取 <answer> 标签                   │
                    │  6. 返回 (response, raw_trace)          │
                    └────────────────┬────────────────────────┘
                                     │
                    ┌────────────────▼────────────────────────┐
                    │  agent-core-rust (PyO3)                 │
                    │  ReActAgent 循环:                       │
                    │    LLM → tool_call → CallbackTool       │
                    │    → Python glob/read/grep → result     │
                    │    → LLM → ... → <answer>               │
                    └─────────────────────────────────────────┘
```

---

### 9. 注意事项与后续优化

1. **并发安全**：`_run_jiuwen_async` 每次调用创建新的 AgentCard/Agent，`Runner.resource_mgr` 是全局单例。并发执行时 SysOperation 的 `work_dir` 不同，但全局 registry 会累积。如遇问题，可在每次执行后清理：`Runner.resource_mgr` 目前无 `remove_sys_operation` 接口，需在 agent-core-rust 侧补齐。

2. **异步运行时**：`asyncio.run()` 在 ThreadPoolExecutor worker 中调用时可能遇到 "event loop already running" 问题。代码已做了 fallback（新建 event loop），但如果 officeqa 的 `workers=36` 并发下仍有问题，可考虑用 `asyncio.run_coroutine_threadsafe` + 共享 loop。

3. **工具路径安全**：`_validate_exec_path` 复用 codex_harness 的实现，会拒绝暴露 `officeqa_split` 等敏感数据目录。`data_dirs` 参数会被验证。

4. **流式模式**：当前使用 `agent.invoke()`（非流式）。如需更细粒度的 trace，可改用 `agent.stream()` 异步迭代 `OutputSchema` chunk，拼接完整 trace。

5. **模型回退**：当 `JIUWEN_API_KEY` / `JIUWEN_API_BASE` 未配置时，回退到 SkillOpt 的 `OPENAI_COMPATIBLE_*` 环境变量，复用已有配置。

6. **Codex CLI 对比**：与 `run_codex_exec` 的对比——
   - codex_exec 启动 `codex exec` 子进程，通过 stdin/stdout 通信
   - jiuwen_exec 直接在 Python 进程内通过 PyO3 调用 Rust，无子进程开销
   - codex 有 `--sandbox workspace-write` 隔离；jiuwen 无沙箱，靠 `work_dir` 软约束
