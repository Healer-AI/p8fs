"""Icon server router for serving email template icons."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/icons", tags=["icons"])

ICON_DIR = Path(__file__).parent.parent / "static" / "icons"


@router.get("/{icon_name}")
async def get_icon(icon_name: str):
    """
    Serve icon images for email templates.

    Args:
        icon_name: Icon filename without extension (e.g., "user", "location")

    Returns:
        PNG image file with 1-year cache headers

    Raises:
        HTTPException: 400 if invalid icon name, 404 if icon not found
    """
    if not icon_name.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid icon name")

    icon_path = ICON_DIR / f"{icon_name}.png"

    if not icon_path.exists():
        logger.warning(f"Icon not found: {icon_name}")
        raise HTTPException(status_code=404, detail="Icon not found")

    return FileResponse(
        icon_path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000"}
    )
