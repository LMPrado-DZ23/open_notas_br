# Plano canônico — Fase 9 (NF-e / SEFAZ) e pendências

Fonte de verdade da **intenção**. Estado atual vem do repositório, dos testes e do
ambiente. Divergência se registra aqui.

Símbolos: ⬜ não iniciado · 🌗 em andamento · ✅ concluído · ⚠️ bloqueado · ❌ falhou · ➡️ próximo

## F9.0 Plano canônico e painel

- ✅ `PLANO.md` criado; painel derivado em `docs/PAINEL.md`
- Aceite: arquivos versionados e consistentes

## F9.1 Cotação real do Melhor Envio (sandbox)

- ⚠️ **Bloqueado pelo proprietário**: exige autorizar o app no navegador
  (`GET /v1/fretes/oauth/iniciar` → abrir a URL → callback)
- Código pronto: OAuth assinado, token selado, cotação por CEP + carrinho
- Aceite: `POST /v1/fretes/cotacao` devolver opções com preço real
- **Não** será marcado ✅ sem chamada real

## F9.2 NF-e 4.00: XML + XSD + assinatura

- ✅ XML gerado (`app/nfe/`), assinado e **validando contra `nfe_v4.00.xsd`**
- ✅ XSDs versionados em `tests/fixtures/schemas/nfe-4.00/` (416 KB)
- ✅ chave de acesso: 44 posições, DV módulo 11
- ✅ algoritmos **CONFIRMADOS no XSD**: `CanonicalizationMethod` e `SignatureMethod`
  são atributos `fixed` (C14N inclusiva e **rsa-sha1**); `Transform` só aceita
  enveloped + C14N inclusiva. O `signxml` recusa SHA-1 por padrão e a recusa é
  desligada numa subclasse isolada, com o motivo documentado.
- Aceite: XML assinado valida contra o XSD — **2 controles negativos** (sem
  assinatura o schema recusa; C14N exclusiva e rsa-sha256 não aparecem)

### ⚠️ Risco aberto: procedência do XSD

Os schemas vieram de repositório de referência, **não do Portal Nacional**. O portal
publica Pacotes de Liberação numerados (PL). Há indicação de **PL_009_V4** (o mais
usado) e **PL_010** (com IBS/CBS, exigido pela Reforma Tributária em 2026).
**Não confirmei qual é o vigente** — e o gerador atual **não emite grupo IBS/CBS**.

Antes de qualquer envio em produção: baixar o PL oficial em Portal Nacional da NF-e
(Documentos > Esquemas XML), substituir os arquivos, registrar a versão aqui e
reavaliar os campos novos.

## F9.3–F9.6 (não iniciadas)

| Fatia | Dependência |
|---|---|
| F9.3 SOAP `NFeStatusServico` SEFAZ-GO homologação | credenciamento NF-e da empresa |
| F9.4 Autorização: lote → recibo → `nfeProc` | F9.3 |
| F9.5 Contingência (SVC/EPEC) | F9.4 |
| F9.6 DANFE do `nfeProc` | F9.4 |

## Decisões registradas

- **Frete cobrado à parte**, não compõe a NFS-e (base do ISS). Padrão e-commerce.
- **NFP-e fora de escopo** (sem padrão nacional publicado).
- **Cancelamento** exige documento autorizado; autor do evento é o CNPJ do
  certificado ativo.

## Evidências da fase anterior (fechadas)

- `POST /v1/emissoes` → `201 authorized`, chave `520025821122233300018100000000000022611076352769`
- `POST .../cancelamento` → `200 cancelled`
- `pytest` → 853 passed · CI verde · 46 rotas

---

## Reconciliação 2026-11-26 — estado real vs. plano

Este bloco existe porque plano e código divergiram durante a evolução para o documento
v10.0. **O plano continua sendo a fonte de verdade da intenção; este bloco é a
reconciliação com o que foi executado.** Detalhe por item em `docs/auditoria_inicial.md`
§15.

### O que o plano previa e não mudou

- F9.0 (plano canônico) — ✅ concluído.
- F9.1 (cotação Melhor Envio real) — ⚠️ continua bloqueada: exige OAuth do proprietário no
  navegador. O código responde 409 dizendo o próximo passo; não finge funcionar.
- F9.2 (NF-e XML + XSD + assinatura) — ✅ concluído, **e o XSD virou PL_010h**.

### O que o plano previa e mudou de escopo

- **F9.3–F9.6 (SOAP SEFAZ-GO)**: o envelope, o cliente, o transporte HTTP e o ciclo de
  autorização estão construídos e testados com transporte falso. A **chamada real**
  continua bloqueada por credenciamento em GO. Não foi possível cumprir o DoD original
  ("ciclo completo em homolog real"), e ele segue pendente.

### O que o plano não previa e entrou

O documento v10.0 trouxe sete lacunas que não estavam neste plano. Cinco foram fechadas:
`CalculoAudit` (item 4), gestão de municípios e credenciais (item 2), hash de XSD (item
6), `Idempotency-Key` por header (item 7) e o conjunto RFC 7807 + rate limit + circuit
breaker + DLQ (item 5).

### O que continua aberto, e por quê

| Item | Bloqueio | Natureza |
|---|---|---|
| F9.3–F9.6 / item 3 (SOAP) | credenciamento NF-e em GO | acesso externo |
| F9.1 (Melhor Envio) | OAuth do proprietário | acesso externo |
| Item 1 (drivers multi-prefeitura) | URL e leiaute oficial por provedor | fonte de dados |
| `pip-audit` no CI | instalar dependência de auditoria | exige ADR (R9) |

**Nenhum desses avança com código.** Registrado para que a próxima sessão não os trate
como esquecimento.
