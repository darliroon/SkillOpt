"""gbrain dataloader — loads gbrain-evals JSONL task files."""
from __future__ import annotations

import json
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader


def _load_jsonl(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


class GbrainDataLoader(SplitDataLoader):
    """gbrain dataloader.

    Expects split_dir with train/, val/, test/ subdirectories.
    Each subdirectory contains an items.json file (written by SplitDataLoader
    during ratio materialization, or manually created for split_dir mode).
    """

    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        json_files = sorted(path.glob("*.json"))
        if json_files:
            with json_files[0].open(encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                return payload
        jsonl_files = sorted(path.glob("*.jsonl"))
        if jsonl_files:
            return _load_jsonl(str(jsonl_files[0]))
        raise FileNotFoundError(
            f"No .json or .jsonl file found in {split_path}"
        )

    def load_raw_items(self, data_path: str) -> list[dict]:
        return _load_jsonl(data_path)
