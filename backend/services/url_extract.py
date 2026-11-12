"""Pull web addresses out of email text. Regex only: nothing is fetched, resolved or opened (R1)."""
import html
import re

_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'()\[\]{}]+")
_HREF = re.compile(r"""(?i)\bhref\s*=\s*["']\s*([^"'\s>]+)""")
_WEB = re.compile(r"(?i)^(?:https?://|www\.)")
_TRAILING = ".,;:!?'\""


def extract_urls(text: str) -> list[str]:
    """Web addresses in order of first appearance, without duplicates. Covers plain-text
    links and href values in HTML, where the visible text often differs from the target."""
    hits = [(m.start(), m.group(0)) for m in _URL.finditer(text)]
    hits += [(m.start(1), m.group(1)) for m in _HREF.finditer(text)]
    seen, urls = set(), []
    for _, raw in sorted(hits):
        url = html.unescape(raw).rstrip(_TRAILING)
        if _WEB.match(url) and url.lower() not in seen:
            seen.add(url.lower())
            urls.append(url)
    return urls


if __name__ == "__main__":
    sample = 'Go to https://a.example/x. Or <a href="http://b.example/?q=1&amp;r=2">here</a>, www.c.example and https://A.example/x again; mailto:no@d.example'
    assert extract_urls(sample) == ["https://a.example/x", "http://b.example/?q=1&r=2", "www.c.example"], extract_urls(sample)
    print("ok")
