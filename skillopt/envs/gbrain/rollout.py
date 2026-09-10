"""gbrain rollout — delegate task to Codex CLI, evaluate with rule judge."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from skillopt.envs.gbrain.evaluator import evaluate
from skillopt.model import is_target_exec_backend
from skillopt.model.codex_harness import prepare_workspace, render_skill_md, run_target_exec


def _build_codex_skill(skill_content: str) -> str:
    return render_skill_md(
        skill_content,
        description="Dynamic SkillOpt skill for the current gbrain task.",
        preamble=(
            "Use this skill when solving the current task.\n"
            "Follow the skill instructions precisely.\n"
        ),
    )


def process_one(
    item: dict,
    out_root: str,
    skill_content: str,
    exec_timeout: int = 120,
    max_completion_tokens: int = 0,
) -> dict:
    """Process one gbrain task: run Codex + evaluate with rule judge."""
    from skillopt.model import azure_openai as _llm

    item_id = str(item.get("task_id") or item.get("id", ""))
    task_text = item.get("task", "")
    judge = item.get("judge", {})

    result: dict = {
        "id": item_id,
        "question": task_text,
        "task_description": task_text,
        "task_type": "gbrain",
        "hard": 0,
        "soft": 0.0,
        "predicted_answer": "",
        "response": "",
        "fail_reason": "",
        "agent_ok": False,
        "n_turns": 0,
    }

    try:
        pred_dir = os.path.join(out_root, "predictions", item_id)
        os.makedirs(pred_dir, exist_ok=True)

        skill_md = _build_codex_skill(skill_content)
        work_dir = os.path.join(pred_dir, "codex_exec")

        prepare_workspace(
            work_dir=work_dir,
            skill_md=skill_md,
            task_text=task_text,
        )

        prompt = (
            "Use the `skillopt-target` skill available in this workspace.\n"
            "Read `task.md` and complete the task as instructed.\n"
            "If the skill instructs you to search or look something up, "
            "use shell commands like `curl` to perform web searches.\n"
        )

        final_message, raw = run_target_exec(
            work_dir=work_dir,
            prompt=prompt,
            model=_llm.TARGET_DEPLOYMENT,
            timeout=exec_timeout,
        )

        response = final_message or raw
        result["response"] = response
        result["agent_ok"] = True
        result["n_turns"] = 1

        eval_result = evaluate(judge, response, raw_trace=raw)
        result["hard"] = eval_result["hard"]
        result["soft"] = eval_result["soft"]
        result["predicted_answer"] = response[:2000]
        if eval_result["hard"] == 0:
            result["fail_reason"] = "; ".join(eval_result["fail_reasons"])

        eval_detail = (
            f"[EVALUATION RESULT]\n"
            f"Task: {task_text}\n"
            f"Response: {response[:500]!r}\n"
            f"Judge: {json.dumps(judge, ensure_ascii=False)}\n"
            f"Pass: {eval_result['hard']}\n"
            f"Score: {eval_result['soft']:.2f}\n"
            f"Failures: {eval_result['fail_reasons']}"
        )
        with open(os.path.join(pred_dir, "conversation.json"), "w", encoding="utf-8") as f:
            json.dump([
                {"type": "message", "turn": 1, "content": response},
                {"role": "system", "content": eval_detail},
            ], f, ensure_ascii=False, indent=2)

    except Exception as e:
        result["fail_reason"] = f"error: {e}"

    return result


def run_batch(
    items: list[dict],
    out_root: str,
    skill_content: str,
    exec_timeout: int = 120,
    workers: int = 4,
    max_completion_tokens: int = 0,
    task_timeout: int = 600,
) -> list[dict]:
    """Run gbrain tasks in parallel. Resume-aware."""
    task_timeout = max(task_timeout, exec_timeout + 60)
    results_path = os.path.join(out_root, "results.jsonl")
    os.makedirs(out_root, exist_ok=True)

    done_ids: set[str] = set()
    existing: list[dict] = []
    if os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    done_ids.add(str(r["id"]))
                    existing.append(r)
                except Exception:
                    pass

    pending = [it for it in items if str(it.get("task_id") or it.get("id", "")) not in done_ids]
    if not pending:
        return existing

    total = len(existing) + len(pending)
    completed = len(existing)
    correct_count = sum(1 for r in existing if r.get("hard", 0))
    if existing:
        print(f"    [rollout] resuming: {completed}/{total} already done", flush=True)

    results = list(existing)

    def _run_one(item: dict) -> dict:
        return process_one(item, out_root, skill_content, exec_timeout, max_completion_tokens)

    with open(results_path, "a", encoding="utf-8") as outf:
        ex = ThreadPoolExecutor(max_workers=workers)
        try:
            futs = {ex.submit(_run_one, it): it for it in pending}
            pending_futs = set(futs)
            while pending_futs:
                done, _ = wait(pending_futs, timeout=5, return_when=FIRST_COMPLETED)
                for fut in done:
                    pending_futs.remove(fut)
                    item = futs[fut]
                    try:
                        res = fut.result()
                    except Exception as exc:
                        res = {
                            "id": str(item.get("task_id") or item.get("id", "")),
                            "question": item.get("task", ""),
                            "task_type": "gbrain",
                            "hard": 0,
                            "soft": 0.0,
                            "fail_reason": f"error: {exc}",
                            "agent_ok": False,
                        }
                    results.append(res)
                    completed += 1
                    if res.get("hard", 0):
                        correct_count += 1
                    acc = correct_count / completed if completed else 0
                    print(
                        f"    [rollout] {completed}/{total} "
                        f"(acc={acc:.3f}) id={res['id']} "
                        f"hard={res.get('hard', '?')}",
                        flush=True,
                    )
                    outf.write(json.dumps(res, ensure_ascii=False) + "\n")
                    outf.flush()
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    return results
