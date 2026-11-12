"""Read an uploaded .eml file into (subject, plain-text body, link source).

Uses only the message body chosen by get_body(): attachments are never selected, decoded,
saved or opened. HTML is reduced to text here on the server, never in the browser (R5).
"""
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser

MAX_EML_BYTES = 2 * 1024 * 1024


class NotAnEmail(ValueError):
    pass


class _TextOnly(HTMLParser):
    _SKIP = {"script", "style", "head", "title"}
    _BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self.skipping += 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self.skipping:
            self.skipping -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    parser = _TextOnly()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts)


def parse_eml(raw: bytes) -> tuple[str, str, str]:
    """Returns (subject, body text for the email model, raw body for link extraction)."""
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        if not msg.keys():
            raise NotAnEmail("no headers")
        subject = str(msg.get("subject", "") or "")[:1000]
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return subject, "", ""
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):  # unknown or broken charset
            content = (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
    except NotAnEmail:
        raise
    except Exception as exc:
        raise NotAnEmail(type(exc).__name__) from None
    if part.get_content_type() == "text/html":
        return subject, html_to_text(content), content
    return subject, content, content
