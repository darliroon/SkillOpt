"""SkillOpt Web Dashboard - FastAPI backend.

Run:
    cd SkillOpt
    python -m uvicorn web.app:app --host 0.0.0.0 --port 7860
    # then open http://localhost:7860
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# -- Paths --

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIGS_DIR = PROJECT_ROOT / "configs"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
LOGS_DIR = PROJECT_ROOT / "logs"
ENVS_DIR = PROJECT_ROOT / "skillopt" / "envs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

# -- App --

app = FastAPI(title="SkillOpt Dashboard", version="0.1.0")


# ===========================================================================
#  Dataset Management
# ===========================================================================

@app.get("/api/datasets")
async def list_datasets():
    """List all datasets under data/."""
    datasets = []
    if not DATA_DIR.exists():
        return {"datasets": []}
    for d in sorted(DATA_DIR.iterdir()):
        if not d.is_dir():
            continue
        splits = {}
        total = 0
        for split in ("train", "val", "test"):
            sp = d / split
            if sp.exists():
                items_file = sp / "items.json"
                if items_file.exists():
                    try:
                        with items_file.open(encoding="utf-8") as f:
                            items = json.load(f)
                        count = len(items) if isinstance(items, list) else 0
                        splits[split] = count
                        total += count
                    except Exception:
                        splits[split] = 0
        manifest = d / "split_manifest.json"
        manifest_info = {}
        if manifest.exists():
            try:
                manifest_info = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                pass
        datasets.append({
            "name": d.name,
            "splits": splits,
            "total": total,
            "has_manifest": manifest.exists(),
            "manifest": manifest_info,
        })
    return {"datasets": datasets}


@app.post("/api/datasets/upload")
async def upload_dataset(file: UploadFile = File(...), dataset_name: str = ""):
    """Upload a JSON file and create a dataset directory under data/."""
    if not dataset_name:
        dataset_name = Path(file.filename or "uploaded").stem
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", dataset_name)
    if not safe_name.endswith("_split"):
        safe_name = safe_name + "_split"

    target_dir = DATA_DIR / safe_name
    target_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    text = content.decode("utf-8", errors="replace")

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(400, "File is not valid JSON")

    if not isinstance(items, list):
        raise HTTPException(400, "Expected a JSON array of items")

    n = len(items)
    train_end = int(n * 0.8)
    val_end = int(n * 0.9)
    splits = {
        "train": items[:train_end],
        "val": items[train_end:val_end],
        "test": items[val_end:],
    }

    for split_name, split_items in splits.items():
        sp = target_dir / split_name
        sp.mkdir(parents=True, exist_ok=True)
        (sp / "items.json").write_text(
            json.dumps(split_items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    manifest = {
        "source_file": file.filename,
        "total_items": n,
        "splits": {k: len(v) for k, v in splits.items()},
        "split_ratio": "80:10:10",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (target_dir / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"status": "ok", "dataset": safe_name, "manifest": manifest}


@app.get("/api/datasets/{name}/items")
async def get_dataset_items(name: str, split: str = "train", limit: int = 20):
    """Preview items from a dataset split."""
    ds_dir = DATA_DIR / name
    items_file = ds_dir / split / "items.json"
    if not items_file.exists():
        raise HTTPException(404, f"Split {split} not found")
    with items_file.open(encoding="utf-8") as f:
        items = json.load(f)
    return {"total": len(items), "items": items[:limit]}


# ===========================================================================
#  Config Management
# ===========================================================================

@app.get("/api/configs")
async def list_configs():
    """List all available config files."""
    configs = []
    if not CONFIGS_DIR.exists():
        return {"configs": []}
    for d in sorted(CONFIGS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            for f in d.glob("*.yaml"):
                configs.append({
                    "name": d.name,
                    "file": f.name,
                    "path": str(f.relative_to(PROJECT_ROOT)),
                })
    return {"configs": configs}


@app.get("/api/configs/{name}")
async def get_config(name: str, file: str = "default.yaml"):
    """Get a config file as parsed YAML."""
    cfg_path = CONFIGS_DIR / name / file
    if not cfg_path.exists():
        raise HTTPException(404, f"Config {name}/{file} not found")
    text = cfg_path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(text)
    except Exception as e:
        parsed = {"_parse_error": str(e)}
    base_config = {}
    base_match = re.search(r"_base_:\s*(.+)", text)
    if base_match:
        base_path = (CONFIGS_DIR / name / base_match.group(1).strip()).resolve()
        if base_path.exists():
            try:
                base_config = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
    return {
        "name": name,
        "file": file,
        "raw": text,
        "parsed": parsed,
        "base_config": base_config,
        "path": str(cfg_path.relative_to(PROJECT_ROOT)),
    }


@app.put("/api/configs/{name}")
async def save_config(name: str, file: str = "default.yaml", body: dict = None):
    """Save a config file."""
    if body is None:
        raise HTTPException(400, "Missing body")
    cfg_path = CONFIGS_DIR / name / file
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    text = body.get("raw", "")
    cfg_path.write_text(text, encoding="utf-8")
    return {"status": "ok", "path": str(cfg_path.relative_to(PROJECT_ROOT))}


@app.get("/api/base-config")
async def get_base_config():
    """Get the base default config."""
    base_path = CONFIGS_DIR / "_base_" / "default.yaml"
    if not base_path.exists():
        raise HTTPException(404, "Base config not found")
    text = base_path.read_text(encoding="utf-8")
    return {"raw": text, "parsed": yaml.safe_load(text) or {}}


# ===========================================================================
#  Envs (environment adapters) CRUD
# ===========================================================================

@app.get("/api/envs")
async def list_envs():
    """List all environment directories under skillopt/envs."""
    envs = []
    if not ENVS_DIR.exists():
        return {"envs": []}
    skip = {"_template", "__pycache__"}
    for d in sorted(ENVS_DIR.iterdir()):
        if not d.is_dir() or d.name in skip or d.name.startswith("__"):
            continue
        files = []
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix == ".py":
                files.append(f.name)
        reg_status = _check_registration(d.name)
        envs.append({
            "name": d.name,
            "py_files": files,
            "has_prompts": (d / "prompts").exists(),
            "has_skills": (d / "skills").exists(),
            "registered_train": reg_status.get("train", False),
            "registered_eval": reg_status.get("eval", False),
        })
    return {"envs": envs}


@app.get("/api/envs/{name}")
async def browse_env(name: str):
    """Browse all files in an env directory (recursive tree)."""
    env_dir = ENVS_DIR / name
    if not env_dir.exists():
        raise HTTPException(404, "Env not found: " + name)

    def build_tree(path, rel=""):
        node = {"name": path.name, "path": rel, "type": "dir" if path.is_dir() else "file"}
        if path.is_dir():
            children = []
            for child in sorted(path.iterdir()):
                if child.name == "__pycache__":
                    continue
                child_rel = (rel + "/" + child.name) if rel else child.name
                children.append(build_tree(child, child_rel))
            node["children"] = children
            node["type"] = "dir"
        else:
            node["size"] = path.stat().st_size
            node["type"] = "file"
        return node

    tree = build_tree(env_dir)
    reg = _check_registration(name)
    return {"name": name, "tree": tree, "registration": reg}


@app.get("/api/envs/{name}/file")
async def read_env_file(name: str, path: str = ""):
    """Read a file from an env directory."""
    file_path = ENVS_DIR / name / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "File not found: " + path)
    content = file_path.read_text(encoding="utf-8", errors="replace")
    return {
        "name": name,
        "path": path,
        "content": content,
        "size": file_path.stat().st_size,
    }


@app.put("/api/envs/{name}/file")
async def save_env_file(name: str, path: str = "", body: dict = None):
    """Save a file in an env directory."""
    if body is None:
        raise HTTPException(400, "Missing body")
    file_path = ENVS_DIR / name / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.get("content", ""), encoding="utf-8")
    return {"status": "ok", "path": path}


@app.post("/api/envs/{name}/create")
async def create_env(name: str, body: dict = None):
    """Create a new env directory from template, plus config and registration."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "", name)
    if not safe:
        raise HTTPException(400, "Invalid env name")

    env_dir = ENVS_DIR / safe
    if env_dir.exists():
        raise HTTPException(409, "Env already exists: " + safe)

    template_dir = ENVS_DIR / "_template"
    if not template_dir.exists():
        raise HTTPException(500, "Template directory not found")

    env_dir.mkdir(parents=True)
    (env_dir / "__init__.py").write_text("", encoding="utf-8")

    parts = safe.split("_")
    class_name = "".join(p.capitalize() for p in parts) if parts else safe

    # adapter.py
    adapter_text = (template_dir / "env_template.py").read_text(encoding="utf-8")
    adapter_text = adapter_text.replace("TemplateBenchmarkEnv", class_name + "Adapter")
    adapter_text = adapter_text.replace("TemplateBenchmarkLoader", class_name + "Loader")
    adapter_text = adapter_text.replace("_template.loader_template", safe + ".dataloader")
    adapter_text = adapter_text.replace("template", safe)
    (env_dir / "adapter.py").write_text(adapter_text, encoding="utf-8")

    # dataloader.py
    loader_text = (template_dir / "loader_template.py").read_text(encoding="utf-8")
    loader_text = loader_text.replace("TemplateBenchmarkLoader", class_name + "Loader")
    loader_text = loader_text.replace("template", safe)
    (env_dir / "dataloader.py").write_text(loader_text, encoding="utf-8")

    # rollout.py
    rollout_lines = [
        '"""Rollout helper for ' + safe + '."""',
        "from __future__ import annotations",
        "import json, os",
        "from pathlib import Path",
        "",
        "",
        "def _score(prediction, ground_truth):",
        "    p = (prediction or '').strip().lower()",
        "    g = (ground_truth or '').strip().lower()",
        "    hard = int(p == g and bool(g))",
        "    soft = 1.0 if hard else 0.0",
        "    return hard, soft",
        "",
        "",
        "def run_batch(*, items, skill_content, out_root,",
        "              workers=4, max_completion_tokens=4096):",
        '    """Run a batch of episodes. TODO: implement your real rollout."""',
        "    os.makedirs(out_root, exist_ok=True)",
        '    prediction_dir = Path(out_root, "predictions")',
        "    results = []",
        "    for item in items:",
        "        # TODO: replace with real model call + scoring",
        "        prediction = ''",
        '        hard, soft = _score(prediction, item.get("ground_truth", ""))',
        '        task_dir = prediction_dir / str(item.get("id", ""))',
        "        task_dir.mkdir(parents=True, exist_ok=True)",
        "        conversation = [",
        '            {"role": "system", "content": skill_content},',
        '            {"role": "user", "content": item.get("question", "")},',
        '            {"role": "assistant", "content": prediction},',
        "        ]",
        '        (task_dir / "conversation.json").write_text(',
        "            json.dumps(conversation, ensure_ascii=False, indent=2), encoding='utf-8')",
        "        results.append({",
        '            "id": str(item.get("id", "")),',
        '            "hard": hard,',
        '            "soft": soft,',
        '            "predicted_answer": prediction,',
        '            "question": item.get("question", ""),',
        '            "task_type": item.get("task_type", "' + safe + '"),',
        "        })",
        '    Path(out_root, "rollouts.json").write_text(',
        "        json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')",
        "    return results",
    ]
    (env_dir / "rollout.py").write_text("\n".join(rollout_lines), encoding="utf-8")

    # prompts
    prompts_dir = env_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "analyst_error.md").write_text(
        "# Error Reflection Prompt\n\nAnalyze the failed rollout and propose a skill patch.\n",
        encoding="utf-8")
    (prompts_dir / "analyst_success.md").write_text(
        "# Success Reflection Prompt\n\nAnalyze the successful rollout and extract reusable patterns.\n",
        encoding="utf-8")
    (prompts_dir / "rollout_system.md").write_text(
        "# Rollout System Prompt\n\nYou are a helpful assistant.\n",
        encoding="utf-8")

    # skills
    skills_dir = env_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "initial.md").write_text(
        "# " + safe + " Initial Skill\n\nTODO: Write your initial skill here.\n",
        encoding="utf-8")

    # config
    cfg_dir = CONFIGS_DIR / safe
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_text = (template_dir / "config_template.yaml").read_text(encoding="utf-8")
    cfg_text = cfg_text.replace("your_benchmark", safe)
    (cfg_dir / "default.yaml").write_text(cfg_text, encoding="utf-8")

    # register
    _register_in_scripts(safe, class_name)

    return {"status": "ok", "env": safe, "class_name": class_name + "Adapter"}


@app.delete("/api/envs/{name}")
async def delete_env(name: str, delete_config: bool = True, delete_data: bool = False):
    """Delete an env directory. Optionally delete config and data."""
    env_dir = ENVS_DIR / name
    if not env_dir.exists():
        raise HTTPException(404, "Env not found: " + name)
    if name in ("_template", "__pycache__"):
        raise HTTPException(403, "Cannot delete protected directory")

    _unregister_from_scripts(name)
    shutil.rmtree(env_dir)

    if delete_config:
        cfg_dir = CONFIGS_DIR / name
        if cfg_dir.exists():
            shutil.rmtree(cfg_dir)

    if delete_data:
        for ds_name in (name + "_split", name + "_id_split", name):
            ds_dir = DATA_DIR / ds_name
            if ds_dir.exists():
                shutil.rmtree(ds_dir)
                break

    return {"status": "ok", "deleted": name}


@app.post("/api/envs/{name}/register")
async def register_env(name: str):
    """Register an env in scripts/train.py and scripts/eval_only.py."""
    adapter_file = ENVS_DIR / name / "adapter.py"
    if not adapter_file.exists():
        raise HTTPException(404, "adapter.py not found")
    text = adapter_file.read_text(encoding="utf-8")
    m = re.search(r"class\s+(\w+Adapter)\b", text)
    if not m:
        raise HTTPException(500, "Could not find adapter class")
    class_name = m.group(1)
    _register_in_scripts(name, class_name)
    return {"status": "ok", "registered": name, "class": class_name}


def _check_registration(env_name):
    """Check if an env is registered in train.py and eval_only.py."""
    result = {"train": False, "eval": False}
    for script_name, key in [("train.py", "train"), ("eval_only.py", "eval")]:
        script_path = SCRIPTS_DIR / script_name
        if script_path.exists():
            text = script_path.read_text(encoding="utf-8")
            if ('"' + env_name + '"') in text or ("'" + env_name + "'") in text:
                result[key] = True
    return result


def _register_in_scripts(env_name, class_name):
    """Add lazy registration blocks to scripts/train.py and eval_only.py."""
    import_block = (
        '\n    try:\n'
        '        from skillopt.envs.' + env_name + '.adapter import ' + class_name + '\n'
        '        _ENV_REGISTRY["' + env_name + '"] = ' + class_name + '\n'
        '    except ImportError:\n'
        '        pass\n'
    )
    for script_name in ("train.py", "eval_only.py"):
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            continue
        text = script_path.read_text(encoding="utf-8")
        if ('"' + env_name + '"') in text:
            continue
        marker = "def get_adapter("
        if marker not in text:
            marker = "def parse_args("
        if marker in text:
            idx = text.index(marker)
            text = text[:idx] + import_block + "\n" + text[idx:]
            script_path.write_text(text, encoding="utf-8")


def _unregister_from_scripts(env_name):
    """Remove registration blocks from scripts."""
    for script_name in ("train.py", "eval_only.py"):
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            continue
        text = script_path.read_text(encoding="utf-8")
        pattern = (
            r'\n\s*try:\n'
            r'\s*from skillopt\.envs\.' + re.escape(env_name) + r'\.\w+ import \w+\n'
            r'\s*_ENV_REGISTRY\["' + re.escape(env_name) + r'"\] = \w+\n'
            r'\s*except ImportError:\n'
            r'\s*pass\n'
        )
        text = re.sub(pattern, "", text)
        script_path.write_text(text, encoding="utf-8")


# ===========================================================================
#  Training Runs (offline / history)
# ===========================================================================

@app.get("/api/runs")
async def list_runs():
    """List all training runs under outputs/."""
    runs = []
    if not OUTPUTS_DIR.exists():
        return {"runs": []}
    for d in sorted(OUTPUTS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        run_info = {"name": d.name, "path": str(d.relative_to(PROJECT_ROOT))}
        cfg_file = d / "config.json"
        if cfg_file.exists():
            try:
                run_info["config"] = json.loads(cfg_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        state_file = d / "runtime_state.json"
        if state_file.exists():
            try:
                run_info["state"] = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        hist_file = d / "history.json"
        if hist_file.exists():
            try:
                hist = json.loads(hist_file.read_text(encoding="utf-8"))
                run_info["num_steps"] = len(hist)
                if hist:
                    last = hist[-1]
                    run_info["last_step"] = last.get("step")
                    run_info["last_action"] = last.get("action")
                    run_info["best_score"] = last.get("best_score")
                    run_info["current_score"] = last.get("current_score")
            except Exception:
                pass
        skills_dir = d / "skills"
        if skills_dir.exists():
            run_info["num_skills"] = len(list(skills_dir.glob("skill_v*.md")))
        summary_file = d / "summary.json"
        if summary_file.exists():
            try:
                run_info["summary"] = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        runs.append(run_info)
    return {"runs": runs}


@app.get("/api/runs/{name}")
async def get_run_detail(name: str):
    """Get detailed info for a specific run."""
    run_dir = OUTPUTS_DIR / name
    if not run_dir.exists():
        raise HTTPException(404, "Run not found: " + name)

    result = {"name": name}
    cfg_file = run_dir / "config.json"
    if cfg_file.exists():
        result["config"] = json.loads(cfg_file.read_text(encoding="utf-8"))
    hist_file = run_dir / "history.json"
    if hist_file.exists():
        result["history"] = json.loads(hist_file.read_text(encoding="utf-8"))
    state_file = run_dir / "runtime_state.json"
    if state_file.exists():
        result["state"] = json.loads(state_file.read_text(encoding="utf-8"))

    skills_dir = run_dir / "skills"
    skills = []
    if skills_dir.exists():
        for f in sorted(skills_dir.glob("skill_v*.md")):
            skills.append({
                "version": f.stem.replace("skill_v", ""),
                "filename": f.name,
                "size": f.stat().st_size,
            })
    result["skills"] = skills
    result["has_best_skill"] = (run_dir / "best_skill.md").exists()

    steps_dir = run_dir / "steps"
    steps = []
    if steps_dir.exists():
        for sd in sorted(steps_dir.iterdir()):
            if sd.is_dir():
                sr = sd / "step_record.json"
                if sr.exists():
                    try:
                        steps.append(json.loads(sr.read_text(encoding="utf-8")))
                    except Exception:
                        pass
    result["steps"] = steps

    tao_file = run_dir / "tao.md"
    if tao_file.exists():
        result["tao"] = tao_file.read_text(encoding="utf-8")

    return result


@app.get("/api/runs/{name}/skill/{version}")
async def get_skill_content(name: str, version: str):
    """Get skill content for a specific version."""
    run_dir = OUTPUTS_DIR / name
    if version == "best":
        skill_file = run_dir / "best_skill.md"
    else:
        skill_file = run_dir / "skills" / ("skill_v%04d.md" % int(version))
    if not skill_file.exists():
        raise HTTPException(404, "Skill not found")
    return {"content": skill_file.read_text(encoding="utf-8"), "filename": skill_file.name}


@app.get("/api/runs/{name}/step/{step_num}")
async def get_step_detail(name: str, step_num: int):
    """Get full step detail: step_record + patches + merged_patch + ranked_edits + edit_apply_report + rollouts."""
    run_dir = OUTPUTS_DIR / name
    step_dir = run_dir / "steps" / ("step_%04d" % step_num)
    sr = step_dir / "step_record.json"
    if not sr.exists():
        raise HTTPException(404, "Step not found")

    result = json.loads(sr.read_text(encoding="utf-8"))

    # individual patches
    patches_dir = step_dir / "patches"
    patches_list = []
    if patches_dir.exists():
        for pf in sorted(patches_dir.iterdir()):
            if pf.suffix == ".json":
                try:
                    patch_data = json.loads(pf.read_text(encoding="utf-8"))
                    patch_data["_filename"] = pf.name
                    patches_list.append(patch_data)
                except Exception:
                    pass
    result["patches_detail"] = patches_list

    # merged patch
    merged_file = step_dir / "merged_patch.json"
    if merged_file.exists():
        try:
            result["merged_patch_detail"] = json.loads(merged_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ranked edits
    ranked_file = step_dir / "ranked_edits.json"
    if ranked_file.exists():
        try:
            result["ranked_edits_detail"] = json.loads(ranked_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # edit apply report
    report_file = step_dir / "edit_apply_report.json"
    if report_file.exists():
        try:
            result["edit_apply_report"] = json.loads(report_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # candidate skill
    candidate_file = step_dir / "candidate_skill.md"
    if candidate_file.exists():
        result["candidate_skill"] = candidate_file.read_text(encoding="utf-8")

    # rollout predictions summary
    rollout_dir = step_dir / "rollout"
    rollouts_file = rollout_dir / "rollouts.json" if rollout_dir.exists() else None
    if rollouts_file and rollouts_file.exists():
        try:
            result["rollouts"] = json.loads(rollouts_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return result


@app.get("/api/runs/latest")
async def get_latest_run():
    """Find the most recently modified run directory."""
    if not OUTPUTS_DIR.exists():
        raise HTTPException(404, "No runs found")
    latest = None
    latest_mtime = 0
    for d in OUTPUTS_DIR.iterdir():
        if d.is_dir():
            mtime = d.stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest = d.name
    if not latest:
        raise HTTPException(404, "No runs found")
    return {"name": latest, "modified": latest_mtime}


@app.get("/api/runs/{name}/summary")
async def get_run_summary(name: str):
    """Get summary.json with all 4-phase results (baseline/best/final/prox test scores)."""
    run_dir = OUTPUTS_DIR / name
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        raise HTTPException(404, "summary.json not found")
    return json.loads(summary_file.read_text(encoding="utf-8"))


@app.get("/api/runs/{name}/gepa")
async def get_gepa_phase(name: str):
    """Get GEPA phase data: audit, iterations, candidates, pareto."""
    run_dir = OUTPUTS_DIR / name
    gepa_dir = run_dir / "gepa_phase"
    if not gepa_dir.exists():
        raise HTTPException(404, "GEPA phase not found")

    result = {"performed": False}

    # audit
    audit_file = gepa_dir / "gepa_audit.json"
    if audit_file.exists():
        result["audit"] = json.loads(audit_file.read_text(encoding="utf-8"))
        result["performed"] = result["audit"].get("performed", True)

    # best skill
    best_file = gepa_dir / "gepa_best_skill.md"
    if best_file.exists():
        result["best_skill"] = best_file.read_text(encoding="utf-8")

    # run log
    run_log_file = gepa_dir / "run_log.json"
    if run_log_file.exists():
        try:
            result["run_log"] = json.loads(run_log_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # candidates
    candidates_file = gepa_dir / "candidates.json"
    if candidates_file.exists():
        try:
            result["candidates"] = json.loads(candidates_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # pareto
    pareto_file = gepa_dir / "pareto" / "instance_front.json"
    if pareto_file.exists():
        try:
            result["pareto"] = json.loads(pareto_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # iterations
    iters_dir = gepa_dir / "iterations"
    if iters_dir.exists():
        iterations = []
        for d in sorted(iters_dir.iterdir()):
            if d.is_dir():
                meta_file = d / "meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        meta["iter_dir"] = d.name
                        # check for skill.txt
                        skill_file = d / "components" / "skill.txt"
                        if skill_file.exists():
                            meta["has_skill"] = True
                        iterations.append(meta)
                    except Exception:
                        pass
        result["iterations"] = iterations

    return result


@app.get("/api/runs/{name}/prox")
async def get_prox_shrink(name: str):
    """Get Prox shrink phase data: audit, LOO results, trial skills."""
    run_dir = OUTPUTS_DIR / name
    prox_dir = run_dir / "prox_shrink"
    if not prox_dir.exists():
        raise HTTPException(404, "Prox shrink not found")

    result = {}

    # audit
    audit_file = prox_dir / "audit.json"
    if audit_file.exists():
        result = json.loads(audit_file.read_text(encoding="utf-8"))

    # preshrink skill
    preshrink_file = prox_dir / "preshrink_skill.md"
    if preshrink_file.exists():
        result["preshrink_skill"] = preshrink_file.read_text(encoding="utf-8")

    # final skill
    final_file = prox_dir / "final_skill.md"
    if final_file.exists():
        result["final_skill"] = final_file.read_text(encoding="utf-8")

    # trial files
    trials = []
    for f in sorted(prox_dir.iterdir()):
        if f.name.startswith("trial_") and f.suffix == ".md":
            trials.append({"filename": f.name, "content": f.read_text(encoding="utf-8")})
    result["trials"] = trials

    # LOO results - find all loo_* dirs with results.jsonl
    loo_dirs = []
    for d in sorted(prox_dir.iterdir()):
        if d.is_dir() and d.name.startswith("loo_"):
            results_file = d / "results.jsonl"
            if results_file.exists():
                try:
                    lines = results_file.read_text(encoding="utf-8").strip().split("\n")
                    loo_results = [json.loads(l) for l in lines if l.strip()]
                    loo_dirs.append({"name": d.name, "results": loo_results})
                except Exception:
                    loo_dirs.append({"name": d.name, "results": []})
    result["loo_results"] = loo_dirs

    # test eval summary
    test_summary_file = prox_dir / "test_eval" / "summary.json"
    if test_summary_file.exists():
        try:
            result["test_summary"] = json.loads(test_summary_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return result


@app.get("/api/runs/{name}/test")
async def get_test_eval(name: str):
    """Get test evaluation results for all 4 skill variants."""
    run_dir = OUTPUTS_DIR / name
    result = {}

    for variant, dirname in [
        ("baseline", "test_eval_baseline"),
        ("best", "test_eval"),
        ("final", "test_eval_final"),
        ("prox", "prox_shrink/test_eval"),
    ]:
        eval_dir = run_dir / dirname
        if not eval_dir.exists():
            continue
        summary_file = eval_dir / "summary.json"
        if summary_file.exists():
            try:
                result[variant] = json.loads(summary_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        else:
            # try eval_summary.json
            alt_file = eval_dir / "eval_summary.json"
            if alt_file.exists():
                try:
                    result[variant] = json.loads(alt_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

    return result


# ===========================================================================
#  Log Files
# ===========================================================================

@app.get("/api/logs")
async def list_logs():
    """List all log files."""
    logs = []
    if not LOGS_DIR.exists():
        return {"logs": []}
    for f in sorted(LOGS_DIR.iterdir(), reverse=True):
        if f.is_file() and f.suffix in (".log", ".txt"):
            logs.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
            })
    return {"logs": logs}


@app.get("/api/logs/{filename}")
async def get_log(filename: str, tail: int = 0):
    """Get log file content. If tail > 0, only return last N lines."""
    log_file = LOGS_DIR / filename
    if not log_file.exists():
        raise HTTPException(404, "Log not found")
    text = log_file.read_text(encoding="utf-8", errors="replace")
    if tail > 0:
        lines = text.splitlines()
        text = "\n".join(lines[-tail:])
    return {"filename": filename, "content": text}


# ===========================================================================
#  Training (live)
# ===========================================================================

_running_procs = {}


@app.post("/api/train/start")
async def start_training(body: dict):
    """Start a training run in a subprocess."""
    config_path = body.get("config_path", "")
    if not config_path:
        raise HTTPException(400, "config_path is required")

    full_path = PROJECT_ROOT / config_path
    if not full_path.exists():
        raise HTTPException(404, "Config file not found: " + config_path)

    run_id = "live_" + str(int(time.time()))
    python_exe = sys.executable
    train_script = PROJECT_ROOT / "scripts" / "train.py"
    cmd = [python_exe, str(train_script), "--config", str(full_path)]

    overrides = body.get("overrides", {})
    for key, val in overrides.items():
        if val is not None and val != "":
            cmd.extend(["--cfg-options", key + "=" + str(val)])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        _running_procs[run_id] = proc
    except Exception as e:
        raise HTTPException(500, "Failed to start training: " + str(e))

    return {"run_id": run_id, "pid": proc.pid, "command": " ".join(cmd)}


@app.post("/api/train/stop/{run_id}")
async def stop_training(run_id: str):
    """Stop a running training process."""
    proc = _running_procs.get(run_id)
    if proc is None:
        raise HTTPException(404, "Run not found or already stopped")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    _running_procs.pop(run_id, None)
    return {"status": "stopped", "run_id": run_id}


@app.get("/api/train/status")
async def training_status():
    """Check which trainings are running."""
    status = {}
    for rid, proc in _running_procs.items():
        status[rid] = {"pid": proc.pid, "running": proc.poll() is None}
    finished = [rid for rid, p in _running_procs.items() if p.poll() is not None]
    for rid in finished:
        status[rid]["running"] = False
        status[rid]["returncode"] = _running_procs[rid].returncode
    return {"status": status}


@app.websocket("/ws/train/{run_id}")
async def ws_train_stream(websocket: WebSocket, run_id: str):
    """WebSocket: stream training stdout in real-time."""
    await websocket.accept()
    proc = _running_procs.get(run_id)
    if proc is None:
        await websocket.send_text(json.dumps({"type": "error", "msg": "Run not found"}))
        await websocket.close()
        return

    try:
        loop = asyncio.get_event_loop()

        def read_line():
            return proc.stdout.readline() if proc.stdout else None

        while True:
            line = await loop.run_in_executor(None, read_line)
            if not line:
                if proc.poll() is not None:
                    remaining = proc.stdout.read() if proc.stdout else ""
                    if remaining:
                        for rem_line in remaining.splitlines():
                            await websocket.send_text(json.dumps({"type": "log", "line": rem_line}))
                    await websocket.send_text(json.dumps({"type": "end", "returncode": proc.returncode}))
                    _running_procs.pop(run_id, None)
                    break
                await asyncio.sleep(0.1)
                continue

            await websocket.send_text(json.dumps({"type": "log", "line": line.rstrip()}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error", "msg": str(e), "trace": traceback.format_exc()
        }))
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ===========================================================================
#  Analysis helpers
# ===========================================================================

@app.get("/api/runs/{name}/timeline")
async def get_run_timeline(name: str):
    """Extract a timeline of key events from history.json for charting."""
    run_dir = OUTPUTS_DIR / name
    hist_file = run_dir / "history.json"
    if not hist_file.exists():
        raise HTTPException(404, "history.json not found")

    history = json.loads(hist_file.read_text(encoding="utf-8"))

    steps_data = []
    token_data = []
    timing_data = []
    actions = []
    cumulative_tokens = {"prompt": 0, "completion": 0}

    for entry in history:
        step = entry.get("step", 0)
        steps_data.append({
            "step": step,
            "epoch": entry.get("epoch"),
            "rollout_hard": entry.get("rollout_hard"),
            "rollout_soft": entry.get("rollout_soft"),
            "selection_hard": entry.get("selection_hard"),
            "selection_soft": entry.get("selection_soft"),
            "best_score": entry.get("best_score"),
            "current_score": entry.get("current_score"),
            "action": entry.get("action"),
        })

        tokens = entry.get("tokens", {})
        step_prompt = 0
        step_completion = 0
        for phase in ("analyst", "merge", "rollout"):
            ph = tokens.get(phase, {})
            step_prompt += ph.get("prompt_tokens", 0)
            step_completion += ph.get("completion_tokens", 0)
        cumulative_tokens["prompt"] += step_prompt
        cumulative_tokens["completion"] += step_completion
        token_data.append({
            "step": step,
            "prompt": step_prompt,
            "completion": step_completion,
            "cumulative_prompt": cumulative_tokens["prompt"],
            "cumulative_completion": cumulative_tokens["completion"],
            "total": step_prompt + step_completion,
        })

        timing = entry.get("timing", {})
        wall = entry.get("wall_time_s", 0)
        timing_data.append({
            "step": step,
            "rollout_s": timing.get("rollout_s", 0),
            "reflect_s": timing.get("reflect_s", 0),
            "aggregate_s": timing.get("aggregate_s", 0),
            "gate_s": timing.get("train_gate_s", 0),
            "evaluate_s": timing.get("evaluate_s", 0),
            "wall_s": wall,
        })

        gate = entry.get("train_gate", {})
        attempts = gate.get("attempts", []) if gate else []
        action_text = entry.get("action", "")
        patches = {
            "n_patches": entry.get("n_patches", 0),
            "n_failure": entry.get("n_failure_patches", 0),
            "n_success": entry.get("n_success_patches", 0),
            "n_edits_merged": entry.get("n_edits_merged", 0),
            "n_edits_ranked": entry.get("n_edits_ranked", 0),
        }
        gate_info = None
        if attempts:
            gate_info = {
                "enabled": gate.get("enabled", False),
                "attempts": [
                    {
                        "attempt": a.get("attempt"),
                        "train_hard": a.get("train_hard"),
                        "passed": a.get("passed"),
                        "reason": a.get("reason"),
                    }
                    for a in attempts
                ],
            }
        actions.append({
            "step": step,
            "action": action_text,
            "patches": patches,
            "gate": gate_info,
        })

    return {
        "steps": steps_data,
        "tokens": token_data,
        "timing": timing_data,
        "actions": actions,
        "num_steps": len(history),
    }


# ===========================================================================
#  Static frontend
# ===========================================================================

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>SkillOpt Dashboard</h1><p>Frontend not found.</p>", 404)


def main():
    """Run the server."""
    import uvicorn
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=7860,
        reload=False,
        cwd=str(PROJECT_ROOT),
    )


if __name__ == "__main__":
    main()
