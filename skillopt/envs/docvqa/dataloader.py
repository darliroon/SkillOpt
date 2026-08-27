from __future__ import annotations

import csv
import re
from pathlib import Path

from skillopt.datasets.base import SplitDataLoader

# Match quoted strings (single or double, with escaped quotes inside) inside brackets
_QUOTED_STR_RE = re.compile(
    r"""(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""
)


def _parse_answers(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    # DocVQA CSV answers are in numpy array repr format: ['ans1' 'ans2'] or ["a" "b"]
    # where elements are space-separated (no commas). ast.literal_eval would silently
    # concatenate adjacent string literals ('a' 'b' -> 'ab'), so we extract quoted strings directly.
    if text.startswith("[") and text.endswith("]"):
        matches = _QUOTED_STR_RE.findall(text)
        if matches:
            answers = []
            for m in matches:
                quote = m[0]
                inner = m[1:-1]
                inner = inner.replace("\\" + quote, quote).replace("\\\\", "\\")
                inner = inner.strip()
                if inner:
                    answers.append(inner)
            if answers:
                return answers
    # Fallback: plain string without brackets
    return [text]


def _extract_document_path(question: str) -> tuple[str, str]:
    marker = "document_path:"
    if marker not in question:
        return question.strip(), ""
    main, tail = question.split(marker, 1)
    return main.strip(), tail.strip()


def _normalize_row(row: dict[str, str]) -> dict:
    question_text, document_path = _extract_document_path(str(row.get("question") or ""))
    answers = _parse_answers(row.get("answer") or row.get("ground_truth") or "")
    image_path = str(row.get("image_path") or document_path or "").strip()
    task_type = str(row.get("topic") or row.get("category") or "docvqa").strip() or "docvqa"
    return {
        "id": str(row.get("questionId") or row.get("id") or "").strip(),
        "question": question_text,
        "answer": answers[0] if answers else "",
        "answers": answers,
        "task_type": task_type,
        "subtask": task_type,
        "image_paths": [image_path] if image_path else [],
        "image_path": image_path,
        "questionId": str(row.get("questionId") or "").strip(),
        "docId": str(row.get("docId") or "").strip(),
        "ucsf_document_id": str(row.get("ucsf_document_id") or "").strip(),
        "ucsf_document_page_no": str(row.get("ucsf_document_page_no") or "").strip(),
        "source_split": str(row.get("source_split") or "").strip(),
    }


class DocVQADataLoader(SplitDataLoader):
    def load_split_items(self, split_path: str) -> list[dict]:
        path = Path(split_path)
        csv_files = sorted(path.glob("*.csv"))
        if not csv_files:
            raise FileNotFoundError(f"No .csv file found in {split_path}")
        with csv_files[0].open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            return [_normalize_row(row) for row in reader]
