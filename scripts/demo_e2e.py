"""Demonstração fim-a-fim do open_notas_br, contra a API rodando.

Percorre o caminho completo que o critério de go-live exige:

    criar tenant -> configuração fiscal -> upload do A1 -> emitir NFS-e
    -> DANFSe local -> webhook assinado recebido e validado -> apuração -> guia

Uso (com `docker compose up` já rodando e `NFSE_ADAPTER=mock`)::

    python -m scripts.demo_e2e

O certificado usado é **gerado no próprio script**, autoassinado, e existe só em
memória. Serve para exercitar o fluxo; não é o seu certificado A1.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx

BASE = os.environ.get("DEMO_API_URL", "http://127.0.0.1:8081")
PORTA_RECEPTOR = int(os.environ.get("DEMO_WEBHOOK_PORT", "8899"))
#: Como o worker (no container) alcança este receptor no host. `127.0.0.1` dentro
#: do container é o próprio container, então o padrão é o alias do Docker Desktop.
HOST_VISTO_PELO_WORKER = os.environ.get("DEMO_WEBHOOK_HOST", "host.docker.internal")
VERDE, VERMELHO, AMARELO, ZERAR = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def ok(mensagem: str) -> None:
    print(f"{VERDE}  OK{ZERAR} {mensagem}")


def falha(mensagem: str) -> None:
    print(f"{VERMELHO}  FALHOU{ZERAR} {mensagem}")


def passo(titulo: str) -> None:
    print(f"\n{AMARELO}== {titulo}{ZERAR}")


def gerar_pfx_autoassinado() -> tuple[bytes, str]:
    """Certificado autoassinado com CNPJ no SAN, apenas para demonstração."""
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    titular = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DEMO E2E LTDA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "DEMO E2E LTDA:11222333000181"),
        ]
    )
    agora = datetime.datetime.now(datetime.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(titular)
        .issuer_name(titular)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - datetime.timedelta(days=1))
        .not_valid_after(agora + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DirectoryName(
                        x509.Name([x509.NameAttribute(NameOID.SERIAL_NUMBER, "11222333000181")])
                    )
                ]
            ),
            critical=False,
        )
        .sign(chave, hashes.SHA256())
    )
    senha = "senha-demo-e2e"
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"demo",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode()),
    )
    return pfx, senha


class Receptor:
    """Servidor HTTP mínimo que valida a assinatura de cada webhook recebido."""

    def __init__(self) -> None:
        self.recebidos: list[dict[str, Any]] = []
        self.segredo = b""
        self._servidor: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def iniciar(self) -> None:
        receptor = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                tamanho = int(self.headers.get("Content-Length", "0"))
                corpo = self.rfile.read(tamanho)
                cabecalho = self.headers.get("X-Notasbr-Signature", "")
                valida = False
                try:
                    partes = dict(item.split("=", 1) for item in cabecalho.split(","))
                    momento = int(partes["t"])
                    esperada = hmac.new(
                        receptor.segredo, f"{momento}.".encode() + corpo, hashlib.sha256
                    ).hexdigest()
                    valida = hmac.compare_digest(esperada, partes["v1"])
                except Exception:
                    valida = False
                receptor.recebidos.append(
                    {
                        "evento": self.headers.get("X-Notasbr-Event", ""),
                        "assinatura_valida": valida,
                        "payload": json.loads(corpo or b"{}"),
                    }
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, formato: str, *args: object) -> None:
                return

        # 0.0.0.0 para aceitar a conexão vinda do container.
        self._servidor = HTTPServer(("0.0.0.0", PORTA_RECEPTOR), Handler)
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()

    def parar(self) -> None:
        if self._servidor:
            self._servidor.shutdown()


def main() -> int:
    sucessos = 0
    total = 0

    def checar(condicao: bool, mensagem: str) -> None:
        nonlocal sucessos, total
        total += 1
        if condicao:
            sucessos += 1
            ok(mensagem)
        else:
            falha(mensagem)

    with httpx.Client(base_url=BASE, timeout=30.0) as http:
        passo("0. API no ar")
        saude = http.get("/health")
        checar(saude.status_code == 200, f"GET /health -> {saude.status_code}")

        # Recusa antes de qualquer escrita: este roteiro emite NFS-e. Se o adaptador for real,
        # ele emitiria documento fiscal de verdade — a demo não tem autorização para isso.
        adaptador = (saude.json() if saude.status_code == 200 else {}).get("nfse_adapter")
        if adaptador != "mock":
            falha(
                f"NFSE_ADAPTER={adaptador!r} nesta instância; a demo exige 'mock'. "
                "Suba com NFSE_ADAPTER=mock: rodar assim emitiria NFS-e real."
            )
            return 2

        passo("1. Criar tenant")
        slug = f"demo-e2e-{int(time.time())}"
        criado = http.post("/v1/tenants", json={"slug": slug, "nome": "Demo E2E LTDA"})
        checar(criado.status_code == 201, f"POST /v1/tenants -> {criado.status_code}")
        if criado.status_code != 201:
            print(criado.text)
            return 1
        tenant = criado.json()
        chave_api = tenant["api_key"]
        cabecalho = {"X-API-Key": chave_api}
        checar(bool(chave_api), "API key devolvida uma única vez")

        passo("2. Configuração fiscal")
        config = http.put(
            "/v1/me/config-fiscal",
            headers=cabecalho,
            json={
                "municipio_ibge": "3550308",
                "uf": "SP",
                "ambiente": "homologacao",
                "codigo_tributacao_nacional": "010701",
                "serie_dps": "1",
                "aliquota_iss": 0.05,
            },
        )
        checar(config.status_code == 200, f"PUT /v1/me/config-fiscal -> {config.status_code}")

        passo("3. Upload do certificado A1 (autoassinado, gerado agora)")
        pfx, senha = gerar_pfx_autoassinado()
        certificado = http.post(
            "/v1/me/certificados",
            headers=cabecalho,
            files={"arquivo": ("demo.pfx", pfx, "application/x-pkcs12")},
            data={"senha": senha, "apelido": "demo-e2e"},
        )
        checar(
            certificado.status_code == 201, f"POST /v1/me/certificados -> {certificado.status_code}"
        )
        if certificado.status_code == 201:
            dados_cert = certificado.json()
            checar(
                dados_cert.get("cnpj") == "11222333000181",
                f"CNPJ extraído do certificado: {dados_cert.get('cnpj')}",
            )

        passo("4. Webhook configurado com segredo")
        receptor = Receptor()
        receptor.iniciar()
        try:
            webhook = http.post(
                "/v1/me/webhook",
                headers=cabecalho,
                json={"url": f"http://{HOST_VISTO_PELO_WORKER}:{PORTA_RECEPTOR}/hook"},
            )
            checar(webhook.status_code == 200, f"POST /v1/me/webhook -> {webhook.status_code}")
            if webhook.json().get("segredo"):
                receptor.segredo = webhook.json()["segredo"].encode()

            passo("5. Emitir NFS-e")
            # Corpo guardado numa variável: o passo 6 precisa reenviar **exatamente** isto.
            corpo_nota = {
                "idempotency_key": "demo-e2e-001",
                "valor": "150.00",
                "descricao": "Corte + barba",
                "competencia": "2026-11",
                "tomador_nome": "Cliente Demo",
                "tomador_documento": "11144477735",
            }
            emissao = http.post("/v1/emissoes", headers=cabecalho, json=corpo_nota)
            checar(emissao.status_code == 201, f"POST /v1/emissoes -> {emissao.status_code}")
            if emissao.status_code != 201:
                print(emissao.text)
                return 1
            nota = emissao.json()
            checar(len(nota["chave"]) == 50, f"Chave de acesso: {nota['chave']}")

            passo("6. Idempotência (mesma chave de idempotência)")
            # Reenvio **idêntico** é o caso que o cliente faz: devolve a mesma nota.
            repetida = http.post("/v1/emissoes", headers=cabecalho, json=corpo_nota)
            checar(
                repetida.status_code == 200 and repetida.json()["ja_existia"] is True,
                f"reenvio idêntico -> {repetida.status_code} ja_existia={repetida.json().get('ja_existia')}",
            )
            checar(
                repetida.json()["invoice_id"] == nota["invoice_id"],
                "reenvio idêntico devolveu a MESMA fatura",
            )

            # Corpo diferente com a mesma chave é 409: sem isso, o cliente que pede R$ 100
            # recebia de volta a nota de R$ 50 e achava que emitiu o que pediu (auditoria §57).
            divergente = dict(corpo_nota, valor="999.00")
            conflito = http.post("/v1/emissoes", headers=cabecalho, json=divergente)
            checar(
                conflito.status_code == 409,
                f"corpo divergente com a mesma chave -> {conflito.status_code} (esperado 409)",
            )

            passo("7. DANFSe local (PDF)")
            danfse = http.get(f"/v1/emissoes/{nota['invoice_id']}/danfse", headers=cabecalho)
            checar(
                danfse.status_code == 200 and danfse.content.startswith(b"%PDF"),
                f"GET .../danfse -> {danfse.status_code}, {len(danfse.content)} bytes, PDF válido",
            )

            passo("8. Webhook assinado (aguardando o worker)")
            prazo = time.time() + 40
            while time.time() < prazo and not receptor.recebidos:
                time.sleep(2)
            checar(bool(receptor.recebidos), f"webhook recebido: {len(receptor.recebidos)}")
            if receptor.recebidos:
                primeiro = receptor.recebidos[0]
                checar(
                    primeiro["assinatura_valida"],
                    f"assinatura HMAC válida: {primeiro['assinatura_valida']}",
                )
                checar(
                    primeiro["payload"].get("chave") == nota["chave"],
                    "payload corresponde à nota emitida",
                )
        finally:
            receptor.parar()

        passo("9. Apuração da competência")
        apuracao = http.post(
            "/v1/apuracoes",
            headers=cabecalho,
            json={"competencia": "2026-11", "provedor": "man"},
        )
        checar(apuracao.status_code == 200, f"POST /v1/apuracoes -> {apuracao.status_code}")
        if apuracao.status_code == 200:
            dados_ap = apuracao.json()
            checar(
                dados_ap["quantidade_documentos"] >= 1,
                f"documentos na apuração: {dados_ap['quantidade_documentos']}, "
                f"ISS {dados_ap['total_iss']}",
            )

            passo("10. Guia (MAN/DNA)")
            guia = http.post(f"/v1/apuracoes/{dados_ap['id']}/guia", headers=cabecalho)
            checar(guia.status_code == 200, f"POST .../guia -> {guia.status_code}")
            if guia.status_code == 200:
                dados_guia = guia.json()
                checar(
                    dados_guia["numero"].startswith("DNA"),
                    f"guia {dados_guia['numero']} vencendo {dados_guia['vencimento']}",
                )

    print(f"\n{'=' * 60}")
    if sucessos == total:
        print(f"{VERDE}TODAS AS {total} VERIFICAÇÕES PASSARAM{ZERAR}")
        return 0
    print(f"{VERMELHO}{total - sucessos} de {total} verificações falharam{ZERAR}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
