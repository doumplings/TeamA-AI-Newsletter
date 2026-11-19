"""Classification: scores each new news item and assigns its importance level (UC-12)."""
from .rules import DEFAULT_RULES, seed_rules
from .service import ImportanceClassifier, ScoreResult, classify_pending, level_for, score

__all__ = [
    "DEFAULT_RULES",
    "ImportanceClassifier",
    "ScoreResult",
    "classify_pending",
    "level_for",
    "score",
    "seed_rules",
]
