"""Agregador de rotas da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import certificados, emissoes, health, tenants

router = APIRouter()
router.include_router(health.router)
router.include_router(tenants.router)
router.include_router(certificados.router)
router.include_router(emissoes.router)

__all__ = ["router"]
