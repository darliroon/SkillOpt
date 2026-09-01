"""Bridge between SkillOpt and GEPA (Genetic-Pareto) optimization.

This module provides:
  - :class:`SkillOptGEPAAdapter`: a GEPA adapter that wraps SkillOpt's
    environment adapter, enabling GEPA to optimize the skill text using
    SkillOpt's rollout infrastructure.
  - :func:`run_gepa_phase`: the Phase-2 entry point called by the trainer
    after SkillOpt training (Phase 1) and before prox shrink (Phase 3).

Pipeline:
  Phase 1: SkillOpt training  → best_skill.md
  Phase 2: GEPA optimization  → gepa_best_skill.md  (this module)
  Phase 3: Prox shrink       → final_skill.md
  Phase 4: Test evaluation   → valid_unseen scores
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from skillopt.model import chat_optimizer
from skillopt.prompts import load_prompt
from skillopt.utils import extract_json


# ── GEPA adapter ──────────────────────────────────────────────────

class SkillOptGEPAAdapter:
    """GEPA adapter wrapping SkillOpt's environment + rollout.

    GEPA calls :meth:`evaluate` to run the skill on a batch of items and
    score them.  It calls :meth:`make_reflective_dataset` to build the
    text fed to the reflection LM (which proposes improved skill text).

    Parameters
    ----------
    adapter : skillopt.envs.base.EnvAdapter
        SkillOpt environment adapter (SearchQA, DocVQA, etc.).
    build_eval_env : callable
        ``(split, env_num, seed) -> (env, n_items)`` — from the trainer.
    seed : int
        Random seed for reproducible rollouts.
    rollout_dir : str
        Directory for rollout artifacts (conversation.json, etc.).
    """

    def __init__(
        self,
        *,
        adapter,
        build_eval_env,
        seed: int,
        rollout_dir: str,
    ):
        self._adapter = adapter
        self._build_eval_env = build_eval_env
        self._seed = seed
        self._rollout_dir = rollout_dir
        self._call_counter = 0

    # ── GEPAAdapter interface ──────────────────────────────────────

    def evaluate(
        self,
        batch: list[dict],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ):
        """Run candidate['skill'] on *batch* items, return scores + trajectories.

        Returns a ``gepa.core.adapter.EvaluationBatch``.
        """
        from gepa.core.adapter import EvaluationBatch

        skill = candidate.get("skill", "")
        self._call_counter += 1

        # Run the full batch through the adapter at once (not one-by-one)
        # This is faster and matches the adapter's expected usage pattern.
        pred_dir = os.path.join(
            self._rollout_dir, f"gepa_batch_{self._call_counter}"
        )
        os.makedirs(pred_dir, exist_ok=True)

        try:
            results = self._adapter.rollout(batch, skill, pred_dir)
        except Exception as exc:
            results = [
                {"id": str(item.get("id", f"item_{i}")),
                 "hard": False, "soft": 0.0,
                 "prediction": "", "reference_text": ""}
                for i, item in enumerate(batch)
            ]

        if not results:
            results = [
                {"id": str(item.get("id", f"item_{i}")),
                 "hard": False, "soft": 0.0,
                 "prediction": "", "reference_text": ""}
                for i, item in enumerate(batch)
            ]

        # Compute scores
        scores = [1.0 if r.get("hard") else 0.0 for r in results]

        # Build trajectories for reflection
        trajectories = None
        if capture_traces:
            trajectories = []
            for i, (item, result) in enumerate(zip(batch, results)):
                item_id = str(item.get("id", f"item_{i}"))
                # SearchQA saves traces under <pred_dir>/predictions/<id>/.
                safe_id = item_id.replace(":", "-")
                conv_path = os.path.join(
                    pred_dir, "predictions", safe_id, "conversation.json",
                )
                conversation = []
                if os.path.exists(conv_path):
                    try:
                        with open(conv_path, "r", encoding="utf-8") as f:
                            conversation = json.load(f)
                    except Exception:
                        pass

                prediction = (
                    result.get("prediction")
                    or result.get("predicted_answer")
                    or result.get("response")
                    or ""
                )
                reference = (
                    result.get("reference_text")
                    or result.get("gold_answers")
                    or ""
                )
                if isinstance(reference, list):
                    reference = " | ".join(str(value) for value in reference)

                trajectories.append({
                    "question": str(item.get("question", ""))[:500],
                    "prediction": str(prediction)[:500],
                    "reference": str(reference)[:300],
                    "correct": bool(result.get("hard")),
                    "score": scores[i],
                    "conversation": conversation,
                })

        return EvaluationBatch(
            outputs=[
                r.get("prediction")
                or r.get("predicted_answer")
                or r.get("response")
                or ""
                for r in results
            ],
            scores=scores,
            trajectories=trajectories,
        )

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch,
        components_to_update: list[str],
    ) -> dict[str, list[dict]]:
        """Build a reflective dataset for GEPA's reflection LM.

        For each component (we only have "skill"), produce a list of
        per-item feedback entries showing the question, model answer,
        correct answer, and conversation excerpt.
        """
        reflective_data: list[dict] = []
        if eval_batch.trajectories is None:
            return {comp: reflective_data for comp in components_to_update}

        for traj in eval_batch.trajectories:
            entry: dict[str, Any] = {
                "input": traj.get("question", ""),
                "output": traj.get("prediction", ""),
                "score": traj.get("score", 0.0),
                "correct": traj.get("correct", False),
            }
            ref = traj.get("reference", "")
            if ref:
                entry["expected"] = ref

            conv = traj.get("conversation", [])
            if conv:
                conv_text = []
                for msg in conv[:5]:
                    if isinstance(msg, dict):
                        role = msg.get("role", msg.get("type", "msg"))
                        content = str(msg.get("content", ""))[:300]
                        conv_text.append(f"[{role}] {content}")
                    elif isinstance(msg, str):
                        conv_text.append(msg[:300])
                entry["trace"] = "\n".join(conv_text)

            reflective_data.append(entry)

        return {comp: reflective_data for comp in components_to_update}

    def propose_new_texts(
        self,
        candidate: dict[str, str],
        reflective_dataset,
        components_to_update: list[str],
        *,
        metadata=None,
    ) -> dict[str, str]:
        """Propose improved skill text using SkillOpt's optimizer LLM.

        This is called by GEPA instead of its default reflection LM.
        Uses SkillOpt's ``chat_optimizer`` which talks to the configured
        optimizer endpoint (e.g., GLM-5.2 via OpenAI-compatible API).
        """
        current_skill = candidate.get("skill", "")

        # Build reflection context from the reflective dataset
        parts = []
        for comp in components_to_update:
            entries = reflective_dataset.get(comp, [])
            for i, entry in enumerate(entries[:10]):  # cap at 10 items
                correct = "✓" if entry.get("score", 0) > 0.5 else "✗"
                q = str(entry.get("input", ""))[:200]
                pred = str(entry.get("output", ""))[:200]
                ref = str(entry.get("expected", ""))[:200]
                trace = str(entry.get("trace", ""))[:500]
                parts.append(
                    f"  [{correct}] Q: {q}\n"
                    f"     Predicted: {pred}\n"
                    f"     Expected: {ref}\n"
                    f"     Trace: {trace}"
                )

        side_info = "\n".join(parts) if parts else "(no failures to reflect on)"

        user_msg = (
            f"## Current Skill\n\n{current_skill}\n\n"
            f"## Execution Feedback (from validation rollouts)\n\n"
            f"The following items show where the current skill succeeds "
            f"and fails. Analyze WHY failures occur and propose an "
            f"improved skill.\n\n{side_info}\n\n"
            f"## Task\n\n"
            f"Produce an improved version of the skill that addresses "
            f"the failure patterns shown above. Keep what works, fix "
            f"what doesn't.\n"
        )

        try:
            response, _ = chat_optimizer(
                system=load_prompt("gepa_reflection"),
                user=user_msg,
                max_completion_tokens=16384,
                retries=3,
                stage="gepa_reflection",
            )
            result = extract_json(response)
            new_skill = str((result or {}).get("skill", "")).strip()
            if not new_skill or len(new_skill) < 50:
                return {comp: current_skill for comp in components_to_update}
            return {comp: new_skill for comp in components_to_update}
        except Exception as exc:
            print(f"  [gepa] propose_new_texts failed: {exc!r}")
            return {comp: current_skill for comp in components_to_update}


# ── Phase 2 entry point ──────────────────────────────────────────

def run_gepa_phase(
    skill: str,
    *,
    adapter,
    build_eval_env,
    out_root: str,
    seed: int,
    env_num: int = 0,
    max_metric_calls: int = 100,
    reflection_lm: str = "",
    reflection_minibatch_size: int = 10,
    run_dir: str = "",
    task_lm: str = "",
) -> tuple[str, dict]:
    """Run GEPA optimization on *skill* using SkillOpt's rollout infrastructure.

    Parameters
    ----------
    skill : str
        The skill text from Phase 1 (SkillOpt training).
    adapter : EnvAdapter
        SkillOpt environment adapter.
    build_eval_env : callable
        ``(split, env_num, seed) -> (env, n_items)`` from trainer.
    out_root : str
        Output root directory.
    seed : int
        Random seed.
    env_num : int
        Number of items for eval (0 = all val items).
    max_metric_calls : int
        GEPA budget — max number of evaluation calls.
    reflection_lm : str
        Model name for GEPA's reflection LM.  Empty = use SkillOpt's
        optimizer model config.
    reflection_minibatch_size : int
        Number of items per reflection minibatch.
    run_dir : str
        Directory for GEPA state.  Empty = auto under out_root.
    task_lm : str
        Model name for GEPA's task LM.  Not used if adapter handles
        rollout (which SkillOpt's does).

    Returns
    -------
    (best_skill, audit) : tuple[str, dict]
        The optimized skill text and an audit dict.
    """
    gepa_dir = os.path.join(out_root, "gepa_phase")
    os.makedirs(gepa_dir, exist_ok=True)
    if not run_dir:
        run_dir = gepa_dir

    rollout_dir = os.path.join(gepa_dir, "rollouts")
    os.makedirs(rollout_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print("  PHASE 2 — GEPA Optimization (process-driven reflection)")
    print(f"{'='*60}")
    print(f"  [gepa] max_metric_calls={max_metric_calls}")
    print(f"  [gepa] reflection_minibatch_size={reflection_minibatch_size}")
    print(f"  [gepa] seed={seed}")

    # Build train and val data for GEPA
    train_env, n_train = build_eval_env("train", env_num or 0, seed)
    val_env, n_val = build_eval_env("valid_seen", env_num or 0, seed)
    print(f"  [gepa] train items={n_train}, val items={n_val}")

    # Use a subset of valset for faster iterations (GEPA evaluates full valset
    # each iteration, so smaller valset = more iterations within budget).
    # Cap at 50 items if valset is larger.
    val_items = list(val_env)
    if len(val_items) > 50:
        import random as _rng
        _r = _rng.Random(seed)
        _r.shuffle(val_items)
        val_items = val_items[:50]
        print(f"  [gepa] valset capped to 50 items for faster iterations")

    # Build the GEPA adapter
    gepa_adapter = SkillOptGEPAAdapter(
        adapter=adapter,
        build_eval_env=build_eval_env,
        seed=seed,
        rollout_dir=rollout_dir,
    )

    # Seed candidate: the skill from Phase 1
    seed_candidate = {"skill": skill}

    # Reflection LM: use SkillOpt's optimizer model if not specified
    refl_lm = reflection_lm or None

    try:
        import gepa
    except ImportError:
        print("  [gepa] ERROR: gepa not installed. Run: pip install gepa")
        return skill, {"error": "gepa not installed", "performed": False}

    try:
        result = gepa.optimize(
            seed_candidate=seed_candidate,
            trainset=list(train_env),
            valset=val_items,
            adapter=gepa_adapter,
            task_lm=None,  # adapter handles rollout
            reflection_lm=refl_lm,
            max_metric_calls=max_metric_calls,
            reflection_minibatch_size=reflection_minibatch_size,
            run_dir=run_dir,
            seed=seed,
            use_wandb=False,
            display_progress_bar=False,
            write_agent_state=True,
            raise_on_exception=False,
        )

        best_skill = result.best_candidate.get("skill", skill) if isinstance(result.best_candidate, dict) else skill
        best_val_score = 0.0
        try:
            best_val_score = float(result.val_aggregate_scores[result.best_idx])
        except (IndexError, TypeError, AttributeError):
            pass
        audit = {
            "performed": True,
            "best_skill_chars": len(best_skill),
            "original_skill_chars": len(skill),
            "improved": best_skill != skill,
            "gepa_result": {
                "best_val_score": best_val_score,
                "n_candidates": len(result.candidates) if hasattr(result, "candidates") else 0,
            },
        }

        # Save GEPA best skill
        with open(os.path.join(gepa_dir, "gepa_best_skill.md"), "w",
                   encoding="utf-8") as f:
            f.write(best_skill)

        with open(os.path.join(gepa_dir, "gepa_audit.json"), "w",
                   encoding="utf-8") as f:
            json.dump(audit, f, indent=2, ensure_ascii=False)

        if audit["improved"]:
            print(
                f"  [gepa] DONE: skill evolved "
                f"({len(skill)}→{len(best_skill)} chars)"
            )
        else:
            print(f"  [gepa] DONE: no improvement, skill unchanged")

        return best_skill, audit

    except Exception as exc:
        print(f"  [gepa] ERROR: {exc!r}")
        traceback.print_exc()
        return skill, {"error": str(exc), "performed": False}
