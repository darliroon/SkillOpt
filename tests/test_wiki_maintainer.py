"""Mock test for WikiSkill Wiki Maintainer implementation.

Tests the wiki_stage pipeline without requiring a real LLM backend:
1. Wiki directory initialization
2. Pattern file I/O (write, list, read)
3. Wiki context formatting for reflect injection
4. Skill-impact tracking
5. Full wiki maintainer flow with mocked LLM
6. Persistence across multiple iterations
7. Pattern limit enforcement
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from skillopt.optimizer.wiki_maintainer import (
    init_wiki,
    run_wiki_maintainer,
    format_wiki_context,
    format_skill_impact_context,
    update_skill_impact,
    write_purpose_md,
    get_wiki_summary,
    _write_pattern,
    _list_patterns,
    _wiki_dir,
    _patterns_dir,
    _format_trajectory_summary,
)


# ── Test data generators ────────────────────────────────────────────────────

def make_mock_rollout_results(n_failures: int = 8, n_successes: int = 4) -> list[dict]:
    """Generate mock rollout results mimicking searchqa-style QA tasks."""
    results = []
    for i in range(n_failures):
        results.append({
            "id": f"q{i+1:03d}",
            "hard": 0,
            "soft": 0.0,
            "predicted_answer": f"wrong_answer_{i}",
            "gold_answer": f"correct_answer_{i}",
            "fail_reason": f"answer_mismatch: predicted 'wrong_answer_{i}', expected 'correct_answer_{i}'",
        })
    for i in range(n_successes):
        results.append({
            "id": f"q{n_failures+i+1:03d}",
            "hard": 1,
            "soft": 1.0,
            "predicted_answer": f"correct_answer_{n_failures+i}",
            "gold_answer": f"correct_answer_{n_failures+i}",
            "fail_reason": "",
        })
    return results


def make_mock_llm_response(patterns: list[dict], summary: str = "mock summary") -> str:
    """Create a mock LLM response JSON string."""
    return json.dumps({
        "summary": summary,
        "patterns": patterns,
    })


# ── Test helpers ─────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


def section(title: str):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ── Tests ────────────────────────────────────────────────────────────────────

def test_wiki_init():
    """Test 1: Wiki directory initialization."""
    section("Test 1: Wiki Directory Initialization")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)
        check("wiki dir created", os.path.isdir(wiki))
        check("patterns dir created", os.path.isdir(_patterns_dir(tmpdir)))
        check("logs.md created", os.path.exists(os.path.join(wiki, "logs.md")))
        check("skill-impact.md created", os.path.exists(os.path.join(wiki, "skill-impact.md")))

        # Test idempotency — calling again should not error
        wiki2 = init_wiki(tmpdir)
        check("init is idempotent", wiki == wiki2)
    finally:
        shutil.rmtree(tmpdir)


def test_pattern_io():
    """Test 2: Pattern file write and list."""
    section("Test 2: Pattern File I/O")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)

        # Write patterns
        _write_pattern(wiki, "answer_format", "failure",
                       "Agent returns answer in wrong format",
                       "Add explicit output format rule",
                       task_ids=["q001", "q003"])
        _write_pattern(wiki, "multi_hop", "failure",
                       "Multi-hop reasoning fails at second step",
                       "Add step-by-step reasoning guidance",
                       task_ids=["q002"])

        patterns = _list_patterns(wiki)
        check("2 patterns listed", len(patterns) == 2, f"got {len(patterns)}")
        check("answer_format in list", any(p["id"] == "answer_format" for p in patterns))
        check("multi_hop in list", any(p["id"] == "multi_hop" for p in patterns))

        # Test pattern update (same ID overwrites)
        _write_pattern(wiki, "answer_format", "failure",
                       "UPDATED: Agent returns answer in wrong format for dates",
                       "UPDATED: Add explicit date format rule",
                       task_ids=["q001", "q003", "q005"])
        patterns = _list_patterns(wiki)
        check("still 2 patterns after update", len(patterns) == 2)

        # Verify updated content
        fname = "pattern_answer_format.md"
        fpath = os.path.join(_patterns_dir(tmpdir), fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        check("updated content present", "UPDATED" in content)
    finally:
        shutil.rmtree(tmpdir)


def test_wiki_context_formatting():
    """Test 3: Wiki context formatting for reflect injection."""
    section("Test 3: Wiki Context Formatting")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)

        # Empty wiki — should return empty string
        ctx = format_wiki_context(tmpdir)
        check("empty wiki → empty context", ctx == "", f"got '{ctx[:50]}'")

        # Add patterns
        _write_pattern(wiki, "p1", "failure", "desc1", "fix1")
        _write_pattern(wiki, "p2", "success", "desc2", "fix2")

        ctx = format_wiki_context(tmpdir)
        check("context non-empty", len(ctx) > 0)
        check("contains p1", "p1" in ctx)
        check("contains p2", "p2" in ctx)
        check("contains header", "Wiki Knowledge Base" in ctx)

        # Truncated context — allow some slack for the truncation marker
        ctx_short = format_wiki_context(tmpdir, max_chars=50)
        check("truncated context", "truncated" in ctx_short or len(ctx_short) <= 55,
              f"got len={len(ctx_short)}: {ctx_short[:80]}")
    finally:
        shutil.rmtree(tmpdir)


def test_skill_impact():
    """Test 4: Skill impact tracking."""
    section("Test 4: Skill Impact Tracking")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)

        # Record an accept
        update_skill_impact(
            tmpdir,
            step=1, epoch=1,
            action="accept_new_best",
            score_before=0.3000, score_after=0.4500,
            edits=[{"op": "append", "content": "Always check date ranges"}],
            pattern_refs=["answer_format", "multi_hop"],
        )

        # Record a reject
        update_skill_impact(
            tmpdir,
            step=2, epoch=1,
            action="reject",
            score_before=0.4500, score_after=0.4200,
            edits=[{"op": "replace", "target": "old rule", "content": "new rule"}],
        )

        # Read back
        impact_path = os.path.join(wiki, "skill-impact.md")
        with open(impact_path, encoding="utf-8") as f:
            content = f.read()

        check("step 1 recorded", "Step 1" in content)
        check("accept recorded", "accept_new_best" in content)
        check("step 2 recorded", "Step 2" in content)
        check("reject recorded", "reject" in content)
        check("score delta present", "+0.1500" in content)
        check("pattern refs present", "answer_format" in content)
        check("edit content present", "date ranges" in content)

        # Test format_skill_impact_context (read-back for reflect injection)
        impact_ctx = format_skill_impact_context(tmpdir)
        check("impact context non-empty", len(impact_ctx) > 0)
        check("impact context has reject", "reject" in impact_ctx)
        check("impact context has accept", "accept" in impact_ctx)
        check("impact context has Step 1", "Step 1" in impact_ctx)
        check("impact context has Step 2", "Step 2" in impact_ctx)
        check("impact context has score delta", "+0.1500" in impact_ctx)

        # Empty wiki → empty context
        empty_ctx = format_skill_impact_context(
            tempfile.mkdtemp(prefix="wiki_empty_")
        )
        check("empty wiki → empty impact context", empty_ctx == "")
    finally:
        shutil.rmtree(tmpdir)


def test_wiki_maintainer_with_mock_llm():
    """Test 5: Full wiki maintainer flow with mocked LLM."""
    section("Test 5: Wiki Maintainer with Mocked LLM")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        rollout_results = make_mock_rollout_results(n_failures=8, n_successes=4)

        # Mock the LLM response
        mock_response = make_mock_llm_response([
            {
                "id": "answer_mismatch",
                "type": "failure",
                "description": "Agent consistently returns wrong answers for factual questions",
                "workaround": "Add a verification step to cross-check answers against context",
                "task_ids": ["q001", "q002", "q003"],
            },
            {
                "id": "no_context_check",
                "type": "failure",
                "description": "Agent does not verify answers against provided context passages",
                "workaround": "Add rule: always re-read context before finalizing answer",
                "task_ids": ["q004", "q005"],
            },
        ], summary="Found 2 recurring failure patterns across 8 failures")

        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_response, {"prompt_tokens": 100, "completion_tokens": 50})

            result = run_wiki_maintainer(
                rollout_results, tmpdir,
                step=1, epoch=1,
                n_failures=10, n_successes=5,
                max_completion_tokens=32000,
            )

        check("result is not None", result is not None)
        check("2 patterns written", result["patterns_written"] == 2, f"got {result}")
        check("2 patterns total", result["patterns_total"] == 2)

        # Verify pattern files exist
        patterns = _list_patterns(_wiki_dir(tmpdir))
        check("answer_mismatch file exists",
              any(p["id"] == "answer_mismatch" for p in patterns))
        check("no_context_check file exists",
              any(p["id"] == "no_context_check" for p in patterns))

        # Verify logs.md was updated
        logs_path = os.path.join(_wiki_dir(tmpdir), "logs.md")
        with open(logs_path, encoding="utf-8") as f:
            logs = f.read()
        check("log has Step 1", "Step 1" in logs)
        check("log has patterns count", "Patterns written: 2" in logs)

        # Verify wiki context now includes patterns
        ctx = format_wiki_context(tmpdir)
        check("context has answer_mismatch", "answer_mismatch" in ctx)
        check("context has no_context_check", "no_context_check" in ctx)
    finally:
        shutil.rmtree(tmpdir)


def test_persistence_across_iterations():
    """Test 6: Wiki persists across multiple iterations (never reset)."""
    section("Test 6: Persistence Across Iterations")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        # Iteration 1: write 2 patterns
        mock_resp_1 = make_mock_llm_response([
            {"id": "pattern_a", "type": "failure",
             "description": "Pattern A description", "workaround": "Fix A"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp_1, {})
            run_wiki_maintainer(
                make_mock_rollout_results(6, 3), tmpdir,
                step=1, epoch=1,
            )

        patterns_after_1 = _list_patterns(_wiki_dir(tmpdir))
        check("1 pattern after iter 1", len(patterns_after_1) == 1)

        # Iteration 2: write 1 more pattern (different ID)
        mock_resp_2 = make_mock_llm_response([
            {"id": "pattern_b", "type": "failure",
             "description": "Pattern B description", "workaround": "Fix B"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp_2, {})
            run_wiki_maintainer(
                make_mock_rollout_results(8, 2), tmpdir,
                step=2, epoch=1,
            )

        patterns_after_2 = _list_patterns(_wiki_dir(tmpdir))
        check("2 patterns after iter 2", len(patterns_after_2) == 2,
              f"got {[p['id'] for p in patterns_after_2]}")
        check("pattern_a still present", any(p["id"] == "pattern_a" for p in patterns_after_2))
        check("pattern_b added", any(p["id"] == "pattern_b" for p in patterns_after_2))

        # Iteration 3: update pattern_a (same ID)
        mock_resp_3 = make_mock_llm_response([
            {"id": "pattern_a", "type": "failure",
             "description": "UPDATED Pattern A", "workaround": "UPDATED Fix A"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp_3, {})
            run_wiki_maintainer(
                make_mock_rollout_results(5, 5), tmpdir,
                step=3, epoch=2,
            )

        patterns_after_3 = _list_patterns(_wiki_dir(tmpdir))
        check("still 2 patterns after update", len(patterns_after_3) == 2)

        # Verify pattern_a was updated
        pa_path = os.path.join(_patterns_dir(tmpdir), "pattern_pattern_a.md")
        with open(pa_path, encoding="utf-8") as f:
            content = f.read()
        check("pattern_a updated", "UPDATED" in content)

        # Check wiki summary
        summary = get_wiki_summary(tmpdir)
        check("summary has 2 patterns", summary["pattern_count"] == 2)
        check("summary has Step 3 log", "Step 3" in summary["last_log_entry"])
    finally:
        shutil.rmtree(tmpdir)


def test_skill_rollback_wiki_persists():
    """Test 7: Wiki persists even when skill is rejected (key WikiSkill property)."""
    section("Test 7: Wiki Persists on Skill Rollback")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)

        # Write patterns
        _write_pattern(wiki, "p1", "failure", "desc1", "fix1")
        _write_pattern(wiki, "p2", "failure", "desc2", "fix2")

        # Record a rejected skill attempt
        update_skill_impact(
            tmpdir,
            step=5, epoch=1,
            action="reject",
            score_before=0.4500, score_after=0.4200,
            edits=[{"op": "append", "content": "bad edit"}],
        )

        # Wiki patterns should still be there
        patterns = _list_patterns(wiki)
        check("patterns survive skill rejection", len(patterns) == 2)

        # Skill-impact should have the rejection recorded
        impact_path = os.path.join(wiki, "skill-impact.md")
        with open(impact_path, encoding="utf-8") as f:
            impact = f.read()
        check("rejection in impact", "reject" in impact)
        check("step 5 in impact", "Step 5" in impact)

        # Next iteration can still read the wiki
        ctx = format_wiki_context(tmpdir)
        check("wiki context still available after rejection", len(ctx) > 0)
        check("p1 in context after rejection", "p1" in ctx)
    finally:
        shutil.rmtree(tmpdir)


def test_pattern_limit_enforcement():
    """Test 8: Pattern count limit removes oldest patterns."""
    section("Test 8: Pattern Limit Enforcement")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)

        # Write 5 patterns
        for i in range(5):
            _write_pattern(wiki, f"p{i}", "failure", f"desc{i}", f"fix{i}")

        # Run wiki maintainer with max_patterns=3
        mock_resp = make_mock_llm_response([
            {"id": "p5", "type": "failure", "description": "new", "workaround": "new fix"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp, {})
            run_wiki_maintainer(
                make_mock_rollout_results(4, 2), tmpdir,
                step=1, epoch=1,
                max_patterns=3,
            )

        patterns = _list_patterns(wiki)
        check("patterns capped at 3", len(patterns) == 3,
              f"got {len(patterns)}: {[p['id'] for p in patterns]}")
        # Newest patterns should survive (p3, p4, p5)
        ids = sorted(p["id"] for p in patterns)
        check("oldest removed", "p0" not in ids and "p1" not in ids,
              f"got {ids}")
    finally:
        shutil.rmtree(tmpdir)


def test_empty_rollout_results():
    """Test 9: Edge case — empty or all-success rollout results."""
    section("Test 9: Edge Cases — Empty/All-Success Results")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        # All successes — no failures to analyze but successes exist
        all_success = [
            {"id": f"q{i}", "hard": 1, "soft": 1.0,
             "predicted_answer": "ans", "gold_answer": "ans"}
            for i in range(5)
        ]
        # Mock LLM since we still analyze successes
        mock_resp = make_mock_llm_response([
            {"id": "good_strategy", "type": "success",
             "description": "Agent correctly verifies answers", "workaround": "Reinforce verification behavior"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp, {})
            result = run_wiki_maintainer(
                all_success, tmpdir,
                step=1, epoch=1,
                n_failures=10, n_successes=5,
            )
        check("all-success handled", result is not None)
        check("1 pattern written for all-success", result and result.get("patterns_written") == 1)

        # Empty results — should skip LLM call entirely
        result_empty = run_wiki_maintainer(
            [], tmpdir,
            step=2, epoch=1,
        )
        check("empty results handled", result_empty is not None)
        check("0 patterns for empty input", result_empty["patterns_written"] == 0)
    finally:
        shutil.rmtree(tmpdir)


def test_no_llm_response():
    """Test 10: LLM returns invalid response — graceful degradation."""
    section("Test 10: LLM Invalid Response — Graceful Degradation")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        rollout = make_mock_rollout_results(5, 2)

        # Mock LLM returning garbage
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = ("This is not JSON", {})
            result = run_wiki_maintainer(
                rollout, tmpdir,
                step=1, epoch=1,
            )

        check("graceful None on invalid JSON", result is not None)
        check("0 patterns written", result["patterns_written"] == 0)
        check("0 patterns total", result["patterns_total"] == 0)

        # Mock LLM throwing exception
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.side_effect = RuntimeError("API error")
            result_err = run_wiki_maintainer(
                rollout, tmpdir,
                step=2, epoch=1,
            )

        check("graceful None on exception", result_err is None)
    finally:
        shutil.rmtree(tmpdir)


# ── Tests for paper-alignment features ──────────────────────────────────────

def test_trajectory_truncation():
    """Test 11: Per-trajectory character truncation (paper: 15k chars)."""
    section("Test 11: Trajectory Truncation (wiki_max_traj_chars)")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        results = [
            {"id": "q001", "hard": 0, "soft": 0.0,
             "predicted_answer": "x" * 500, "gold_answer": "y" * 500,
             "fail_reason": "z" * 500},
        ]
        # Without truncation (fields are internally capped at 200/200/300)
        summary_full = _format_trajectory_summary(results, "Test", max_chars_per_traj=0)
        check("no truncation: full length", len(summary_full) > 500,
              f"got len={len(summary_full)}")

        # With truncation to 100 chars per traj
        summary_trunc = _format_trajectory_summary(results, "Test", max_chars_per_traj=100)
        check("truncation applied", "..." in summary_trunc)
        # Each entry should be at most ~100 + header chars
        # The whole summary should be much shorter
        check("truncated summary shorter", len(summary_trunc) < len(summary_full))

        # Test in run_wiki_maintainer
        mock_resp = make_mock_llm_response([
            {"id": "trunc_test", "type": "failure",
             "description": "test", "workaround": "test fix"},
        ])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp, {})
            run_wiki_maintainer(
                make_mock_rollout_results(5, 2), tmpdir,
                step=1, epoch=1,
                max_traj_chars=100,
            )
        check("run_wiki_maintainer accepts max_traj_chars", True)
    finally:
        shutil.rmtree(tmpdir)


def test_index_md_persistence():
    """Test 12: index.md is persisted after run_wiki_maintainer."""
    section("Test 12: index.md Persistence")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)
        _write_pattern(wiki, "p1", "failure", "Failure pattern A", "Fix A")
        _write_pattern(wiki, "p2", "failure", "Failure pattern B", "Fix B")

        # Run wiki maintainer to trigger _write_index_md
        mock_resp = make_mock_llm_response([])
        with patch("skillopt.optimizer.wiki_maintainer.chat_optimizer") as mock_chat:
            mock_chat.return_value = (mock_resp, {})
            run_wiki_maintainer(
                make_mock_rollout_results(4, 2), tmpdir,
                step=1, epoch=1,
            )

        index_path = os.path.join(wiki, "index.md")
        check("index.md exists", os.path.exists(index_path))

        with open(index_path, encoding="utf-8") as f:
            content = f.read()
        check("index has title", "Wiki Pattern Index" in content)
        check("index lists p1", "p1" in content)
        check("index lists p2", "p2" in content)
        check("index has total count", "Total patterns: 2" in content)
    finally:
        shutil.rmtree(tmpdir)


def test_purpose_md():
    """Test 13: PURPOSE.md writes skill→pattern traceability."""
    section("Test 13: PURPOSE.md Traceability")
    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)
        skill_dir = os.path.join(tmpdir, "skills")
        os.makedirs(skill_dir, exist_ok=True)

        # Write PURPOSE.md with pattern refs
        purpose_path = write_purpose_md(
            tmpdir,
            skill_path=skill_dir,
            step=3, epoch=1,
            pattern_refs=["answer_format", "multi_hop"],
            action="accept_new_best",
            edits_summary="2 edits, delta=+0.0500",
        )

        check("PURPOSE.md exists", os.path.exists(purpose_path))
        with open(purpose_path, encoding="utf-8") as f:
            content = f.read()
        check("has Step 3", "Step 3" in content)
        check("has action", "accept_new_best" in content)
        check("has answer_format ref", "answer_format" in content)
        check("has multi_hop ref", "multi_hop" in content)
        check("references pattern file path", "pattern_answer_format.md" in content)

        # Write without pattern refs
        purpose_path2 = write_purpose_md(
            tmpdir, skill_path=skill_dir,
            step=4, epoch=1, action="reject",
        )
        with open(purpose_path2, encoding="utf-8") as f:
            content2 = f.read()
        check("no refs: has 'None'", "None" in content2)
        check("has reject action", "reject" in content2)
    finally:
        shutil.rmtree(tmpdir)


def test_react_proposer():
    """Test 14: ReAct Skill Proposer with mocked LLM."""
    section("Test 14: ReAct Skill Proposer")
    from skillopt.optimizer.react_proposer import (
        run_react_proposer, _parse_action, _is_final_answer, _read_file,
    )

    tmpdir = tempfile.mkdtemp(prefix="wiki_test_")
    try:
        wiki = init_wiki(tmpdir)
        _write_pattern(wiki, "answer_format", "failure",
                       "Agent returns dates in ISO format",
                       "Add rule: output in Month DD, YYYY")

        # Create mock trajectory files
        pred_dir = os.path.join(tmpdir, "rollout", "predictions")
        task_dir = os.path.join(pred_dir, "q001")
        os.makedirs(task_dir, exist_ok=True)
        import json as _json
        with open(os.path.join(task_dir, "conversation.json"), "w") as f:
            _json.dump([{"step": 1, "action": "search", "reasoning": "looked for date"}], f)

        # Write index.md
        from skillopt.optimizer.wiki_maintainer import _write_index_md
        _write_index_md(wiki)

        # Test helper functions
        action = _parse_action('Thought: I need to check\nAction: read_file("wiki/patterns/pattern_answer_format.md")')
        check("parse_action extracts path",
              action == "wiki/patterns/pattern_answer_format.md")

        final = _is_final_answer('Thought: done\nFinal Answer: {"patch": {"edits": []}}')
        check("is_final_answer detects", final is not None)

        no_final = _is_final_answer('Thought: need more info\nAction: read_file("x")')
        check("is_final_answer rejects non-final", no_final is None)

        # Test _read_file
        content = _read_file(os.path.join(wiki, "index.md"))
        check("read_file reads index.md", "Wiki Pattern Index" in content)

        content = _read_file(os.path.join(wiki, "patterns", "pattern_answer_format.md"))
        check("read_file reads pattern", "ISO format" in content)

        content = _read_file("nonexistent_file.md")
        check("read_file handles missing file", "not found" in content)

        # Test full ReAct loop with mocked LLM
        call_count = [0]
        def mock_chat(system, user, max_completion_tokens=0, retries=5,
                      stage="optimizer", reasoning_effort=None, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: read a pattern
                return ('Thought: I should check the answer_format pattern.\n'
                        'Action: read_file("wiki/patterns/pattern_answer_format.md")'), {}
            elif call_count[0] == 2:
                # Second call: produce final answer
                return ('Thought: I found the pattern about ISO format.\n'
                        'Final Answer: {"reasoning": "ISO format issue", '
                        '"patch": {"edits": [{"op": "append", '
                        '"target": "## Rules", '
                        '"content": "[wiki:answer_format] Output dates in Month DD, YYYY format"}]}}'), {}
            return "{}", {}

        with patch("skillopt.optimizer.react_proposer.chat_optimizer",
                   side_effect=mock_chat):
            patch_result = run_react_proposer(
                make_mock_rollout_results(4, 2),
                "# Skill\n## Rules\n- Be accurate\n",
                wiki_dir=wiki,
                out_root=tmpdir,
                prediction_dir=pred_dir,
                step=1, epoch=1,
                max_iterations=5,
            )

        check("react proposer returns patch", patch_result is not None)
        if patch_result:
            edits = patch_result.get("patch", {}).get("edits", [])
            check("patch has 1 edit", len(edits) == 1, f"got {len(edits)}")
            if edits:
                content = str(edits[0].get("content", ""))
                check("edit references wiki pattern", "[wiki:answer_format]" in content)
    finally:
        shutil.rmtree(tmpdir)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  WikiSkill Wiki Maintainer — Mock Test Suite")
    print("="*60)

    test_wiki_init()
    test_pattern_io()
    test_wiki_context_formatting()
    test_skill_impact()
    test_wiki_maintainer_with_mock_llm()
    test_persistence_across_iterations()
    test_skill_rollback_wiki_persists()
    test_pattern_limit_enforcement()
    test_empty_rollout_results()
    test_no_llm_response()
    test_trajectory_truncation()
    test_index_md_persistence()
    test_purpose_md()
    test_react_proposer()

    print(f"\n{'='*60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}\n")
    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
