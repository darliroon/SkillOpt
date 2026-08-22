#!/usr/bin/env python3
"""Standalone SkillProx backward (proximal shrink) runner.

Re-runs the post-training prox shrink phase on an existing skill file
without re-training. Useful to validate gate / tolerance changes against
a previously trained ``best_skill.md``.

Usage
-----
    python scripts/run_prox_standalone.py --config configs/searchqa/default.yaml \
        --skill outputs/searchqa_gpt52opt_prox/best_skill.md \
        --out_root outputs/searchqa_prox_standalone
"""
from __future__ import annotations

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from skillopt.utils.console import force_utf8_stdout_stderr

force_utf8_stdout_stderr()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=str, required=True,
                   help="Path to the environment YAML config")
    p.add_argument("--skill", type=str, required=True,
                   help="Path to the pre-shrink skill file (e.g. best_skill.md)")
    p.add_argument("--out_root", type=str, required=True,
                   help="Output directory for prox_shrink/ artifacts")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    from skillopt.config import load_config, flatten_config, is_structured
    from train import get_adapter  # scripts/train.py registry helper
    from skillopt.model import (
        configure_azure_openai,
        configure_claude_code_exec,
        configure_codex_exec_from_config,
        configure_copilot_chat,
        configure_copilot_exec,
        configure_cursor_exec,
        configure_minimax_chat,
        configure_openai_compatible,
        configure_qwen_chat,
        set_reasoning_effort,
        set_target_backend,
        set_target_deployment,
        set_optimizer_backend,
        set_optimizer_deployment,
    )
    from skillopt.engine.trainer import _resolve_role_backends
    from skillopt.optimizer.prox_shrink import run_prox_shrink

    cfg = load_config(args.config)
    if is_structured(cfg):
        cfg = flatten_config(cfg)
    cfg["out_root"] = args.out_root
    os.makedirs(args.out_root, exist_ok=True)

    with open(args.skill, encoding="utf-8") as f:
        skill = f.read()
    print(f"[prox-standalone] skill: {args.skill} ({len(skill)} chars)")

    # ── Backend / model setup (mirrors trainer.train()) ────────────────
    backend = cfg.get("model_backend", "azure_openai")
    optimizer_backend, target_backend = _resolve_role_backends(
        backend, cfg.get("optimizer_backend"), cfg.get("target_backend")
    )
    cfg["optimizer_backend"] = optimizer_backend
    cfg["target_backend"] = target_backend
    set_optimizer_backend(optimizer_backend)
    set_target_backend(target_backend)
    configure_codex_exec_from_config(cfg)

    adapter = get_adapter(cfg)
    adapter.setup(cfg)
    dataloader = adapter.get_dataloader()

    out_root = cfg["out_root"]

    def _build_eval_env(split: str, env_num: int, seed: int):
        if dataloader is None:
            env_manager = adapter.build_eval_env(
                env_num=env_num,
                split=split,
                seed=seed,
                out_root=out_root,
            )
            actual_n = len(env_manager) if hasattr(env_manager, "__len__") else env_num
            return env_manager, actual_n
        batch = dataloader.build_eval_batch(
            env_num=env_num,
            split=split,
            seed=seed,
            out_root=out_root,
        )
        env_manager = adapter.build_env_from_batch(batch, out_root=out_root)
        return env_manager, batch.batch_size

    configure_azure_openai(
        endpoint=(cfg.get("azure_openai_endpoint") or cfg.get("azure_endpoint") or None),
        api_version=(cfg.get("azure_openai_api_version") or cfg.get("azure_api_version") or None),
        api_key=(cfg.get("azure_openai_api_key") or cfg.get("azure_api_key") or None),
        auth_mode=cfg.get("azure_openai_auth_mode") or None,
        ad_scope=cfg.get("azure_openai_ad_scope") or None,
        managed_identity_client_id=cfg.get("azure_openai_managed_identity_client_id") or None,
        optimizer_endpoint=cfg.get("optimizer_azure_openai_endpoint") or None,
        optimizer_api_version=cfg.get("optimizer_azure_openai_api_version") or None,
        optimizer_api_key=cfg.get("optimizer_azure_openai_api_key") or None,
        optimizer_auth_mode=cfg.get("optimizer_azure_openai_auth_mode") or None,
        optimizer_ad_scope=cfg.get("optimizer_azure_openai_ad_scope") or None,
        optimizer_managed_identity_client_id=(
            cfg.get("optimizer_azure_openai_managed_identity_client_id") or None
        ),
        target_endpoint=cfg.get("target_azure_openai_endpoint") or None,
        target_api_version=cfg.get("target_azure_openai_api_version") or None,
        target_api_key=cfg.get("target_azure_openai_api_key") or None,
        target_auth_mode=cfg.get("target_azure_openai_auth_mode") or None,
        target_ad_scope=cfg.get("target_azure_openai_ad_scope") or None,
        target_managed_identity_client_id=(
            cfg.get("target_azure_openai_managed_identity_client_id") or None
        ),
    )
    set_optimizer_deployment(cfg["optimizer_model"])
    set_target_deployment(cfg["target_model"])
    configure_claude_code_exec(
        path=cfg.get("claude_code_exec_path", "claude"),
        profile=cfg.get("claude_code_exec_profile", ""),
        use_sdk=cfg.get("claude_code_exec_use_sdk", None),
        effort=cfg.get("claude_code_exec_effort", cfg.get("reasoning_effort", "medium")),
        max_thinking_tokens=cfg.get("claude_code_exec_max_thinking_tokens", 16384),
    )
    configure_cursor_exec(
        path=cfg.get("cursor_exec_path") or None,
        sandbox=cfg.get("cursor_exec_sandbox") or None,
    )
    configure_copilot_exec(
        path=cfg.get("copilot_exec_path") or None,
        home=cfg.get("copilot_exec_home") or None,
        allow_all_tools=cfg.get("copilot_exec_allow_all_tools"),
    )
    configure_copilot_chat(
        optimizer_model=cfg.get("copilot_chat_optimizer_model") or None,
        target_model=cfg.get("copilot_chat_target_model") or None,
        timeout=cfg.get("copilot_chat_timeout") or None,
    )
    configure_qwen_chat(
        base_url=cfg.get("qwen_chat_base_url") or None,
        api_key=cfg.get("qwen_chat_api_key") or None,
        temperature=cfg.get("qwen_chat_temperature"),
        timeout_seconds=cfg.get("qwen_chat_timeout_seconds"),
        max_tokens=cfg.get("qwen_chat_max_tokens"),
        enable_thinking=cfg.get("qwen_chat_enable_thinking"),
        optimizer_base_url=cfg.get("optimizer_qwen_chat_base_url") or None,
        optimizer_api_key=cfg.get("optimizer_qwen_chat_api_key") or None,
        optimizer_temperature=cfg.get("optimizer_qwen_chat_temperature"),
        optimizer_timeout_seconds=cfg.get("optimizer_qwen_chat_timeout_seconds"),
        optimizer_max_tokens=cfg.get("optimizer_qwen_chat_max_tokens"),
        optimizer_enable_thinking=cfg.get("optimizer_qwen_chat_enable_thinking"),
        target_base_url=cfg.get("target_qwen_chat_base_url") or None,
        target_api_key=cfg.get("target_qwen_chat_api_key") or None,
        target_temperature=cfg.get("target_qwen_chat_temperature"),
        target_timeout_seconds=cfg.get("target_qwen_chat_timeout_seconds"),
        target_max_tokens=cfg.get("target_qwen_chat_max_tokens"),
        target_enable_thinking=cfg.get("target_qwen_chat_enable_thinking"),
    )
    configure_minimax_chat(
        base_url=cfg.get("minimax_base_url") or None,
        api_key=cfg.get("minimax_api_key") or None,
        temperature=cfg.get("minimax_temperature"),
        max_tokens=cfg.get("minimax_max_tokens"),
        enable_thinking=cfg.get("minimax_enable_thinking"),
    )
    configure_openai_compatible(
        base_url=cfg.get("openai_compatible_base_url") or None,
        api_key=cfg.get("openai_compatible_api_key") or None,
        optimizer_base_url=cfg.get("optimizer_openai_compatible_base_url") or None,
        optimizer_api_key=cfg.get("optimizer_openai_compatible_api_key") or None,
        target_base_url=cfg.get("target_openai_compatible_base_url") or None,
        target_api_key=cfg.get("target_openai_compatible_api_key") or None,
        max_tokens=cfg.get("openai_compatible_max_tokens"),
    )
    minimax_model_cfg = cfg.get("minimax_model")
    if minimax_model_cfg and cfg.get("target_backend") == "minimax_chat":
        set_target_deployment(str(minimax_model_cfg))
    os.environ["REFLACT_CODEX_TRACE_TO_OPTIMIZER"] = (
        "1"
        if target_backend == "codex_exec" and cfg.get("codex_trace_to_optimizer", False)
        else "0"
    )
    set_reasoning_effort(cfg.get("reasoning_effort", "") or None)

    if adapter.requires_ray():
        import ray
        if not ray.is_initialized():
            ray.init(num_gpus=0)

    print(
        f"  [model config] backend={backend}  "
        f"optimizer={cfg['optimizer_model']} ({optimizer_backend})  "
        f"target={cfg['target_model']} ({target_backend})"
    )

    # ── Run the prox shrink phase with trainer-identical parameters ────
    pack_raw = int(cfg.get("prox_sub_pack_chars", -1))
    result = run_prox_shrink(
        skill,
        adapter=adapter,
        build_eval_env=_build_eval_env,
        out_root=out_root,
        seed=int(cfg["seed"]),
        env_num=int(cfg["sel_env_num"]),
        loo_env_num=int(cfg.get("prox_loo_env_num", 0) or 0),
        max_trials=max(1, int(cfg.get("prox_max_trials", 3))),
        hard_tolerance=float(cfg.get("prox_hard_tolerance", -1.0)),
        soft_tolerance=float(cfg.get("prox_soft_tolerance", -1.0)),
        tolerance_scale=max(0.1, float(cfg.get("prox_tolerance_scale", 2.5))),
        max_compression=min(1.0, max(0.0, float(cfg.get("prox_max_compression", 0.10)))),
        max_completion_tokens=int(cfg["optimizer_max_completion_tokens"]),
        adaptive_drill=bool(cfg.get("prox_adaptive_drill", True)),
        noise_gate=float(cfg.get("prox_noise_gate", -1.0)),
        sub_pack_chars=pack_raw if pack_raw < 0 else max(200, pack_raw),
        drill_budget=max(0, int(cfg.get("prox_drill_budget", 6))),
    )

    print(f"\n[prox-standalone] shrunk={result.get('shrunk')}")
    if result.get("shrunk"):
        print(
            f"  chars {result['base_chars']}->{result['final_chars']} "
            f"({result['compression']:.1%} compression)"
        )
        print(
            f"  hard {result['base_hard']:.4f}->{result['final_hard']:.4f}  "
            f"soft {result['base_soft']:.4f}->{result['final_soft']:.4f}"
        )
        print(f"  final skill: {os.path.join(out_root, 'prox_shrink', 'final_skill.md')}")
    print(f"  audit: {os.path.join(out_root, 'prox_shrink', 'audit.json')}")


if __name__ == "__main__":
    main()
