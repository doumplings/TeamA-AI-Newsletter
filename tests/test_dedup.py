"""Deduplicator (UC-11). UT-09 to UT-12 from Report 2, using the worked examples of Section 6.3.3."""
from datetime import datetime, timedelta, timezone

from collector.dedup import Deduplicator, same_story, share_of_words, title_words

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
A = "OpenAI releases GPT-6, its most capable model"


def test_title_words_drop_filler_and_keep_model_names_whole():
    assert title_words(A) == {"openai", "releases", "gpt-6", "capable", "model"}


def test_ut09_same_announcement_worded_two_ways_is_the_same_story():
    b = "OpenAI launches GPT-6 model"
    assert share_of_words(title_words(A), title_words(b)) == 3 / 6
    assert same_story(A, NOW, b, NOW)


def test_ut10_two_companies_releases_are_different_stories():
    b = "Google releases Gemini 4 model"
    assert share_of_words(title_words(A), title_words(b)) == 2 / 8
    assert not same_story(A, NOW, b, NOW)


def test_ut11_three_days_apart_is_the_same_story_and_four_is_not():
    assert same_story(A, NOW, A, NOW + timedelta(days=3))
    assert not same_story(A, NOW, A, NOW + timedelta(days=4))


def test_ut12_the_candidate_with_the_highest_share_wins(factory, make):
    first, second, mine = make.source("Site A"), make.source("Site B"), make.source("Site C")
    make.item(first, "Acme launches Nova model today", published_at=NOW)                        # share 0.5
    best = make.item(second, "Acme launches Nova model for developers worldwide", published_at=NOW)  # share 5/7
    with factory() as db:
        dedup = Deduplicator(db)
        found = dedup.find_original("Acme launches Nova model for developers", NOW + timedelta(hours=2), mine)
        assert found == best
        assert dedup.find_original("Completely unrelated robotics paper", NOW, mine) is None


def test_a_tie_goes_to_the_earliest_and_the_same_source_is_never_compared(factory, make):
    first, second, mine = make.source("Site A"), make.source("Site B"), make.source("Site C")
    later = make.item(first, "Acme launches Nova model", published_at=NOW + timedelta(hours=1))
    earlier = make.item(second, "Acme launches Nova model", published_at=NOW)
    with factory() as db:
        dedup = Deduplicator(db)
        assert dedup.find_original("Acme launches Nova model", NOW + timedelta(hours=3), mine) == earlier
        # A site's own posts often share most title words without being repeats.
        assert dedup.find_original("Acme launches Nova model", NOW + timedelta(hours=3), second) == later
        assert dedup.find_original("Acme launches Nova model", NOW + timedelta(days=5), mine) is None


def test_an_original_stored_in_this_cycle_can_be_repeated_by_a_later_item(factory, make):
    with factory() as db:
        dedup = Deduplicator(db)
        assert dedup.find_original("Acme launches Nova model", NOW, 1) is None
        dedup.remember(42, 1, "Acme launches Nova model", NOW)
        assert dedup.find_original("Acme launches Nova model today", NOW, 2) == 42
