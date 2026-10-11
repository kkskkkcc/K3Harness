from __future__ import annotations

import asyncio
import json
import logging
import re
import ssl
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener
from xml.etree import ElementTree

logger = logging.getLogger(__name__)


def _build_opener(proxy_url: str):
    """Return an urllib opener that honours an explicit proxy URL only.

    Passing ``proxy_url=""`` produces a ``ProxyHandler({})`` which explicitly
    disables every system HTTP proxy. This is deliberate: the project's web
    search should not silently fall back to whatever HTTP_PROXY/HTTPS_PROXY
    the host happens to have, because (a) rule-set mistakes on a local proxy
    tool can silently break search, and (b) the K3 board may run on a closed
    network where any inherited proxy would be unreachable. Operators who do
    want a proxy configure ``WEB_SEARCH_PROXY`` explicitly.
    """
    if proxy_url:
        return build_opener(ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        }))
    return build_opener(ProxyHandler({}))


class _TextParser(HTMLParser):
    """Turn the small HTML snippets returned by search providers into plain text."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", unescape(" ".join(self.parts))).strip()


class _DuckParser(HTMLParser):
    """Parse DuckDuckGo Lite results (the regular HTML endpoint changed shape)."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, str, str]] = []
        self._title = ""
        self._snippet = ""
        self._url = ""
        self._in_title = False
        self._in_snippet = False
        self._snippet_tag = ""

    def _finish(self) -> None:
        title = re.sub(r"\s+", " ", unescape(self._title)).strip()
        snippet = re.sub(r"\s+", " ", unescape(self._snippet)).strip()
        if title and self._url:
            self.items.append((title, snippet, self._url))
        self._title = ""
        self._snippet = ""
        self._url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result-link" in classes:
            if self._title:
                self._finish()
            href = attributes.get("href") or ""
            self._url = _decode_duck_url(href)
            self._in_title = True
        elif "result-snippet" in classes:
            self._in_snippet = True
            self._snippet_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_snippet and tag == self._snippet_tag:
            self._in_snippet = False
            self._snippet_tag = ""
            self._finish()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title += data
        elif self._in_snippet:
            self._snippet += data

    def close(self) -> None:
        super().close()
        if self._title:
            self._finish()


def _decode_duck_url(href: str) -> str:
    """Resolve DuckDuckGo's redirect URL to the actual source URL."""
    absolute = urljoin("https://duckduckgo.com", href)
    parsed = urlparse(absolute)
    target = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(target) if target else absolute


def _fetch(url: str, *, accept: str = "text/html", proxy_url: str = "") -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; K3Agent/1.0)",
            "Accept": accept,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    opener = _build_opener(proxy_url)
    with opener.open(request, timeout=6) as response:
        return response.read(2_000_000)


def _search_duckduckgo(query: str, proxy_url: str = "") -> list[tuple[str, str, str]]:
    url = "https://lite.duckduckgo.com/lite/?q=" + quote_plus(query[:300])
    parser = _DuckParser()
    parser.feed(_fetch(url, proxy_url=proxy_url).decode("utf-8", errors="replace"))
    parser.close()
    return parser.items


def _is_dictionary_entry(title: str) -> bool:
    """Detect Baidu/Hanyu dictionary card results that Bing RSS returns for
    single-character queries. These have titles like ``你（汉语文字）_百度百科``
    or ``我（汉语汉字）_百度百科`` and are useless as answers to most user
    questions, so we strip them.
    """
    lowered = title.lower()
    return any(
        marker in lowered
        for marker in ("汉语文字", "汉语汉字", "汉语字典", "_字典", "_词典")
    )


def _rewrite_short_chinese_query(query: str) -> str:
    """Augment very short Chinese queries so Bing returns encyclopaedia
    entries instead of single-character dictionary cards.

    ``你`` by itself returns a Baidu "汉语文字" entry; ``你 百科`` returns the
    actual concept entry. The rewrite only fires for queries that look like
    single terms (no spaces, ≤ 2 Chinese characters, no URL/Python tokens);
    real user questions already contain enough context for Bing.
    """
    stripped = query.strip()
    if " " in stripped or "\n" in stripped:
        return stripped
    # Heuristic: short CJK-only query with no question mark / no operators
    cjk = sum(1 for ch in stripped if "\u4e00" <= ch <= "\u9fff")
    if cjk <= 2 and cjk == len(stripped):
        return f"{stripped} 百科"
    return stripped


def _search_bing(query: str, proxy_url: str = "") -> list[tuple[str, str, str]]:
    effective_query = _rewrite_short_chinese_query(query)
    url = "https://www.bing.com/search?format=rss&q=" + quote_plus(effective_query[:300])
    root = ElementTree.fromstring(
        _fetch(url, accept="application/rss+xml, text/xml", proxy_url=proxy_url)
    )
    results: list[tuple[str, str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        text_parser = _TextParser()
        text_parser.feed(description)
        snippet = text_parser.text()
        if not (title and link):
            continue
        if _is_dictionary_entry(title):
            continue
        results.append((unescape(title), snippet, link))
    return results


# Wikipedia REST search is the most reliable source for entity / term lookups:
# it returns the actual encyclopaedia entry instead of an ad-laden SERP, and
# the API does not require keys or rate-limit credentials from us. Results
# are tried in Chinese first, then English, because Chinese Wikipedia has
# better coverage of mainland entities while English is the fallback for
# technical terms.
_WIKI_LANGS: tuple[str, ...] = ("zh", "en")


def _search_wikipedia(query: str, proxy_url: str = "") -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    for lang in _WIKI_LANGS:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        params = (
            "?action=query&list=search&format=json&utf8=1"
            "&srlimit=5&srprop=snippet"
            f"&srsearch={quote_plus(query[:200])}"
        )
        try:
            payload = json.loads(
                _fetch(api + params, accept="application/json", proxy_url=proxy_url).decode(
                    "utf-8", errors="replace"
                )
            )
        except (ValueError, Exception):
            continue
        hits = payload.get("query", {}).get("search", []) if isinstance(payload, dict) else []
        if not hits:
            continue
        for hit in hits:
            title = unescape(hit.get("title", "")).strip()
            # Wikipedia returns snippets as HTML with <span> highlights.
            snippet_html = unescape(hit.get("snippet", "")).strip()
            text_parser = _TextParser()
            text_parser.feed(snippet_html)
            snippet = text_parser.text()
            page_id = hit.get("pageid")
            url = f"https://{lang}.wikipedia.org/?curid={page_id}" if page_id else ""
            if title and url:
                results.append((title, snippet, url))
        if results:
            return results
    return results


# Mojeek is an independent crawler-based engine that exposes a clean HTML
# page; we only need to pull each result's title, snippet, and link. It
# avoids Bing's RSS feed, which routinely returns a "character dictionary"
# entry for short Chinese queries instead of the requested topic.
def _search_mojeek(query: str, proxy_url: str = "") -> list[tuple[str, str, str]]:
    url = "https://www.mojeek.com/search?q=" + quote_plus(query[:200])
    html = _fetch(url, proxy_url=proxy_url).decode("utf-8", errors="replace")
    parser = _DuckParser()
    parser.feed(html)
    parser.close()
    return parser.items


def _format_results(provider: str, items: list[tuple[str, str, str]]) -> str:
    lines = [f"外网搜索结果（{provider}，请核对来源）："]
    for index, (title, snippet, url) in enumerate(items[:5], start=1):
        lines.append(f"{index}. {title}")
        if snippet:
            lines.append(f"   摘要：{snippet}")
        lines.append(f"   来源：{url}")
    return "\n".join(lines)


def _classify_failure(exc: Exception, proxy_url: str) -> str:
    """Turn a low-level exception into a short, actionable Chinese phrase."""
    import socket

    if isinstance(exc, TimeoutError):
        note = "（疑似代理或网络超时）" if proxy_url else "（网络超时）"
        return f"超时{note}"
    if isinstance(exc, ssl.SSLError):
        return "SSL 握手失败（代理拒绝/证书不匹配）"
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.gaierror):
            return f"域名解析失败（{reason}）"
        if isinstance(reason, ConnectionRefusedError):
            return "代理拒绝连接"
        return f"网络错误（{type(reason).__name__ if reason else type(exc).__name__}）"
    if isinstance(exc, (socket.gaierror, ConnectionError)):
        return f"网络错误（{type(exc).__name__}）"
    return f"{type(exc).__name__}"


def _search_sync(query: str, proxy_url: str = "") -> str:
    """Search the web through a resilient provider chain.

    Order matters. Wikipedia and Mojeek both return topical results for
    short Chinese queries; Bing RSS does not, so it is reserved as a last
    resort. DuckDuckGo Lite stays in the chain as a generic fallback.
    """
    errors: list[str] = []
    for provider, search in (
        ("Wikipedia", _search_wikipedia),
        ("Mojeek", _search_mojeek),
        ("DuckDuckGo", _search_duckduckgo),
        ("Bing", _search_bing),
    ):
        try:
            items = search(query, proxy_url=proxy_url)
            if items:
                return _format_results(provider, items)
            errors.append(f"{provider}未返回结果")
        except Exception as exc:  # parser / provider-shape errors are user-visible
            errors.append(f"{provider}{_classify_failure(exc, proxy_url)}")
    detail = "；".join(errors)
    hint = (
        "如使用本地代理，请确认 .env 中 WEB_SEARCH_PROXY 设置正确；"
        "如未使用代理，请检查网络连通性。"
        if not proxy_url
        else f"已配置的代理 {proxy_url} 拒绝了搜索请求，请检查代理规则是否放行 "
        f"Wikipedia / Mojeek / DuckDuckGo / Bing。"
    )
    return (
        f"外网搜索失败：{detail}。{hint}搜索结果不会作为上下文，Agent 不会基于此编造答案。"
    )


async def search_web(query: str, proxy_url: str = "") -> str:
    """Opt-in external search. Callers must explicitly enable it per request."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_search_sync, query, proxy_url), timeout=14
        )
    except TimeoutError:
        return "外网搜索超时（14秒）。请稍后重试或缩短问题。"
    except Exception as exc:
        return f"外网搜索失败（{type(exc).__name__}）。请稍后重试。"
