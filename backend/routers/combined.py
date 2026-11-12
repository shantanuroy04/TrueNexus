"""POST /api/analyze-email and POST /api/check-eml: the email model on the text plus the URL
model on every link found in it. Worst signal wins; a partial result is never a clean one."""
import logging
import re

from fastapi import APIRouter, HTTPException, Request

from routers.email import EmailIn
from routers.url import is_web_address
from services.eml import MAX_EML_BYTES, NotAnEmail, parse_eml
from services.runtime import POST_LIMIT, limiter, run_model
from services.url_extract import extract_urls

router = APIRouter()
log = logging.getLogger("mlphil")
MAX_URLS = 20
EML_TYPE = "message/rfc822"


def defang(url: str) -> str:
    """Same rule as url_v5_service.defang, for links the URL model could not score."""
    return re.sub(r"^http", "hxxp", url, flags=re.I).replace(".", "[.]")


def overall(email_verdict: str, bands: list[str]) -> str:
    if email_verdict == "PHISHING" or "High" in bands:
        return "HIGH"
    if email_verdict == "SPAM" or "Medium" in bands:
        return "MEDIUM"
    if email_verdict == "UNCERTAIN":
        return "UNCERTAIN"
    if email_verdict == "UNAVAILABLE" or "UNAVAILABLE" in bands:
        return "UNAVAILABLE"
    return "LOW"


def overall_reason(email_verdict: str, bands: list[str]) -> str:
    first = "Email model unavailable" if email_verdict == "UNAVAILABLE" else f"Email classified {email_verdict}"
    n = len(bands)
    noun = "link" if n == 1 else "links"
    if n == 0:
        links = "no links found"
    elif "High" in bands:
        links = f"{bands.count('High')} of {n} {noun} rated High"
    elif "Medium" in bands:
        links = f"{bands.count('Medium')} of {n} {noun} rated Medium"
    elif "UNAVAILABLE" in bands:
        links = f"{bands.count('UNAVAILABLE')} of {n} {noun} could not be checked"
    else:
        links = f"{n} {noun} checked, none flagged"
    return f"{first}; {links}"


def _analyze(state, subject: str, text: str, link_source: str) -> dict:
    email = {"verdict": "UNAVAILABLE"}
    if state.email_model is not None:
        try:
            email = {"model_version": state.versions["email"], **state.email_model.predict(subject, text)}
        except ValueError as exc:
            raise HTTPException(422, {"message": str(exc)}) from None
        except Exception as exc:
            log.warning("email inference failed: %s", type(exc).__name__)

    found = [u for u in extract_urls(link_source) if is_web_address(u)]
    service, urls = state.url_model, []
    for url in found[:MAX_URLS]:
        try:
            if service is None:
                raise RuntimeError("url model not loaded")
            urls.append(service.check_url(service.URLIn(url=url)))
        except Exception as exc:  # includes the service's own 422: not checked is not clean
            log.warning("link check failed: %s", type(exc).__name__)
            urls.append({"url_defanged": defang(url), "band": "UNAVAILABLE"})

    bands = [u["band"] for u in urls]
    return {
        "email": email,
        "urls": urls,
        "urls_found": len(found),
        "urls_checked": len(urls),
        "urls_capped": len(found) > MAX_URLS,
        "overall": overall(email["verdict"], bands),
        "overall_reason": overall_reason(email["verdict"], bands),
    }


async def _run(request: Request, subject: str, text: str, link_source: str) -> dict:
    state = request.app.state
    if state.email_model is None and state.url_model is None:
        raise HTTPException(503, "UNAVAILABLE")
    if not (subject.strip() or text.strip()):
        raise HTTPException(422, {"message": "empty email"})
    return await run_model(lambda: _analyze(state, subject, text, link_source))


@router.post("/api/analyze-email")
@limiter.limit(POST_LIMIT)
async def analyze_email(request: Request, body: EmailIn):
    return await _run(request, body.subject, body.body, body.body)


@router.post("/api/check-eml")
@limiter.limit(POST_LIMIT)
async def check_eml(request: Request):
    """Raw .eml bytes with Content-Type message/rfc822 (no multipart parser needed).
    Returns the analyze-email result plus parsed_subject."""
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != EML_TYPE:
        raise HTTPException(415, "Upload a .eml file.")
    raw = await request.body()
    if len(raw) > MAX_EML_BYTES:
        raise HTTPException(413, "File is larger than 2 MB.")
    try:
        subject, text, link_source = parse_eml(raw)
    except NotAnEmail:
        raise HTTPException(422, {"message": "This file does not look like an email."}) from None
    return {**await _run(request, subject, text, link_source), "parsed_subject": subject}
