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

- 🌗 XML gerado (`app/nfe/`) e **validado contra `nfe_v4.00.xsd` oficial** exceto a
  assinatura
- ✅ XSDs oficiais versionados em `tests/fixtures/schemas/nfe-4.00/`
- ✅ chave de acesso de 44 posições com DV módulo 11
- ⚠️ **Assinatura**: o XSD não aceita `rsa-sha256`/`sha256` nos atributos da
  `Signature`. A enumeração exata precisa ser lida do XSD antes de escolher o
  algoritmo — o valor legado (RSA-SHA1) é **hipótese**, não fato, e o `signxml`
  recusa SHA-1 por padrão.
- Aceite: XML **assinado** validando contra o XSD

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
