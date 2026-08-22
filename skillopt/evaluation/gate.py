"""Validation gate — accept / reject candidate skills.

Analogous to validation-based early stopping and model selection in neural
network training: compares the candidate's score against the current and
best scores, then returns an accept/reject decision.

The trainer owns side-effects (cache lookup, rollout, printing, state
mutation).  This module is the pure decision function.

Metric selection
----------------
Three gate metrics are supported:

* ``"hard"`` (default, backward-compatible):
  Compare candidate vs current/best using *hard* exact-match accuracy.
* ``"soft"``:
  Compare using *soft* per-item score (F1 / partial credit / etc.).
  Use this when a small held-out selection set has too few items for
  hard accuracy to be sensitive to incremental skill improvements.
* ``"mixed"``:
  Compare using a weighted average ``(1 - w) * hard + w * soft``.
  ``w`` is configurable via ``mixed_weight`` (default ``0.5``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


GateAction = Literal["accept_new_best", "accept", "reject"]
GateMetric = Literal["hard", "soft", "mixed"]


@dataclass(frozen=True)
class GateResult:
    """Immutable outcome of the validation gate."""

    action: GateAction
    current_skill: str
    current_score: float
    best_skill: str
    best_score: float
    best_step: int


def compute_semantic_density(
    skill_content: str,
    leading_words: list[str] | None = None,
) -> float:
    """Compute the semantic density of leading words in a skill document."""
    if not skill_content or not skill_content.strip():
        return 0.0
    if leading_words is None:
        leading_words = [
            "MUST", "ALWAYS", "NEVER", "ONLY", "CRITICAL", "IMPORTANT",
            "RESOLVE", "PREFER", "ENSURE", "STRICT", "VERIFY"
        ]
    
    # Strip metadata comments to focus purely on instruction text
    skill = skill_content
    for start, end in [
        ("<!-- SLOW_UPDATE_START -->", "<!-- SLOW_UPDATE_END -->"),
        ("<!-- APPENDIX_START -->", "<!-- APPENDIX_END -->")
    ]:
        while True:
            s_idx = skill.find(start)
            if s_idx == -1:
                break
            e_idx = skill.find(end, s_idx)
            if e_idx == -1:
                skill = skill[:s_idx] + skill[s_idx + len(start):]
                break
            skill = skill[:s_idx] + skill[e_idx + len(end):]

    import re
    words = re.findall(r'[a-zA-Z0-9]+', skill.lower())
    if not words:
        return 0.0
    
    leading_set = {w.lower() for w in leading_words}
    leading_count = sum(1 for w in words if w in leading_set)
    return leading_count / len(words)


def select_gate_score(
    hard: float,
    soft: float,
    metric: GateMetric = "hard",
    mixed_weight: float = 0.5,
    *,
    skill_content: str = "",
    use_semantic_density: bool = False,
    semantic_density_weight: float = 0.05,
    leading_words: list[str] | None = None,
) -> float:
    """Project (hard, soft) onto a single comparison metric.

    Parameters
    ----------
    hard, soft
        Aggregate hard / soft scores from a rollout batch (both 0..1).
    metric
        Which metric to compare on.
    mixed_weight
        For ``"mixed"``: weight given to ``soft``. Must be in ``[0, 1]``.
        Ignored for ``"hard"`` / ``"soft"``.
    skill_content
        The raw skill document content.
    use_semantic_density
        Whether to adjust the score based on semantic density of leading words.
    semantic_density_weight
        Scaling weight for the semantic density bonus.
    leading_words
        Optional custom list of high-influence words to prioritize.
    """
    if metric == "hard":
        score = float(hard)
    elif metric == "soft":
        score = float(soft)
    elif metric == "mixed":
        w = max(0.0, min(1.0, float(mixed_weight)))
        score = (1.0 - w) * float(hard) + w * float(soft)
    else:
        raise ValueError(
            f"unknown gate metric {metric!r}; expected 'hard', 'soft', or 'mixed'"
        )

    if use_semantic_density:
        density = compute_semantic_density(skill_content, leading_words)
        score += float(semantic_density_weight) * density

    return score


def evaluate_gate(
    candidate_skill: str,
    cand_hard: float,
    current_skill: str,
    current_score: float,
    best_skill: str,
    best_score: float,
    best_step: int,
    global_step: int,
    *,
    cand_soft: float = 0.0,
    metric: GateMetric = "hard",
    mixed_weight: float = 0.5,
    use_semantic_density: bool = False,
    semantic_density_weight: float = 0.05,
    leading_words: list[str] | None = None,
) -> GateResult:
    """Pure gate decision: compare candidate score to current/best.

    Parameters
    ----------
    candidate_skill
        The candidate skill content being evaluated.
    cand_hard, cand_soft
        Aggregate hard / soft scores of the candidate on the selection set.
    current_skill, current_score
        The currently-active skill and its *metric-space* score.
    best_skill, best_score, best_step
        The best-so-far skill, its *metric-space* score, and the step
        at which it was accepted.
    global_step
        Current global training step (recorded if a new best is accepted).
    cand_soft
        Soft score of the candidate; only consulted when ``metric != "hard"``.
        Defaults to ``0.0`` for backward compatibility with callers that
        previously passed only ``cand_hard``.
    metric
        Which metric to compare on. Defaults to ``"hard"`` to preserve
        the original gate behavior.
    mixed_weight
        Weight on ``soft`` when ``metric == "mixed"``.
    use_semantic_density
        Whether to adjust the score based on semantic density of leading words.
    semantic_density_weight
        Scaling weight for the semantic density bonus.
    leading_words
        Optional custom list of high-influence words to prioritize.

    Returns
    -------
    GateResult
        Updated state; the caller decides what to do with it (print,
        mutate trainer state, log, etc.).
    """
    cand_score = select_gate_score(
        cand_hard,
        cand_soft,
        metric,
        mixed_weight,
        skill_content=candidate_skill,
        use_semantic_density=use_semantic_density,
        semantic_density_weight=semantic_density_weight,
        leading_words=leading_words,
    )

    if cand_score > current_score:
        if cand_score > best_score:
            return GateResult(
                action="accept_new_best",
                current_skill=candidate_skill,
                current_score=cand_score,
                best_skill=candidate_skill,
                best_score=cand_score,
                best_step=global_step,
            )
        return GateResult(
            action="accept",
            current_skill=candidate_skill,
            current_score=cand_score,
            best_skill=best_skill,
            best_score=best_score,
            best_step=best_step,
        )
    return GateResult(
        action="reject",
        current_skill=current_skill,
        current_score=current_score,
        best_skill=best_skill,
        best_score=best_score,
        best_step=best_step,
    )


def auto_tolerances(results: list, scale: float) -> tuple[float, float]:
    """Estimate comparison tolerances from the sampling noise of a rollout.

    Used by both the prox Gate 3 (validation floor) and the train gate to
    make tolerances dataset-agnostic.  The comparison is between two scores
    measured on the SAME n items (paired).  A conservative upper bound for
    the score-difference stddev is the sum of the two single-measurement
    variances (exact when independent, shrinks with positive correlation):

        σ_diff_hard = sqrt(2·p(1−p)/n)     p = mean per-item hard (Bernoulli)
        σ_diff_soft = sqrt(2·s²/m)         s² = per-item soft sample variance

    ``tolerance = scale × σ_diff`` ⇒ a zero-degradation candidate is
    noise-rejected with probability ≈ Φ(−scale) one-sided (1.5 → ~6.7%,
    2.5 → ~0.6%).  The floor adapts automatically to sample size and task
    difficulty, so switching datasets needs no manual re-tuning.
    """
    n = len(results)
    if n == 0:
        return 0.0, 0.0

    def _h(r: object) -> float:
        return float(r.hard if hasattr(r, "hard") else r.get("hard", 0))

    def _s(r: object) -> float | None:
        v = r.soft if hasattr(r, "soft") else r.get("soft")
        return None if v is None else float(v)

    hards = [_h(r) for r in results]
    p = sum(hards) / n
    sigma_hard = (2.0 * max(p * (1.0 - p), 0.0) / n) ** 0.5

    softs = [s for s in (_s(r) for r in results) if s is not None]
    if len(softs) > 1:
        m = len(softs)
        mu = sum(softs) / m
        s2 = sum((x - mu) ** 2 for x in softs) / (m - 1)
        sigma_soft = (2.0 * s2 / m) ** 0.5
    else:
        sigma_soft = sigma_hard
    return scale * sigma_hard, scale * sigma_soft


def auto_train_gate_tolerances(
    results: list, scale: float, metric: str, mixed_weight: float = 0.5
) -> dict:
    """Auto ``train_gate_pass`` kwargs from the step-① rollout noise.

    Returns the exact kwargs to splat into :func:`train_gate_pass`:
    ``hard``/``soft`` map their σ-based tolerance onto the compared metric,
    ``and`` measures both legs independently, and ``mixed`` derives the σ
    of the weighted per-item composite ``(1−w)·hard + w·soft``.
    """
    h_tol, s_tol = auto_tolerances(results, scale)
    if metric == "hard":
        return {"hard_tolerance": h_tol}
    if metric == "soft":
        return {"soft_tolerance": s_tol}
    if metric == "and":
        return {"hard_tolerance": h_tol, "soft_tolerance": s_tol}
    # mixed: σ of the weighted per-item composite (items missing soft are
    # dropped so the composite is well-defined).
    w = min(1.0, max(0.0, float(mixed_weight)))

    def _pair(r: object) -> tuple[float, float] | None:
        h = float(r.hard if hasattr(r, "hard") else r.get("hard", 0))
        v = r.soft if hasattr(r, "soft") else r.get("soft")
        return None if v is None else (h, float(v))

    pairs = [p for p in (_pair(r) for r in results) if p is not None]
    n = len(pairs)
    if n < 2:
        return {"hard_tolerance": h_tol}
    comp = [(1.0 - w) * h + w * s for h, s in pairs]
    mu = sum(comp) / n
    s2 = sum((x - mu) ** 2 for x in comp) / (n - 1)
    return {"tolerance": scale * (2.0 * s2 / n) ** 0.5}


def train_gate_pass(
    cand_hard: float,
    cand_soft: float,
    cur_hard: float,
    cur_soft: float,
    *,
    metric: str = "hard",
    mixed_weight: float = 0.5,
    tolerance: float = 0.0,
    hard_tolerance: float | None = None,
    soft_tolerance: float | None = None,
) -> tuple[bool, str]:
    """SkillProx-style forward closed-loop gate (re-execution on train batch).

    Compares the candidate skill's re-execution scores on the *same training
    batch* against the current skill's rollout scores from phase ①.  Both
    metrics (projected onto ``metric``) must not drop by more than
    ``tolerance``.

    Unlike :func:`evaluate_gate` (which uses strict > for model selection on
    the selection split), this gate is a *correctness check*: equality passes,
    because a candidate that holds the same train performance while fixing
    diagnosed failures is still a valid forward step.

    Parameters
    ----------
    cand_hard, cand_soft
        Aggregate hard / soft scores of the candidate on the training batch.
    cur_hard, cur_soft
        Aggregate hard / soft scores of the current skill on the same batch
        (recorded during phase ① ROLLOUT).
    metric
        Which metric to compare on: ``hard`` / ``soft`` / ``mixed`` project
        both scores onto one number; ``"and"`` (SkillProx paper-faithful)
        requires **both** hard AND soft to hold the floor independently.
    mixed_weight
        Weight on ``soft`` when ``metric == "mixed"``.
    tolerance
        Allowed drop on the compared metric(s) (absorbs LLM sampling noise).
        Default 0.0 = strict.  For ``"and"`` the same tolerance applies to
        both metrics.
    hard_tolerance, soft_tolerance
        Per-metric overrides for auto mode (``scale × σ_diff`` measured from
        the step-① rollout).  When given they take precedence over
        ``tolerance`` on their respective leg: ``hard`` for the hard metric /
        hard leg of ``"and"``, ``soft`` for the soft leg.

    Returns
    -------
    (passed, reason)
        ``passed`` is True when the candidate passes.  ``reason`` is a short
        human-readable explanation for logging / retry feedback.
    """
    if metric == "and":
        hard_tol = max(0.0, float(tolerance)) if hard_tolerance is None else max(0.0, hard_tolerance)
        soft_tol = max(0.0, float(tolerance)) if soft_tolerance is None else max(0.0, soft_tolerance)
        hard_ok = cand_hard >= cur_hard - hard_tol
        soft_ok = cand_soft >= cur_soft - soft_tol
        detail = (
            f"(hard {cur_hard:.4f}->{cand_hard:.4f}, soft {cur_soft:.4f}->{cand_soft:.4f})"
        )
        if hard_ok and soft_ok:
            return True, (
                f"pass both metrics >= floor - tol hard {hard_tol:.4f}/soft {soft_tol:.4f} {detail}"
            )
        failed = "hard" if not hard_ok else "soft"
        if not hard_ok and not soft_ok:
            failed = "hard AND soft"
        return False, (
            f"fail {failed} below floor - tol hard {hard_tol:.4f}/soft {soft_tol:.4f} {detail}"
        )

    cand_score = select_gate_score(cand_hard, cand_soft, metric, mixed_weight)  # type: ignore[arg-type]
    cur_score = select_gate_score(cur_hard, cur_soft, metric, mixed_weight)
    if metric == "hard" and hard_tolerance is not None:
        tol = max(0.0, hard_tolerance)
    elif metric == "soft" and soft_tolerance is not None:
        tol = max(0.0, soft_tolerance)
    else:
        tol = max(0.0, float(tolerance))

    if cand_score >= cur_score - tol:
        return True, (
            f"pass {cand_score:.4f} >= {cur_score:.4f} - tol {tol:.4f} "
            f"(hard {cur_hard:.4f}->{cand_hard:.4f}, soft {cur_soft:.4f}->{cand_soft:.4f})"
        )
    return False, (
        f"fail {cand_score:.4f} < {cur_score:.4f} - tol {tol:.4f} "
        f"(hard {cur_hard:.4f}->{cand_hard:.4f}, soft {cur_soft:.4f}->{cand_soft:.4f})"
    )


# ── SkillProx Backward: unit decomposition + Prox trial gate ────────────────
#
# Pure helpers for the post-training proximal (shrink) step.  The trainer /
# prox_shrink orchestrator owns side-effects (rollouts, LLM calls, IO).

# Mechanism-managed blocks that must survive any shrink trial untouched.
_PROTECTED_MARKER_PAIRS: list[tuple[str, str]] = [
    ("<!-- SLOW_UPDATE_START -->", "<!-- SLOW_UPDATE_END -->"),
    ("<!-- APPENDIX_START -->", "<!-- APPENDIX_END -->"),
]

_PLACEHOLDER_RE = re.compile(r"<!-- __PROX_SPAN_(\d+)__ -->")


def _extract_protected_spans(skill: str) -> tuple[str, list[str]]:
    """Replace protected mechanism blocks with one-line placeholders.

    Returns ``(body, spans)`` where *body* carries ``<!-- __PROX_SPAN_i__ -->``
    placeholders and *spans* holds the original block texts (markers
    included) in document order.
    """
    body = skill
    spans: list[str] = []
    for start_marker, end_marker in _PROTECTED_MARKER_PAIRS:
        while True:
            s_idx = body.find(start_marker)
            if s_idx == -1:
                break
            e_idx = body.find(end_marker, s_idx)
            if e_idx == -1:
                # Orphan start marker: the marker alone is the span.
                span = start_marker
                rest_from = s_idx + len(start_marker)
            else:
                span = body[s_idx:e_idx + len(end_marker)]
                rest_from = e_idx + len(end_marker)
            spans.append(span)
            body = (
                body[:s_idx]
                + f"<!-- __PROX_SPAN_{len(spans) - 1}__ -->"
                + body[rest_from:]
            )
    return body, spans


def _restore_protected_spans(body: str, spans: list[str]) -> str:
    for i, span in enumerate(spans):
        body = body.replace(f"<!-- __PROX_SPAN_{i}__ -->", span)
    return body


def _pull_placeholders(text: str, anchor: int, anchors: list[tuple[int, str]]) -> str:
    """Remove every placeholder from *text*, recording (anchor, placeholder).

    The blank lines immediately before a placeholder are stripped along with
    it; rebuild re-inserts ``\n\n{placeholder}`` after the anchored segment.
    """
    while True:
        m = _PLACEHOLDER_RE.search(text)
        if not m:
            return text
        anchors.append((anchor, m.group(0)))
        text = text[:m.start()].rstrip("\n") + text[m.end():]


def decompose_skill_units(skill: str, drilldown_chars: int = 3000) -> dict:
    """Decompose a skill into shrinkable units (L2/L3 in SkillProx).

    Sections are split on ``##`` headers.  A ``##`` section longer than
    *drilldown_chars* that contains ``###`` subsections is drilled down: its
    header block (the ``##`` line plus any intro text before the first
    ``###``) becomes a *fixed* unit that is always kept on rebuild, and each
    ``###`` subsection becomes an independently removable unit.  This keeps
    the leave-one-out audit resolution meaningful when a single ``##``
    section has grown to thousands of characters.

    The preamble before the first ``##`` header and any protected mechanism
    block (slow-update guidance, appendix notes) are excluded from the
    shrinkable set — they are re-attached verbatim on rebuild.  Placeholders
    for protected blocks are anchored to the segment (preamble or unit) they
    followed, so deleting a unit never deletes a protected block: an anchor
    whose unit is dropped re-attaches after the next surviving unit (or at
    the end).

    Returns
    -------
    ``{"preamble": str, "units": [{"id", "header", "content", "char_len",
    "fixed"}], "protected_spans": [str],
    "placeholder_anchors": [(anchor, placeholder)]}``
    with anchor ``-1`` = after the preamble, else after that unit id.
    """
    body, spans = _extract_protected_spans(skill)
    parts = re.split(r"\n(?=## )", body)
    anchors: list[tuple[int, str]] = []
    preamble = _pull_placeholders(parts[0], -1, anchors)
    units: list[dict] = []

    def _add_unit(text: str, fixed: bool) -> None:
        text = text.strip()
        if not text:
            return
        units.append({
            "id": len(units),
            "header": text.splitlines()[0].strip(),
            "content": text,
            "char_len": len(text),
            "fixed": fixed,
        })

    for part in parts[1:]:
        if not part.strip():
            continue
        # Drill down an oversized ## section into its ### subsections.
        subparts = (
            re.split(r"\n(?=### )", part)
            if drilldown_chars > 0 and len(part.strip()) > drilldown_chars
            else None
        )
        if subparts and len(subparts) > 1:
            # subparts[0] always holds at least the "## " header line.
            _add_unit(_pull_placeholders(subparts[0], len(units), anchors), fixed=True)
            for sub in subparts[1:]:
                _add_unit(_pull_placeholders(sub, len(units), anchors), fixed=False)
        else:
            _add_unit(_pull_placeholders(part, len(units), anchors), fixed=False)
    return {
        "preamble": preamble.strip(),
        "units": units,
        "protected_spans": spans,
        "placeholder_anchors": anchors,
    }


def rebuild_skill(decomp: dict, unit_replacements: dict[int, str | None] | None = None) -> str:
    """Rebuild the skill text from a decomposition.

    ``unit_replacements`` maps unit id → new unit text (``None`` drops the
    unit).  Protected spans are re-attached verbatim after their anchored
    segment; when that segment was dropped they move to the next surviving
    unit (or the end), never disappearing.
    """
    replacements = unit_replacements or {}
    segments: list[tuple[str, int]] = []  # (text, anchor)
    if decomp["preamble"]:
        segments.append((decomp["preamble"], -1))
    for unit in decomp["units"]:
        # Fixed units (drilled-down section header blocks) are kept verbatim.
        if unit.get("fixed"):
            segments.append((unit["content"], unit["id"]))
            continue
        # NOTE: membership check, not .get() — an explicit None value means
        # "drop this unit" and must not be confused with "not replaced".
        if unit["id"] not in replacements:
            segments.append((unit["content"], unit["id"]))
            continue
        repl = replacements[unit["id"]]
        if repl is None or not str(repl).strip():
            continue  # dropped
        segments.append((str(repl).strip(), unit["id"]))

    # Insert each placeholder after its anchored segment; when the anchor is
    # absent (dropped unit), defer to the next surviving segment, else the end.
    pending: list[str] = []
    chunks: list[str] = []
    anchor_to_idx = {anchor: i for i, (_t, anchor) in enumerate(segments)}
    for anchor, placeholder in decomp.get("placeholder_anchors", []):
        idx = anchor_to_idx.get(anchor)
        if idx is None:
            pending.append(placeholder)
            continue
        seg_text, seg_anchor = segments[idx]
        segments[idx] = (seg_text + "\n\n" + placeholder, seg_anchor)
    if pending:
        if segments:
            last_text, last_anchor = segments[-1]
            segments[-1] = (last_text + "\n\n" + "\n\n".join(pending), last_anchor)
        else:
            segments.append(("\n\n".join(pending), -1))

    chunks = [text for text, _anchor in segments if text]
    body = "\n\n".join(chunks)
    if body and not body.endswith("\n"):
        body += "\n"
    return _restore_protected_spans(body, decomp["protected_spans"])


def skill_without_unit(skill: str, unit_content: str) -> str | None:
    """Rebuild *skill* with the unit matching *unit_content* removed.

    Returns ``None`` when no unit matches (comparison ignores trailing
    whitespace, e.g. when the caller reconstructed the content text).
    """
    decomp = decompose_skill_units(skill)
    target = unit_content.strip()
    for unit in decomp["units"]:
        if unit.get("fixed"):
            continue  # section header blocks are never removable units
        if unit["content"] == target:
            return rebuild_skill(decomp, {unit["id"]: None})
    return None


def replace_skill_unit(skill: str, unit_content: str, new_content: str) -> str | None:
    """Rebuild *skill* with the unit matching *unit_content* replaced.

    Returns ``None`` when no unit matches (comparison ignores trailing
    whitespace).
    """
    decomp = decompose_skill_units(skill)
    target = unit_content.strip()
    for unit in decomp["units"]:
        if unit.get("fixed"):
            continue  # section header blocks are not replaceable units
        if unit["content"] == target:
            return rebuild_skill(decomp, {unit["id"]: new_content})
    return None


def drill_unit_into_subs(unit_content: str, pack_chars: int = 800) -> list[str]:
    """Split a unit's body into paragraph-block sub-units for adaptive drilldown.

    The unit's header line (line 0) is never part of any sub-unit — it stays
    in the skill whenever a single block is removed.  Paragraphs (blank-line
    separated) are greedily packed into consecutive blocks of at least
    *pack_chars* characters; a short trailing remainder is merged into the
    previous block.  Returns ``[]`` when the body yields fewer than two
    blocks (nothing worth drilling).
    """
    lines = unit_content.splitlines()
    if not lines:
        return []
    body = "\n".join(lines[1:])
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paras:
        return []

    blocks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for para in paras:
        cur.append(para)
        cur_len += len(para) + 2
        if cur_len >= pack_chars:
            blocks.append("\n\n".join(cur))
            cur, cur_len = [], 0
    if cur:
        if blocks and cur_len < pack_chars:
            blocks[-1] = blocks[-1] + "\n\n" + "\n\n".join(cur)
        else:
            blocks.append("\n\n".join(cur))
    return blocks if len(blocks) >= 2 else []


def _sub_span_in(unit_body: str, sub: str) -> tuple[int, int] | None:
    """Locate a drilled sub-block inside its parent unit, whitespace-tolerant.

    ``drill_unit_into_subs`` strips paragraphs before packing, so the block's
    internal ``"\\n\\n"`` boundaries may correspond to ``" \\n\\n"`` (trailing
    spaces) in the original text — a plain substring test fails.  This joins
    the block's paragraphs with a blank-line pattern that tolerates
    surrounding spaces/tabs instead.
    """
    paras = [p for p in re.split(r"\n\s*\n", sub) if p.strip()]
    if not paras:
        return None
    pat = r"[ \t]*\n[ \t]*\n[ \t]*".join(re.escape(p) for p in paras)
    m = re.search(pat, unit_body)
    return (m.start(), m.end()) if m else None


def skill_without_subunit(
    skill: str, unit_content: str, sub_content: str
) -> str | None:
    """Rebuild *skill* with one drilled sub-block removed from its parent unit.

    Equivalent to ``replace_skill_unit(skill, unit_content,
    unit_content.replace(sub_content, ""))`` but with whitespace collapse so
    the ablated parent stays well-formed.  Returns ``None`` when the parent
    unit or the sub-block cannot be located.
    """
    decomp = decompose_skill_units(skill)
    target = unit_content.strip()
    sub = sub_content.strip()
    for unit in decomp["units"]:
        if unit.get("fixed"):
            continue
        if unit["content"] != target:
            continue
        span = _sub_span_in(target, sub)
        if span is None:
            return None
        start, end = span
        new_unit = re.sub(r"\n{3,}", "\n\n", target[:start] + target[end:]).strip()
        return rebuild_skill(decomp, {unit["id"]: new_unit})
    return None


def prox_trial_pass(
    trial_skill: str,
    prev_skill: str,
    *,
    trial_hard: float,
    trial_soft: float,
    base_hard: float,
    base_soft: float,
    hard_tolerance: float = 0.0,
    soft_tolerance: float = 0.02,
    max_compression: float = 0.10,
    base_chars: int = 0,
) -> tuple[bool, str]:
    """SkillProx backward triple gate for one shrink trial.

    Gate 1 — structure: trial is non-empty, keeps at least one ``##`` section
    when the previous skill had any, and preserves every protected marker.
    Gate 2 — strict shrink: strictly fewer characters than *prev_skill*, and
    cumulative compression (vs ``base_chars``) stays within ``max_compression``
    (soft cap, see below).
    Gate 3 — validation floor: hard and soft must not drop beyond their
    tolerances vs the *pre-shrink baseline* (not the evolving skill), so
    accepted trials cannot drift below the forward-phase result.

    The compression cap implements the paper's "累计压缩率软上限" as a *soft*
    cap: exceeding it does not auto-reject. Over-compression is allowed only
    with positive evidence — the trial must strictly beat the pre-shrink
    baseline on at least one metric (hard or soft); the floors themselves are
    still enforced by Gate 3. Rationale: when the LOO audit proves a unit is
    negative-utility, deleting it may legitimately compress far beyond the
    conservative cap. Rejection still terminates the phase, preserving
    single-pass finite termination.

    Returns ``(passed, reason)``.
    """
    # Gate 1: structure ────────────────────────────────────────────────
    if not trial_skill.strip():
        return False, "structure: empty skill"
    prev_sections = len(re.findall(r"(?m)^## ", prev_skill))
    trial_sections = len(re.findall(r"(?m)^## ", trial_skill))
    if prev_sections > 0 and trial_sections == 0:
        return False, "structure: all ## sections removed"
    for pair in _PROTECTED_MARKER_PAIRS:
        for marker in pair:
            if trial_skill.count(marker) != prev_skill.count(marker):
                return False, (
                    f"structure: protected marker count changed for {marker}"
                )

    # Gate 2: strict shrink + cumulative compression cap ───────────────
    if len(trial_skill) >= len(prev_skill):
        return False, (
            f"shrink: not strictly smaller ({len(prev_skill)} -> {len(trial_skill)} chars)"
        )
    ref_chars = base_chars if base_chars > 0 else len(prev_skill)
    compression = (ref_chars - len(trial_skill)) / max(ref_chars, 1)
    cap_escaped = False
    if compression > max_compression + 1e-9:
        # Soft cap: over-compression needs positive evidence — strictly beat
        # the pre-shrink baseline on at least one metric (floors are checked
        # by Gate 3 below).
        if trial_hard > base_hard + 1e-9 or trial_soft > base_soft + 1e-9:
            cap_escaped = True
        else:
            return False, (
                f"compression {compression:.3f} > cap {max_compression:.3f} "
                f"without score improvement (hard {base_hard:.4f}->{trial_hard:.4f}, "
                f"soft {base_soft:.4f}->{trial_soft:.4f})"
            )

    # Gate 3: validation floor vs pre-shrink baseline ──────────────────
    if trial_hard < base_hard - hard_tolerance - 1e-9:
        return False, (
            f"val hard {base_hard:.4f}->{trial_hard:.4f} drops beyond tol {hard_tolerance:.4f}"
        )
    if trial_soft < base_soft - soft_tolerance - 1e-9:
        return False, (
            f"val soft {base_soft:.4f}->{trial_soft:.4f} drops beyond tol {soft_tolerance:.4f}"
        )
    escape_note = (
        f" [soft-cap escape: compression {compression:.3f} > cap "
        f"{max_compression:.3f}, score improved]"
        if cap_escaped
        else ""
    )
    return True, (
        f"pass (chars {len(prev_skill)}->{len(trial_skill)}, compression "
        f"{compression:.3f}, hard {base_hard:.4f}->{trial_hard:.4f}, "
        f"soft {base_soft:.4f}->{trial_soft:.4f}){escape_note}"
    )
