#!/usr/bin/env python
"""Materialize OfficeQA split items and referenced Treasury Bulletin docs.

Downloads from the ModelScope mirror (evalscope/officeqa) to bypass the gated
Hugging Face repo:

  1. officeqa_full.csv           -> question/answer payload (246 rows)
  2. manifest uid join           -> data/officeqa_split/{train,val,test}/items.json
  3. referenced *.txt only       -> data/officeqa_docs_official/transformed/

Only the bulletin files referenced by the 246 questions are downloaded
(~1-3 files per question), not the full 697-file corpus.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MS_BASE = "https://www.modelscope.cn/datasets/evalscope/officeqa/resolve/master"
MANIFEST_DIR = PROJECT_ROOT / "data" / "officeqa_id_split"
OUT_SPLIT = PROJECT_ROOT / "data" / "officeqa_split"
DOCS_DIR = PROJECT_ROOT / "data" / "officeqa_docs_official" / "transformed"
SPLITS = ("train", "val", "test")


def fetch(url: str, retries: int = 4, timeout: int = 180) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - retry any transport error
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_exc}") from last_exc


def split_lines(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).splitlines() if part.strip()]


def main() -> int:
    # 1. Official question CSV from the mirror.
    print("downloading officeqa_full.csv ...")
    csv_bytes = fetch(f"{MS_BASE}/officeqa_full.csv")
    rows = {
        r["uid"]: r
        for r in csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
        if r.get("uid")
    }
    print(f"  csv rows: {len(rows)}")

    # 2. Join with the curated manifest, write materialized items.
    all_source_files: set[str] = set()
    for split in SPLITS:
        manifest_path = MANIFEST_DIR / split / "items.json"
        manifest_items = json.loads(manifest_path.read_text(encoding="utf-8"))
        out_items: list[dict] = []
        missing: list[str] = []
        for m in manifest_items:
            uid = str(m.get("uid") or m.get("id") or "").strip()
            row = rows.get(uid)
            if row is None:
                missing.append(uid)
                continue
            source_files = sorted(
                set(split_lines(m.get("source_files")))
                | set(split_lines(row.get("source_files")))
            )
            all_source_files.update(source_files)
            out_items.append({
                "id": uid,
                "uid": uid,
                "question": str(row.get("question") or "").strip(),
                "ground_truth": str(row.get("answer") or "").strip(),
                "category": str(m.get("category") or row.get("difficulty") or "officeqa").strip(),
                "source_files": source_files,
                "source_docs": sorted(
                    set(split_lines(m.get("source_docs")))
                    | set(split_lines(row.get("source_docs")))
                ),
                "split": split,
            })
        if missing:
            print(f"  [{split}] WARNING: {len(missing)} uids missing from CSV: {missing[:5]}")
        out_dir = OUT_SPLIT / split
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "items.json").write_text(
            json.dumps(out_items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  [{split}] materialized {len(out_items)} items -> {out_dir / 'items.json'}")

    # 3. Download only the referenced bulletin txt files.
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    todo = sorted(
        f for f in all_source_files
        if f and not (DOCS_DIR / f).exists()
    )
    print(f"referenced docs: {len(all_source_files)} unique, {len(todo)} to download")
    failed: list[str] = []

    def download(name: str) -> str:
        data = fetch(f"{MS_BASE}/treasury_bulletins_parsed/transformed/{name}")
        (DOCS_DIR / name).write_bytes(data)
        return name

    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(download, name): name for name in todo}
            done = 0
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    fut.result()
                    done += 1
                    if done % 20 == 0 or done == len(todo):
                        print(f"  docs {done}/{len(todo)}")
                except Exception as exc:  # noqa: BLE001
                    failed.append(name)
                    print(f"  FAIL {name}: {exc}")

    present = [f for f in sorted(all_source_files) if (DOCS_DIR / f).exists()]
    total_mb = sum((DOCS_DIR / f).stat().st_size for f in present) / 1e6
    print(f"docs present: {len(present)}/{len(all_source_files)} ({total_mb:.1f} MB)")
    if failed:
        print(f"failed ({len(failed)}): {failed}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
