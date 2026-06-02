"""OCR-Vergleichsmetriken für die /api/compare-Antwort.

Drei Gruppen, die die UI als Tabs darstellt:

* Intrinsisch — beschreibende Statistiken pro Engine (Tokens, Zeichen,
  Konfidenz, Latenz). Keine Qualitätsaussage, nur Volumen/Performance.
* Vergleich   — paarweise Maße zwischen beiden Engines (normalisierte
  Levenshtein-Distanzen, Token-Jaccard, Token-Precision/Recall/F1).
  Bewusst NICHT als CER/WER bezeichnet, da diese Begriffe per Definition
  eine Referenz erfordern.
* Referenz    — echte CER/WER, layout-entspannte CER/WER und Token-F1
  gegen vom Nutzer gelieferte Ground-Truth, sofern vorhanden.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from rapidfuzz.distance import Levenshtein

from eval.metrics import cer as _cer_against_reference
from eval.metrics import wer as _wer_against_reference

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_BLANK_LINE_RE = re.compile(r"(?:\r?\n\s*){2,}")
_LINE_RE = re.compile(r"\r?\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text or "")


def _safe_div(numer: float, denom: float) -> float:
    return numer / denom if denom else 0.0


def _norm_levenshtein(a: list[str] | str, b: list[str] | str) -> float:
    """Normalised symmetric edit distance in [0, 1].

    Defined as ``Lev(a,b) / max(len(a), len(b))``. Symmetric — neither
    side is treated as reference. Returned as a fraction (0 = identical,
    1 = completely different) to mirror CER/WER scaling, but explicitly
    NOT called CER/WER since neither side is ground truth.
    """
    if not a and not b:
        return 0.0
    distance = Levenshtein.distance(a, b)
    return distance / max(len(a), len(b))


def _word_tokens_for_distance(text: str) -> list[str]:
    return text.split()


def _char_tokens_for_distance(text: str) -> list[str]:
    return list(text)


def _split_relaxed_blocks(text: str) -> list[str]:
    stripped = (text or "").strip()
    if not stripped:
        return []

    # Prefer explicit document structure first. If the text has no useful
    # block boundaries, fall back to sentence boundaries before treating it as
    # one ordered sequence.
    for pattern in (_BLANK_LINE_RE, _LINE_RE, _SENTENCE_RE):
        blocks = [part.strip() for part in pattern.split(stripped) if part.strip()]
        if len(blocks) > 1:
            return blocks
    return [stripped]


def relaxed_cer(reference_text: str, hypothesis_text: str) -> float:
    """Character error rate after order-independent block matching.

    This is intentionally not standard CER. It first splits both sides into
    visible layout/text blocks, then finds the cheapest one-to-one block
    assignment regardless of order. Moving a whole matched block is therefore
    free, while changed characters, missing blocks, and extra blocks are still
    charged as character edits.
    """
    return _relaxed_edit_rate(reference_text, hypothesis_text, _char_tokens_for_distance)


def relaxed_wer(reference_text: str, hypothesis_text: str) -> float:
    """Word error rate after order-independent block matching.

    This is intentionally not standard WER. It first splits both sides into
    visible layout/text blocks, then finds the cheapest one-to-one block
    assignment regardless of order. Moving a whole matched block is therefore
    free, while changed words, missing blocks, and extra blocks are still
    charged as word edits.
    """
    return _relaxed_edit_rate(reference_text, hypothesis_text, _word_tokens_for_distance)


def _relaxed_edit_rate(
    reference_text: str,
    hypothesis_text: str,
    tokenize_block: Callable[[str], list[str]],
) -> float:
    ref_blocks = [tokenize_block(block) for block in _split_relaxed_blocks(reference_text)]
    hyp_blocks = [tokenize_block(block) for block in _split_relaxed_blocks(hypothesis_text)]
    ref_blocks = [tokens for tokens in ref_blocks if tokens]
    hyp_blocks = [tokens for tokens in hyp_blocks if tokens]
    ref_len = sum(len(tokens) for tokens in ref_blocks)
    hyp_len = sum(len(tokens) for tokens in hyp_blocks)
    if ref_len == 0:
        return 0.0 if hyp_len == 0 else 1.0
    if not hyp_blocks:
        return 1.0

    return _block_assignment_cost(ref_blocks, hyp_blocks, ref_len, hyp_len) / ref_len


def _block_assignment_cost(
    ref_blocks: list[list[str]],
    hyp_blocks: list[list[str]],
    ref_len: int,
    hyp_len: int,
) -> int:
    size = len(ref_blocks) + len(hyp_blocks)
    hyp_count = len(hyp_blocks)
    cost: list[list[int]] = []
    for ref_tokens in ref_blocks:
        row = [Levenshtein.distance(ref_tokens, hyp_tokens) for hyp_tokens in hyp_blocks]
        row.extend([len(ref_tokens)] * len(ref_blocks))
        cost.append(row)
    for _hyp_tokens in hyp_blocks:
        row = [len(other_hyp) for other_hyp in hyp_blocks]
        row.extend([0] * len(ref_blocks))
        # Only the matching dummy row can consume this hypothesis at insertion
        # cost. Other dummy rows get a prohibitively high cost to keep the
        # assignment meaningful while still square.
        high_cost = ref_len + hyp_len + 1
        for idx in range(hyp_count):
            if idx != len(cost) - len(ref_blocks):
                row[idx] = high_cost
        cost.append(row)

    return _hungarian_min_cost(cost, size)


def _hungarian_min_cost(cost: list[list[int]], size: int) -> int:
    """Minimum-cost square assignment for a dense cost matrix."""
    u = [0] * (size + 1)
    v = [0] * (size + 1)
    p = [0] * (size + 1)
    way = [0] * (size + 1)
    for i in range(1, size + 1):
        p[0] = i
        j0 = 0
        minv = [10**18] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = 10**18
            j1 = 0
            for j in range(1, size + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(size + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assignment = [0] * (size + 1)
    for j in range(1, size + 1):
        assignment[p[j]] = j
    return sum(cost[i - 1][assignment[i] - 1] for i in range(1, size + 1))


def _intrinsic(
    *,
    text: str,
    words_per_page: list[list[dict[str, Any]]],
    latency_ms: int | None,
) -> dict[str, Any]:
    flat_words = [w for page in words_per_page for w in page]
    confidences: list[float] = []
    for w in flat_words:
        conf = w.get("confidence")
        if isinstance(conf, (int, float)) and conf > 0:
            confidences.append(float(conf))
    avg_conf = sum(confidences) / len(confidences) if confidences else None
    return {
        "tokens": len(_tokenize(text)),
        "chars": len(text),
        "avg_confidence": avg_conf,
        "latency_ms": latency_ms,
        "word_box_count": len(flat_words),
    }


def _comparison(our_text: str, their_text: str) -> dict[str, Any]:
    our_tokens = _tokenize(our_text)
    their_tokens = _tokenize(their_text)
    our_set = set(our_tokens)
    their_set = set(their_tokens)
    intersection = len(our_set & their_set)
    union = len(our_set | their_set)

    # Treat 'theirs' as the reference side for the asymmetric P/R/F1 view.
    # Precision = how many of our tokens are also in theirs (anti-hallucination).
    # Recall    = how many of their tokens we also produced (coverage).
    precision = _safe_div(intersection, len(our_set))
    recall = _safe_div(intersection, len(their_set))
    f1 = _safe_div(2 * precision * recall, precision + recall)

    return {
        "delta_char": _norm_levenshtein(our_text, their_text),
        "delta_word": _norm_levenshtein(our_tokens, their_tokens),
        "token_jaccard": _safe_div(intersection, union),
        "token_precision": precision,
        "token_recall": recall,
        "token_f1": f1,
        "reference_side": "theirs",
    }


def reference_only(reference_text: str, hypothesis_text: str) -> dict[str, Any]:
    """Reference-vs-hypothesis metrics for a single side.

    Wird genutzt, wenn die Referenz schon vorliegt und nur die Werte gegen
    eigene OCR berechnet werden sollen — ohne separaten Compare-Aufruf
    gegen eine externe Engine.
    """
    return {
        "ours": _reference_side(reference_text, hypothesis_text),
        "char_count": len(reference_text),
        "token_count": len(_tokenize(reference_text)),
    }


def _reference_side(reference_text: str, hypothesis_text: str) -> dict[str, Any]:
    ref_tokens = set(_tokenize(reference_text))
    hyp_tokens = set(_tokenize(hypothesis_text))
    intersection = len(ref_tokens & hyp_tokens)
    precision = _safe_div(intersection, len(hyp_tokens))
    recall = _safe_div(intersection, len(ref_tokens))
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {
        "cer": _cer_against_reference(reference_text, hypothesis_text),
        "relaxed_cer": relaxed_cer(reference_text, hypothesis_text),
        "wer": _wer_against_reference(reference_text, hypothesis_text),
        "relaxed_wer": relaxed_wer(reference_text, hypothesis_text),
        "token_precision": precision,
        "token_recall": recall,
        "token_f1": f1,
    }


def compute(
    *,
    our_text: str,
    our_words_per_page: list[list[dict[str, Any]]],
    our_latency_ms: int | None,
    their_text: str,
    their_words_per_page: list[list[dict[str, Any]]],
    their_latency_ms: int | None,
    reference_text: str | None = None,
) -> dict[str, Any]:
    """Top-level builder consumed by /api/compare and the UI metrics panel."""
    intrinsic = {
        "ours": _intrinsic(
            text=our_text,
            words_per_page=our_words_per_page,
            latency_ms=our_latency_ms,
        ),
        "theirs": _intrinsic(
            text=their_text,
            words_per_page=their_words_per_page,
            latency_ms=their_latency_ms,
        ),
    }
    comparison = _comparison(our_text, their_text)
    reference: dict[str, Any] | None = None
    if reference_text and reference_text.strip():
        reference = {
            "ours": _reference_side(reference_text, our_text),
            "theirs": _reference_side(reference_text, their_text),
            "char_count": len(reference_text),
            "token_count": len(_tokenize(reference_text)),
        }
    return {
        "intrinsic": intrinsic,
        "comparison": comparison,
        "reference": reference,
    }
