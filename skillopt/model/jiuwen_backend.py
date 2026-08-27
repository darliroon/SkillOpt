"""Jiuwen (agent-core-rust) exec backend for SkillOpt.

Wraps the openjiuwenrust PyO3 extension to run a ReActAgent with local file
tools (glob/read/grep) in a workspace directory, mirroring run_codex_exec.
"""
from __future__ import annotations

import asyncio
import fnmatch
import glob as _glob_mod
import os

# Suppress Rust info/debug logs before the PyO3 module is imported.
os.environ.setdefault("RUST_LOG", "error")

import re
import shutil
from typing import Any

from skillopt.model.codex_harness import (
    prepare_workspace,
    render_skill_md,
    _retry_prompt,
    _validate_exec_path,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_JIUWEN_EXEC_CONFIG: dict[str, Any] = {
    "provider": os.environ.get("JIUWEN_MODEL_PROVIDER", "openai"),
    "api_key": os.environ.get("JIUWEN_API_KEY", ""),
    "api_base": os.environ.get("JIUWEN_API_BASE", ""),
    "verify_ssl": False,
    "max_iterations": 8,
    "empty_response_retries": 5,
}


def configure_jiuwen_exec(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    verify_ssl: bool | None = None,
    max_iterations: int | None = None,
    empty_response_retries: int | None = None,
) -> None:
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
    if empty_response_retries is not None:
        _JIUWEN_EXEC_CONFIG["empty_response_retries"] = int(empty_response_retries)


def get_jiuwen_exec_config() -> dict[str, Any]:
    return dict(_JIUWEN_EXEC_CONFIG)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
_TOOL_SCHEMAS = [
    {
        "name": "glob",
        "description": "List files matching a glob pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.txt'."},
                "path": {"type": "string", "description": "Directory to search in. Default: root."},
            },
            "required": ["pattern"],
        },
    },
    {
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
    {
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
]

# ---------------------------------------------------------------------------
# Local tool implementations
# ---------------------------------------------------------------------------

def _resolve_search_roots(search_path: str, roots: list[str]) -> list[str]:
    """Resolve a user-provided search path against workspace roots.

    Ensures file operations never escape the workspace. Mirrors how Codex
    scopes file access to its working directory.
    """
    if not search_path:
        return roots
    if os.path.isabs(search_path):
        for root in roots:
            if search_path.startswith(root):
                return [search_path]
        return []  # absolute path outside workspace
    return [os.path.join(r, search_path) for r in roots]


def _tool_glob(args: dict, roots: list[str]) -> str:
    pattern = args.get("pattern", "*")
    search_path = args.get("path", "")
    results: list[str] = []
    search_roots = _resolve_search_roots(search_path, roots)
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
    return "".join(lines[start:end])


def _tool_grep(args: dict, roots: list[str]) -> str:
    pattern = args.get("pattern", "")
    search_path = args.get("path", "")
    if not pattern:
        return "No pattern provided."
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return f"Invalid regex: {exc}"
    search_roots = _resolve_search_roots(search_path, roots)
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


_TOOL_DISPATCH = {"glob": _tool_glob, "read": _tool_read, "grep": _tool_grep}


def _make_tool_callback(tool_name: str, roots: list[str]):
    def callback(inputs: dict) -> str:
        tool_fn = _TOOL_DISPATCH.get(tool_name)
        if tool_fn is None:
            return f"Unknown tool: {tool_name}"
        return tool_fn(inputs, roots)
    return callback


# ---------------------------------------------------------------------------
# Artifacts & answer extraction
# ---------------------------------------------------------------------------

def _persist_jiuwen_artifacts(work_dir: str, raw: str, response: str) -> None:
    with open(os.path.join(work_dir, "jiuwen_raw.txt"), "w", encoding="utf-8") as f:
        f.write(raw)
    with open(os.path.join(work_dir, "jiuwen_response.txt"), "w", encoding="utf-8") as f:
        f.write(response)


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
    """Run a Jiuwen ReActAgent and return (response, raw_trace)."""
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
    try:
        return asyncio.run(_run_jiuwen_async(
            work_dir=work_dir, prompt=prompt, model=model,
            timeout=timeout, data_dirs=data_dirs, config=config,
        ))
    except RuntimeError as exc:
        if "already running" in str(exc) or "cannot be called from a running event loop" in str(exc):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_run_jiuwen_async(
                    work_dir=work_dir, prompt=prompt, model=model,
                    timeout=timeout, data_dirs=data_dirs, config=config,
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
    from openjiuwenrust._rust import (
        AgentCard, ReActAgent, ReActAgentConfig,
        ToolCard, CallbackTool,
        SysOperationCard, OperationMode, LocalWorkConfig,
        Runner, RunnerConfig, CheckpointerConfig,
    )

    roots: list[str] = [work_dir]
    for d in data_dirs or []:
        roots.append(_validate_exec_path(d))

    # 1. SysOperation (file system access scoped to work_dir)
    sysop_card = SysOperationCard(
        mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(work_dir=work_dir),
    )
    Runner.resource_mgr.add_sys_operation(sysop_card)
    sysop_id = sysop_card.id

    # 2. Runner config
    runner_config = RunnerConfig(
        distributed_mode=True,
        checkpointer_config=CheckpointerConfig(type_="in_memory", conf=None),
    )
    Runner.set_config(runner_config)
    Runner.start()

    # 3. Build ReActAgent
    agent_card = AgentCard(
        id=f"skillopt-jiuwen-{os.path.basename(work_dir)}",
        name="skillopt-target",
        description="SkillOpt target agent",
    )
    agent = ReActAgent(agent_card)

    # 4. Configure model client
    # The Python openai_compatible backend supports multi-key round-robin
    # (comma-separated keys); the Rust agent does not, so pick one randomly.
    raw_api_key = config.get("api_key", "") or os.environ.get("OPENAI_COMPATIBLE_API_KEY", "")
    api_keys = [k.strip() for k in raw_api_key.split(",") if k.strip()]
    api_key = api_keys[0] if api_keys else ""
    # Rust reqwest appends "/chat/completions" to api_base; strip trailing "/"
    # to avoid the double-slash "/v1//chat/completions" 404 error.
    api_base = config.get("api_base", "") or os.environ.get("OPENAI_COMPATIBLE_BASE_URL", "")
    api_base = api_base.rstrip("/")
    provider = config.get("provider", "openai")

    react_config = ReActAgentConfig()
    react_config = react_config.configure_model_client(
        provider=provider, api_key=api_key, api_base=api_base,
        model_name=model, verify_ssl=config.get("verify_ssl", True),
    )
    react_config = react_config.configure_max_iterations(
        config.get("max_iterations", 24)
    )

    # 5. System prompt — mirrors Claude Code's ExecBackend system prompt.
    #    Codex has its own built-in prompt that guides file reading; Jiuwen's
    #    Rust ReActAgent does not, so we provide the same generic workspace
    #    instruction that Claude Code uses (not dataset-specific).
    system_prompt = (
        "Use the workspace files to solve the task. "
        "Read task.md and the skill at .agents/skills/skillopt-target/SKILL.md before answering. "
        "Do not call a Skill tool; the ReflACT guidance is a local markdown file."
    )
    react_config = react_config.configure_prompt_template([
        {"role": "system", "content": system_prompt},
    ])
    react_config.sys_operation_id = sysop_id
    agent.configure(react_config)

    # 6. Register tools via CallbackTool
    ability_mgr = agent.ability_manager
    for schema in _TOOL_SCHEMAS:
        tool_card = ToolCard(
            id=f"tool_{schema['name']}",
            name=schema["name"],
            description=schema["description"],
            input_params=schema["parameters"],
        )
        cb = CallbackTool(tool_card, _make_tool_callback(schema["name"], roots))
        ability_mgr.add_callback_tool(cb)

    # 7. Run the agent
    inputs = {"query": prompt}
    trace_chunks: list[str] = []

    try:
        result = await asyncio.wait_for(agent.invoke(inputs), timeout=timeout)
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
