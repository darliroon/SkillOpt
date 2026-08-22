"""SkillProx Backward — post-training proximal skill shrink.

Runs AFTER the forward training loop finishes, on the best skill:

  1. Baseline  — evaluate the pre-shrink skill on the selection set
                 (valid_seen).  This fixes the validation floor that every
                 trial must hold (Gate 3) and the character count the
                 cumulative compression cap is measured against.
  2. Decompose — split the skill into ``##`` section units; protected
                 mechanism blocks (slow-update guidance, appendix) are
                 stripped and re-attached verbatim, never shrinkable.
  3. LOO audit — leave-one-out utility: for each unit, evaluate the skill
                 with that unit removed; ``utility = ref - loo``.  Units
                 with utility ≤ 0 are prime shrink candidates.  Ambiguous
                 units (|Δhard| inside the noise gate) are adaptively
                 drilled into ≥800-char paragraph blocks and re-audited
                 block-by-block (two-phase LOO, budget-capped).
  4. Shrinker  — optimizer LLM proposes a strictly smaller trial skill,
                 guided by the utility table.
  5. Triple gate — structure / strict-shrink + compression cap /
                 validation floor vs the PRE-SHRINK baseline.
  6. Chain     — an accepted trial becomes the current skill and the next
                 round starts; the first failure terminates the phase
                 (single-pass finite termination, per the paper).

The trainer owns side-effects (env building, rollouts); this module
orchestrates them through the ``build_eval_env`` callback so it stays
environment-agnostic.

Public API
----------
- :func:`run_prox_shrink` — the whole backward phase; returns an audit dict.
"""
from __future__ import annotations

import json
import os
import traceback

from skillopt.evaluation.gate import (
    auto_tolerances as _auto_tolerances,
    decompose_skill_units,
    drill_unit_into_subs,
    prox_trial_pass,
    skill_without_subunit,
    skill_without_unit,
)
from skillopt.model import chat_optimizer
from skillopt.prompts import load_prompt
from skillopt.utils import compute_score, extract_json


def _sanitize_trial(text) -> str:
    """Normalize an LLM-produced trial skill: strip fences / whitespace."""
    if not text:
        return ""
    t = str(text).strip()
    # Strip one wrapping markdown fence (```markdown ... ```).
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            body = t[first_nl + 1:]
            if body.rstrip().endswith("```"):
                t = body.rstrip()[:-3].rstrip()
    return t


def _format_units_table(
    units: list[dict],
    utilities: dict[int, dict],
    drilled: dict[int, list[dict]] | None = None,
) -> str:
    """Render the LOO utility audit as a compact markdown table.

    Drilled parents (ambiguous at section level) carry indented ``↳`` rows
    for each audited paragraph block.
    """
    drilled = drilled or {}
    lines = [
        "| # | Section | Chars | Δhard if removed | Δsoft if removed | Verdict |",
        "|---|---------|-------|------------------|------------------|---------|",
    ]
    for u in units:
        if u.get("fixed"):
            lines.append(
                f"| {u['id']} | {u['header'][:60]} | {u['char_len']} "
                f"| — | — | section header (fixed — keep) |"
            )
            continue
        util = utilities.get(u["id"], {"utility_hard": 0.0, "utility_soft": 0.0})
        uh = util["utility_hard"]
        us = util["utility_soft"]
        if u["id"] in drilled:
            verdict = "ambiguous at section level — see drilled blocks below"
        elif uh <= 0 and us <= 0:
            verdict = "removable (no measured value)"
        elif uh <= 0.02 and us <= 0.02:
            verdict = "low value (marginal)"
        else:
            verdict = "valuable (keep core, may tighten wording)"
        lines.append(
            f"| {u['id']} | {u['header'][:60]} | {u['char_len']} "
            f"| {uh:+.4f} | {us:+.4f} | {verdict} |"
        )
        for s in drilled.get(u["id"], []):
            sh = s["utility_hard"]
            ss = s["utility_soft"]
            if sh <= 0 and ss <= 0:
                s_verdict = "block removable"
            elif sh <= 0.02 and ss <= 0.02:
                s_verdict = "block marginal"
            else:
                s_verdict = "block valuable — keep"
            lines.append(
                f"| {u['id']}.{s['sub']} | ↳ {s['header'][:57]} "
                f"| {s['char_len']} | {sh:+.4f} | {ss:+.4f} | {s_verdict} |"
            )
    return "\n".join(lines)


# Auto-drill packing bounds: a removable block smaller than the floor is a
# semantically incoherent shrink target; above the cap the drill loses
# resolution on very large sections.
DRILL_PACK_FLOOR = 400
DRILL_PACK_CAP = 2000
# Noise gates wider than this ceiling mean block-level effects (necessarily
# smaller than section-level ones) drown in measurement noise → drilling
# would only burn rollouts without producing evidence.
DRILL_SKIP_GATE = 0.05


def _auto_pack_chars(unit_len: int) -> int:
    """Auto packing size for adaptive drilldown.

    ``clamp(unit_len / 6, 400, 2000)`` — each drilled unit yields ~4-6
    blocks regardless of absolute section size, so the granularity scales
    with the skill's own writing density instead of requiring per-dataset
    manual tuning.
    """
    return max(DRILL_PACK_FLOOR, min(DRILL_PACK_CAP, unit_len // 6))


def _rollout_scores(
    adapter,
    build_eval_env,
    skill: str,
    split: str,
    env_num: int,
    seed: int,
    rollout_dir: str,
) -> tuple[float, float, list]:
    """Build the eval env, roll *skill* out, return (hard, soft, results)."""
    env, _n = build_eval_env(split, env_num, seed)
    results = adapter.rollout(env, skill, rollout_dir)
    hard, soft = compute_score(results)
    return hard, soft, results


def run_prox_shrink(
    skill: str,
    *,
    adapter,
    build_eval_env,
    out_root: str,
    seed: int,
    env_num: int = 0,
    loo_env_num: int = 0,
    max_trials: int = 3,
    hard_tolerance: float = -1.0,
    soft_tolerance: float = -1.0,
    tolerance_scale: float = 2.5,
    max_compression: float = 0.10,
    max_completion_tokens: int = 0,
    adaptive_drill: bool = True,
    noise_gate: float = -1.0,
    sub_pack_chars: int = -1,
    drill_budget: int = 6,
) -> dict:
    """Run the SkillProx backward (proximal shrink) phase on *skill*.

    Parameters
    ----------
    skill : str
        The pre-shrink skill (normally the best-on-val skill).
    adapter : EnvAdapter
        Environment adapter (rollout side-effects).
    build_eval_env : callable
        ``build_eval_env(split, env_num, seed) -> (env_manager, n)`` —
        the trainer's closure for deterministic evaluation splits.
    out_root : str
        Output root; audit artifacts go to ``<out_root>/prox_shrink/``.
    seed : int
        Split seed (must match the forward phase for comparability).
    env_num : int
        Selection-set size for baseline / trial gating rollouts
        (``sel_env_num`` semantics; 0 = environment default).
    loo_env_num : int
        Selection-set size for the LOO audit (0 = same as ``env_num``).
        Can be lowered to cut audit cost on large selection sets.
    max_trials : int
        Maximum number of shrink rounds (each = LOO + Shrinker + gate).
    hard_tolerance, soft_tolerance : float
        Gate 3 validation floor tolerances vs the pre-shrink baseline.
        Negative values mean AUTO: computed after the baseline rollout as
        ``tolerance_scale × σ_diff`` (see :func:`_auto_tolerances`), so the
        floor adapts to the val size / task difficulty per dataset.
    tolerance_scale : float
        k-factor for auto tolerances (only used when a tolerance < 0).
        2.5 ⇒ a zero-degradation trial is noise-rejected ~1.2% of the time.
    max_compression : float
        Cumulative compression cap vs the pre-shrink character count.
    max_completion_tokens : int
        Token budget for the Shrinker optimizer call.
    adaptive_drill : bool
        Two-phase LOO: after the section-level audit, units whose
        |Δhard| sits inside the noise gate are drilled into paragraph
        blocks (≥ *sub_pack_chars* chars each, header line kept fixed)
        and each block gets its own LOO rollout.  Clear-signal units
        (|Δhard| ≥ gate) are never drilled — money is spent only where
        the section-level measurement is inconclusive.
    noise_gate : float
        The |Δhard| band that counts as "ambiguous".  Negative = AUTO:
        ``0.5 × σ_diff_hard`` from the baseline rollout (the unpaired
        σ overestimates the paired LOO noise; halving approximates the
        correlation between same-item re-measurements).  ``0`` disables
        drilling.  Regardless of how the gate is set, drilling is skipped
        outright when it exceeds ``DRILL_SKIP_GATE`` (0.05): block effects
        are necessarily smaller than section effects, so a wider gate
        means block-level LOO is pure noise.
    sub_pack_chars : int
        Target minimum character length of a drilled paragraph block.
        Negative = AUTO: ``clamp(unit_len / 6, 400, 2000)`` per unit, so
        each drilled section yields ~4-6 blocks regardless of absolute
        size — the granularity scales with the skill's own writing
        density and no per-dataset tuning is needed.  Positive = fixed
        packing size.  Blocks are kept ≥ the floor so per-block effects
        stay above the measurement noise floor (paragraph-level
        granularity is deliberately avoided — its effect size is
        unmeasurable at typical val sizes).
    drill_budget : int
        Max total drilled blocks evaluated per round (cost control).
        Candidates are processed largest-unit-first; a unit needs ≥ 2
        blocks inside the budget to be drilled at all.

    Returns
    -------
    dict
        Audit record (also persisted to ``prox_shrink/audit.json``) with
        ``final_skill`` and per-round details.  When nothing was accepted,
        ``final_skill`` equals the input *skill*.
    """
    prox_dir = os.path.join(out_root, "prox_shrink")
    os.makedirs(prox_dir, exist_ok=True)
    # Persist the pre-shrink skill so the prox folder is self-contained:
    # preshrink_skill.md (input) vs final_skill.md (shrunk) can be compared
    # without touching best_skill.md, which the trainer keeps pre-prox.
    with open(
        os.path.join(prox_dir, "preshrink_skill.md"), "w", encoding="utf-8"
    ) as f:
        f.write(skill)

    base_chars = len(skill)
    loo_env = loo_env_num if loo_env_num > 0 else env_num

    # ── 1. Baseline on the selection split (fixes the validation floor) ──
    print(f"\n{'='*60}")
    print("  PROX SHRINK — SkillProx backward phase (post-training)")
    print(f"{'='*60}")
    base_hard, base_soft, base_results = _rollout_scores(
        adapter, build_eval_env, skill, "valid_seen", env_num, seed,
        os.path.join(prox_dir, "baseline_eval"),
    )
    print(
        f"  [prox] baseline: chars={base_chars} "
        f"hard={base_hard:.4f} soft={base_soft:.4f}"
    )

    # Auto tolerances: negative inputs → scale × measured sampling noise.
    tol_auto_hard = hard_tolerance < 0
    tol_auto_soft = soft_tolerance < 0
    if tol_auto_hard or tol_auto_soft:
        a_hard, a_soft = _auto_tolerances(base_results, tolerance_scale)
        if tol_auto_hard:
            hard_tolerance = a_hard
        if tol_auto_soft:
            soft_tolerance = a_soft
        print(
            f"  [prox] auto tolerance (scale={tolerance_scale}, "
            f"n={len(base_results)}): hard_tol={hard_tolerance:.4f} "
            f"soft_tol={soft_tolerance:.4f}"
        )

    audit: dict = {
        "performed": True,
        "base_chars": base_chars,
        "base_hard": base_hard,
        "base_soft": base_soft,
        "params": {
            "max_trials": max_trials,
            "hard_tolerance": hard_tolerance,
            "soft_tolerance": soft_tolerance,
            "tolerance_auto_hard": tol_auto_hard,
            "tolerance_auto_soft": tol_auto_soft,
            "tolerance_scale": tolerance_scale,
            "max_compression": max_compression,
            "loo_env_num": loo_env,
            "adaptive_drill": adaptive_drill,
            "noise_gate": noise_gate,
            "sub_pack_chars": sub_pack_chars,
            "drill_budget": drill_budget,
        },
        "rounds": [],
    }

    cur_skill = skill
    cur_hard, cur_soft = base_hard, base_soft

    for rnd in range(max_trials):
        # ── 2. Unit decomposition ────────────────────────────────────────
        # Oversized ## sections (> drilldown_chars) are drilled into ###
        # subsections; their header blocks are fixed units, kept verbatim.
        decomp = decompose_skill_units(cur_skill)
        units = decomp["units"]
        removable = [u for u in units if not u.get("fixed")]
        if not removable:
            print(f"  [prox] round {rnd}: no removable units to shrink — stop")
            break

        # ── 3. Leave-one-out utility audit ───────────────────────────────
        # Reference = current skill on the LOO split.  Reuse the baseline
        # rollout only on round 0 when both use the same split size.
        if rnd == 0 and loo_env == env_num:
            ref_hard, ref_soft = base_hard, base_soft
        else:
            ref_hard, ref_soft, _ = _rollout_scores(
                adapter, build_eval_env, cur_skill, "valid_seen",
                loo_env, seed, os.path.join(prox_dir, f"loo_ref_r{rnd}"),
            )
        print(
            f"\n  [prox] round {rnd}/{max_trials - 1}: {len(removable)} removable "
            f"unit(s) of {len(units)} total, chars={len(cur_skill)} "
            f"ref(hard={ref_hard:.4f}, soft={ref_soft:.4f})"
        )

        utilities: dict[int, dict] = {}
        for u in removable:
            ablated = skill_without_unit(cur_skill, u["content"])
            if ablated is None:  # unit text drifted — should not happen
                utilities[u["id"]] = {
                    "loo_hard": ref_hard, "loo_soft": ref_soft,
                    "utility_hard": 0.0, "utility_soft": 0.0,
                }
                continue
            loo_dir = os.path.join(prox_dir, f"loo_r{rnd}_u{u['id']}")
            loo_hard, loo_soft, _ = _rollout_scores(
                adapter, build_eval_env, ablated, "valid_seen",
                loo_env, seed, loo_dir,
            )
            utilities[u["id"]] = {
                "loo_hard": loo_hard,
                "loo_soft": loo_soft,
                "utility_hard": ref_hard - loo_hard,
                "utility_soft": ref_soft - loo_soft,
            }
            print(
                f"    [loo] u{u['id']} {u['header'][:40]:<40s} "
                f"Δhard={ref_hard - loo_hard:+.4f} "
                f"Δsoft={ref_soft - loo_soft:+.4f}"
            )

        # ── 3b. Adaptive drilldown (two-phase LOO) ───────────────────────
        # Units whose |Δhard| is inside the noise gate are ambiguous at
        # section level → drill them into paragraph blocks and re-audit
        # each block.  Clear-signal units skip the drill; the budget caps
        # the extra rollout cost (largest units first).
        drilled: dict[int, list[dict]] = {}
        drill_notes: dict[int, str] = {}
        if adaptive_drill and noise_gate != 0:
            gate = noise_gate
            if gate < 0:
                gate, _ = _auto_tolerances(base_results, 0.5)
            auto_pack = sub_pack_chars < 0
            if gate > DRILL_SKIP_GATE:
                # Block effects are strictly smaller than section effects;
                # a gate this wide means even section-level signals are
                # barely measurable → block-level LOO would be pure noise.
                print(
                    f"    [drill] noise gate={gate:.4f} > block-effect "
                    f"ceiling {DRILL_SKIP_GATE:.2f} — drilling skipped "
                    "(block-level signal unmeasurable at this val size)"
                )
                candidates = []
            else:
                min_unit = (
                    2 * DRILL_PACK_FLOOR if auto_pack else sub_pack_chars
                )
                candidates = [
                    u for u in removable
                    if u["id"] in utilities
                    and abs(utilities[u["id"]]["utility_hard"]) < gate
                    and u["char_len"] >= min_unit
                ]
            candidates.sort(key=lambda u: -u["char_len"])
            if candidates:
                print(
                    f"    [drill] noise gate={gate:.4f} "
                    f"pack={'auto' if auto_pack else sub_pack_chars}: "
                    f"{len(candidates)} ambiguous unit(s), "
                    f"budget={drill_budget} block(s)"
                )
            budget = drill_budget
            for u in candidates:
                if budget < 2:
                    break
                pack = (
                    _auto_pack_chars(u["char_len"])
                    if auto_pack
                    else sub_pack_chars
                )
                subs = drill_unit_into_subs(u["content"], pack)
                if len(subs) < 2:
                    continue  # too small to split meaningfully
                full_n = len(subs)
                if len(subs) > budget:
                    subs = subs[:budget]
                    drill_notes[u["id"]] = (
                        f"partial drill ({len(subs)}/{full_n} blocks audited, "
                        "remaining blocks unaudited — treat conservatively)"
                    )
                budget -= len(subs)
                recs: list[dict] = []
                for k, sub in enumerate(subs):
                    ablated = skill_without_subunit(
                        cur_skill, u["content"], sub
                    )
                    if ablated is None:
                        continue
                    loo_dir = os.path.join(
                        prox_dir, f"loo_r{rnd}_u{u['id']}_s{k}"
                    )
                    loo_hard, loo_soft, _ = _rollout_scores(
                        adapter, build_eval_env, ablated, "valid_seen",
                        loo_env, seed, loo_dir,
                    )
                    recs.append({
                        "sub": k,
                        "header": sub.splitlines()[0][:60] if sub else "",
                        "char_len": len(sub),
                        "loo_hard": loo_hard,
                        "loo_soft": loo_soft,
                        "utility_hard": ref_hard - loo_hard,
                        "utility_soft": ref_soft - loo_soft,
                    })
                    print(
                        f"    [drill] u{u['id']}.s{k} "
                        f"{recs[-1]['header'][:36]:<36s} "
                        f"Δhard={ref_hard - loo_hard:+.4f} "
                        f"Δsoft={ref_soft - loo_soft:+.4f}"
                    )
                if recs:
                    drilled[u["id"]] = recs

        # ── 4. Shrinker optimizer call ───────────────────────────────────
        units_table = _format_units_table(units, utilities, drilled)
        min_chars = int(base_chars * (1.0 - max(0.0, max_compression)))
        user = (
            f"## Current Skill ({len(cur_skill)} chars)\n\n"
            f"{cur_skill}\n\n"
            f"## Unit Utility Audit (leave-one-out on validation)\n\n"
            f"Reference scores with the full skill: "
            f"hard={ref_hard:.4f}, soft={ref_soft:.4f}\n\n"
            f"{units_table}\n\n"
            f"## Constraints\n\n"
            f"- Cumulative compression cap: {max_compression:.1%} of the "
            f"original {base_chars} chars → the trial must be ≥ {min_chars} "
            f"chars (current: {len(cur_skill)} chars).\n"
            f"- The trial must be strictly smaller than the current skill.\n"
            f"- Rows marked \"ambiguous ... see drilled blocks below\" are "
            f"indented ``↳`` paragraph blocks audited inside that section; "
            f"each block may be dropped or tightened independently while "
            f"keeping its parent section header.\n"
            f"- Copy protected blocks "
            f"(<!-- SLOW_UPDATE_START/END -->, <!-- APPENDIX_START/END -->) "
            f"verbatim.\n"
        )
        try:
            response, _ = chat_optimizer(
                system=load_prompt("prox_shrink"),
                user=user,
                max_completion_tokens=max_completion_tokens,
                retries=3,
                stage="prox_shrink",
            )
            result = extract_json(response)
            trial_skill = _sanitize_trial(
                (result or {}).get("trial_skill", "")
            )
            shrink_reasoning = str((result or {}).get("reasoning", "")).strip()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            print(f"  [prox] round {rnd}: Shrinker call failed: {exc!r}")
            audit["rounds"].append({
                "round": rnd, "accepted": False,
                "gate_passed": False,
                "gate_reason": f"shrinker error: {exc!r}",
            })
            break

        with open(
            os.path.join(prox_dir, f"trial_r{rnd}.md"), "w", encoding="utf-8"
        ) as f:
            f.write(trial_skill)

        # Compare under the same normalization the trial went through:
        # a trial differing only in trailing whitespace is NOT a shrink.
        cur_norm = _sanitize_trial(cur_skill)
        if not trial_skill or trial_skill == cur_norm:
            reason = "empty trial" if not trial_skill else "trial identical to current skill"
            print(f"  [prox] round {rnd}: {reason} — stop")
            audit["rounds"].append({
                "round": rnd, "accepted": False,
                "gate_passed": False, "gate_reason": reason,
                "shrink_reasoning": shrink_reasoning,
            })
            break

        # ── 5. Trial rollout + triple gate ───────────────────────────────
        trial_hard, trial_soft, _ = _rollout_scores(
            adapter, build_eval_env, trial_skill, "valid_seen",
            env_num, seed, os.path.join(prox_dir, f"trial_eval_r{rnd}"),
        )
        passed, reason = prox_trial_pass(
            trial_skill,
            cur_skill,
            trial_hard=trial_hard,
            trial_soft=trial_soft,
            base_hard=base_hard,
            base_soft=base_soft,
            hard_tolerance=hard_tolerance,
            soft_tolerance=soft_tolerance,
            max_compression=max_compression,
            base_chars=base_chars,
        )
        print(
            f"  [prox] trial: {len(cur_skill)}->{len(trial_skill)} chars, "
            f"hard={trial_hard:.4f} soft={trial_soft:.4f} — "
            f"{'PASS' if passed else 'REJECT'} ({reason})"
        )
        audit["rounds"].append({
            "round": rnd,
            "skill_chars": len(cur_skill),
            "units": [
                {
                    "id": u["id"],
                    "header": u["header"],
                    "char_len": u["char_len"],
                    "fixed": bool(u.get("fixed")),
                    **(
                        utilities[u["id"]]
                        if not u.get("fixed")
                        else {"loo_hard": None, "loo_soft": None,
                              "utility_hard": None, "utility_soft": None}
                    ),
                    **(
                        {"drilled_subs": drilled[u["id"]]}
                        if u["id"] in drilled
                        else {}
                    ),
                    **(
                        {"drill_note": drill_notes[u["id"]]}
                        if u["id"] in drill_notes
                        else {}
                    ),
                }
                for u in units
            ],
            "ref_hard": ref_hard,
            "ref_soft": ref_soft,
            "trial_chars": len(trial_skill),
            "trial_hard": trial_hard,
            "trial_soft": trial_soft,
            "gate_passed": passed,
            "gate_reason": reason,
            "shrink_reasoning": shrink_reasoning,
            "accepted": passed,
        })

        if not passed:
            break

        cur_skill = trial_skill
        cur_hard, cur_soft = trial_hard, trial_soft

    # ── 6. Persist audit + result ────────────────────────────────────────
    audit["final_skill"] = cur_skill
    audit["final_chars"] = len(cur_skill)
    audit["compression"] = (base_chars - len(cur_skill)) / max(base_chars, 1)
    audit["final_hard"] = cur_hard
    audit["final_soft"] = cur_soft
    audit["shrunk"] = cur_skill != skill
    with open(os.path.join(prox_dir, "audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    if audit["shrunk"]:
        with open(
            os.path.join(prox_dir, "final_skill.md"), "w", encoding="utf-8"
        ) as f:
            f.write(cur_skill)

    if audit["shrunk"]:
        print(
            f"\n  [prox] DONE: {base_chars}->{len(cur_skill)} chars "
            f"({audit['compression']:.1%} compression), "
            f"hard {base_hard:.4f}->{cur_hard:.4f}, "
            f"soft {base_soft:.4f}->{cur_soft:.4f}"
        )
    else:
        print(f"\n  [prox] DONE: no shrink accepted, skill unchanged")
    return audit
