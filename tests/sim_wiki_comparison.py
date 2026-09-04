"""Wiki on/off 对比仿真: 用 mock 数据跑完整训练流程, 对比知识沉淀效果。

仿真设计:
- 5 个训练 step, 每个 step 12 个 task (8 失败 + 4 成功)
- 失败类型随 step 变化, 模拟真实训练中失败模式的演化
- wiki_maintainer 使用真实代码 (mock LLM 返回 pattern 分析)
- reflect 使用真实 run_minibatch_reflect (mock LLM 根据 wiki_context 返回不同质量的 patch)
- 对比指标: pattern 积累速度、wiki context 大小、reflect patch 质量

关键模拟逻辑:
- wiki=off: reflect analyst 每步从零分析, 产出通用 patch
- wiki=on: reflect analyst 能看到累积 pattern, 产出针对性 patch (引用 pattern id)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from unittest.mock import patch as mock_patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from skillopt.optimizer.wiki_maintainer import (
    init_wiki,
    run_wiki_maintainer,
    format_wiki_context,
    update_skill_impact,
    get_wiki_summary,
)
from skillopt.gradient.reflect import run_minibatch_reflect
from skillopt.utils import compute_score


# ── Mock data: failure types per step ─────────────────────────────────────────

FAILURE_TYPES = {
    "answer_format": {
        "fail_reason": "answer_mismatch: agent returned '2024-01-15' but expected 'January 15, 2024'",
        "predicted": "2024-01-15",
        "gold": "January 15, 2024",
    },
    "multi_hop": {
        "fail_reason": "incomplete: agent found first entity but missed the second-hop connection",
        "predicted": "partial_answer",
        "gold": "full_answer_with_connection",
    },
    "date_range": {
        "fail_reason": "date_range_error: agent returned a single date instead of a range",
        "predicted": "2024-03-10",
        "gold": "2024-03-10 to 2024-03-20",
    },
    "entity_linking": {
        "fail_reason": "entity_confusion: agent confused two similar entities with different attributes",
        "predicted": "Entity_A",
        "gold": "Entity_B",
    },
    "temporal_reasoning": {
        "fail_reason": "temporal_error: agent failed to order events chronologically",
        "predicted": "event3 before event1",
        "gold": "event1 before event3",
    },
}

# 每个 step 的失败类型分布 (failure_type: count)
STEP_FAILURES = [
    {"answer_format": 3, "multi_hop": 5},           # step 0
    {"answer_format": 2, "date_range": 3, "multi_hop": 3},  # step 1
    {"date_range": 4, "entity_linking": 4},         # step 2
    {"answer_format": 1, "entity_linking": 4, "temporal_reasoning": 3},  # step 3
    {"temporal_reasoning": 3, "date_range": 2, "entity_linking": 3},     # step 4
]

# Wiki Maintainer mock LLM 的 pattern 返回 (按 step)
WIKI_MOCK_RESPONSES = [
    # step 0: 发现 answer_format 和 multi_hop
    [
        {"id": "answer_format", "type": "failure",
         "description": "Agent returns dates in ISO format instead of natural language",
         "workaround": "Add rule: when question asks for a date, output in 'Month DD, YYYY' format"},
        {"id": "multi_hop", "type": "failure",
         "description": "Agent stops at first hop, missing the connection to second entity",
         "workaround": "Add rule: for multi-entity questions, always verify the link between entities"},
    ],
    # step 1: 发现 date_range (新), 更新 answer_format
    [
        {"id": "date_range", "type": "failure",
         "description": "Agent returns single date when question asks for a range",
         "workaround": "Add rule: check for 'between', 'from...to', 'range' keywords and output a range"},
        {"id": "answer_format", "type": "failure",
         "description": "Agent returns dates in ISO format, recurring across multiple steps",
         "workaround": "Reinforce: output dates in 'Month DD, YYYY' format; this pattern has appeared in 2 steps"},
    ],
    # step 2: 发现 entity_linking (新)
    [
        {"id": "entity_linking", "type": "failure",
         "description": "Agent confuses similar entities with different attributes",
         "workaround": "Add rule: when multiple entities share names, disambiguate using context attributes"},
    ],
    # step 3: 发现 temporal_reasoning (新)
    [
        {"id": "temporal_reasoning", "type": "failure",
         "description": "Agent fails to order events chronologically",
         "workaround": "Add rule: for 'before/after/sequence' questions, list events in temporal order"},
    ],
    # step 4: 无新 pattern (所有失败已被 wiki 覆盖)
    [],
]


# ── Mock trajectory files ──────────────────────────────────────────────────────

def _make_conversation(task_id: str, failure_type: str | None) -> list[dict]:
    """Create a mock conversation.json for a task."""
    conv = [
        {"step": 1, "action": f"search({task_id}_query)", "env_feedback": "Found 3 results", "reasoning": f"Searching for information about {task_id}"},
        {"step": 2, "action": "read_result(1)", "env_feedback": "Content retrieved", "reasoning": "Reading the first result"},
        {"step": 3, "action": "formulate_answer", "env_feedback": "Answer submitted", "reasoning": "Based on the search results, I'll formulate my answer"},
    ]
    if failure_type:
        ft = FAILURE_TYPES[failure_type]
        conv.append({"role": "system", "content": f"Verification failed: {ft['fail_reason']}"})
    else:
        conv.append({"role": "system", "content": "Verification passed: answer matches gold"})
    return conv


def _setup_prediction_dir(prediction_dir: str, results: list[dict]) -> None:
    """Create mock conversation.json files for each result."""
    os.makedirs(prediction_dir, exist_ok=True)
    for r in results:
        tid = str(r["id"])
        task_dir = os.path.join(prediction_dir, tid)
        os.makedirs(task_dir, exist_ok=True)
        conv = _make_conversation(tid, r.get("_failure_type"))
        with open(os.path.join(task_dir, "conversation.json"), "w", encoding="utf-8") as f:
            json.dump(conv, f, ensure_ascii=False)


def _make_rollout_results(step_idx: int) -> list[dict]:
    """Generate mock rollout results for a step."""
    failure_dist = STEP_FAILURES[step_idx]
    results = []
    task_idx = 0

    # Failures
    for ftype, count in failure_dist.items():
        ft = FAILURE_TYPES[ftype]
        for _ in range(count):
            task_idx += 1
            results.append({
                "id": f"step{step_idx}_task{task_idx:03d}",
                "hard": 0,
                "soft": 0.0,
                "predicted_answer": ft["predicted"],
                "gold_answer": ft["gold"],
                "fail_reason": ft["fail_reason"],
                "task_description": f"Question about {ftype}",
                "task_type": ftype,
                "n_turns": 4,
                "_failure_type": ftype,
            })

    # Successes
    for i in range(4):
        task_idx += 1
        results.append({
            "id": f"step{step_idx}_task{task_idx:03d}",
            "hard": 1,
            "soft": 1.0,
            "predicted_answer": f"correct_{i}",
            "gold_answer": f"correct_{i}",
            "fail_reason": "",
            "task_description": f"Simple question {i}",
            "task_type": "simple",
            "n_turns": 3,
            "_failure_type": None,
        })

    return results


# ── Mock LLM for reflect ─────────────────────────────────────────────────────

def _make_reflect_response(user_prompt: str, wiki_context: str) -> str:
    """Generate mock reflect LLM response based on wiki context availability.

    When wiki_context is present: return targeted patches that reference wiki patterns.
    When wiki_context is absent: return generic patches.
    """
    # Detect which wiki patterns are mentioned in the user prompt
    wiki_patterns_present = []
    for ptype in FAILURE_TYPES:
        if f"**{ptype}**" in user_prompt or ptype in wiki_context:
            wiki_patterns_present.append(ptype)

    edits = []

    if wiki_patterns_present:
        # With wiki: produce targeted edits referencing specific patterns
        for ptype in wiki_patterns_present[:3]:  # max 3 edits
            ft = FAILURE_TYPES[ptype]
            edits.append({
                "op": "append",
                "target": "## Rules",
                "content": f"[wiki:{ptype}] When the question involves {ptype}, ensure: {ft['gold']}. Previous workaround: see wiki pattern {ptype}.",
            })
        reasoning = f"Analysis guided by {len(wiki_patterns_present)} wiki pattern(s): {', '.join(wiki_patterns_present[:3])}. Applying targeted fixes based on accumulated knowledge."
    else:
        # Without wiki: produce generic, less targeted edits
        edits.append({
            "op": "append",
            "target": "## Rules",
            "content": "Improve answer accuracy by double-checking against the question context before submitting.",
        })
        reasoning = "No prior knowledge available. Applying a general improvement based on current failures only."

    return json.dumps({
        "reasoning": reasoning,
        "patch": {"edits": edits},
    }, ensure_ascii=False)


# ── Simulation runner ────────────────────────────────────────────────────────

def run_simulation(use_wiki: bool, n_steps: int = 5, use_react: bool = False) -> dict:
    """Run a full simulation with wiki on or off, optionally with ReAct Proposer.

    Returns metrics dict.
    """
    mode = "react" if use_react else ("wiki_on" if use_wiki else "wiki_off")
    tmpdir = tempfile.mkdtemp(prefix=f"sim_{mode}_")
    out_root = os.path.join(tmpdir, "run")
    os.makedirs(out_root, exist_ok=True)

    if use_wiki:
        init_wiki(out_root)

    skill_content = "# Skill Document\n\n## Rules\n- Always answer accurately.\n"

    metrics = {
        "use_wiki": use_wiki,
        "use_react": use_react,
        "mode": mode,
        "steps": [],
    }

    # Track LLM call stats
    llm_call_log = []

    # ReAct mock state
    react_call_state = {"call_idx": 0}

    def mock_chat_optimizer(system, user, max_completion_tokens=0, retries=5,
                           stage="optimizer", reasoning_effort=None, timeout=None):
        """Mock chat_optimizer that handles wiki_maintainer, analyst, and react_proposer."""
        llm_call_log.append({"stage": stage, "user_len": len(user)})

        if stage == "wiki_maintainer":
            step_idx = len(metrics["steps"])
            if step_idx < len(WIKI_MOCK_RESPONSES):
                patterns = WIKI_MOCK_RESPONSES[step_idx]
                return json.dumps({
                    "summary": f"Step {step_idx}: found {len(patterns)} pattern(s)",
                    "patterns": patterns,
                }, ensure_ascii=False), {"prompt_tokens": 500, "completion_tokens": 200}
            return json.dumps({"summary": "No new patterns", "patterns": []}), {}

        if stage == "analyst":
            wiki_ctx = format_wiki_context(out_root) if use_wiki else ""
            response_text = _make_reflect_response(user, wiki_ctx)
            return response_text, {"prompt_tokens": 1000, "completion_tokens": 300}

        if stage == "react_proposer":
            # Simulate ReAct: first read a pattern, then produce final answer
            react_call_state["call_idx"] += 1
            # Check which patterns exist
            from skillopt.optimizer.wiki_maintainer import _list_patterns, _wiki_dir
            patterns = _list_patterns(_wiki_dir(out_root))
            pattern_ids = [p["id"] for p in patterns]

            if pattern_ids and react_call_state["call_idx"] % 2 == 1:
                # Odd call: read first pattern
                pid = pattern_ids[0]
                return (
                    f"Thought: I should check the {pid} pattern.\n"
                    f'Action: read_file("wiki/patterns/pattern_{pid}.md")'
                ), {}
            else:
                # Even call: produce final answer with all pattern refs
                edits = []
                for pid in pattern_ids[:3]:
                    ft = FAILURE_TYPES.get(pid, {"gold": "correct", "fail_reason": "unknown"})
                    edits.append({
                        "op": "append",
                        "target": "## Rules",
                        "content": f"[wiki:{pid}] Based on wiki knowledge: ensure {ft.get('gold', 'accuracy')}.",
                    })
                if not edits:
                    edits.append({
                        "op": "append",
                        "target": "## Rules",
                        "content": "Improve answer accuracy by double-checking.",
                    })
                return (
                    "Thought: I have enough information.\n"
                    f"Final Answer: {json.dumps({'reasoning': 'react-based', 'patch': {'edits': edits}}, ensure_ascii=False)}"
                ), {}

        return "{}", {}

    for step in range(n_steps):
        step_dir = os.path.join(out_root, f"step_{step:04d}")
        os.makedirs(step_dir, exist_ok=True)

        # ① ROLLOUT (mock)
        rollout_results = _make_rollout_results(step)
        rollout_dir = os.path.join(step_dir, "rollout")
        pred_dir = os.path.join(rollout_dir, "predictions")
        _setup_prediction_dir(pred_dir, rollout_results)
        r_hard, r_soft = compute_score(rollout_results)

        step_metrics = {
            "step": step,
            "rollout_hard": round(r_hard, 4),
            "rollout_soft": round(r_soft, 4),
            "n_results": len(rollout_results),
            "n_failures": sum(1 for r in rollout_results if not r.get("hard")),
        }

        # ①.5 WIKI MAINTAINER
        wiki_context = ""
        if use_wiki:
            with mock_patch("skillopt.optimizer.wiki_maintainer.chat_optimizer",
                       side_effect=mock_chat_optimizer):
                wiki_result = run_wiki_maintainer(
                    rollout_results, out_root,
                    step=step, epoch=1,
                    n_failures=10, n_successes=5,
                    max_patterns=40,
                )
            wiki_context = format_wiki_context(out_root)
            step_metrics["wiki_patterns_written"] = (
                wiki_result.get("patterns_written", 0) if wiki_result else 0
            )
            step_metrics["wiki_patterns_total"] = (
                wiki_result.get("patterns_total", 0) if wiki_result else 0
            )
            step_metrics["wiki_context_chars"] = len(wiki_context)
        else:
            step_metrics["wiki_patterns_written"] = 0
            step_metrics["wiki_patterns_total"] = 0
            step_metrics["wiki_context_chars"] = 0

        # ② REFLECT: ReAct Proposer or standard reflect
        patches_dir = os.path.join(step_dir, "patches")

        if use_wiki and use_react:
            # ReAct Proposer mode
            from skillopt.optimizer.react_proposer import run_react_proposer
            from skillopt.optimizer.wiki_maintainer import _wiki_dir, _write_index_md
            _write_index_md(_wiki_dir(out_root))  # ensure index.md is current
            with mock_patch("skillopt.optimizer.react_proposer.chat_optimizer",
                       side_effect=mock_chat_optimizer):
                react_patch = run_react_proposer(
                    rollout_results, skill_content,
                    wiki_dir=_wiki_dir(out_root),
                    out_root=out_root,
                    prediction_dir=pred_dir,
                    step=step, epoch=1,
                    max_iterations=8,
                    max_traj_chars=15000,
                )
            raw_patches = [react_patch] if react_patch else []
        else:
            # Standard reflect mode (full injection)
            with mock_patch("skillopt.gradient.reflect.chat_optimizer",
                       side_effect=mock_chat_optimizer):
                raw_patches = run_minibatch_reflect(
                    rollout_results, skill_content,
                    prediction_dir=pred_dir,
                    patches_dir=patches_dir,
                    workers=1,
                    failure_only=False,
                    minibatch_size=4,
                    edit_budget=4,
                    random_seed=42,
                    step_buffer_context="",
                    meta_skill_context="",
                    wiki_context=wiki_context,
                )

        # Analyze reflect output
        n_patches = len([p for p in raw_patches if p is not None])
        total_edits = 0
        wiki_referenced_edits = 0
        unique_patterns_referenced = set()

        for p in raw_patches:
            if p is None or not isinstance(p, dict):
                continue
            patch = p.get("patch", {})
            edits = patch.get("edits", [])
            total_edits += len(edits)
            for e in edits:
                if isinstance(e, dict):
                    content = str(e.get("content", ""))
                    # Check if this edit references a wiki pattern
                    wiki_refs = re.findall(r"\[wiki:(\w+)\]", content)
                    if wiki_refs:
                        wiki_referenced_edits += 1
                        unique_patterns_referenced.update(wiki_refs)

        step_metrics["reflect_patches"] = n_patches
        step_metrics["reflect_total_edits"] = total_edits
        step_metrics["reflect_wiki_referenced_edits"] = wiki_referenced_edits
        step_metrics["reflect_unique_patterns_referenced"] = len(unique_patterns_referenced)

        # Simulate gate: accept if improvement
        # With wiki: more targeted edits → higher simulated score
        base_score = r_hard
        if use_wiki and wiki_referenced_edits > 0:
            # Simulated improvement from targeted patches
            simulated_score = min(1.0, base_score + 0.03 * wiki_referenced_edits)
        else:
            # Generic patches give smaller improvement
            simulated_score = min(1.0, base_score + 0.01 * total_edits)

        step_metrics["simulated_score_after"] = round(simulated_score, 4)
        step_metrics["simulated_delta"] = round(simulated_score - base_score, 4)

        # Wiki skill-impact tracking
        if use_wiki:
            action = "accept_new_best" if step_metrics["simulated_delta"] > 0 else "reject"
            update_skill_impact(
                out_root,
                step=step, epoch=1,
                action=action,
                score_before=base_score,
                score_after=simulated_score,
                edits=[{"op": "append", "content": f"step{step} edits"}],
            )

        metrics["steps"].append(step_metrics)

    # Final wiki summary
    if use_wiki:
        metrics["final_wiki_summary"] = get_wiki_summary(out_root)
    else:
        metrics["final_wiki_summary"] = {"pattern_count": 0}

    metrics["total_llm_calls"] = len(llm_call_log)
    metrics["llm_call_breakdown"] = {
        stage: sum(1 for c in llm_call_log if c["stage"] == stage)
        for stage in ["wiki_maintainer", "analyst", "react_proposer"]
    }

    shutil.rmtree(tmpdir)
    return metrics


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_comparison(wiki_off: dict, wiki_on: dict, react: dict):
    """Print a formatted 3-way comparison table."""
    print("\n" + "=" * 100)
    print("  Wiki on/off + ReAct 三模式对比仿真结果")
    print("=" * 100)

    print("\n┌─────────┬────────────────────────┬────────────────────────┬────────────────────────┐")
    print("│ Step    │     Wiki OFF           │     Wiki ON (inject)   │     Wiki + ReAct        │")
    print("├─────────┼────────────────────────┼────────────────────────┼────────────────────────┤")

    for i in range(len(wiki_on["steps"])):
        off_s = wiki_off["steps"][i]
        on_s = wiki_on["steps"][i]
        re_s = react["steps"][i]

        def fmt(s):
            return (f"e={s['reflect_total_edits']} "
                    f"r={s['reflect_wiki_referenced_edits']} "
                    f"Δ={s['simulated_delta']:+.3f}")

        print(
            f"│ Step {i} "
            f"│ {fmt(off_s):<22} "
            f"│ {fmt(on_s):<22} "
            f"│ {fmt(re_s):<22} │"
        )

    print("└─────────┴────────────────────────┴────────────────────────┴────────────────────────┘")

    # Summary
    print("\n┌─────────────────────────────────┬──────────┬──────────┬──────────┐")
    print("│ Metric                          │ Wiki OFF │ Wiki ON  │ ReAct    │")
    print("├─────────────────────────────────┼──────────┼──────────┼──────────┤")

    def total(m, key):
        return sum(s.get(key, 0) for s in m["steps"])

    rows = [
        ("Total reflect edits", total(wiki_off,"reflect_total_edits"), total(wiki_on,"reflect_total_edits"), total(react,"reflect_total_edits")),
        ("Wiki-referenced edits", total(wiki_off,"reflect_wiki_referenced_edits"), total(wiki_on,"reflect_wiki_referenced_edits"), total(react,"reflect_wiki_referenced_edits")),
        ("Total simulated Δ",
         f"{total(wiki_off,'simulated_delta'):+.4f}",
         f"{total(wiki_on,'simulated_delta'):+.4f}",
         f"{total(react,'simulated_delta'):+.4f}"),
        ("Final wiki patterns", 0, wiki_on["final_wiki_summary"]["pattern_count"], react["final_wiki_summary"]["pattern_count"]),
        ("LLM calls (total)", wiki_off["total_llm_calls"], wiki_on["total_llm_calls"], react["total_llm_calls"]),
        ("LLM calls (react_proposer)", 0, 0, react["llm_call_breakdown"].get("react_proposer", 0)),
    ]

    for label, off_v, on_v, re_v in rows:
        print(f"│ {label:<31} │ {str(off_v):>8} │ {str(on_v):>8} │ {str(re_v):>8} │")
    print("└─────────────────────────────────┴──────────┴──────────┴──────────┘")

    # Key findings
    off_d = total(wiki_off, "simulated_delta")
    on_d = total(wiki_on, "simulated_delta")
    re_d = total(react, "simulated_delta")
    on_patterns = wiki_on["final_wiki_summary"]["pattern_count"]

    print("\n┌─ Key Findings ──────────────────────────────────────────────────────────────┐")
    print(f"│ 1. Wiki 积累: {on_patterns} 个 pattern 在 5 步内沉淀                            │")
    print(f"│ 2. Wiki 引用 edit: off={total(wiki_off,'reflect_wiki_referenced_edits')} "
          f"on={total(wiki_on,'reflect_wiki_referenced_edits')} "
          f"react={total(react,'reflect_wiki_referenced_edits')}                        │")
    print(f"│ 3. 模拟增益: off={off_d:+.3f} on={on_d:+.3f} react={re_d:+.3f}                  │")
    print(f"│ 4. ReAct vs 注入: react 用 {react['llm_call_breakdown'].get('react_proposer',0)} 次按需检索       │")
    print(f"│    替代了全量注入, LLM 总调用量: on={wiki_on['total_llm_calls']} react={react['total_llm_calls']}     │")
    print("└──────────────────────────────────────────────────────────────────────────────┘")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 100)
    print("  WikiSkill 三模式仿真: wiki_off vs wiki_on(注入) vs wiki+ReAct")
    print("  使用 mock 数据 + mock LLM, 跑真实 wiki_maintainer + reflect + react 代码")
    print("=" * 100)

    print("\n[1/3] 运行 wiki=off 仿真...")
    wiki_off = run_simulation(use_wiki=False, n_steps=5)
    print(f"  完成: {len(wiki_off['steps'])} steps, {wiki_off['total_llm_calls']} LLM calls")

    print("\n[2/3] 运行 wiki=on (全量注入) 仿真...")
    wiki_on = run_simulation(use_wiki=True, n_steps=5, use_react=False)
    print(f"  完成: {len(wiki_on['steps'])} steps, {wiki_on['total_llm_calls']} LLM calls")

    print("\n[3/3] 运行 wiki+ReAct 仿真...")
    react = run_simulation(use_wiki=True, n_steps=5, use_react=True)
    print(f"  完成: {len(react['steps'])} steps, {react['total_llm_calls']} LLM calls")

    print("\n对比结果:")
    print_comparison(wiki_off, wiki_on, react)

    # Save raw metrics
    results_path = os.path.join(PROJECT_ROOT, "tests", "sim_wiki_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"wiki_off": wiki_off, "wiki_on": wiki_on, "react": react}, f, indent=2, ensure_ascii=False)
    print(f"\n  原始数据已保存到: {results_path}")


if __name__ == "__main__":
    main()
