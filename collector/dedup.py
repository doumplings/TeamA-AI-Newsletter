"""Same-story check (UC-11, Report 2 Sections 6.3.3 and 9.1.2).

Exact copies are already blocked by the unique canonical URL. Different sites
reporting one story have different links, so this compares titles: two items are
the same story when at least half of all their different title words are shared
(Equation 6.2) and they were published at most three days apart.
"""
import re
from datetime import timedelta

from sqlalchemy import func, select

from models import NewsItem

SHARED_WORDS_NEEDED = 0.5
SAME_STORY_DAYS = 3

# Small filler words that say nothing about which story a title is.
FILLER_WORDS = frozenset("""
a an and are as at be by for from has have in is it its most of on or that the
their this to was were will with new now how why what
""".split())

# "GPT-6" and "4.5" stay one word, so model names are compared whole.
_WORD = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def title_words(title):
    """Lower-case title words without filler words."""
    return frozenset(_WORD.findall(title.lower())) - FILLER_WORDS


def share_of_words(a, b):
    """Equation 6.2: words both titles have / all the different words in the two titles."""
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def same_story(title_a, when_a, title_b, when_b, needed=SHARED_WORDS_NEEDED, days=SAME_STORY_DAYS):
    """The share-of-words and days-apart test."""
    if when_a is not None and when_b is not None and abs(when_a - when_b) > timedelta(days=days):
        return False
    return share_of_words(title_words(title_a), title_words(title_b)) >= needed


class Deduplicator:
    """Finds the stored story a new item repeats, if any.

    Candidates are loaded once per source transaction (originals inside the
    three-day window on either side) and kept as word sets, so each new item
    costs a few hundred set comparisons and no extra queries.
    """

    def __init__(self, db, shared_words_needed=SHARED_WORDS_NEEDED, same_story_days=SAME_STORY_DAYS):
        self.db = db
        self.shared_words_needed = shared_words_needed
        self.window = timedelta(days=same_story_days)
        self._candidates = None  # [(item_id, source_id, words, when)]
        self._since = None

    def _load(self, since):
        when = func.coalesce(NewsItem.published_at, NewsItem.collected_at)
        rows = self.db.execute(
            select(NewsItem.item_id, NewsItem.source_id, NewsItem.title, when)
            .where(NewsItem.duplicate_of.is_(None), when >= since)
        )
        self._candidates = [(item_id, source_id, title_words(title), at) for item_id, source_id, title, at in rows]
        self._since = since

    def find_original(self, title, published_at, source_id):
        """Item id of the stored story this one repeats, or None.

        Only other sources are compared: one site's own posts often share most of
        their title words ("Weekly roundup #12" / "#13") without being repeats.
        If several stored stories pass, the highest share wins; a tie goes to the earliest.
        """
        since = published_at - self.window
        if self._candidates is None or since < self._since:
            self._load(since)
        words = title_words(title)
        if not words:
            return None
        best = None
        for item_id, other_source, other_words, when in self._candidates:
            if other_source == source_id or abs(when - published_at) > self.window:
                continue
            share = share_of_words(words, other_words)
            if share < self.shared_words_needed:
                continue
            key = (-share, when, item_id)
            if best is None or key < best[0]:
                best = (key, item_id)
        return best[1] if best else None

    def remember(self, item_id, source_id, title, published_at):
        """A newly stored original can be repeated by a later item in the same cycle."""
        if self._candidates is not None:
            self._candidates.append((item_id, source_id, title_words(title), published_at))
