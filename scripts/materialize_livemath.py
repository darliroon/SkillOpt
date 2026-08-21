"""Materialize LiveMathematicianBench split from ID manifest + raw data."""
import json
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, ".pylibs"))
from skillopt.envs.livemathematicianbench.dataloader import load_items

# 1. Load and normalize raw items
items = load_items("data")
print(f"Loaded {len(items)} normalized items")
print(f"Keys: {list(items[0].keys())}")
raw_items = {it["id"]: it for it in items}

# 2. Materialize each split from ID manifest
src_split = "data/livemathematicianbench_id_split"
dst_split = "data/livemathematicianbench_split"

for split in ["train", "val", "test"]:
    src_path = os.path.join(src_split, split, "items.json")
    dst_dir = os.path.join(dst_split, split)
    os.makedirs(dst_dir, exist_ok=True)

    with open(src_path, encoding="utf-8") as f:
        id_items = json.load(f)

    full_items = []
    for id_item in id_items:
        item_id = id_item["id"]
        if item_id in raw_items:
            full_items.append(raw_items[item_id])
        else:
            print(f"  WARNING: {item_id} not found in raw data!")

    dst_path = os.path.join(dst_dir, "items.json")
    with open(dst_path, "w", encoding="utf-8") as f:
        json.dump(full_items, f, ensure_ascii=False, indent=2)

    print(f"{split}: {len(full_items)} items -> {dst_path}")

print("Done!")
