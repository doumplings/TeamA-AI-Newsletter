"""Normalize feeds, HTML cards, JSON API results, and URLs."""
import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
from bs4 import BeautifulSoup


def clean(value):
    soup = BeautifulSoup(str(value or ""), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def date(value):
    if not value:
        return None
    if isinstance(value, (tuple, list)):
        return datetime.fromtimestamp(calendar.timegm(tuple(value)), timezone.utc)
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        result = parsedate_to_datetime(str(value))
    return result.replace(tzinfo=result.tzinfo or timezone.utc).astimezone(timezone.utc)


def canonicalize(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Item URL must be an HTTP(S) URL without credentials")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "mc_cid", "mc_eid")]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", urlencode(sorted(query)), ""))


@dataclass
class Item:
    title: str
    url: str
    published_at: datetime | None = None
    summary: str | None = None
    body: str | None = None

    def normalized(self, base):
        self.title = clean(self.title)
        if not self.title or not self.url:
            raise ValueError("Item requires a title and link")
        self.url = urljoin(base, self.url)
        canonicalize(self.url)
        self.summary = clean(self.summary) or None
        self.body = clean(self.body) or None
        return self


def feed_items(content):
    feed = feedparser.parse(content)
    if feed.get("bozo") and not feed.entries:
        raise ValueError("Invalid RSS/Atom feed")
    if not feed.get("version"):
        raise ValueError("Response is not an RSS/Atom feed")
    for entry in feed.entries:
        yield Item(entry.get("title", ""), entry.get("link", ""),
                   date(entry.get("published_parsed") or entry.get("updated_parsed")),
                   entry.get("summary"),
                   entry.get("content", [{}])[0].get("value"))


def html_items(content, config):
    soup = BeautifulSoup(content, "html.parser")
    def field(card, name, attr=None):
        selector = config.get(name + "_selector")
        node = card.select_one(selector) if selector else None
        return (node.get(attr) if attr else node.get_text(" ", strip=True)) if node else None
    for card in soup.select(config["item_selector"]):
        yield Item(str(field(card, "title") or ""), str(field(card, "link", "href") or ""),
                   date(field(card, "date", "datetime") or field(card, "date")),
                   str(field(card, "summary") or "") or None,
                   str(field(card, "body") or "") or None)


def path(data, dotted):
    for key in dotted.split(".") if dotted else []:
        data = data[key]
    return data


def json_items(data, config):
    if config.get("adapter") == "bluesky":
        if data.get("error") or data.get("errors"):
            raise ValueError("Bluesky returned API errors")
        if not isinstance(data.get("posts"), list):
            raise ValueError("Bluesky response requires a posts array")
        for post in data["posts"]:
            record = post['record']
            # Collect original public posts, rather than replies.
            if record.get('reply'):
                continue
            text = record['text']
            if config.get("ai_only") and not re.search(
                r"\b(?:AI|artificial intelligence|machine learning|LLMs?|GPT(?:-?\d[\w.-]*)?|Claude|Gemini|OpenAI|Anthropic|language models?)\b",
                text, re.IGNORECASE,
            ):
                continue
            uri = post['uri'].split('/')
            if len(uri) != 5 or uri[:2] != ['at:', ''] or uri[3] != 'app.bsky.feed.post' or not uri[2] or not uri[4]:
                raise ValueError('Invalid Bluesky post URI')
            # DID-based permalinks remain stable when the author's handle changes.
            url = 'https://bsky.app/profile/' + uri[2] + '/post/' + uri[4]
            yield Item(text[:240], url, date(record.get('createdAt')), text)
        return
    if config.get("adapter") == "nyt":
        for row in path(data, config.get("items_path", "response.docs")):
            headline = row.get("headline") or {}
            # Only the title determines AI relevance.
            ai_pattern = (r"(?<!\w)(?:A\.?I\.?|artificial intelligence|machine learning|"
                          r"LLMs?|chatbots?|ChatGPT|GPT(?:-?\d[\w.-]*)?|OpenAI|Anthropic|"
                          r"language models?)(?!\w)")
            if not re.search(ai_pattern, str(headline.get("main") or ""), re.IGNORECASE):
                continue
            yield Item(headline.get("main", ""), row.get("web_url", ""),
                       date(row.get("pub_date")), row.get("abstract") or row.get("snippet"),
                       row.get("lead_paragraph"))
        return
    fields = config.get("fields", {})
    for row in path(data, config.get("items_path", "")):
        def value(name):
            key = fields.get(name, name)
            try:
                return path(row, key)
            except (KeyError, TypeError):
                return None
        yield Item(value("title") or "", value("url") or "", date(value("published_at")),
                   value("summary"), value("body"))
