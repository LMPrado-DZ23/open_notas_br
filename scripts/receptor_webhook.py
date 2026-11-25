"""Receptor de webhook para prova de integração da Fase 5.

Escuta em 0.0.0.0:8899 e valida a assinatura HMAC de cada requisição, gravando o
resultado em `receiver.log`. Rodar só para verificação manual; não faz parte do
produto.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ARQUIVO_SEGREDO = Path(sys.argv[1])
LOG = ARQUIVO_SEGREDO.with_name("receiver.log")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        tamanho = int(self.headers.get("Content-Length", "0"))
        corpo = self.rfile.read(tamanho)
        assinatura = self.headers.get("X-Notasbr-Signature", "")
        evento = self.headers.get("X-Notasbr-Event", "")

        valida = False
        motivo = ""
        esperada = ""
        momento = 0
        try:
            partes = dict(item.split("=", 1) for item in assinatura.split(","))
            momento = int(partes["t"])
            recebida = partes["v1"]
            # Lê o segredo a cada requisição: permite trocar o tenant em teste sem
            # reiniciar o receptor.
            segredo = ARQUIVO_SEGREDO.read_text(encoding="utf-8").strip().encode()
            esperada = hmac.new(segredo, f"{momento}.".encode() + corpo, hashlib.sha256).hexdigest()
            valida = hmac.compare_digest(esperada, recebida)
            motivo = "" if valida else "assinatura divergente"
            if abs(int(time.time()) - momento) > 300:
                valida = False
                motivo = "fora da tolerância"
        except Exception as exc:
            motivo = f"erro ao validar: {type(exc).__name__}: {exc}"

        registro = {
            "evento": evento,
            "assinatura_recebida": assinatura,
            "assinatura_esperada": f"t={momento},v1={esperada}",
            "assinatura_valida": valida,
            "motivo": motivo,
            "payload": json.loads(corpo or b"{}"),
        }
        with LOG.open("a", encoding="utf-8") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, formato: str, *args: object) -> None:
        return


if __name__ == "__main__":
    LOG.write_text("", encoding="utf-8")
    servidor = HTTPServer(("0.0.0.0", 8899), Handler)
    print("receptor ouvindo em 0.0.0.0:8899", flush=True)
    servidor.serve_forever()
