"""gbrain rule-based evaluator.

Each task has a judge with a list of checks. Supported operations:
  - tool_called:   pass if a real tool/function call for the tool is found in the Codex trace
  - regex:         pass if the regex matches the final response
  - section_present: pass if a section header is present in the response
  - contains:      pass if the arg string appears in the response
"""
from __future__ import annotations

import re


def _check_tool_called(arg: str, response: str, raw_trace: str) -> bool:
    """Check if a real tool/function call for *arg* appears in the trace.

    Codex CLI traces contain structured log lines. A real tool call shows as:
      - event.name="codex.tool_call" tool_name=web_search
      - ToolCall: web_search
      - event.name="codex.tool_decision" tool_name=web_search

    For "search" specifically, also checks if exec_command was used to run
    a search-related shell command (curl, grep, find, wget) within the
    SAME event line (not cross-line matching).
    """
    # Pattern 1: Codex structured events with tool_name field
    structured_patterns = [
        rf'tool_name["\s:=]+{re.escape(arg)}\b',
        rf'"name"\s*:\s*"{re.escape(arg)}"',
    ]
    for pat in structured_patterns:
        if re.search(pat, raw_trace, re.IGNORECASE):
            if arg == "search":
                if re.search(rf'tool_name["\s:=]+(?:web_)?{re.escape(arg)}\b', raw_trace, re.IGNORECASE):
                    return True
                if re.search(rf'"name"\s*:\s*"(?:web_)?{re.escape(arg)}"', raw_trace, re.IGNORECASE):
                    return True
            else:
                return True

    # Pattern 2: "ToolCall: <tool_name>" in Codex stream events
    toolcall_pat = rf'ToolCall:\s+(?:web_)?{re.escape(arg)}\b'
    if re.search(toolcall_pat, raw_trace, re.IGNORECASE):
        return True

    # Pattern 3: For "search" specifically, check if exec_command was used
    # to run a search-related command. We check WITHIN the same event line
    # to avoid cross-line false positives.
    if arg == "search":
        # Check each line that has exec_command for search-related commands
        for line in raw_trace.split("\n"):
            if "exec_command" in line and re.search(
                r'(?:curl|wget|grep|find\s|http|browse|search|query)',
                line, re.IGNORECASE
            ):
                return True
        # Also check for explicit web_search tool events
        web_search_patterns = [
            r'tool_name["\s:=]+web_search\b',
            r'"tool_name"\s*:\s*"web_search"',
            r'ToolCall:\s+web_search\b',
            r'event\.name="codex\.tool_call"[^}]*tool_name=web_search',
            r'event\.name="codex\.tool_decision"[^}]*tool_name=web_search',
        ]
        for pat in web_search_patterns:
            if re.search(pat, raw_trace, re.IGNORECASE):
                return True

    return False


def evaluate(judge: dict, response: str, raw_trace: str = "") -> dict:
    """Evaluate a single gbrain task against its rule-based judge.

    Returns dict with: hard (0|1), soft (float), fail_reasons (list[str]).
    """
    checks = judge.get("checks", [])
    if not checks:
        return {"hard": 1, "soft": 1.0, "fail_reasons": []}

    fail_reasons: list[str] = []
    n_pass = 0

    for check in checks:
        op = check.get("op", "")
        arg = check.get("arg", "")
        passed = False

        if op == "tool_called":
            passed = _check_tool_called(arg, response, raw_trace)

        elif op == "regex":
            if re.search(arg, response, re.DOTALL | re.IGNORECASE):
                passed = True

        elif op == "section_present":
            header_patterns = [
                rf"^#+\s*{re.escape(arg)}\s*$",
                rf"^\s*{re.escape(arg)}\s*:?\s*$",
                rf"\b{re.escape(arg)}\b\s*[:\n]",
            ]
            for pat in header_patterns:
                if re.search(pat, response, re.MULTILINE | re.IGNORECASE):
                    passed = True
                    break

        elif op == "contains":
            if arg.lower() in response.lower():
                passed = True

        else:
            passed = True

        if passed:
            n_pass += 1
        else:
            fail_reasons.append(f"{op}({arg!r}) failed")

    hard = 1 if n_pass == len(checks) else 0
    soft = n_pass / len(checks) if checks else 1.0
    return {"hard": hard, "soft": soft, "fail_reasons": fail_reasons}
