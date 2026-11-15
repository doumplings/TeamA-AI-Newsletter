"""Importance score and level (UC-12, Report 2 Sections 6.3.1, 6.3.2 and 9.1.3).

    Score = source points + keyword points + 5 x extra sources      (6.1)

kept between 0 and 100. High is 70 or more, Medium 40 to 69, Low below 40.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select

from models import (CycleRunRepository, CycleType, ImportanceLevel, MatchField, MatchRecord,
                    NewsItemRepository, ScoringRuleRepository, Source)

log = logging.getLogger("ainews.classifier")

HIGH_CUTOFF = 70
MEDIUM_CUTOFF = 40
EXTRA_SOURCE_POINTS = 5
BATCH_SIZE = 200
MAX_BATCHES = 10  # a cycle scores at most 2,000 items; the rest wait for the next one


class CompiledRule(NamedTuple):
    rule_id: int
    code: str
    weight: int
    pattern: re.Pattern


@dataclass
class ScoreResult:
    """The result of scoring one item: the final score and the rules that contributed."""
    score: int
    matches: list[MatchRecord] = field(default_factory=list)


def compile_rules(rules):
    """Build each active rule's pattern once per cycle; a broken pattern is skipped and reported."""
    compiled, broken = [], []
    for rule in rules:
        try:
            compiled.append(CompiledRule(rule.rule_id, rule.code, rule.weight, re.compile(rule.pattern, re.IGNORECASE)))
        except re.error:
            broken.append(rule.code)
    return compiled, broken


def level_for(score, high_cutoff=HIGH_CUTOFF, medium_cutoff=MEDIUM_CUTOFF):
    if score >= high_cutoff:
        return ImportanceLevel.high
    if score >= medium_cutoff:
        return ImportanceLevel.medium
    return ImportanceLevel.low


def score(item, source, rules, extra_source_points=EXTRA_SOURCE_POINTS):
    """Equation 6.1. Each rule adds its points once per story, however many of its words appear."""
    body = " ".join(part for part in (item.summary, item.body) if part)
    total = source.base_weight
    matches = []
    for rule in rules:
        if rule.pattern.search(item.title):
            where = MatchField.title
        elif body and rule.pattern.search(body):
            where = MatchField.body
        else:
            continue
        total += rule.weight
        matches.append(MatchRecord(rule.rule_id, where, Decimal(rule.weight)))
    # Sources known when the story is scored; later reports do not change it (Section 9.1.3).
    total += extra_source_points * (item.corroboration_count - 1)
    return ScoreResult(max(0, min(100, total)), matches)


class ImportanceClassifier:
    """Scores every unclassified item and records the cycle."""

    def __init__(self, factory, batch_size=BATCH_SIZE, high_cutoff=HIGH_CUTOFF,
                 medium_cutoff=MEDIUM_CUTOFF, extra_source_points=EXTRA_SOURCE_POINTS):
        self.factory = factory
        self.batch_size = batch_size
        self.high_cutoff = high_cutoff
        self.medium_cutoff = medium_cutoff
        self.extra_source_points = extra_source_points

    def classify_pending(self):
        classified = failures = 0
        levels = {level.value: 0 for level in ImportanceLevel}
        errors = []
        with self.factory.begin() as db:
            run_id = CycleRunRepository(db).start(CycleType.classify)
            rules, broken = compile_rules(ScoringRuleRepository(db).active())
        if broken:
            failures += len(broken)
            errors.append("invalid rule pattern: " + ", ".join(broken))
        try:
            for _ in range(MAX_BATCHES):
                # One transaction per batch: score, level and rule matches are saved
                # together, so a story is never left half-classified.
                with self.factory.begin() as db:
                    repository = NewsItemRepository(db)
                    items = repository.unclassified(self.batch_size)
                    if not items:
                        break
                    sources = {s.source_id: s for s in db.scalars(
                        select(Source).where(Source.source_id.in_({i.source_id for i in items})))}
                    for item in items:
                        result = score(item, sources[item.source_id], rules, self.extra_source_points)
                        level = level_for(result.score, self.high_cutoff, self.medium_cutoff)
                        repository.save_classification(item.item_id, Decimal(result.score), level, result.matches)
                        levels[level.value] += 1
                    classified += len(items)
                if len(items) < self.batch_size:
                    break
        except Exception as exc:
            failures += 1
            errors.append(type(exc).__name__)
            log.error("Classify cycle failed (%s); unscored items wait for the next cycle", type(exc).__name__)
        finally:
            with self.factory.begin() as db:
                CycleRunRepository(db).finish(run_id, classified, failures,
                                              json.dumps({"levels": levels, "errors": errors}))
        return {"run_id": run_id, "items_classified": classified, "failures": failures, "levels": levels}


def classify_pending(factory):
    """One classify cycle with the default settings."""
    return ImportanceClassifier(factory).classify_pending()
