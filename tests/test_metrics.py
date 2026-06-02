from __future__ import annotations

from app.services.compare_metrics import reference_only
from eval.metrics import wer


def test_wer_is_order_sensitive_for_moved_words() -> None:
    assert wer("alpha beta gamma delta", "gamma delta alpha beta") == 1.0


def test_token_f1_is_order_insensitive_for_moved_words() -> None:
    metrics = reference_only("alpha beta gamma delta", "gamma delta alpha beta")["ours"]

    assert metrics["wer"] == 1.0
    assert metrics["token_f1"] == 1.0


def test_relaxed_wer_tolerates_moved_blocks() -> None:
    metrics = reference_only("alpha beta\ngamma delta", "gamma delta\nalpha beta")["ours"]

    assert metrics["wer"] == 1.0
    assert metrics["relaxed_cer"] == 0.0
    assert metrics["relaxed_wer"] == 0.0


def test_relaxed_cer_penalizes_character_errors_inside_matched_blocks() -> None:
    metrics = reference_only("alpha beta\ngamma delta", "gamma de1ta\nalpha beta")["ours"]
    ref_chars_without_separators = len("alpha beta") + len("gamma delta")

    assert metrics["relaxed_cer"] == 1 / ref_chars_without_separators


def test_relaxed_wer_penalizes_missing_blocks() -> None:
    metrics = reference_only("alpha beta\ngamma delta", "alpha beta")["ours"]
    ref_chars_without_separators = len("alpha beta") + len("gamma delta")

    assert metrics["relaxed_cer"] == len("gamma delta") / ref_chars_without_separators
    assert metrics["relaxed_wer"] == 0.5
