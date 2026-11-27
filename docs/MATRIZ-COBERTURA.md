# Matriz de cobertura fiscal — nível de prova por operação

**Referência:** `work/auditoria-e-fase-a` (base `55351cb`), 2026-11-26. Medições em
`docs/auditoria_inicial.md` (§23, §26, §31, §37, §42, §44).

## Como ler

Cada célula diz **o que existe** e **qual prova sustenta**. Prova não é opinião:

| Símbolo | Significa |
|---|---|
| ✅ **teste** | existe código e teste automatizado determinístico (mock de transporte, sem rede) |
| ✅ **real** | houve chamada real ao autorizador, com resposta registrada na auditoria |
| 🔒 **bloqueado** | código existe, falta credencial/credenciamento externo para exercitar |
| ❌ **ausente** | não implementado |

**Nunca** leia ✅ teste como homologação. Teste prova contrato de software; homologação prova
aceitação do autorizador — são níveis diferentes e o projeto os reporta separados.

## NFS-e (padrão nacional, DPS → SEFIN)

| Operação | Estado | Prova | Ambiente validado |
|---|---|---|---|
| Schema de entrada e modelo | ✅ | teste (`test_transporte_schemas`, `nfse/schemas.py`) | local |
| Geração da DPS | ✅ | teste (`nfse/dps.py`) | local |
| Validação XSD | ✅ | teste (`tests/test_schema_dps.py`) | local |
| Assinatura XMLDSig | ✅ | teste (`nfse/signer.py`, ASSIN-004 verifica a assinatura) | local |
| Transporte REST + mTLS | ✅ | teste + **chamada real** (§31) | homologação |
| Autorização (emissão) | ✅ **real** | NFS-e autorizada em Produção Restrita em 25/11/2026 (`REFERENCIAS` §15: chave, consulta, DANFSe e cancelamento aceito); XML guardado traz `cStat=100` e `ambGer=2`; `codigo_status` agora é persistido (§78); `protocolo` nulo porque a NFS-e não tem esse campo | homologação |
| Consulta de DPS/NFS-e | ✅ | teste | local |
| Cancelamento (evento) | ✅ | teste | local |
| Demais eventos | ✅ | teste (`eventos_tipos` com restrições do leiaute) | local |
| PDF (DANFSe) | ✅ | teste (`danfse/`) | local |
| Roteamento por provedor municipal (ABRASF) | 🔒 **sem transporte real** | contrato, roteamento, fluxo RPS/lote e assinatura testados com `TransporteFalso` (§66); **não existe cliente SOAP municipal** e nenhum provedor tem URL/leiaute com fonte oficial no repositório | — |
| Contingência | ❌ | não existe para NFS-e neste projeto | — |

**Sobre o banco de desenvolvimento:** medido em 2026-11-26 e novamente em 2026-11-27 —
`fiscal_documents`: 4 registros, 4 com `xml_autorizado` e `chave`, **0 com `protocolo`**;
`invoices`: 3 `authorized`, 1 `cancelled`, 10 `rejected`, 2 `pending`, 1 `error`, **todos** com
`ambiente = homologacao`.

Esse banco **mistura** execuções em mock com chamadas reais: as chaves que começam com `6718062`
são do adaptador mock (execuções de 2026-11-27 no demo em container); as que começam com `5200258`
(município de Goiânia) datam de 2026-11-25 e correspondem à autorização real documentada em
`REFERENCIAS` §15. Ou seja: **existe autorização real em Produção Restrita**, mas o banco sozinho
não a prova — a prova é a seção §15 com a chave e o ciclo completo.

**Lacuna real e aberta:** `protocolo` nunca é persistido. A nota foi autorizada e o número do
protocolo não entrou no banco. Isso não invalida a autorização, mas impede responder "qual o
protocolo desta NFS-e" a partir do sistema — e é o que a coluna acima registra como pendência.

## NF-e 4.00

| Operação | Estado | Prova | Ambiente validado |
|---|---|---|---|
| Schema de entrada e modelo | ✅ | teste | local |
| Geração do XML | ✅ | teste (`nfe/gerador.py`) | local |
| Validação XSD | ✅ | teste (manifesto SHA-256, §40) | local |
| Assinatura (RSA-SHA1, C14N inclusivo) | ✅ | teste | local |
| Consulta de status | ✅ **real** | `cStat 107` em GO, ES, SC, TO, MT (§31) | homologação |
| Transporte de autorização (`NFeAutorizacao4`) | 🔒 | envelope e transporte testados; **credenciamento SEFAZ-GO ausente** | — |
| Autorização / recibo | 🔒 | depende do item acima | — |
| Cancelamento, CC-e, inutilização | 🔒 | mesmo bloqueio | — |
| Distribuição DF-e / manifestação | ❌ | não implementado | — |
| Contingência (SVC/EPEC/off-line) | ❌ | não implementada | — |
| PDF (DANFE) | ✅ | teste (`danfe/a4.py`) | local |

## NFC-e (modelo 65)

| Operação | Estado | Prova |
|---|---|---|
| Geração | ❌ | `app/nfe/gerador.py` fixa `mod="55"`; parametrizar sem QR Code geraria XML inválido (§23) |
| QR Code / `infNFeSupl` | 🔒 | depende de **CSC por UF**, que só o contribuinte possui |
| Autorização | 🔒 | depende dos dois acima |
| PDF (cupom) | ✅ | teste (`danfe/nfe.py`, representação) |

## CT-e 4.00

| Operação | Estado | Prova | Ambiente validado |
|---|---|---|---|
| Schema, geração, XSD, assinatura | ✅ | testes (`cte/gerador.py`) | local |
| Consulta de status | ✅ **real** | `cStat 107` (SVRS) · MT exigiu POST, GET dava 500 (§31) | homologação |
| Consulta de situação por chave | ✅ **real, por script** | `cStat 236` (§31) — chamada feita por script, **não** por rota da API (§59) | homologação |
| Evento (cancelamento) | ✅ | teste de envio e de XML (montagem + `enviar_evento` com `cnpj`) | local |
| Autorização (`CTeRecepcaoSincV4`) | 🔒 **sem rota** | módulo `cte/transmissao.py` existe e está testado, mas nenhum endpoint o chama (§59) | — |
| Inutilização | ❌ | **serviço não existe no leiaute 4.00** (404 medido com controles que funcionam) | — |
| Contingência | ❌ | não implementada | — |
| PDF (DACTE) | ✅ | teste | local |

## MDF-e 3.00

| Operação | Estado | Prova | Ambiente validado |
|---|---|---|---|
| Schema, geração, XSD, assinatura | ✅ | testes (`mdfe/gerador.py`) | local |
| Consulta de status | ✅ **real** | `cStat 107` (SVRS) | homologação |
| Autorização (`MDFeRecepcaoSinc`) | 🔒 **sem rota** | módulo existe e está testado, sem endpoint (§59) | — |
| Encerramento / eventos | 🔒 | mesmo bloqueio | — |
| Inutilização | ❌ | ausente também no leiaute; o INI de referência não traz a chave | — |
| PDF (DAMDFE) | ✅ | teste | local |

## Catálogo de endpoints

| Documento | Cobertura no catálogo | Prova |
|---|---|---|
| NF-e `NFeStatusServico` | 54/54 (27 UFs x 2 ambientes) | sonda real (§31) |
| CT-e / MDF-e status | 27/27 UFs por ambiente | sonda real |
| Total de endpoints | **864** (55:270, 65:270, 57:162, 58:162) | medido |

Endpoints mortos foram **removidos** do catálogo, não mantidos "por precaução": 108 linhas de
inutilização (404) e 108 de `RET_RECEPCAO` (fluxo assíncrono 3.00, 404). Catálogo com URL morta é
pior que catálogo menor — a primeira emissão falha longe da causa.

## Resumo executivo

| Documento | Gerar | XSD | Assinar | Transmitir | Consultar | PDF |
|---|---|---|---|---|---|---|
| NFS-e | ✅ teste | ✅ teste | ✅ teste | ✅ **real** (Produção Restrita, 25/11/2026) | ✅ teste | ✅ teste |
| NF-e | ✅ teste | ✅ teste | ✅ teste | 🔒 credenciamento | ✅ **real** | ✅ teste |
| NFC-e | ❌ | — | — | 🔒 CSC | — | ✅ teste |
| CT-e | ✅ teste | ✅ teste | ✅ teste | 🔒 credenciamento | ✅ **real** | ✅ teste |
| MDF-e | ✅ teste | ✅ teste | ✅ teste | 🔒 credenciamento | ✅ **real** | ✅ teste |

**Nenhum documento foi autorizado em produção. Nenhuma nota emitida para cliente real.**
