from __future__ import annotations

from translation_context import (
    MAX_CONTEXT_ITEM_TOKENS,
    MAX_CONTEXT_TOKENS,
    RollingTranslationContext,
    build_translation_context,
    estimate_context_tokens,
    translation_cache_key,
    trim_context_tail,
)


def test_token_estimate_handles_cjk_ascii_and_mixed_text() -> None:
    assert estimate_context_tokens("中文测试") == 4
    assert estimate_context_tokens("abcdefgh") == 2
    assert estimate_context_tokens("中文abcd") == 3
    assert estimate_context_tokens("  hello\n  world  ") == 3


def test_item_trimming_keeps_the_most_recent_tail() -> None:
    text = "开" * 20 + "结尾"
    assert trim_context_tail(text, 4) == "开开结尾"
    assert estimate_context_tokens(trim_context_tail("中" * 700, 500)) <= 500


def test_context_enforces_item_count_and_total_budget() -> None:
    items = [str(index) + ("中" * 499) for index in range(6)]
    context = build_translation_context(items, source="clipboard")

    assert len(context.previous) == 4
    assert not context.previous[0].startswith("0")
    assert context.previous[-1].startswith("5")
    assert all(
        estimate_context_tokens(item) <= MAX_CONTEXT_ITEM_TOKENS
        for item in context.previous
    )
    assert context.token_estimate <= MAX_CONTEXT_TOKENS


def test_current_sentence_shares_budget_and_is_not_duplicated() -> None:
    full_cue = "This is the full current subtitle."
    partial = build_translation_context(
        ["previous cue"],
        current=full_cue,
        source="youtube",
        target_text="current subtitle",
    )
    whole = build_translation_context(
        ["previous cue"],
        current=full_cue,
        source="youtube",
        target_text=full_cue,
    )

    assert partial.current == full_cue
    assert whole.current == ""

    long_cue = "中" * 700
    assert build_translation_context(
        current=long_cue,
        source="youtube",
        target_text=long_cue,
    ).current == ""


def test_rolling_context_expires_and_keeps_five_latest_entries() -> None:
    now = [100.0]
    rolling = RollingTranslationContext(clock=lambda: now[0], idle_seconds=300)
    for index in range(6):
        context = rolling.snapshot_and_record(f"sentence {index}")

    assert context.previous == tuple(f"sentence {i}" for i in range(5))
    next_context = rolling.snapshot_and_record("sentence 6")
    assert next_context.previous == tuple(f"sentence {i}" for i in range(1, 6))

    now[0] += 301
    assert rolling.snapshot_and_record("after idle").is_empty


def test_cache_key_changes_with_context() -> None:
    first = build_translation_context(["bank account"])
    second = build_translation_context(["river bank"])
    assert translation_cache_key("zh", "bank", first) != translation_cache_key(
        "zh", "bank", second
    )


def test_rolling_context_can_be_cleared_manually() -> None:
    rolling = RollingTranslationContext()
    rolling.snapshot_and_record("first")
    rolling.clear()
    assert rolling.snapshot_and_record("second").is_empty
