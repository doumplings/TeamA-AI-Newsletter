"""The keyword categories of the importance score (Report 2, Table 6-6b).

Rules live in the ``scoring_rules`` table so they can be tuned or switched off
without a code change (Section 6.3.5). This list only fills an empty table.
"""
import re

from sqlalchemy.dialects.postgresql import insert

from models import ScoringRule

# (code, name, words or phrases that trigger it, keyword points)
# The table gives example words; the other forms of the same words are listed too,
# so "OpenAI releases GPT-6" (the report's own example in Section 6.3.3) counts as a release.
DEFAULT_RULES = [
    ("K1", "New model release",
     ["release", "releases", "released", "releasing", "launch", "launches", "launched", "launching",
      "introducing", "introduces", "unveils", "unveiled", "unveiling"], 40),
    ("K2", "Model shutdown or breaking API change",
     ["deprecate", "deprecates", "deprecated", "deprecating", "deprecation", "retire", "retires", "retired",
      "retiring", "shut down", "shuts down", "shutting down", "shutdown", "breaking change", "breaking changes"], 40),
    ("K3", "Price change", ["price", "prices", "pricing"], 20),
    ("K4", "Funding or acquisition",
     ["funding", "raises", "raised", "acquires", "acquired", "acquiring", "acquisition", "acquisitions"], 20),
    ("K5", "Law or regulation",
     ["regulation", "regulations", "law", "laws", "executive order", "executive orders", "ai act"], 20),
    # Negative on purpose: routine posts the customer does not want to be notified about.
    ("K6", "Event, webinar or hiring post", ["meetup", "meetups", "webinar", "webinars", "join us", "hiring"], -20),
]


def words_pattern(words):
    """One whole-word pattern for a rule's word list: "law" matches "new AI law", not "lawsuit"."""
    return r"\b(?:" + "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words) + r")\b"


def seed_rules(factory):
    """Insert missing default rules without changing rules already in the table."""
    with factory.begin() as db:
        for code, name, words, weight in DEFAULT_RULES:
            db.execute(
                insert(ScoringRule)
                .values(code=code, name=name, pattern=words_pattern(words), weight=weight)
                .on_conflict_do_nothing(index_elements=[ScoringRule.code])
            )
