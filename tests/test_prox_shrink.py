"""Tests for SkillProx backward (proximal shrink) + dual-metric train gate.

Covers:
- train_gate_pass with the "and" dual-metric mode
- unit decomposition / rebuild helpers in skillopt.evaluation.gate
- prox_trial_pass triple gate branches
- run_prox_shrink end-to-end with a fake adapter + monkeypatched optimizer
"""
from __future__ import annotations

import json
import os

import pytest

from skillopt.evaluation.gate import (
    decompose_skill_units,
    drill_unit_into_subs,
    prox_trial_pass,
    auto_tolerances,
    rebuild_skill,
    replace_skill_unit,
    skill_without_subunit,
    skill_without_unit,
    train_gate_pass,
)
from skillopt.evaluation.gate import auto_train_gate_tolerances
from skillopt.optimizer import prox_shrink


# ── Fixtures ────────────────────────────────────────────────────────────────

SKILL = (
    "# Title\n\nPreamble line.\n\n"
    "## Search Strategy\nDo X first.\n\n"
    "## Answer Format\nAlways box.\n\n"
    "## Verbose Filler\nLorem ipsum dolor sit amet.\n\n"
    "<!-- SLOW_UPDATE_START -->\nkeep me\n<!-- SLOW_UPDATE_END -->\n"
)


# ── train_gate_pass: "and" dual metric ─────────────────────────────────────

class TestTrainGateAndMetric:
    def test_both_hold_passes(self) -> None:
        ok, reason = train_gate_pass(0.80, 0.70, 0.80, 0.70, metric="and", tolerance=0.05)
        assert ok
        assert "pass" in reason

    def test_hard_fails_only(self) -> None:
        ok, reason = train_gate_pass(0.70, 0.70, 0.80, 0.70, metric="and", tolerance=0.05)
        assert not ok
        assert "hard" in reason and "soft" not in reason.split("below")[0]

    def test_soft_fails_only(self) -> None:
        ok, reason = train_gate_pass(0.80, 0.60, 0.80, 0.70, metric="and", tolerance=0.05)
        assert not ok
        assert "soft" in reason

    def test_both_fail_reports_both(self) -> None:
        ok, reason = train_gate_pass(0.60, 0.50, 0.80, 0.70, metric="and", tolerance=0.05)
        assert not ok
        assert "hard AND soft" in reason

    def test_within_tolerance_passes(self) -> None:
        # drop of exactly tolerance on both sides still passes
        ok, _ = train_gate_pass(0.75, 0.65, 0.80, 0.70, metric="and", tolerance=0.05)
        assert ok

    def test_beyond_tolerance_fails(self) -> None:
        ok, _ = train_gate_pass(0.74, 0.65, 0.80, 0.70, metric="and", tolerance=0.05)
        assert not ok

    def test_zero_tolerance_strict(self) -> None:
        ok, _ = train_gate_pass(0.799, 0.70, 0.80, 0.70, metric="and", tolerance=0.0)
        assert not ok


# ── train-gate auto tolerance (per-metric σ) ────────────────────────────────

class TestTrainGateAutoTolerance:
    def test_hard_metric_uses_hard_sigma(self) -> None:
        results = [{"hard": 1 if i < 8 else 0, "soft": 0.9} for i in range(10)]
        kwargs = auto_train_gate_tolerances(results, 1.5, "hard")
        assert set(kwargs) == {"hard_tolerance"}
        assert kwargs["hard_tolerance"] == pytest.approx(
            1.5 * (2 * 0.8 * 0.2 / 10) ** 0.5
        )

    def test_and_metric_measures_legs_independently(self) -> None:
        results = [
            {"hard": 1 if i < 8 else 0, "soft": 0.9 if i % 2 else 0.4}
            for i in range(10)
        ]
        kwargs = auto_train_gate_tolerances(results, 1.5, "and")
        assert set(kwargs) == {"hard_tolerance", "soft_tolerance"}
        # tiny soft drop inside noise passes; hard drop far beyond σ fails
        # (n=10 → σ_diff≈0.179, ×1.5 ≈ 0.27, so the drop must exceed that)
        ok, _ = train_gate_pass(0.80, 0.89, 0.80, 0.90, metric="and", **kwargs)
        assert ok
        ok, _ = train_gate_pass(0.40, 0.90, 0.80, 0.90, metric="and", **kwargs)
        assert not ok

    def test_mixed_metric_composite_sigma(self) -> None:
        results = [
            {"hard": 1 if i < 8 else 0, "soft": 1.0 if i < 8 else 0.0}
            for i in range(10)
        ]
        kwargs = auto_train_gate_tolerances(results, 2.0, "mixed", 0.5)
        assert set(kwargs) == {"tolerance"}
        comp = [1.0] * 8 + [0.0] * 2
        mu = sum(comp) / 10
        s2 = sum((x - mu) ** 2 for x in comp) / 9
        assert kwargs["tolerance"] == pytest.approx(2.0 * (2 * s2 / 10) ** 0.5)

    def test_searchqa_sized_batch_not_over_tight(self) -> None:
        # n=40, p≈0.78 (searchqa-like) → σ_diff≈0.093; the old fixed 0.05
        # was only 0.54σ (~29% noise rejection).  auto ×1.5 ≈ 0.14 gives
        # the intended ~6.7% level.
        results = [{"hard": 1 if i < 31 else 0, "soft": 0.85} for i in range(40)]
        kwargs = auto_train_gate_tolerances(results, 1.5, "hard")
        assert kwargs["hard_tolerance"] == pytest.approx(
            1.5 * (2 * 0.775 * 0.225 / 40) ** 0.5, abs=1e-4
        )
        assert kwargs["hard_tolerance"] > 0.12


# ── Unit decomposition ──────────────────────────────────────────────────────

class TestDecomposeSkillUnits:
    def test_splits_on_h2_sections(self) -> None:
        decomp = decompose_skill_units(SKILL)
        assert [u["header"] for u in decomp["units"]] == [
            "## Search Strategy", "## Answer Format", "## Verbose Filler",
        ]
        assert decomp["preamble"].startswith("# Title")

    def test_protected_span_is_not_a_unit(self) -> None:
        decomp = decompose_skill_units(SKILL)
        for u in decomp["units"]:
            assert "SLOW_UPDATE" not in u["content"]

    def test_rebuild_roundtrip(self) -> None:
        decomp = decompose_skill_units(SKILL)
        assert rebuild_skill(decomp) == SKILL

    def test_drop_unit(self) -> None:
        ablated = skill_without_unit(SKILL, "## Verbose Filler\nLorem ipsum dolor sit amet.\n")
        assert "Lorem ipsum" not in ablated
        assert "## Search Strategy" in ablated
        assert "SLOW_UPDATE_START" in ablated

    def test_drop_unit_no_match_returns_none(self) -> None:
        assert skill_without_unit(SKILL, "## Nonexistent\n") is None

    def test_replace_unit(self) -> None:
        new = replace_skill_unit(
            SKILL, "## Verbose Filler\nLorem ipsum dolor sit amet.\n",
            "## Verbose Filler\nShort.\n",
        )
        assert "Short." in new
        assert "Lorem ipsum" not in new

    def test_appendix_also_protected(self) -> None:
        skill = SKILL + "\n<!-- APPENDIX_START -->\nnote\n<!-- APPENDIX_END -->\n"
        decomp = decompose_skill_units(skill)
        assert rebuild_skill(decomp) == skill
        ablated = skill_without_unit(
            skill, "## Verbose Filler\nLorem ipsum dolor sit amet.\n"
        )
        assert "APPENDIX_START" in ablated


# ── Drilldown decomposition (oversized ## → ### subsections) ───────────────

def _big_skill() -> str:
    """Skill whose first ## section exceeds 3000 chars and has ### subs."""
    section = "## Big Section\nIntro text.\n\n"
    for i in range(5):
        section += f"### Sub {i}\n" + "guidance detail.\n" * 60 + "\n"
    return (
        "# Doc\n\nPreamble.\n\n"
        + section
        + "## Small\nDo Y.\n\n"
        + "<!-- SLOW_UPDATE_START -->\nkeep\n<!-- SLOW_UPDATE_END -->\n"
    )


class TestDrilldownDecompose:
    def test_large_section_drilled_into_subsections(self) -> None:
        decomp = decompose_skill_units(_big_skill())
        headers = [u["header"] for u in decomp["units"]]
        assert headers[0] == "## Big Section"
        assert headers[1:6] == [f"### Sub {i}" for i in range(5)]
        assert headers[6] == "## Small"
        # header block of the drilled section is fixed; everything else is not
        assert decomp["units"][0]["fixed"] is True
        assert all(not u["fixed"] for u in decomp["units"][1:])

    def test_small_section_not_drilled(self) -> None:
        decomp = decompose_skill_units(_big_skill())
        small = [u for u in decomp["units"] if u["header"] == "## Small"]
        assert len(small) == 1 and not small[0]["fixed"]

    def test_drilldown_roundtrip(self) -> None:
        skill = _big_skill()
        assert rebuild_skill(decompose_skill_units(skill)) == skill

    def test_drop_subsection_keeps_section_header(self) -> None:
        skill = _big_skill()
        decomp = decompose_skill_units(skill)
        sub2 = next(u for u in decomp["units"] if u["header"] == "### Sub 2")
        ablated = skill_without_unit(skill, sub2["content"])
        assert ablated is not None
        assert "## Big Section" in ablated          # header survives
        assert "Intro text." in ablated             # section intro survives
        assert "guidance detail." in ablated        # other subsections survive
        assert "### Sub 2" not in ablated
        assert "SLOW_UPDATE_START" in ablated       # protected block survives

    def test_fixed_header_not_removable(self) -> None:
        skill = _big_skill()
        decomp = decompose_skill_units(skill)
        header_unit = decomp["units"][0]
        assert header_unit["fixed"]
        assert skill_without_unit(skill, header_unit["content"]) is None

    def test_drilldown_disabled_by_zero_threshold(self) -> None:
        decomp = decompose_skill_units(_big_skill(), drilldown_chars=0)
        assert [u["header"] for u in decomp["units"]] == ["## Big Section", "## Small"]
        assert rebuild_skill(decomp) == _big_skill()

    def test_large_section_without_subsections_stays_whole(self) -> None:
        skill = (
            "# Doc\n\n"
            "## Big But Flat\n" + "one long rule.\n" * 300 + "\n"
            "## Small\nDo Y.\n"
        )
        decomp = decompose_skill_units(skill)
        assert [u["header"] for u in decomp["units"]] == ["## Big But Flat", "## Small"]
        assert rebuild_skill(decomp) == skill

    def test_protected_block_inside_drilled_section(self) -> None:
        skill = (
            "# Doc\n\n## Big Section\nIntro.\n\n"
            "### Sub 0\n" + "a.\n" * 800 + "\n"
            "### Sub 1\n" + "b.\n" * 800 + "\n"
            "<!-- SLOW_UPDATE_START -->\ninner\n<!-- SLOW_UPDATE_END -->\n\n"
            "### Sub 2\n" + "c.\n" * 800
        )
        decomp = decompose_skill_units(skill)
        assert rebuild_skill(decomp) == skill
        sub1 = next(u for u in decomp["units"] if u["header"] == "### Sub 1")
        ablated = skill_without_unit(skill, sub1["content"])
        assert ablated is not None
        assert "SLOW_UPDATE_START" in ablated   # block moves, never lost
        assert "### Sub 1" not in ablated


# ── prox_trial_pass triple gate ─────────────────────────────────────────────

class TestProxTrialPass:
    BASE = dict(
        trial_hard=0.80, trial_soft=0.70,
        base_hard=0.80, base_soft=0.70,
        hard_tolerance=0.05, soft_tolerance=0.02,
        max_compression=0.10, base_chars=1000,
    )

    def _trial(self, **kw) -> str:
        # 900 chars of 1000 → 10% compression, strictly smaller than prev
        return "x" * 900

    def test_ok_trial_passes(self) -> None:
        ok, reason = prox_trial_pass("x" * 900, "y" * 1000, **self.BASE)
        assert ok, reason

    def test_empty_trial_rejected(self) -> None:
        ok, reason = prox_trial_pass("", "y" * 1000, **self.BASE)
        assert not ok and "structure" in reason

    def test_all_sections_removed_rejected(self) -> None:
        prev = "preamble\n\n## A\nx\n"
        ok, reason = prox_trial_pass("no sections", prev, **self.BASE)
        assert not ok and "structure" in reason

    def test_protected_marker_lost_rejected(self) -> None:
        prev = "## A\nx\n<!-- SLOW_UPDATE_START -->\nq\n<!-- SLOW_UPDATE_END -->\n"
        trial = "## A\nx\n" + "y" * 50
        ok, reason = prox_trial_pass(trial, prev, **self.BASE)
        assert not ok and "protected" in reason

    def test_not_strictly_smaller_rejected(self) -> None:
        ok, reason = prox_trial_pass("x" * 1000, "y" * 1000, **self.BASE)
        assert not ok and "shrink" in reason

    def test_beyond_compression_cap_rejected(self) -> None:
        ok, reason = prox_trial_pass("x" * 500, "y" * 1000, **self.BASE)
        assert not ok and "compression" in reason

    def test_soft_cap_escape_on_hard_improvement(self) -> None:
        # 50% compression > cap 0.10, but hard strictly beats baseline → escape
        kw = dict(self.BASE, trial_hard=0.85)
        ok, reason = prox_trial_pass("x" * 500, "y" * 1000, **kw)
        assert ok, reason
        assert "soft-cap escape" in reason

    def test_soft_cap_escape_on_soft_improvement(self) -> None:
        # Over-compression justified by a strict soft improvement instead
        kw = dict(self.BASE, trial_soft=0.75)
        ok, reason = prox_trial_pass("x" * 500, "y" * 1000, **kw)
        assert ok, reason
        assert "soft-cap escape" in reason

    def test_soft_cap_escape_still_enforces_floors(self) -> None:
        # Over-compression + hard improvement, but soft drops beyond tol →
        # escape granted, yet Gate 3 rejects the trial
        kw = dict(self.BASE, trial_hard=0.85, trial_soft=0.60)
        ok, reason = prox_trial_pass("x" * 500, "y" * 1000, **kw)
        assert not ok and "soft" in reason

    def test_hard_drop_beyond_tol_rejected(self) -> None:
        kw = dict(self.BASE, trial_hard=0.70)
        ok, reason = prox_trial_pass("x" * 900, "y" * 1000, **kw)
        assert not ok and "hard" in reason

    def test_soft_drop_beyond_tol_rejected(self) -> None:
        kw = dict(self.BASE, trial_soft=0.60)
        ok, reason = prox_trial_pass("x" * 900, "y" * 1000, **kw)
        assert not ok and "soft" in reason

    def test_drop_within_tol_passes(self) -> None:
        kw = dict(self.BASE, trial_hard=0.75, trial_soft=0.68)
        ok, _ = prox_trial_pass("x" * 900, "y" * 1000, **kw)
        assert ok


# ── _sanitize_trial ─────────────────────────────────────────────────────────

class TestSanitizeTrial:
    def test_strips_markdown_fence(self) -> None:
        fenced = "```markdown\n## A\ncontent\n```"
        assert prox_shrink._sanitize_trial(fenced) == "## A\ncontent"

    def test_plain_text_untouched(self) -> None:
        assert prox_shrink._sanitize_trial("  ## A\n") == "## A"

    def test_empty(self) -> None:
        assert prox_shrink._sanitize_trial("") == ""
        assert prox_shrink._sanitize_trial(None) == ""


# ── auto tolerances ─────────────────────────────────────────────────────────

class TestAutoTolerances:
    def test_formula_bernoulli_hard(self) -> None:
        # 8/10 hard → σ_diff = sqrt(2·0.8·0.2/10) ≈ 0.179; ×2.5 → 0.447
        results = [{"hard": 1 if i < 8 else 0, "soft": 0.7} for i in range(10)]
        th, _ts = prox_shrink._auto_tolerances(results, 2.5)
        assert th == pytest.approx(2.5 * (2 * 0.8 * 0.2 / 10) ** 0.5)

    def test_formula_soft_variance(self) -> None:
        softs = [1.0, 0.5, 0.0, 0.5]  # mean 0.5, s² = 1/6
        results = [{"hard": 1, "soft": s} for s in softs]
        _th, ts = prox_shrink._auto_tolerances(results, 1.0)
        assert ts == pytest.approx((2 * (1 / 6) / 4) ** 0.5)

    def test_degenerate_fallback(self) -> None:
        # all-correct: p(1-p)=0 → hard tol 0; soft falls back to hard σ
        results = [{"hard": 1, "soft": 1.0}] * 5
        th, ts = prox_shrink._auto_tolerances(results, 2.0)
        assert th == 0.0 and ts == 0.0
        assert prox_shrink._auto_tolerances([], 2.0) == (0.0, 0.0)

    def test_auto_mode_recorded_in_audit(self, tmp_path, monkeypatch) -> None:
        # tolerance < 0 → auto-computed after baseline; recorded in params
        adapter = FakeAdapter(lambda skill: (0.8, 0.7))

        def trial_fn(user: str) -> str:
            return "# T\n\n## A\nshort\n"

        calls = []

        def fake_chat_optimizer(*, system, user, max_completion_tokens, retries, stage):
            calls.append(user)
            return json.dumps({"reasoning": "r", "trial_skill": trial_fn(user)}), {}

        monkeypatch.setattr(prox_shrink, "chat_optimizer", fake_chat_optimizer)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            hard_tolerance=-1.0,
            soft_tolerance=-1.0,
            tolerance_scale=2.5,
        )
        p = audit["params"]
        assert p["tolerance_auto_hard"] is True
        assert p["tolerance_auto_soft"] is True
        assert p["hard_tolerance"] == pytest.approx(2.5 * (2 * 0.8 * 0.2 / 10) ** 0.5)
        assert p["hard_tolerance"] > 0

    def test_explicit_tolerance_overrides_auto(self, tmp_path, monkeypatch) -> None:
        adapter = FakeAdapter(lambda skill: (0.8, 0.7))

        def trial_fn(user: str) -> str:
            return "# T\n\n## A\nshort\n"

        def fake_chat_optimizer(*, system, user, max_completion_tokens, retries, stage):
            return json.dumps({"reasoning": "r", "trial_skill": trial_fn(user)}), {}

        monkeypatch.setattr(prox_shrink, "chat_optimizer", fake_chat_optimizer)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            hard_tolerance=0.05,   # explicit
            soft_tolerance=-1.0,   # auto
        )
        p = audit["params"]
        assert p["tolerance_auto_hard"] is False
        assert p["hard_tolerance"] == 0.05
        assert p["tolerance_auto_soft"] is True




# ── Adaptive drilldown: pure helpers ───────────────────────────────────────

class TestDrillUnitIntoSubs:
    def test_packing_and_header_excluded(self) -> None:
        unit = (
            "## Header\n"
            + "para one. " * 30 + "\n\n"   # ~300 chars → own block
            + "para two. " * 30 + "\n\n"   # ~300 chars → own block
            + "tail." * 10                  # ~50-char remainder
        )
        subs = drill_unit_into_subs(unit, pack_chars=200)
        assert len(subs) == 2
        assert all("## Header" not in s for s in subs)
        assert "tail." in subs[-1]          # short remainder merged back
        for s in subs:
            assert len(s) >= 200

    def test_too_short_returns_empty(self) -> None:
        assert drill_unit_into_subs("## H\n\nshort body", 200) == []
        assert drill_unit_into_subs("## H", 200) == []
        assert drill_unit_into_subs("", 200) == []


class TestSkillWithoutSubunit:
    def test_removes_block_keeps_header_and_protected(self) -> None:
        skill = (
            "# T\n\n## S\nhead para AAA\n\npara BBB\n\npara CCC\n\n"
            "<!-- SLOW_UPDATE_START -->\nkeep\n<!-- SLOW_UPDATE_END -->\n"
        )
        unit = "## S\nhead para AAA\n\npara BBB\n\npara CCC"
        out = skill_without_subunit(skill, unit, "para BBB")
        assert out is not None
        assert "para BBB" not in out
        assert "## S" in out and "head para AAA" in out
        assert "SLOW_UPDATE_START" in out and "keep" in out

    def test_missing_sub_returns_none(self) -> None:
        skill = "# T\n\n## S\nbody\n"
        assert skill_without_subunit(skill, "## S\nbody", "nope") is None


# ── Adaptive drilldown: two-phase LOO end-to-end ────────────────────────────

# NOTE: the leading ``+`` on continuation lines is load-bearing — without it
# Python's implicit string-literal concatenation would glue ``"\n\n"`` to the
# next color's literal, turning each color line into 20 tiny paragraphs.
DRILL_SKILL = (
    "# Title\n\n"
    "## Ambig Section\n"
    + "BBBB " + "alpha guidance. " * 20 + "\n\n"
    + "beta guidance. " * 20 + "\n\n"
    + "gamma guidance. " * 20 + "\n\n"
    + "## Kept\nDo X.\n\n"
    "<!-- SLOW_UPDATE_START -->\nkeep me\n<!-- SLOW_UPDATE_END -->\n"
)

# A ~6k-char ambiguous section: 12 paragraphs of ~500 chars each.  With
# auto packing (unit/6 ≈ 1000) greedy packing yields ~4-6 coarse blocks,
# never one block per paragraph.
BIG_DRILL_SKILL = (
    "# Title\n\n"
    "## Big Ambig\n"
    + "".join(f"point {i} " + "detail. " * 62 + "\n\n" for i in range(12))
    + "## Kept\nDo X.\n\n"
    "<!-- SLOW_UPDATE_START -->\nkeep me\n<!-- SLOW_UPDATE_END -->\n"
)


class TestAdaptiveDrill:
    def _patch_optimizer(self, monkeypatch):
        calls = []

        def fake_chat_optimizer(*, system, user, max_completion_tokens, retries, stage):
            calls.append(user)
            trial = (
                "# T\n\n## A\ns\n\n"
                "<!-- SLOW_UPDATE_START -->\nkeep me\n<!-- SLOW_UPDATE_END -->\n"
            )
            return json.dumps({"reasoning": "r", "trial_skill": trial}), {}

        monkeypatch.setattr(prox_shrink, "chat_optimizer", fake_chat_optimizer)
        return calls

    def test_ambiguous_unit_is_drilled(self, tmp_path, monkeypatch) -> None:
        # Section-level LOO is a wash (utility 0 → ambiguous) but one
        # paragraph block is measurably harmful once audited alone.
        def score_fn(skill: str):
            if "## Ambig Section" not in skill:
                return (0.6, 0.6)
            if "BBBB" in skill:
                return (0.6, 0.6)
            return (0.8, 0.8)

        adapter = FakeAdapter(score_fn)
        calls = self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=200,
            # explicit narrow gate: the auto gate at n=10 (≈0.11) exceeds
            # the block-effect ceiling and would (correctly) skip drilling
            noise_gate=0.03,
        )
        r0 = audit["rounds"][0]
        ambig = next(u for u in r0["units"] if u["char_len"] > 500)
        subs = ambig.get("drilled_subs")
        assert subs and len(subs) == 3
        assert subs[0]["utility_hard"] == pytest.approx(-0.2)
        assert subs[1]["utility_hard"] == pytest.approx(0.0)
        # the Shrinker table carries the drill rows
        assert "↳" in calls[0]
        assert "ambiguous at section level" in calls[0]
        # sub rollouts persisted under their own loo dirs
        assert os.path.isdir(tmp_path / "prox_shrink" / "loo_r0_u0_s0")

    def test_clear_signal_unit_is_not_drilled(self, tmp_path, monkeypatch) -> None:
        # Whole-section removal already improves the score (|Δ| ≥ gate) →
        # clear negative asset, drilling is pointless and must not run.
        def score_fn(skill: str):
            if "BBBB" in skill:
                return (0.6, 0.6)
            return (0.8, 0.8)

        adapter = FakeAdapter(score_fn)
        self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=200,
            noise_gate=0.03,
        )
        assert all("drilled_subs" not in u for u in audit["rounds"][0]["units"])

    def test_drill_budget_truncates_with_note(self, tmp_path, monkeypatch) -> None:
        adapter = FakeAdapter(lambda skill: (0.6, 0.6))
        self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=200,
            drill_budget=2,
            noise_gate=0.03,
        )
        ambig = next(
            u for u in audit["rounds"][0]["units"] if u["char_len"] > 500
        )
        assert len(ambig["drilled_subs"]) == 2
        assert "partial drill" in ambig["drill_note"]

    def test_noise_gate_zero_disables_drill(self, tmp_path, monkeypatch) -> None:
        adapter = FakeAdapter(lambda skill: (0.6, 0.6))
        self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=200,
            noise_gate=0.0,
        )
        assert all("drilled_subs" not in u for u in audit["rounds"][0]["units"])

    def test_auto_pack_sizes_blocks_to_unit(self, tmp_path, monkeypatch) -> None:
        # sub_pack_chars=-1 → pack = clamp(unit/6, 400, 2000): a large
        # ambiguous section is split into ~6 coarse blocks (not one block
        # per paragraph), each staying ≥ the 400-char semantic floor.
        adapter = FakeAdapter(lambda skill: (0.6, 0.6))
        self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            BIG_DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=-1,
            noise_gate=0.03,
        )
        big = next(u for u in audit["rounds"][0]["units"] if u["char_len"] > 5000)
        subs = big.get("drilled_subs")
        assert subs, "large ambiguous unit should be drilled in auto mode"
        assert 4 <= len(subs) <= 7
        assert all(s["char_len"] >= 400 for s in subs)

    def test_drill_skipped_when_gate_too_wide(self, tmp_path, monkeypatch) -> None:
        # A noise gate above the block-effect ceiling (0.05) means even
        # section-level signals barely clear the noise — block-level LOO
        # would be pure noise, so drilling must be skipped outright.
        adapter = FakeAdapter(lambda skill: (0.6, 0.6))
        self._patch_optimizer(monkeypatch)

        audit = prox_shrink.run_prox_shrink(
            DRILL_SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            sub_pack_chars=200,
            noise_gate=0.5,
        )
        assert all("drilled_subs" not in u for u in audit["rounds"][0]["units"])


class FakeAdapter:
    """Rollout scores are a deterministic function of the skill text."""

    def __init__(self, score_fn):
        self.score_fn = score_fn
        self.rollout_calls: list[str] = []

    def rollout(self, env, skill, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        self.rollout_calls.append(skill)
        hard, soft = self.score_fn(skill)
        with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"hard": hard, "soft": soft}, f)
        return [{"id": str(i), "hard": 1 if i < hard * 10 else 0, "soft": soft}
                for i in range(10)]


def _make_build_eval_env():
    def build(split, env_num, seed):
        return object(), env_num
    return build


class TestRunProxShrink:
    def _monkeypatch_optimizer(self, monkeypatch, trial_fn):
        calls = []

        def fake_chat_optimizer(*, system, user, max_completion_tokens, retries, stage):
            calls.append(user)
            trial = trial_fn(user)
            return json.dumps({"reasoning": "r", "trial_skill": trial}), {}

        monkeypatch.setattr(prox_shrink, "chat_optimizer", fake_chat_optimizer)
        return calls

    def test_accepted_shrink_updates_final_skill(self, tmp_path, monkeypatch) -> None:
        # Baseline skill: removing the filler unit keeps scores; a shorter
        # skill (drop filler) also keeps scores → trial passes the gate.
        def score_fn(skill: str):
            return 0.8, 0.7

        adapter = FakeAdapter(score_fn)

        def trial_fn(user: str) -> str:
            # produce a strictly smaller skill preserving sections + markers
            return (
                "# Title\n\nPreamble line.\n\n"
                "## Search Strategy\nDo X.\n\n"
                "## Answer Format\nBox.\n\n"
                "<!-- SLOW_UPDATE_START -->\nkeep me\n<!-- SLOW_UPDATE_END -->\n"
            )

        self._monkeypatch_optimizer(monkeypatch, trial_fn)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
            max_compression=0.5,
        )
        assert audit["shrunk"] is True
        assert len(audit["final_skill"]) < len(SKILL)
        assert audit["final_hard"] == pytest.approx(0.8)
        # artifacts persisted
        assert os.path.isfile(tmp_path / "prox_shrink" / "audit.json")
        assert os.path.isfile(tmp_path / "prox_shrink" / "trial_r0.md")
        # baseline + per-unit LOO + ref(only round0 reuses base) + trial rollouts
        assert len(adapter.rollout_calls) >= 1 + 3 + 1

    def test_rejected_trial_keeps_original(self, tmp_path, monkeypatch) -> None:
        # Trial scores collapse → gate 3 rejects → skill unchanged.
        adapter = FakeAdapter(lambda skill: (
            (0.8, 0.7) if "Lorem" in skill or "keep me" not in skill else (0.2, 0.2)
        ))
        # simpler: score by length — the shrunk trial scores worse
        def score_fn(skill: str):
            if len(skill) > 120:
                return 0.8, 0.7
            return 0.2, 0.2

        adapter = FakeAdapter(score_fn)

        def trial_fn(user: str) -> str:
            return "# T\n\n## A\nshort\n"

        self._monkeypatch_optimizer(monkeypatch, trial_fn)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=3,
        )
        assert audit["shrunk"] is False
        assert audit["final_skill"] == SKILL
        assert audit["rounds"][0]["gate_passed"] is False
        # single-pass termination: no second Shrinker round after failure
        assert len(audit["rounds"]) == 1

    def test_shrinker_error_terminates(self, tmp_path, monkeypatch) -> None:
        adapter = FakeAdapter(lambda skill: (0.8, 0.7))

        def fake_chat_optimizer(**kwargs):
            raise RuntimeError("optimizer down")

        monkeypatch.setattr(prox_shrink, "chat_optimizer", fake_chat_optimizer)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=2,
        )
        assert audit["shrunk"] is False
        assert audit["rounds"][0]["gate_reason"].startswith("shrinker error")

    def test_identical_trial_terminates(self, tmp_path, monkeypatch) -> None:
        adapter = FakeAdapter(lambda skill: (0.8, 0.7))

        def trial_fn(user: str) -> str:
            return SKILL  # not strictly smaller

        self._monkeypatch_optimizer(monkeypatch, trial_fn)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=2,
        )
        assert audit["shrunk"] is False
        assert "identical" in audit["rounds"][0]["gate_reason"]

    def test_loo_utilities_recorded(self, tmp_path, monkeypatch) -> None:
        # Removing the filler unit does not hurt; removing Strategy does.
        def score_fn(skill: str):
            if "## Search Strategy" not in skill:
                return 0.5, 0.5
            return 0.8, 0.7

        adapter = FakeAdapter(score_fn)

        def trial_fn(user: str) -> str:
            return "# T\n\n## A\nshort\n"

        self._monkeypatch_optimizer(monkeypatch, trial_fn)

        audit = prox_shrink.run_prox_shrink(
            SKILL,
            adapter=adapter,
            build_eval_env=_make_build_eval_env(),
            out_root=str(tmp_path),
            seed=42,
            env_num=10,
            max_trials=1,
        )
        units = {u["header"]: u for u in audit["rounds"][0]["units"]}
        assert units["## Search Strategy"]["utility_hard"] == pytest.approx(0.3)
        assert units["## Verbose Filler"]["utility_hard"] == pytest.approx(0.0)
