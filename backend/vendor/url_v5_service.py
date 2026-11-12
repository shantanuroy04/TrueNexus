"""ML Phil — URL v5 FastAPI integration (drop-in router).

PRD rules honoured:
  SEC-01 / FR-011  never fetch / resolve / render the submitted URL (string analysis only)
  AC-03            exactly one band (Low / Medium / High) + numeric score
  AC-04            >=1 evidence item or an explicit "no strong indicators" statement
  SEC-04           URL echoed back defanged (hxxp, [.]) — never clickable

Usage in main.py:
    from url_v5_service import router as url_router
    app.include_router(url_router)
Set MLPHIL_URL_BUNDLE to the model_bundle folder (default ./model_bundle).
"""
from __future__ import annotations
import os, re, sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

BUNDLE = Path(os.environ.get("MLPHIL_URL_BUNDLE", Path(__file__).parent / "model_bundle"))
sys.path.insert(0, str(BUNDLE))
from predictor import URLRiskV5          # noqa: E402  (bundle ships its own urlcore/features)
import urlcore as U                      # noqa: E402

MODEL = URLRiskV5(BUNDLE)                # load once at startup
router = APIRouter()
BAND = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}


class URLIn(BaseModel):
    url: str = Field(..., max_length=2048)


def defang(url: str) -> str:
    return re.sub(r"^http", "hxxp", url, flags=re.I).replace(".", "[.]")


def evidence(url: str) -> list[str]:
    """Human-readable indicators taken from the same features the model uses (no network)."""
    p = U.parse(url)
    f = dict(zip(U.NUM_FEATURES, U.numeric(p)))
    x = dict(zip(U.EXTRA_FEATURES, U.extra(p, MODEL.lm, MODEL.tld_index)))
    ev = []
    if f["is_ip"]: ev.append("Uses a raw IP address instead of a domain name")
    if f["userinfo"] or f["at_in_path"]: ev.append("Contains '@', which can hide the real destination")
    if f["punycode"]: ev.append("Internationalised (punycode) hostname — possible look-alike characters")
    if x["lookalike_d1"] or x["lookalike_d2"]: ev.append("Domain name is a near-spelling of a well-known brand")
    if f["brand_in_sub"] or x["brand_token_in_host"] or f["brand_in_sld_mixed"]:
        ev.append(f"Brand name appears in the address but the real domain is '{p['reg']}'")
    if f["brand_in_path"]: ev.append("Brand name appears in the path of an unrelated domain")
    if f["lure_words_host"] or f["lure_words_path"]: ev.append("Uses lure words (login / verify / account / update …)")
    if f["platform"]: ev.append(f"Hosted on a free/shared platform ({p['platform']}) often abused for phishing")
    if f["shortener"]: ev.append("Link shortener hides the final destination")
    if f["embedded_url"]: ev.append("Another URL is embedded inside this one (redirect pattern)")
    if f["sub_labels"] >= 3: ev.append("Unusually many subdomain levels")
    if f["has_port"]: ev.append("Non-standard port number")
    if f["file_ext"] and f["path_depth"] >= 1: ev.append("Points directly at a script/page file (.php/.html …)")
    if x["lm_sld"] < -4.0: ev.append("Domain name looks randomly generated")
    return ev


@router.post("/api/check-url")
def check_url(body: URLIn):
    a = MODEL.assess(body.url)
    if a["risk"] == "INVALID":
        raise HTTPException(status_code=422, detail="Provide a valid public http(s) URL")
    ev = evidence(body.url) or ["No strong URL-pattern indicators found"]
    return {
        "model": "mlphil_url_v5",
        "band": BAND[a["risk"]],
        "score": round(a["score"] * 100, 1),          # 0–100 for the UI
        "evidence": ev,
        "url_defanged": defang(body.url),
        "note": a["note"],
        "disclaimer": "URL-text analysis only. The link was not opened. A Low band is not a safety guarantee.",
    }


@router.get("/api/health")
def health():
    return {"status": "ok", "url_model": "mlphil_url_v5", "thr_high": MODEL.thr_alert, "thr_medium": MODEL.thr_review}
