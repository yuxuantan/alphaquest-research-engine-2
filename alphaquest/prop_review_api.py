"""Local, isolated review artifacts for prop subtasks 1–3. No simulation endpoint."""

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt

from .prop.review import EXPORTS, create_review


router = APIRouter(prefix="/api/prop-review", tags=["Prop implementation review"])


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["rithmic", "tradovate", "wealthcharts"] = "rithmic"
    quantity: StrictInt = 2


def root(request):
    return request.app.state.store.path.parent / "prop_reviews"


def review_path(request, review_id):
    path = root(request) / review_id.hex
    if not (path / "review.json").is_file():
        raise HTTPException(404, "Saved prop review not found.")
    return path


@router.post("", status_code=201)
def run_review(body: ReviewRequest, request: Request):
    if body.quantity not in (1, 2):
        raise HTTPException(422, "Choose demonstration quantity 1 or 2.")
    try:
        return create_review(root(request), body.platform, body.quantity)
    except FileNotFoundError:
        raise HTTPException(503, "Review requires this repository's docs/prop_simulation.md. Run from a source checkout.") from None


@router.get("/latest")
def latest_review(request: Request):
    pointer = root(request) / "latest"
    if not pointer.is_file():
        raise HTTPException(404, "No demonstration saved yet. Generate a review first.")
    try:
        review_id = UUID(pointer.read_text(encoding="ascii"))
    except ValueError:
        raise HTTPException(500, "Saved review pointer is invalid.") from None
    return saved_review(review_id, request)


@router.get("/{review_id}")
def saved_review(review_id: UUID, request: Request):
    result = json.loads((review_path(request, review_id) / "review.json").read_text(encoding="utf-8"))
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.get("/{review_id}/exports/{filename}")
def export_review(review_id: UUID, filename: str, request: Request):
    if filename not in EXPORTS:
        raise HTTPException(404, "Review export not found.")
    path = review_path(request, review_id) / filename
    if not path.is_file():
        raise HTTPException(404, "Review export not found.")
    media_type = {".json": "application/json", ".csv": "text/csv", ".md": "text/plain", ".zip": "application/zip"}[Path(filename).suffix]
    return FileResponse(path, media_type=media_type, filename="prop-review-" + review_id.hex + "-" + filename)
