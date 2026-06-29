"""Stable API surface matching docs/api/openapi-draft.yaml."""

from fastapi import APIRouter

from . import projects, assets, jobs

router = APIRouter()
router.include_router(projects.router)
router.include_router(assets.router)
router.include_router(jobs.router)
