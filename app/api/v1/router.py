"""Agregador de rotas da API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    apuracoes,
    auditoria,
    certificados,
    cnpj,
    consulta,
    credenciais,
    emissoes,
    fretes,
    health,
    integracoes,
    lotes,
    municipios,
    observabilidade,
    representacoes,
    tax,
    tenants,
    transportes,
    transportes_status,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(consulta.router)
router.include_router(municipios.router)
router.include_router(credenciais.router)
router.include_router(observabilidade.router)
router.include_router(admin.router)
router.include_router(fretes.router)
router.include_router(tenants.router)
router.include_router(certificados.router)
router.include_router(emissoes.router)
router.include_router(cnpj.router)
router.include_router(tax.router)
router.include_router(auditoria.router)
router.include_router(apuracoes.router)
router.include_router(lotes.router)
router.include_router(integracoes.router)
router.include_router(representacoes.router)

__all__ = ["router"]
router.include_router(transportes.router)
router.include_router(transportes_status.router)
