"""Documento fiscal autorizado com a chave de acesso já estreitada.

`FiscalDocument.chave` é `str | None` no ORM porque um documento pode existir antes da
autorização. Depois de autorizado, a chave **é** obrigatória — e tanto o cancelamento quanto os
eventos da NFS-e dependem disso.

Antes de existir este tipo, as duas rotinas garantiam a chave em tempo de execução
(`if documento is None or not documento.chave: raise`) e depois continuavam usando
`documento.chave`, que para o `mypy` seguia sendo `str | None`. O invariante existia só na
cabeça de quem leu: qualquer refatoração que movesse o `raise` reintroduzia o `None` no lugar
onde ele vira `TypeError` ou, pior, `"None"` no XML assinado.

Carregar a chave ao lado do documento põe o invariante no tipo.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.models.invoice import FiscalDocument


@dataclass(frozen=True, slots=True)
class DocumentoAutorizado:
    """Documento autorizado + chave de acesso não nula."""

    documento: FiscalDocument
    chave: str
