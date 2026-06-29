"""Auth routes — Phase 5 skeleton. Current implementation is a placeholder
that accepts all requests (Flask handles actual authentication during the
bridge phase).
"""

from fastapi import APIRouter

router = APIRouter(tags=["Auth"], prefix="/auth")


@router.get("/me")
async def get_current_user():
    """Get current authenticated user — placeholder."""
    return {
        "authenticated": False,
        "message": "Auth is handled by Flask during the migration bridge phase.",
    }


@router.post("/login")
async def login():
    """Login — placeholder proxied to Flask."""
    return {"message": "Login is handled by Flask during the migration bridge phase."}


@router.post("/logout")
async def logout():
    """Logout — placeholder."""
    return {"message": "Logged out."}
