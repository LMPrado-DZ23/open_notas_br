"""Agregador de rotas da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import certificados, cnpj, emissoes, health, tax, tenants

router = APIRouter()
router.include_router(health.router)
router.include_router(tenants.router)
router.include_router(certificados.router)
router.include_router(emissoes.router)
router.include_router(cnpj.router)
router.include_router(tax.router)

__all__ = ["router"]
