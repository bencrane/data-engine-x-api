# app/routers/steps.py — Step registry (list available steps)

from fastapi import APIRouter, Depends

from app.auth import AuthContext, get_current_auth
from app.models.step import Step
from app.services.registry import get_available_steps

router = APIRouter()


@router.post("/list", response_model=list[Step])
async def list_steps(
    auth: AuthContext = Depends(get_current_auth),
):
    """List all available processing steps."""
    return await get_available_steps()
