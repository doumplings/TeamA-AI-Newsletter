"""ImportanceClassifier (UC-12). UT-01 to UT-08 from Report 2, Table 11-1."""
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from classifier import DEFAULT_RULES, ImportanceClassifier, level_for, score, seed_rules
from classifier.rules import words_pattern
from classifier.service import CompiledRule
from models import ImportanceLevel, MatchField, NewsItem, RuleMatch, ScoringRule

RULES = [CompiledRule(n, code, weight, re.compile(words_pattern(words), re.IGNORECASE))
         for n, (code, _, words, weight) in enumerate(DEFAULT_RULES, start=1)]
OFFICIAL, NEWS_SITE, COMMUNITY = (SimpleNamespace(base_weight=w) for w in (30, 20, 10))


def story(title, summary=None, body=None, sources=1):
    return SimpleNamespace(title=title, summary=summary, body=body, corroboration_count=sources)


def test_ut01_official_release_with_price_and_two_other_sources_is_100_high():
    result = score(story("Acme releases its new model with lower pricing", sources=3), OFFICIAL, RULES)
    assert result.score == 100 and level_for(result.score) == ImportanceLevel.high  # 30 + 40 + 20 + 5 x 2
    assert {m.rule_id for m in result.matches} == {1, 3}


def test_ut02_official_shutdown_notice_is_70_the_lowest_high():
    result = score(story("Legacy completions API will be retired in March"), OFFICIAL, RULES)
    assert result.score == 70 and level_for(result.score) == ImportanceLevel.high


def test_ut03_price_cut_on_a_news_site_is_40_the_lowest_medium():
    result = score(story("Acme cuts prices for its embedding models"), NEWS_SITE, RULES)
    assert result.score == 40 and level_for(result.score) == ImportanceLevel.medium


def test_ut04_meetup_post_from_an_official_source_is_10_low():
    result = score(story("Come to our developer meetup in Berlin"), OFFICIAL, RULES)
    assert result.score == 10 and level_for(result.score) == ImportanceLevel.low
    assert result.matches[0].contribution == -20


def test_ut05_level_boundaries():
    levels = [level_for(s).value for s in (0, 39, 40, 69, 70, 100)]
    assert levels == ["low", "low", "medium", "medium", "high", "high"]


def test_ut06_score_is_kept_between_0_and_100():
    assert score(story("We are hiring: join us"), COMMUNITY, RULES).score == 0  # 10 - 20
    everything = story("Acme launches a model, deprecated the old one, changes pricing, raises funding as the AI Act lands")
    assert score(everything, OFFICIAL, RULES).score == 100  # 30 + 40 + 40 + 20 + 20 + 20


def test_ut07_a_rule_counts_once_and_only_matches_whole_words():
    thrice = score(story("Release notes: release 2 follows release 1"), OFFICIAL, RULES)
    assert thrice.score == 70 and len(thrice.matches) == 1
    assert score(story("Authors file lawsuit against Acme"), OFFICIAL, RULES).matches == []
    assert [m.rule_id for m in score(story("A new AI law passes"), OFFICIAL, RULES).matches] == [5]


def test_a_match_in_the_summary_counts_as_body_and_phrases_span_spaces():
    result = score(story("Quarterly update", summary="The v1 endpoint will shut  down next year."), OFFICIAL, RULES)
    assert result.score == 70 and result.matches[0].field == MatchField.body


def test_ut08_classify_pending_scores_every_item_and_ignores_inactive_rules(factory, make):
    seed_rules(factory)
    with factory.begin() as db:
        db.execute(update(ScoringRule).where(ScoringRule.code == "K3").values(is_active=False))
    official, community = make.source(weight=30), make.source("Forum", weight=10)
    a = make.item(official, "Introducing Acme-5, our most capable model")
    b = make.item(official, "New pricing for the Acme API")              # only the inactive rule would match
    c = make.item(community, "Acme raises $2B in new funding", corroboration_count=2)

    summary = ImportanceClassifier(factory).classify_pending()
    assert summary["items_classified"] == 3 and summary["failures"] == 0

    with factory() as db:
        items = {i.item_id: i for i in db.scalars(select(NewsItem))}
        assert [(int(items[x].importance_score), items[x].importance_level.value) for x in (a, b, c)] == [
            (70, "high"), (30, "low"), (35, "low")]
        assert all(i.classified_at is not None for i in items.values())
        matched = {(m.item_id, m.rule.code) for m in db.scalars(select(RuleMatch))}
        assert matched == {(a, "K1"), (c, "K4")}

    # Nothing left to do: the next cycle scores no item twice.
    assert ImportanceClassifier(factory).classify_pending()["items_classified"] == 0


def test_a_broken_rule_pattern_is_reported_and_the_rest_still_apply(factory, make):
    seed_rules(factory)
    with factory.begin() as db:
        db.add(ScoringRule(code="BAD", name="Broken", pattern="(unclosed", weight=10))
    item = make.item(make.source(), "Acme launches a model")
    summary = ImportanceClassifier(factory).classify_pending()
    assert summary["items_classified"] == 1 and summary["failures"] == 1
    with factory() as db:
        assert int(db.get(NewsItem, item).importance_score) == 70


@pytest.mark.parametrize("words", [["shut down"], ["ai act"]])
def test_phrases_match_as_whole_phrases(words):
    pattern = re.compile(words_pattern(words), re.IGNORECASE)
    assert pattern.search(f"the {words[0].upper()} is here") and not pattern.search(words[0].replace(" ", "x"))
