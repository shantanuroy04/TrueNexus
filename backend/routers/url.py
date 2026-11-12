"""POST /api/check-url: fail-closed wrapper around url_v5_service.check_url. Analyses the
URL string only: nothing here opens, resolves or fetches it (R1)."""
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.runtime import POST_LIMIT, limiter, run_model

router = APIRouter()
INVALID = "Provide a valid public http(s) URL"
# "javascript:alert(1)" or "mailto:a@b.com", but not "example.com:8080/x"
_NON_WEB_SCHEME = re.compile(r"(?i)^[a-z][a-z0-9+.-]*:[^\d/]")
_SCHEME = re.compile(r"(?i)^[a-z][a-z0-9+.-]*://")


class UrlIn(BaseModel):
    url: str = Field(max_length=2048)


def is_web_address(url: str) -> bool:
    """The model parser accepts any bare word as a host; rating "hello" as "No URL
    warning" would read as a clean result."""
    has_scheme = _SCHEME.match(url) is not None
    if _NON_WEB_SCHEME.match(url) or (has_scheme and not url.lower().startswith(("http://", "https://"))):
        return False
    try:
        host = urlsplit(url if has_scheme else f"http://{url}").hostname or ""
    except ValueError:
        return False
    return "." in host or ":" in host


@router.post("/api/check-url")
@limiter.limit(POST_LIMIT)
async def check_url(request: Request, body: UrlIn):
    service = request.app.state.url_model
    if service is None:
        raise HTTPException(503, "UNAVAILABLE")
    # Stripped because the service's defang only rewrites "http" at position 0.
    url = body.url.strip()
    if not is_web_address(url):
        raise HTTPException(422, INVALID)
    return await run_model(lambda: service.check_url(service.URLIn(url=url)))
