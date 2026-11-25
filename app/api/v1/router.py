"""Agregador de rotas da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health, tenants

router = APIRouter()
router.include_router(health.router)
router.include_router(tenants.router)

__all__ = ["router"]
