You will be given several failed agent trajectories from one minibatch and the current skill document.

Summarize the lessons from these trajectories into one complete replacement skill document.

When rewriting from a minibatch, use the current trajectories as the primary
evidence for updates. Preserve essential task-format instructions, but avoid mechanically carrying over
stale, redundant, or conflicting rules. Prefer a concise, coherent replacement
skill over a long document with weakly supported guidance.

## Environment Context

The agent runs in a **Codex CLI sandbox**. Key facts:
- There is NO built-in `search` tool. The agent must use **shell commands** (e.g., `curl`, `wget`) to search the web.
- When a judge check requires `tool_called('search')`, the evaluator scans the raw trace for `exec_command` entries containing search-related shell commands like `curl`, `wget`, `grep`, `http`.
- The skill should instruct the agent to **execute shell commands** (e.g., `curl "https://..."`) to perform research — NOT to "call a search tool".
- The workspace contains a `task.md` file with the task description and a `SKILL.md` with the skill instructions.

Do not include task-specific answers, IDs, file paths, gold values, or entity names.
If the skill contains a protected block between <!-- SLOW_UPDATE_START --> and
<!-- SLOW_UPDATE_END -->, keep that block unchanged.

Respond ONLY with a valid JSON object:
{
  "batch_size": <number of trajectories analysed>,
  "failure_summary": [
    {"failure_type": "<type>", "count": <int>, "description": "<one-line>"}
  ],
  "patch": {
    "reasoning": "<brief summary of the rewrite>",
    "skill_candidates": [
      {
        "title": "<short title>",
        "change_summary": ["<short change 1>", "<short change 2>"],
        "new_skill": "<complete rewritten skill document>"
      }
    ]
  }
}

Return exactly one item in "skill_candidates".
