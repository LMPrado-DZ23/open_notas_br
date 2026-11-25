"""Agregador de rotas da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    apuracoes,
    certificados,
    cnpj,
    emissoes,
    health,
    integracoes,
    lotes,
    representacoes,
    tax,
    tenants,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(tenants.router)
router.include_router(certificados.router)
router.include_router(emissoes.router)
router.include_router(cnpj.router)
router.include_router(tax.router)
router.include_router(apuracoes.router)
router.include_router(lotes.router)
router.include_router(integracoes.router)
router.include_router(representacoes.router)

__all__ = ["router"]
