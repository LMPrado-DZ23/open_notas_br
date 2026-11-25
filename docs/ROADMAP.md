# Roadmap — 6 fases

Cada fase tem Definition of Done verificável. Não se avança por calendário, e sim
por evidência: teste passando, container healthy, chamada real respondendo.

## Fase 1 — Fundação do repositório ✅ concluída

**Entregue**

- `docker compose up --build` sobe API, worker, PostgreSQL 16 e Redis 7; serviço
  one-shot `migrate` aplica as migrações antes da API e do worker.
- `/health` (readiness, com banco e Redis) e `/health/live` (liveness).
- Migração `0001` com as 9 tabelas base, verificada com `alembic check`.
- Multi-tenant: criação de tenant, API key só como hash, rotação, isolamento,
  configuração fiscal por município/ambiente.
- Cofre AES-256-GCM (primitivas) e assinatura HMAC de webhook já testados.
- Worker ARQ com `ping` e `heartbeat`, e healthcheck próprio que prova
  processamento, não apenas processo vivo.
- 212 testes, ruff limpo, `openapi.json` gerado.

**Evidência coletada nesta máquina**

```
docker compose ps  ->  api healthy, worker healthy, postgres healthy, redis healthy
curl /health       ->  HTTP 200 {"status":"ok", database.ok=true, redis.ok=true}
alembic check      ->  No new upgrade operations detected.
pytest             ->  212 passed
```

**Pendências humanas desta fase**

- Confirmar se `MASTER_ENCRYPTION_KEY` será gerenciada por KMS/secret manager ou
  por arquivo `.env` no host. A aplicação exige a chave em produção; *onde* ela
  mora é decisão de operação.

## Fase 2 — Cofre de certificados A1 + assinatura XML ✅ concluída

**DoD**

- Upload de `.pfx`/`.p12` cifrado com AES-256-GCM usando a chave-mestra.
- Teste unitário de cifra/decifra e de extração de validade e CNPJ do certificado.
- Assinatura XMLDSig válida contra fixture de DPS.
- Certificado descriptografado apenas em memória.

**Entregue**: `POST /v1/me/certificados` (upload multipart, selagem AES-256-GCM,
metadados, 409 em duplicata), `GET`/`DELETE`/`ativar`/`saude`; assinatura XMLDSig
RSA-SHA256 com C14N exclusiva e `Signature` sem prefixo; DPS 1.01 montada com
validação de forma; emissão fim-a-fim idempotente.

**Risco declarado:** o certificado de teste é autoassinado e gerado em execução —
nunca commitado. Assinatura que valida contra ele **não** prova aceitação pela
SEFIN; isso é homologação, não teste unitário.

## Fase 3 — Motor tributário + CNPJ + NFS-e (parcial)

**DoD**

- Consulta de CNPJ com cache, limite de requisições e fallback para dados abertos.
- Calculadora IBS/CBS com alíquotas versionadas por competência (2026: CBS 0,9%,
  IBS 0,1%), com parâmetros explícitos.
- Montagem de DPS assinada.
- `SefinNacionalAdapter` com emissão, consulta por chave e cancelamento, com a URL
  base vinda de configuração e mocks para os endpoints **[A VALIDAR]**.
- Teste de integração emite nota mockada e devolve XML autorizado simulado.

**Já entregue antes do previsto**: montagem de DPS assinada, adapter real com
emissão/consulta/cancelamento, emissão idempotente e CNPJ alfanumérico
(IN RFB 2.229/2024, validado contra o exemplo oficial).

**Falta**: consulta de CNPJ com cache e fallback para dados abertos, e endpoint
de simulação IBS/CBS.

## Fase 4 — DANFSe local + DANFE adapter + apuração/guias

**DoD**

- DANFSe v2 gerado localmente a partir do XML, com seção IBS/CBS, e teste de
  fidelidade XML → PDF conferindo campos obrigatórios.
- Adapter de DANFE com interface unificada.
- Apuração por tenant e competência, com provedores MAN/DNA, DAS e guia municipal.

**Divergência a resolver antes de começar:** o briefing cita NT 008 v1.02
(14/07/2026); a referência local implementa v1.01 (30/06/2026). A versão entra como
parâmetro do gerador, para que a troca seja de template e não de código.

## Fase 5 — Worker de fila, lotes e webhooks

**DoD**

- Job de emissão com transição `PENDING → PROCESSING → AUTHORIZED | REJECTED | ERROR`.
- Importação em lote (CSV/planilha) com relatório de sucesso/falha por linha.
- Webhook assinado com HMAC-SHA256, retry com backoff exponencial, registro em
  `webhook_deliveries`.

## Fase 6 — Conectores DZ23 e Brizu + OpenAPI

**DoD**

- Contrato de entrada/saída para DZ23 (venda/fatura paga → emissão) e Brizu
  (agendamento/atendimento pago → emissão).
- Exemplo de chamada fim-a-fim com mocks.
- `openapi.json` cobrindo todos os endpoints e guia de integração por parceiro.

## Escopo ampliado (solicitado após a Fase 1)

O pedido inicial cobria NFS-e, DANFSe e um adapter de NF-e/DANFE. O solicitante
acrescentou, com imagens de referência: **DANFE Simplificado – Etiqueta**,
**etiqueta de envio por volume** (estilo marketplace), e os documentos **CT-e,
MDF-e e NFP-e**. São três fases novas, além das seis originais.

Detalhe de campos e decisões em [DOCUMENTOS-FISCAIS.md](DOCUMENTOS-FISCAIS.md).

### Fase 7 — NF-e e NFC-e completas

- Emissão de NF-e (55) e NFC-e (65): montagem, assinatura, envio, consulta de
  recibo, tratamento de `cStat`.
- Eventos: cancelamento, carta de correção, inutilização de numeração.
- **DANFE A4** a partir do XML autorizado.
- **DANFE Simplificado – Etiqueta** (chave em Code128, protocolo, emitente,
  operação 0/1, destinatário, valor total).
- **DANFE NFC-e** (cupom) para PDV.
- **Etiqueta de envio por volume**: `Volume i/n`, peso, nº da nota, coleta,
  destinatário, remetente, um código de barras por volume.
- Cobertura de rejeição: mapear os códigos de rejeição mais comuns da SEFAZ para
  mensagem acionável, sem perder o código original.

### Fase 8 — CT-e e MDF-e

- CT-e (57) e CT-e OS (67): emissão, DACTE, cancelamento.
- MDF-e (58): abertura, inclusão de NF-e, encerramento, DAMDFE.
- Vínculo MDF-e ↔ NF-e: o manifesto referencia as chaves das notas da carga;
  a consistência entre eles é regra de negócio, não detalhe de layout.

### Fase 9 — NFP-e e logística

- NFP-e conforme a UF do emitente (layout e autorizador estaduais).
- Etiqueta de envio com integração logística: código de rastreio, coleta,
  consolidação por volume.
- Impressão em lote (ZPL/PDF) e reimpressão por volume.

**Risco declarado:** NFP-e é estadual e heterogêneo; assim como NFS-e municipal, não
será implementado pela metade. Se a UF alvo não estiver confirmada, a fase entra
como adapter com layout por UF e apenas as UFs validadas habilitadas.

## Critério de go-live


1. `docker compose up` sobe tudo e o healthcheck responde.
2. Todos os testes passam, com cobertura ≥ 80% nos módulos fiscais e de segurança.
3. Fluxo mockado demonstrável: criar tenant → upload de A1 → emitir NFS-e (mock
   SEFIN) → gerar DANFSe local → disparar webhook assinado.
4. README separa o que está pronto para produção restrita do que depende de
   homologação oficial.
5. Nenhum segredo no repositório.

**Fora do critério, e de propósito:** ligar produção real. Isso exige certificado
A1 válido, credenciamento municipal/SEFIN e teste em ambiente de homologação — nada
disso é alcançável por código neste ambiente.

## Fora do roadmap

- Substituir contador ou emitir parecer fiscal.
- Classificação fiscal automática de produto.
- Emissão em produção sem homologação validada antes.
- "DART nacional unificado": não existe. Guias são MAN/DNA, DAS e municipal.
