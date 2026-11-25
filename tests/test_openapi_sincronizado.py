"""Guarda contra divergência entre o `openapi.json` versionado e o app real.

O contrato publicado é o que o parceiro integra. Se o código muda e o arquivo não,
alguém implementa contra um schema que não existe — e o erro aparece só em runtime,
do lado de quem integrou.

Este teste falha quando os dois divergem; a correção é regenerar o arquivo.
"""

from __future__ import annotations

import json
import pathlib

from app.main import criar_app

RAIZ = pathlib.Path(__file__).resolve().parent.parent


class TestOpenApiVersionado:
    def test_arquivo_existe(self) -> None:
        assert (RAIZ / "openapi.json").is_file()

    def test_esta_sincronizado_com_o_app(self) -> None:
        versionado = json.loads((RAIZ / "openapi.json").read_text(encoding="utf-8"))
        atual = criar_app().openapi()
        assert versionado.get("paths") == atual.get("paths"), (
            "openapi.json divergiu do app. Regenere com:\n"
            '  python -c "import json,pathlib; from app.main import criar_app; '
            "pathlib.Path('openapi.json').write_text("
            "json.dumps(criar_app().openapi(), ensure_ascii=False, indent=2) + chr(10), "
            'encoding="utf-8")\\"'
        )

    def test_cobre_todas_as_rotas(self) -> None:
        versionado = json.loads((RAIZ / "openapi.json").read_text(encoding="utf-8"))
        rotas_app = set(criar_app().openapi()["paths"])
        assert set(versionado["paths"]) == rotas_app
        assert len(rotas_app) >= 35
