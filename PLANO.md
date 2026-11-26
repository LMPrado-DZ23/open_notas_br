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

- `POST /v1/emissoes` → `201 authorized`, chave `52002582264339333000122000000000000226110763527690`
- `POST .../cancelamento` → `200 cancelled`
- `pytest` → 853 passed · CI verde · 46 rotas
