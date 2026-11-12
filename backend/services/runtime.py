"""Model loading and inference plumbing. Anything that goes wrong leaves the model
unavailable, never a clean result (R3). Only error class names are logged (R6)."""
import asyncio
import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path

from fastapi import HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

log = logging.getLogger("mlphil")
limiter = Limiter(key_func=get_remote_address)
POST_LIMIT = "30/minute"
TIMEOUT_S = 20.0
VENDOR = Path(__file__).resolve().parent.parent / "vendor"
EMAIL_VERDICTS = {"LEGITIMATE", "SPAM", "PHISHING", "UNCERTAIN"}


def load_url_model():
    """Returns the url_v5_service module. It loads the bundle at import time, so a
    missing bundle fails here instead of crashing the server."""
    sys.path.insert(0, str(VENDOR))
    sys.modules.pop("url_v5_service", None)  # a fresh import re-reads MLPHIL_URL_BUNDLE
    service = importlib.import_module("url_v5_service")
    result = service.check_url(service.URLIn(url="https://example.com/"))
    if result["band"] not in {"Low", "Medium", "High"} or not result["evidence"]:
        raise RuntimeError("self-test failed")
    # The service hard-codes "mlphil_url_v5" in its replies; the bundle's metadata names the real version.
    return service, service.MODEL.meta.get("version") or result["model"]


def load_email_model():
    """Uses the email_preprocess.py saved inside the model folder, by path, so the code
    always comes from the same training run as the weights."""
    model_dir = Path(os.environ["MLPHIL_EMAIL_MODEL_DIR"])
    spec = importlib.util.spec_from_file_location("email_preprocess", model_dir / "email_preprocess.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.EmailClassifier(model_dir)
    result = model.predict("Self test", "Minutes from the weekly project meeting are attached.")
    if result["verdict"] not in EMAIL_VERDICTS:
        raise RuntimeError("self-test failed")
    return model, f"{model_dir.name}, trained {model.cfg['trained']}"


def try_load(name, loader):
    """Returns (model, version), or (None, None) if the model cannot be made ready."""
    try:
        return loader()
    except Exception as exc:
        log.warning("%s model unavailable: %s", name, type(exc).__name__)
        return None, None


async def run_model(call, unavailable="UNAVAILABLE"):
    # run_in_executor, not run_in_threadpool: anyio threads ignore cancellation, so
    # wait_for would block until inference finished and the timeout would never fire.
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, call), TIMEOUT_S)
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("inference failed: %s", type(exc).__name__)
        raise HTTPException(503, unavailable) from None
