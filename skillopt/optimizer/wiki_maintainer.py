"""WikiSkill Wiki Maintainer — persistent knowledge base management.

Implements the Wiki Layer from WikiSkill (arXiv:2608.27454):
- Maintains ``wiki/patterns/`` (one markdown file per failure/success pattern)
- Maintains ``wiki/logs.md`` (per-iteration evolution log)
- Maintains ``wiki/skill-impact.md`` (accepted/rejected skill changes + diffs)

The wiki persists across all iterations and is never rolled back, even when
a candidate skill is rejected by the validation gate. This allows knowledge
to compound across the full optimization trajectory.

Public API
----------
- :func:`init_wiki`               — create wiki directory structure
- :func:`run_wiki_maintainer`     — LLM analysis of trajectories → pattern updates
- :func:`format_wiki_context`     — format wiki patterns for reflect injection
- :func:`update_skill_impact`     — append a skill accept/reject record
- :func:`get_wiki_summary`        — get pattern count and latest log entry
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


# ── Wiki directory layout ────────────────────────────────────────────────────

WIKI_DIRNAME = "wiki"
PATTERNS_DIRNAME = "patterns"
LOGS_FILENAME = "logs.md"
IMPACT_FILENAME = "skill-impact.md"


def _wiki_dir(out_root: str) -> str:
    return os.path.join(out_root, WIKI_DIRNAME)


def _patterns_dir(out_root: str) -> str:
    return os.path.join(_wiki_dir(out_root), PATTERNS_DIRNAME)


def _logs_path(out_root: str) -> str:
    return os.path.join(_wiki_dir(out_root), LOGS_FILENAME)


def _impact_path(out_root: str) -> str:
    return os.path.join(_wiki_dir(out_root), IMPACT_FILENAME)


# ── Initialization ───────────────────────────────────────────────────────────

def init_wiki(out_root: str) -> str:
    """Create the wiki directory structure if it does not exist.

    Returns the wiki directory path.
    """
    wiki = _wiki_dir(out_root)
    patterns = _patterns_dir(out_root)
    os.makedirs(patterns, exist_ok=True)

    logs_path = _logs_path(out_root)
    if not os.path.exists(logs_path):
        with open(logs_path, "w", encoding="utf-8") as f:
            f.write("# Wiki Evolution Log\n\n")
            f.write("This file is updated by the Wiki Maintainer after each iteration.\n\n")

    impact_path = _impact_path(out_root)
    if not os.path.exists(impact_path):
        with open(impact_path, "w", encoding="utf-8") as f:
            f.write("# Skill Impact Tracker\n\n")
            f.write("Records all skill accept/reject decisions with diffs.\n\n")

    return wiki


# ── Pattern file I/O ─────────────────────────────────────────────────────────

def _pattern_filename(pattern_id: str) -> str:
    """Sanitize a pattern ID into a valid filename."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", pattern_id)
    return f"pattern_{safe}.md"


def _list_patterns(wiki_dir: str) -> list[dict]:
    """List all existing patterns with their IDs and one-line summaries."""
    patterns_dir = os.path.join(wiki_dir, PATTERNS_DIRNAME)
    if not os.path.isdir(patterns_dir):
        return []
    results = []
    for fname in sorted(os.listdir(patterns_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(patterns_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            # Extract pattern_id from filename: "pattern_<id>.md" → "<id>"
            if fname.startswith("pattern_") and fname.endswith(".md"):
                pid = fname[len("pattern_"):-len(".md")]
            else:
                pid = fname.replace(".md", "")
            # Extract description as summary
            summary = ""
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("**Description:**"):
                    summary = line[len("**Description:**"):].strip()[:100]
                    break
            results.append({
                "id": pid,
                "filename": fname,
                "summary": summary,
                "content_preview": content[:200],
            })
        except OSError:
            continue
    return results


def _write_pattern(wiki_dir: str, pattern_id: str, pattern_type: str,
                   description: str, workaround: str,
                   task_ids: list[str] | None = None) -> str:
    """Write or update a pattern file."""
    patterns_dir = os.path.join(wiki_dir, PATTERNS_DIRNAME)
    os.makedirs(patterns_dir, exist_ok=True)
    fname = _pattern_filename(pattern_id)
    fpath = os.path.join(patterns_dir, fname)

    task_ref = ""
    if task_ids:
        task_ref = f"\n**Evidence (task IDs):** {', '.join(task_ids)}\n"

    content = (
        f"# Pattern: {pattern_id}\n\n"
        f"**Type:** {pattern_type}\n\n"
        f"**Description:** {description}\n\n"
        f"**Workaround:** {workaround}\n"
        f"{task_ref}\n"
        f"---\n"
    )
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    return fpath


def _append_logs(wiki_dir: str, entry: str) -> None:
    """Append a log entry to logs.md."""
    logs_path = os.path.join(wiki_dir, LOGS_FILENAME)
    with open(logs_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n\n")


def _append_impact(wiki_dir: str, entry: str) -> None:
    """Append an entry to skill-impact.md."""
    impact_path = os.path.join(wiki_dir, IMPACT_FILENAME)
    with open(impact_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n\n")


def _write_index_md(wiki_dir: str) -> str:
    """Persist the wiki pattern index to wiki/index.md.

    This file is read by the ReAct Proposer as its initial "catalog"
    of available knowledge patterns.
    """
    patterns = _list_patterns(wiki_dir)
    index_path = os.path.join(wiki_dir, "index.md")

    lines = ["# Wiki Pattern Index\n"]
    if not patterns:
        lines.append("(no patterns yet)\n")
    else:
        fail_patterns = [p for p in patterns if "fail" in p.get("content_preview", "").lower() or "failure" in p.get("content_preview", "").lower()]
        success_patterns = [p for p in patterns if p not in fail_patterns]

        if fail_patterns:
            lines.append("## Failure Patterns\n")
            for p in fail_patterns:
                lines.append(f"- **{p['id']}**: {p['summary']}")
            lines.append("")
        if success_patterns:
            lines.append("## Success Patterns\n")
            for p in success_patterns:
                lines.append(f"- **{p['id']}**: {p['summary']}")
            lines.append("")

        lines.append(f"_Total patterns: {len(patterns)}_\n")

    content = "\n".join(lines)
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    return index_path


def write_purpose_md(
    out_root: str,
    *,
    skill_path: str,
    step: int,
    epoch: int,
    pattern_refs: list[str] | None = None,
    action: str = "",
    edits_summary: str = "",
) -> str:
    """Write a PURPOSE.md file mapping the skill back to motivating wiki patterns.

    This implements the WikiSkill paper's Skills Layer requirement:
    each skill directory contains a PURPOSE.md that traces the skill's
    creation/modification back to the wiki patterns that inspired it.
    """
    wiki_dir = _wiki_dir(out_root)
    purpose_path = os.path.join(skill_path, "PURPOSE.md")

    lines = [
        "# Purpose\n",
        f"**Last modified:** Step {step} (Epoch {epoch})\n",
        f"**Action:** {action}\n",
    ]

    if pattern_refs:
        lines.append("## Motivating Wiki Patterns\n")
        for pid in pattern_refs:
            lines.append(f"- `{pid}` (see `wiki/patterns/pattern_{pid}.md`)")
        lines.append("")
    else:
        lines.append("## Motivating Wiki Patterns\n(None — no specific patterns referenced)\n")

    if edits_summary:
        lines.append("## Edits Summary\n")
        lines.append(edits_summary)
        lines.append("")

    content = "\n".join(lines)
    os.makedirs(os.path.dirname(purpose_path), exist_ok=True)
    with open(purpose_path, "w", encoding="utf-8") as f:
        f.write(content)
    return purpose_path


# ── Trajectory sampling ──────────────────────────────────────────────────────

def _sample_trajectories(
    rollout_results: list[dict],
    n_failures: int = 10,
    n_successes: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Sample failure and success trajectories from rollout results."""
    failures = [r for r in rollout_results if not r.get("hard") or float(r.get("hard", 0)) < 1e-9]
    successes = [r for r in rollout_results if r.get("hard") and float(r.get("hard", 0)) > 0.5]

    # Take up to n_failures, preferring diverse fail_reasons
    sampled_failures = failures[:n_failures] if len(failures) <= n_failures else failures[:n_failures]
    sampled_successes = successes[:n_successes] if len(successes) <= n_successes else successes[:n_successes]

    return sampled_failures, sampled_successes


def _format_trajectory_summary(results: list[dict], label: str, max_chars_per_traj: int = 0) -> str:
    """Format a compact summary of trajectory results for the LLM.

    If max_chars_per_traj > 0, each trajectory's total text is capped.
    """
    if not results:
        return f"### {label}\n(none)\n"
    lines = [f"### {label}"]
    for r in results:
        tid = str(r.get("id", "?"))
        predicted = str(r.get("predicted_answer", r.get("answer", "N/A")))[:200]
        gold = str(r.get("gold_answer", r.get("gold", "N/A")))[:200]
        fail_reason = str(r.get("fail_reason", ""))[:300]
        hard = r.get("hard", 0)
        soft = r.get("soft", 0.0)
        entry = (
            f"\n**Task {tid}:** hard={int(hard)} soft={soft:.2f}\n"
            f"- Predicted: {predicted}\n"
            f"- Gold: {gold}\n"
            f"- Fail reason: {fail_reason}\n"
        )
        if max_chars_per_traj > 0 and len(entry) > max_chars_per_traj:
            entry = entry[:max_chars_per_traj] + "...\n"
        lines.append(entry)
    return "\n".join(lines)


# ── Wiki Maintainer LLM call ──────────────────────────────────────────────────

def run_wiki_maintainer(
    rollout_results: list[dict],
    out_root: str,
    *,
    step: int = 0,
    epoch: int = 1,
    n_failures: int = 10,
    n_successes: int = 5,
    max_patterns: int = 40,
    max_completion_tokens: int = 0,
    max_traj_chars: int = 0,
    system_prompt: str | None = None,
) -> dict | None:
    """Run the Wiki Maintainer agent on rollout results.

    Samples failure and success trajectories, calls an LLM to analyze
    patterns, and writes new/updated pattern files to the wiki.

    Returns a dict with ``{"patterns_written": int, "patterns_total": int}``
    or ``None`` on failure.
    """
    wiki_dir = init_wiki(out_root)

    # Sample trajectories
    sampled_failures, sampled_successes = _sample_trajectories(
        rollout_results, n_failures, n_successes,
    )

    if not sampled_failures and not sampled_successes:
        print("    [wiki] no trajectories to analyze — skipping")
        return {"patterns_written": 0, "patterns_total": len(_list_patterns(wiki_dir))}

    # Build existing patterns index
    existing_patterns = _list_patterns(wiki_dir)
    patterns_index = ""
    if existing_patterns:
        lines = []
        for p in existing_patterns:
            lines.append(f"- {p['id']}: {p['summary']}")
        patterns_index = "\n".join(lines)
    else:
        patterns_index = "(none — this is the first iteration)"

    # Format trajectories for analysis (with per-traj truncation)
    fail_summary = _format_trajectory_summary(sampled_failures, "Failure Trajectories", max_traj_chars)
    success_summary = _format_trajectory_summary(sampled_successes, "Success Trajectories", max_traj_chars)

    # Load prompt
    actual_system = system_prompt if system_prompt is not None else load_prompt("wiki_maintainer")

    user = (
        f"## Iteration Context\n"
        f"- Step: {step}\n"
        f"- Epoch: {epoch}\n"
        f"- Total rollout results: {len(rollout_results)}\n"
        f"- Failures sampled: {len(sampled_failures)}\n"
        f"- Successes sampled: {len(sampled_successes)}\n\n"
        f"## Existing Wiki Patterns\n{patterns_index}\n\n"
        f"## Trajectory Analysis\n\n"
        f"{fail_summary}\n\n"
        f"{success_summary}\n"
    )

    try:
        response, _ = chat_optimizer(
            system=actual_system,
            user=user,
            max_completion_tokens=max_completion_tokens,
            retries=3,
            stage="wiki_maintainer",
        )
        result = extract_json(response)
    except Exception as e:
        print(f"    [wiki] LLM call failed: {e}")
        traceback.print_exc()
        return None

    if not result or not isinstance(result, dict):
        print("    [wiki] no valid JSON response from LLM — skipping pattern update")
        return {"patterns_written": 0, "patterns_total": len(_list_patterns(wiki_dir))}

    # Process patterns from LLM response
    new_patterns = result.get("patterns", [])
    if not isinstance(new_patterns, list):
        new_patterns = []

    patterns_written = 0
    for p in new_patterns:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id", f"p{patterns_written + 1}"))
        ptype = str(p.get("type", "failure"))
        desc = str(p.get("description", ""))
        workaround = str(p.get("workaround", ""))
        task_ids = p.get("task_ids", [])
        if not isinstance(task_ids, list):
            task_ids = [str(task_ids)] if task_ids else []

        if not desc:
            continue

        _write_pattern(wiki_dir, pid, ptype, desc, workaround, task_ids)
        patterns_written += 1

    # Enforce max_patterns limit (keep newest)
    all_patterns = _list_patterns(wiki_dir)
    if len(all_patterns) > max_patterns:
        excess = len(all_patterns) - max_patterns
        # Remove oldest patterns (first in sorted order)
        for p in all_patterns[:excess]:
            fpath = os.path.join(wiki_dir, PATTERNS_DIRNAME, p["filename"])
            try:
                os.remove(fpath)
            except OSError:
                pass

    # Append to evolution log
    log_entry = (
        f"## Step {step} (Epoch {epoch})\n"
        f"- Rollout results: {len(rollout_results)}\n"
        f"- Failures sampled: {len(sampled_failures)}\n"
        f"- Successes sampled: {len(sampled_successes)}\n"
        f"- Patterns written: {patterns_written}\n"
        f"- Total patterns: {len(_list_patterns(wiki_dir))}\n"
        f"- Key insights: {result.get('summary', 'N/A')}\n"
    )
    _append_logs(wiki_dir, log_entry)

    # Persist index.md (knowledge pattern index for ReAct Proposer)
    _write_index_md(wiki_dir)

    final_total = len(_list_patterns(wiki_dir))
    print(
        f"    [wiki] patterns written={patterns_written} "
        f"total={final_total}"
    )

    return {
        "patterns_written": patterns_written,
        "patterns_total": final_total,
    }


# ── Wiki context formatting for reflect injection ────────────────────────────

def format_wiki_context(out_root: str, max_chars: int = 4000) -> str:
    """Format the wiki pattern index for injection into the reflect stage.

    Returns a compact text block listing all pattern IDs and summaries.
    Returns empty string if no patterns exist or wiki is disabled.
    """
    wiki_dir = _wiki_dir(out_root)
    patterns = _list_patterns(wiki_dir)
    if not patterns:
        return ""

    lines = [
        "## Wiki Knowledge Base\n",
        "The following failure/success patterns have been accumulated across "
        "iterations. Use them to guide your analysis — avoid proposing edits "
        "that conflict with known workarounds, and prioritize patterns that "
        "remain unresolved.\n",
    ]
    for p in patterns:
        lines.append(f"- **{p['id']}**: {p['summary']}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (wiki index truncated)"
    return text


def format_skill_impact_context(out_root: str, max_entries: int = 5, max_chars: int = 2000) -> str:
    """Read skill-impact.md and format recent entries for reflect injection.

    This lets the reflect LLM see which edits were previously accepted or
    rejected, avoiding repetition of already-failed approaches.

    Returns empty string if no entries exist.
    """
    wiki_dir = _wiki_dir(out_root)
    impact_path = os.path.join(wiki_dir, IMPACT_FILENAME)
    if not os.path.exists(impact_path):
        return ""

    with open(impact_path, encoding="utf-8") as f:
        content = f.read()

    # Split into entries (each starts with "## Step ")
    sections = content.split("## Step ")
    # Skip the header (first section before any "## Step ")
    entries = sections[1:] if len(sections) > 1 else []
    if not entries:
        return ""

    # Take the most recent N entries (from the end)
    recent = entries[-max_entries:]

    lines = [
        "## Recent Skill Changes (from wiki skill-impact tracker)\n",
        "These are the most recent skill edit outcomes. "
        "Do NOT re-propose edits that were **rejected** — they already failed validation. "
        "Build on **accepted** edits instead.\n",
    ]
    for entry in recent:
        # Extract action and key info
        entry_text = entry.strip()
        lines.append(f"- ## Step {entry_text}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (skill-impact truncated)"
    return text


# ── Skill impact tracking ─────────────────────────────────────────────────────

def update_skill_impact(
    out_root: str,
    *,
    step: int,
    epoch: int,
    action: str,
    score_before: float,
    score_after: float,
    edits: list[dict] | None = None,
    pattern_refs: list[str] | None = None,
) -> None:
    """Append a skill accept/reject record to skill-impact.md."""
    wiki_dir = init_wiki(out_root)

    edits_str = ""
    if edits:
        lines = []
        for e in edits[:10]:  # limit to 10 edits
            op = e.get("op", "unknown")
            content = str(e.get("content", ""))[:100]
            target = str(e.get("target", ""))[:100]
            if op == "append":
                lines.append(f"  + append: {content}")
            elif op == "replace":
                lines.append(f"  ~ replace: {target} → {content}")
            elif op == "delete":
                lines.append(f"  - delete: {target}")
            else:
                lines.append(f"  ? {op}: {content}")
        edits_str = "\n".join(lines)

    pattern_ref_str = ""
    if pattern_refs:
        pattern_ref_str = f"\n**Pattern refs:** {', '.join(pattern_refs)}\n"

    delta = score_after - score_before
    delta_str = f"{'+' if delta >= 0 else ''}{delta:.4f}"

    entry = (
        f"## Step {step} (Epoch {epoch})\n"
        f"- **Action:** {action}\n"
        f"- **Score:** {score_after:.4f} (prev: {score_before:.4f}, delta: {delta_str})\n"
        f"{pattern_ref_str}"
    )
    if edits_str:
        entry += f"\n**Edits:**\n{edits_str}\n"

    _append_impact(wiki_dir, entry)


# ── Summary for debugging ────────────────────────────────────────────────────

def get_wiki_summary(out_root: str) -> dict:
    """Return a summary of the wiki state for debugging/logging."""
    wiki_dir = _wiki_dir(out_root)
    patterns = _list_patterns(wiki_dir)

    # Read last log entry
    logs_path = _logs_path(out_root)
    last_log = ""
    if os.path.exists(logs_path):
        with open(logs_path, encoding="utf-8") as f:
            content = f.read()
        # Get last section
        sections = content.split("## Step ")
        if len(sections) > 1:
            last_log = "## Step " + sections[-1].strip()

    return {
        "pattern_count": len(patterns),
        "pattern_ids": [p["id"] for p in patterns],
        "last_log_entry": last_log[:500],
    }
