"""Stable API surface matching docs/api/openapi-draft.yaml."""

from fastapi import APIRouter

from . import projects, assets, jobs, system, auth

router = APIRouter()
router.include_router(projects.router)
router.include_router(assets.router)
router.include_router(jobs.router)
router.include_router(system.router)
router.include_router(auth.router)
