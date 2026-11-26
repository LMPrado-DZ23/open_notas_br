"""Observabilidade dos circuitos: `sefaz_circuit_state` em JSON.

Seção 1.2 do v10.0 pede a métrica `sefaz_circuit_state{uf}`. Esta rota entrega o mesmo
dado em JSON, sem exigir um exporter Prometheus — que seria dependência nova sem ADR.

**Pública de propósito**: é estado de saúde de infraestrutura, não dado de tenant. Um
cliente precisa saber que a SEFAZ de GO está com circuito aberto para entender por que a
emissão dele está falhando. Nenhum payload, nenhuma credencial, nenhum tenant aparece
aqui — só nome de circuito e estado.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.circuit import Estado
from app.nfse.resiliencia import registro_padrao

router = APIRouter(prefix="/health", tags=["health"])

#: Valor numérico por estado, igual ao que a métrica Prometheus usaria.
CODIGO_DO_ESTADO = {
    Estado.FECHADO: 0,
    Estado.MEIO_ABERTO: 1,
    Estado.ABERTO: 2,
}


@router.get("/circuitos")
async def circuitos() -> dict:
    """Estado atual de cada circuito.

    Lista vazia significa "nada foi chamado ainda", **não** "tudo saudável" — um circuito
    só existe depois do primeiro uso. Deixar isso explícito evita a leitura errada de que
    ausência de dados é ausência de problema.
    """
    estados = registro_padrao.estados()
    return {
        "circuitos": [
            {"nome": nome, "estado": estado, "codigo": CODIGO_DO_ESTADO[Estado(estado)]}
            for nome, estado in sorted(estados.items())
        ],
        "total": len(estados),
        "observacao": (
            "lista vazia significa que nenhum serviço externo foi chamado ainda, "
            "não que todos estejam saudáveis"
        ),
    }
