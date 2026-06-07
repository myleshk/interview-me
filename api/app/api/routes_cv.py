"""CV download route — ``/v1/cv/download``.

Serves a static PDF file from ``data/static/cv.pdf``.
If the file is missing, returns 404.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(prefix="/v1", tags=["CV"])

_DEFAULT = Path(__file__).resolve().parent.parent.parent / "data"
_BASE = Path(os.environ.get("DATA_DIR", str(_DEFAULT)))
CV_PATH = _BASE / "static" / "cv.pdf"


@router.get(
    "/cv/download",
    summary="Download the owner's CV as PDF",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_cv() -> FileResponse:
    """Serve the static CV PDF."""
    if not CV_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CV file not found. Place your PDF at data/static/cv.pdf",
        )
    return FileResponse(
        path=str(CV_PATH),
        media_type="application/pdf",
        filename="cv.pdf",
    )
