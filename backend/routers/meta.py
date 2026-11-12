"""GET /api/health and GET /api/model-info. Every number in model-info is read from a file the
training run produced; anything missing is null, never written by hand (R8)."""
import csv
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter()
log = logging.getLogger("mlphil")
METRIC_KEYS = ("n_legit", "n_spam", "n_phish", "macro_f1", "accuracy", "phish_recall", "phish_malicious_caught", "phish_to_legit",
               "legit_false_alert", "spam_recall", "ece", "uncertain_rate")


@router.get("/api/health")
def health(request: Request, response: Response):
    state = request.app.state
    url, email = state.url_model is not None, state.email_model is not None
    if not (url or email):
        response.status_code = 503
    status = "ready" if url and email else "degraded" if url or email else "down"
    return {"status": status, "url_model": url, "email_model": email, "accounts": state.db_ready, "versions": state.versions}


def _reports_dir() -> Path | None:
    if "MLPHIL_EMAIL_REPORTS" in os.environ:
        return Path(os.environ["MLPHIL_EMAIL_REPORTS"])
    if "MLPHIL_EMAIL_MODEL_DIR" in os.environ:
        return Path(os.environ["MLPHIL_EMAIL_MODEL_DIR"]).parent / "email_reports"
    return None


def _number(value):
    try:
        return float(value) if value not in ("", None) else None
    except ValueError:
        return None


def _interval(value):
    """'[0.521, 0.560]' -> [0.521, 0.56]; '-' -> None."""
    parts = [_number(p) for p in str(value).strip("[] ").split(",")] if value and value != "-" else []
    return parts if len(parts) == 2 and None not in parts else None


def _pick(row: dict) -> dict:
    return {k: _number(row.get(k)) for k in METRIC_KEYS}


def _email_metrics():
    folder = _reports_dir()
    if folder is None or not (folder / "summary.json").exists():
        return None
    try:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        with open(folder / "external_metrics.csv", encoding="utf-8") as f:
            by_source = [{"source": r[""], **_pick(r)} for r in csv.DictReader(f) if r[""] != "ALL"]
        with open(folder / "external_ci95.csv", encoding="utf-8") as f:
            ci = {r[""]: r for r in csv.DictReader(f)}.get("ALL", {})
        return {
            "internal": _pick(summary["internal"]),
            "external": _pick(summary["external"]),
            "external_ci95": {k: _interval(ci.get(k)) for k in ("macro_f1", "phish_recall", "phish_to_legit", "legit_false_alert")},
            "external_by_source": by_source,
            "targets": [{"name": t[0], "value": _number(t[1]), "target": _number(t[2]), "result": t[3]} for t in summary.get("targets", [])],
            # Paths are left out on purpose (R9).
            "sources": [{"source": d["source"], "role": d["role"], "rows": d.get("kept_rows")} for d in summary.get("data", [])],
            # v6 and later: how the test was kept apart from training (None for older reports)
            "split_design": summary.get("split_design"),
        }
    except Exception as exc:
        log.warning("email reports unreadable: %s", type(exc).__name__)
        return None


def _url_metrics():
    """Figures from final_report.json inside the URL bundle (written by the URL pipeline notebook), else None."""
    bundle = os.environ.get("MLPHIL_URL_BUNDLE")
    if not bundle or not (Path(bundle) / "final_report.json").exists():
        return None
    try:
        report = json.loads((Path(bundle) / "final_report.json").read_text(encoding="utf-8"))
        results = []
        for row in report.get("results", []):
            if row.get("split") not in ("test", "ext_test") or row.get("metric") not in ("recall", "false_alert"):
                continue
            lo, hi = _number(row.get("ci_lo")), _number(row.get("ci_hi"))
            results.append({"split": row["split"], "cohort": str(row.get("cohort")), "metric": row["metric"],
                            "n": _number(row.get("n")), "rate": _number(row.get("rate_HIGH")),
                            "ci95": [lo, hi] if lo is not None and hi is not None else None})
        criteria = [{"name": name, "value": _number(c.get("value")), "target": _number(c.get("target")), "passed": bool(c.get("passed"))}
                    for name, c in report.get("criteria", {}).items()]
        return {"verdict": report.get("verdict"), "results": results, "criteria": criteria}
    except Exception as exc:
        log.warning("url report unreadable: %s", type(exc).__name__)
        return None


@router.get("/api/model-info")
def model_info(request: Request):
    state = request.app.state
    if state.url_model is None and state.email_model is None:
        raise HTTPException(503, "UNAVAILABLE")
    url = None
    if state.url_model is not None:
        model = state.url_model.MODEL
        url = {
            "version": state.versions["url"],
            "thr_high": round(model.thr_alert * 100, 3),
            "thr_medium": round(model.thr_review * 100, 3),
            "metrics": _url_metrics(),  # None for bundles without final_report.json (v5)
        }
    email = None
    if state.email_model is not None:
        cfg = getattr(state.email_model, "cfg", None) or {}
        email = {
            "version": state.versions["email"],
            "base_model": cfg.get("base_model"),
            "labels": list(cfg.get("labels", {}).values()) or None,
            "max_length": cfg.get("max_length"),
            "phishing_threshold": cfg.get("phishing_threshold"),
            "uncertain_below": cfg.get("uncertain_below"),
            "trained": cfg.get("trained"),
            "metrics": _email_metrics(),
        }
    return {"url": url, "email": email}
