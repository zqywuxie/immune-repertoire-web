"""Auth routes for the Phase 5 FastAPI bridge."""

from fastapi import APIRouter, Depends

from ..core.auth import ApiPrincipal, require_current_user

router = APIRouter(tags=["Auth"], prefix="/auth")


@router.get("/me")
async def get_current_user(principal: ApiPrincipal = Depends(require_current_user)):
    """Get current authenticated user / migration principal."""
    return {
        "authenticated": principal.authenticated,
        "subject": principal.subject,
        "auth_mode": principal.auth_mode,
    }


@router.post("/login")
async def login():
    """Login — placeholder proxied to Flask."""
    return {"message": "Session login is handled by Flask during the migration bridge phase."}


@router.post("/logout")
async def logout():
    """Logout — placeholder."""
    return {"message": "Logged out."}
