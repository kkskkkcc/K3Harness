from self_learning_agent.web_search import (
    _decode_duck_url,
    _DuckParser,
    _search_bing,
)


def test_duckduckgo_lite_parser_extracts_source_and_nested_snippet() -> None:
    parser = _DuckParser()
    parser.feed(
        """
        <a class='result-link'
           href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa'>A result</a>
        <td class='result-snippet'>A <b>short</b> summary.</td>
        """
    )
    parser.close()
    assert parser.items == [("A result", "A short summary.", "https://example.com/a")]


def test_duck_redirect_url_is_decoded() -> None:
    assert _decode_duck_url(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews"
    ) == "https://example.com/news"


def test_bing_rss_parser_reads_items(monkeypatch) -> None:
    rss = b"""<?xml version='1.0'?><rss><channel><item>
      <title>Example</title><link>https://example.com</link>
      <description><![CDATA[Summary <b>here</b>]]></description>
    </item></channel></rss>"""
    monkeypatch.setattr("self_learning_agent.web_search._fetch", lambda *args, **kwargs: rss)
    assert _search_bing("example") == [("Example", "Summary here", "https://example.com")]
