"""Centralized policy checks, pacing, conditional HTTP, and bounded retries."""
import os
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

import requests


class PolicyError(RuntimeError):
    pass


class Client:
    def __init__(self, user_agent="AINewsCollector/1.0", session=None, sleep=time.sleep, clock=time.monotonic):
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.sleep, self.clock = sleep, clock
        self.next_request = {}
        self.last_request = {}
        self.robots = {}
        self.bluesky_access = None

    def close(self):
        self.session.close()

    def _request(self, url, delay, **kwargs):
        origin = urlsplit(url)
        key = (origin.scheme, origin.netloc)
        for attempt in range(3):
            self.sleep(max(0, self.next_request.get(key, 0) - self.clock()))
            self.last_request[key] = self.clock()
            self.next_request[key] = self.clock() + delay
            response = self.session.get(url, timeout=(10, 30), allow_redirects=False, **kwargs)
            if response.status_code not in (429, 500, 502, 503, 504):
                return response
            retry = response.headers.get("Retry-After", "")
            try:
                wait = float(retry)
            except ValueError:
                try:
                    wait = parsedate_to_datetime(retry).timestamp() - time.time()
                except (TypeError, ValueError):
                    wait = 2 ** attempt
            # Long waits fail this source; the next scheduled cycle can retry.
            if wait > 60 or attempt == 2:
                raise RuntimeError(f"HTTP {response.status_code}; retry on a later cycle")
            self.next_request[key] = max(self.next_request[key], self.clock() + max(0, wait))
        raise RuntimeError("HTTP retry limit")

    def _bluesky_credentials(self):
        """Create one session per cycle; cache only in this client's memory."""
        if self.bluesky_access is not None:
            return self.bluesky_access
        response = self.session.post(
            'https://bsky.social/xrpc/com.atproto.server.createSession',
            json={'identifier': os.environ['BLUESKY_HANDLE'].strip(),
                  'password': os.environ['BLUESKY_APP_PASSWORD'].strip()},
            headers={'User-Agent': self.user_agent}, timeout=(10, 30), allow_redirects=False,
        )
        if response.status_code != 200:
            raise RuntimeError(f'HTTP {response.status_code}: Bluesky login failed; check BLUESKY_HANDLE and BLUESKY_APP_PASSWORD')
        try:
            token = response.json()['accessJwt']
            if not isinstance(token, str) or not token:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('Bluesky login returned an invalid session') from None
        self.bluesky_access = token
        return token

    def check(self, url, config, *, authenticated=False):
        if config.get("terms_status") != "allowed" or not config.get("terms_url"):
            raise PolicyError("Review source terms and configure terms_status=allowed and terms_url")
        parsed = urlsplit(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise PolicyError("Source must have an HTTP(S) URL without credentials")
        delay = max(1.0, float(config.get("min_interval_seconds", 2)))
        # Public AppView search is a documented API, separate from web crawling.
        if (config.get('adapter') == 'bluesky' and parsed.scheme == 'https'
                and (parsed.netloc == 'public.api.bsky.app'
                     or (parsed.netloc == 'bsky.social' and authenticated))
                and parsed.path == '/xrpc/app.bsky.feed.searchPosts'):
            return delay
        if (config.get("adapter") == "nyt" and url ==
                "https://api.nytimes.com/svc/search/v2/articlesearch.json"):
            return max(delay, 12.0)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            response = self._request(origin + "/robots.txt", delay, headers={"User-Agent": self.user_agent})
            parser = RobotFileParser()
            if response.status_code in (404, 410):
                parser.parse([])
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                raise PolicyError(f"Cannot verify robots.txt: HTTP {response.status_code}")
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(self.user_agent, url):
            raise PolicyError("robots.txt disallows this URL")
        delay = max(delay, parser.crawl_delay(self.user_agent) or 0)
        rate = parser.request_rate(self.user_agent)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        key = (parsed.scheme, parsed.netloc)
        if key in self.last_request:
            self.next_request[key] = max(self.next_request.get(key, 0), self.last_request[key] + delay)
        return delay

    def get(self, url, config, headers=None, params=None):
        if config.get("adapter") == "nyt":
            if url != "https://api.nytimes.com/svc/search/v2/articlesearch.json":
                raise PolicyError("NYT credentials require the official Article Search endpoint")
            token = os.environ.get("NYT_API_KEY", "").strip()
            if not token:
                raise RuntimeError("Set NYT_API_KEY in the project .env")
            params = {**(params or {}), "api-key": token}
            delay = self.check(url, config)
            try:
                response = self._request(url, delay, headers={"User-Agent": self.user_agent}, params=params)
            except requests.RequestException:
                raise RuntimeError("NYT API network request failed") from None
            if response.status_code != 200:
                raise RuntimeError(f"NYT API HTTP {response.status_code}; check key, API access, and quota")
            return response
        # Authenticated app requests go through the user's hosted PDS, which
        # proxies them to AppView. Never send these credentials to arbitrary URLs.
        if config.get('adapter') == 'bluesky' and url == 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts':
            handle = os.environ.get('BLUESKY_HANDLE', '').strip()
            password = os.environ.get('BLUESKY_APP_PASSWORD', '').strip()
            if bool(handle) != bool(password):
                raise RuntimeError('Set both BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in the root .env')
            if handle and password:
                if config.get('terms_status') != 'allowed' or not config.get('terms_url'):
                    raise PolicyError('Review source terms before using the API')
                token = self._bluesky_credentials()
                url = 'https://bsky.social/xrpc/app.bsky.feed.searchPosts'
                headers = {**(headers or {}), 'Authorization': 'Bearer ' + token,
                           'atproto-proxy': 'did:web:api.bsky.app#bsky_appview'}
        # Every redirect is checked before it is followed. Never forward credentials.
        for _ in range(6):
            authenticated = bool((headers or {}).get('Authorization', '').startswith('Bearer '))
            delay = self.check(url, config, authenticated=authenticated)
            response = self._request(url, delay, headers={**(headers or {}), "User-Agent": self.user_agent}, params=params)
            if response.status_code in (301, 302, 303, 307, 308):
                target = urljoin(url, response.headers["Location"])
                if urlsplit(target).netloc != urlsplit(url).netloc:
                    headers = None
                url, params = target, None
                continue
            if config.get('adapter') == 'bluesky' and response.status_code >= 400:
                hint = 'Bluesky API request failed'
                if response.status_code in (401, 403):
                    hint = ('Bluesky denied authenticated search; check app-password permissions or service availability'
                            if authenticated else
                            'Bluesky denied public search; set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in root .env')
                raise RuntimeError(f"HTTP {response.status_code}: " + hint)
            if response.status_code != 304:
                response.raise_for_status()
            return response
        raise PolicyError("Too many redirects")

    def render(self, url, config):
        from playwright.sync_api import sync_playwright
        # All browser traffic, including scripts and navigation, goes through the
        # same policy/pacing transport. No service workers or hidden requests.
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                context = browser.new_context(user_agent=self.user_agent, service_workers="block")
                def route_request(route):
                    if route.request.resource_type not in ("document", "script", "xhr", "fetch"):
                        route.abort()
                        return
                    try:
                        response = self.get(route.request.url, config)
                        route.fulfill(status=response.status_code, body=response.content,
                                      content_type=response.headers.get("Content-Type", "text/plain"))
                    except Exception:
                        route.abort()
                context.route("**/*", route_request)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector(config["item_selector"], timeout=30000)
                return page.content()
            finally:
                browser.close()
