"""Consulta de status de transporte passa pelo circuito, escopado por UF (§85).

Antes: `GET /v1/transportes/status` chamava a SEFAZ **sem** circuito. Com a SEFAZ da UF fora, cada
requisição queimava 30 s de timeout do transporte — e o endpoint recebe a UF, que é exatamente o escopo
que o circuito deveria usar. Só as escritas (emissão, cancelamento, evento) tinham proteção.

Estes testes provam o escopo da chave, não a implementação do circuito (que já tem testes próprios).
"""

from __future__ import annotations

from app.nfse.resiliencia import chave_sefaz


def test_chave_da_consulta_e_por_uf() -> None:
    """A chave inclui a UF e a operação: GO fora não pode abrir o circuito de SP."""
    go = chave_sefaz("GO", "consulta_status")
    sp = chave_sefaz("SP", "consulta_status")

    assert go != sp
    assert "GO" in go and "consulta_status" in go
    assert go == "sefaz:GO:consulta_status"


def test_operacao_de_consulta_nao_confunde_com_autorizacao() -> None:
    assert chave_sefaz("GO", "consulta_status") != chave_sefaz("GO", "autorizacao")
