"""POST /api/check-email: the handler from app_email.py, with its status codes and messages.
predict() output is returned unchanged, plus model_version."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.runtime import POST_LIMIT, limiter, run_model

router = APIRouter()
MAX_CHARS = 100_000


class EmailIn(BaseModel):
    subject: str = Field(default="", max_length=1_000)
    body: str = Field(..., max_length=MAX_CHARS)


@router.post("/api/check-email")
@limiter.limit(POST_LIMIT)
async def check_email(request: Request, body: EmailIn):
    model = request.app.state.email_model
    if model is None:
        raise HTTPException(503, {"verdict": "UNAVAILABLE", "message": "Email model not loaded."})

    def predict():
        try:
            return model.predict(body.subject, body.body)
        except ValueError as exc:
            raise HTTPException(422, {"message": str(exc)}) from None

    result = await run_model(predict, {"verdict": "UNAVAILABLE", "message": "Analysis failed; try again."})
    # This model's predict() does not report a version; the site footer needs one.
    return {"model_version": request.app.state.versions["email"], **result}
