"""ReAct-based Skill Proposer — WikiSkill 论文的核心设计。

以 ReAct (Reasoning + Acting) 方式工作:
1. Proposer 启动时只获得 index.md + skill-impact.md + 本轮摘要
2. 用 read_file 工具按需读取具体 pattern 文件和原始轨迹
3. Thought → Action → Observation 循环，直到产出 Final Answer (patch)

对齐论文 §3.2.3: "Skill Proposer reviews the updated wiki and reads execution
traces from the latest iteration to generate or modify candidate skills."
"""
from __future__ import annotations

import json
import os
import re
import time
import traceback

from skillopt.model import chat_optimizer
from skillopt.prompts import load_prompt
from skillopt.utils import extract_json


def _read_file(path: str, max_chars: int = 15000) -> str:
    """Read a file and truncate to max_chars.

    Implements the paper's per-trajectory 15k character limit.
    """
    if not os.path.exists(path):
        return f"(file not found: {path})"
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read(max_chars + 1)
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncated)"
        return content
    except OSError as e:
        return f"(error reading {path}: {e})"


def _format_iteration_summary(
    rollout_results: list[dict],
    step: int,
    epoch: int,
) -> str:
    """Format a compact summary of the current iteration for the Proposer."""
    failures = [r for r in rollout_results if not r.get("hard") or float(r.get("hard", 0)) < 1e-9]
    successes = [r for r in rollout_results if r.get("hard") and float(r.get("hard", 0)) > 0.5]

    lines = [
        f"## Current Iteration Summary (Step {step}, Epoch {epoch})\n",
        f"- Total rollouts: {len(rollout_results)}",
        f"- Failures: {len(failures)}",
        f"- Successes: {len(successes)}\n",
    ]

    if failures:
        lines.append("### Key Failures\n")
        for r in failures[:8]:
            tid = str(r.get("id", "?"))
            fail_reason = str(r.get("fail_reason", ""))[:200]
            predicted = str(r.get("predicted_answer", ""))[:80]
            gold = str(r.get("gold_answer", ""))[:80]
            lines.append(
                f"- **{tid}**: {fail_reason}\n"
                f"  - Predicted: {predicted} | Gold: {gold}\n"
            )

    return "\n".join(lines)


def _parse_action(response: str) -> str | None:
    """Extract the read_file path from a ReAct action line.

    Returns the file path, or None if no action found.
    """
    # Pattern: Action: read_file("path") or Action: read_file('path')
    match = re.search(r'Action:\s*read_file\(\s*["\']([^"\']+)["\']\s*\)', response)
    if match:
        return match.group(1)
    return None


def _is_final_answer(response: str) -> str | None:
    """Extract the Final Answer JSON from a ReAct response.

    Returns the JSON string, or None if not a final answer.
    """
    match = re.search(r'Final Answer:\s*(.+)', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _extract_thought(response: str) -> str:
    """Extract the Thought: line from a ReAct response."""
    match = re.search(r'Thought:\s*(.+?)(?:\n(?:Action:|Final Answer:)|$)', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def run_react_proposer(
    rollout_results: list[dict],
    skill_content: str,
    wiki_dir: str,
    out_root: str,
    prediction_dir: str,
    *,
    step: int = 0,
    epoch: int = 1,
    max_iterations: int = 8,
    max_traj_chars: int = 15000,
    max_completion_tokens: int = 0,
    system_prompt: str | None = None,
) -> dict | None:
    """Run the ReAct-based Skill Proposer.

    The Proposer starts with minimal context (index + impact + summary),
    then uses read_file to access specific patterns and trajectories on demand.

    Returns a patch dict ``{"reasoning": str, "patch": {"edits": [...]}}``
    or ``None`` on failure.
    """
    # Build initial context (minimal — just index, impact, and summary)
    index_path = os.path.join(wiki_dir, "index.md")
    index_content = _read_file(index_path) if os.path.exists(index_path) else "(no wiki index)"

    impact_path = os.path.join(wiki_dir, "skill-impact.md")
    # Read last 3000 chars of skill-impact (recent entries)
    impact_content = ""
    if os.path.exists(impact_path):
        with open(impact_path, encoding="utf-8") as f:
            full_impact = f.read()
        impact_content = full_impact[-3000:] if len(full_impact) > 3000 else full_impact

    iteration_summary = _format_iteration_summary(rollout_results, step, epoch)

    # Load prompt
    actual_system = system_prompt if system_prompt is not None else load_prompt("react_proposer")

    # Write current skill to a temp path so read_file can access it
    skill_temp_path = os.path.join(wiki_dir, "..", "skills", "SKILL.md")
    os.makedirs(os.path.dirname(skill_temp_path), exist_ok=True)
    with open(skill_temp_path, "w", encoding="utf-8") as f:
        f.write(skill_content)

    # Build the initial user message
    initial_user = (
        f"## Initial Context\n\n"
        f"{index_content}\n\n"
        f"## Recent Skill-Impact History\n\n"
        f"{impact_content}\n\n"
        f"{iteration_summary}\n\n"
        f"You have the `read_file(path)` tool available. "
        f"Paths are relative to the workspace root.\n"
        f"Available paths include:\n"
        f"- `wiki/patterns/pattern_<id>.md`\n"
        f"- `raw/<task_id>/conversation.json`\n"
        f"- `skills/SKILL.md`\n"
        f"- `wiki/skill-impact.md`\n\n"
        f"Start your ReAct investigation now."
    )

    # ReAct loop
    conversation = [{"role": "user", "content": initial_user}]
    file_read_count = 0
    patterns_read: list[str] = []
    trajectories_read: list[str] = []

    for iteration in range(max_iterations):
        try:
            # Call LLM with the current conversation
            response_text = _call_llm_with_conversation(
                actual_system, conversation, max_completion_tokens,
            )
        except Exception as e:
            print(f"    [react] LLM call failed at iteration {iteration}: {e}")
            traceback.print_exc()
            return None

        if not response_text:
            print(f"    [react] empty response at iteration {iteration}")
            return None

        # Check for Final Answer
        final_json = _is_final_answer(response_text)
        if final_json:
            thought = _extract_thought(response_text)
            print(
                f"    [react] final answer at iter {iteration}, "
                f"patterns_read={len(patterns_read)}, "
                f"trajectories_read={len(trajectories_read)}"
            )
            try:
                patch = extract_json(final_json)
                if patch and isinstance(patch, dict):
                    if "patch" not in patch:
                        patch = {"reasoning": thought, "patch": patch}
                    return patch
                else:
                    print(f"    [react] invalid JSON in final answer")
                    return None
            except Exception:
                print(f"    [react] failed to parse final answer JSON")
                return None

        # Check for Action: read_file
        file_path = _parse_action(response_text)
        if file_path:
            file_read_count += 1
            thought = _extract_thought(response_text)

            # Resolve path relative to out_root
            full_path = os.path.join(out_root, file_path) if not os.path.isabs(file_path) else file_path

            # Read the file (with truncation)
            observation = _read_file(full_path, max_traj_chars)

            # Track what was read
            if "patterns/" in file_path:
                pid = os.path.basename(file_path).replace("pattern_", "").replace(".md", "")
                patterns_read.append(pid)
            elif "conversation.json" in file_path or "raw/" in file_path:
                trajectories_read.append(file_path)

            # Append to conversation
            conversation.append({"role": "assistant", "content": response_text})
            conversation.append({
                "role": "user",
                "content": f"Observation:\n{observation}",
            })

            print(
                f"    [react] iter {iteration}: read {file_path} "
                f"({len(observation)} chars)"
            )
            continue

        # Neither Action nor Final Answer — try to parse as final answer
        # (some LLMs don't follow the format exactly)
        try:
            patch = extract_json(response_text)
            if patch and isinstance(patch, dict):
                print(f"    [react] parsed implicit final answer at iter {iteration}")
                return patch
        except Exception:
            pass

        # Stuck — ask the LLM to produce a final answer
        conversation.append({"role": "assistant", "content": response_text})
        conversation.append({
            "role": "user",
            "content": "Please produce your Final Answer now. Output the skill patch as JSON.",
        })

    print(f"    [react] max iterations ({max_iterations}) reached, no final answer")
    return None


def _call_llm_with_conversation(
    system: str,
    conversation: list[dict],
    max_completion_tokens: int = 0,
) -> str:
    """Call chat_optimizer with a multi-turn conversation.

    Falls back to concatenating messages if the model API doesn't support
    multi-turn conversations.
    """
    # Build a single user message from the conversation history
    # (after the first user message, each subsequent pair is Action/Observation)
    user_parts = []
    for msg in conversation:
        if msg["role"] == "user":
            user_parts.append(msg["content"])
        elif msg["role"] == "assistant":
            user_parts.append(f"[Assistant]\n{msg['content']}")
        user_parts.append("---")

    # Remove the last separator
    if user_parts and user_parts[-1] == "---":
        user_parts.pop()

    combined_user = "\n\n".join(user_parts)

    response, _ = chat_optimizer(
        system=system,
        user=combined_user,
        max_completion_tokens=max_completion_tokens,
        retries=2,
        stage="react_proposer",
    )
    return response
