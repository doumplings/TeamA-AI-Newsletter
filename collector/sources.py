"""Default sources for the local collector testing API."""
from models import Source, SourceType
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

BLUESKY_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
BLUESKY_TERMS = ['artificial intelligence', 'machine learning', 'LLM', 'OpenAI', 'Anthropic']

FEED_URL = "https://huggingface.co/blog/feed.xml"
NYT_API_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
NYT_AI_FEED_URL = "https://www.nytimes.com/svc/collections/v1/publish/https://www.nytimes.com/spotlight/artificial-intelligence/rss.xml"


def rss(name, url, terms, weight=30):
    return dict(name=name, source_type=SourceType.rss, url=url, base_weight=weight,
                is_active=True, config={"terms_status": "allowed", "terms_url": terms,
                                        "min_interval_seconds": 5})


def default_sources():
    return [
        rss("Hugging Face Blog", FEED_URL, "https://huggingface.co/terms-of-service"),
        rss("OpenAI News", "https://openai.com/news/rss.xml", "https://openai.com/policies/terms-of-use/"),
        rss("Google AI Blog", "https://blog.google/technology/ai/rss/", "https://policies.google.com/terms"),
        rss("MIT News — Artificial Intelligence", "https://news.mit.edu/rss/topic/artificial-intelligence2",
            "https://news.mit.edu/terms-of-use", 20),
        dict(name="The New York Times — Artificial Intelligence", source_type=SourceType.api,
             url=NYT_API_URL, base_weight=20, is_active=True,
             config={"terms_status": "allowed",
                     "terms_url": "https://developer.nytimes.com/terms",
                     "adapter": "nyt", "params": {"q": '"artificial intelligence"', "sort": "newest"},
                     "items_path": "response.docs",
                     "fields": {"title": "headline.main", "url": "web_url",
                                "published_at": "pub_date", "summary": "abstract", "body": "lead_paragraph"},
                     "max_pages": 100, "min_interval_seconds": 12}),
        dict(name="Bluesky — AI news", source_type=SourceType.api,
             url=BLUESKY_URL, base_weight=15, is_active=True,
             config={"adapter": "bluesky", "terms_status": "allowed",
                     "terms_url": "https://bsky.social/about/support/tos",
                     "search_terms": BLUESKY_TERMS,
                     "params": {"q": BLUESKY_TERMS[0], "sort": "latest", "lang": "en", "limit": 100},
                     "ai_only": True, "since_param": "since",
                     "next_token_path": "cursor", "page_token_param": "cursor",
                     "max_pages": 100, "min_interval_seconds": 2}),
    ]

def seed_source(factory):
    """Insert missing defaults without changing existing source settings."""
    with factory.begin() as db:
        # One-way retirement of the previous provider; keep historical rows and
        # their foreign-key references, but never schedule requests to it again.
        db.execute(update(Source).where(Source.config['adapter'].astext == 'x').values(is_active=False, config={'retired': True}))
        db.execute(update(Source).where(Source.url == NYT_AI_FEED_URL).values(is_active=False))
        for source in default_sources():
            statement = insert(Source).values(**source)
            if source['url'] == BLUESKY_URL:
                # Upgrade existing databases too; keep activation and checkpoint.
                statement = statement.on_conflict_do_update(index_elements=[Source.url],
                    set_={'config': statement.excluded.config})
            else:
                statement = statement.on_conflict_do_nothing(index_elements=[Source.url])
            db.execute(statement)
