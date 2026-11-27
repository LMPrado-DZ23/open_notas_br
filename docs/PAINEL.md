# Painel (vista derivada)

> Gerado por `python -m scripts.gerar_painel` em 2026-11-26. **Não editar à mão.**
> Fonte de verdade da intenção: `PLANO.md`. Do estado: código + testes medidos agora.

## Baseline medida

| Métrica | Valor |
|---|---|
| Rotas | 58 |
| Tabelas ORM | 15 |
| Migrations | 11 (head `0011`) |
| Testes aprovados | 1471 |
| Municípios no seed | 5571 (IBGE, 27 UFs) |
| Postgres de teste | porta 55434, db `notasbr` |

## Lacunas do documento v10.0

Atualizado em 2026-11-27 (auditoria §61). O que mudou desde a primeira versão deste painel está
marcado na coluna "o que falta" — as células antigas diziam "AUSENTE" para coisas que já existem.

| # | Lacuna | Estado | O que falta |
|---|---|---|---|
| 1 | Drivers NFS-e multi-prefeitura | 🌗 PARCIAL | contrato, roteamento e motor ABRASF existem e são testados, mas **não estão ligados** ao `nfse/servico.py` (§59) |
| 2 | Modelos município/credencial/webservice + rotas | ✅ | conectividade no cadastro (sem endpoint real por município) |
| 3 | Transporte SOAP DF-e | 🌗 PARCIAL | transporte testado e status **real** medido (`cStat 107`); **autorização sem rota e sem credenciamento** |
| 4 | `CalculoAudit` | ✅ | — |
| 5 | RFC 7807 / circuit / DLQ / rate limit | 🌗 PARCIAL | circuit no fluxo, DLQ de webhook e rate limit **instalado**; falta traces (ADR 0003) |
| 6 | Hash SHA-256 de XSD | ✅ | substituir pelo ZIP oficial do Portal Nacional |
| 7 | `Idempotency-Key` por header | ✅ | concorrência e corpo divergente cobertos (§55, §57) |

## Fatias do plano original (F9)

| Fatia | Estado |
|---|---|
| F9.0 Plano canônico | ✅ |
| F9.1 Cotação Melhor Envio real | ⚠️ bloqueado (OAuth do proprietário) |
| F9.2 NF-e XML + XSD + assinatura | ✅ |
| F9.3 SOAP SEFAZ-GO | 🌗 transporte pronto, **sem rota de autorização** |
| F9.4 Autorização NF-e | 🔒 credenciamento |
| F9.5 Contingência | ⬜ |
| F9.6 DANFE do nfeProc | ✅ |

## Estado fiscal por documento

Prova por capacidade em `docs/MATRIZ-COBERTURA.md`; aqui é o resumo. "Módulo" = existe e é testado,
**sem rota** (não é capacidade da API).

| Documento | Geração | Assinatura | Transmissão | Consulta | PDF |
|---|---|---|---|---|---|
| NFS-e | ✅ | ✅ | ✅ real (homologação) | ✅ | ✅ |
| NF-e | ✅ | ✅ | 🔒 credenciamento | ✅ real (status) | ✅ |
| NFC-e | ❌ falta CSC | ❌ | 🔒 | ❌ | ✅ |
| CT-e | ✅ | ✅ | 🔒 módulo, sem rota | ✅ real (status) | ✅ |
| MDF-e | ✅ | ✅ | 🔒 módulo, sem rota | ✅ real (status) | ✅ |

## Bloqueios externos

1. `pip-audit` não instalado — **decidido no ADR 0002**, com gatilho (não é pendência esquecida)
2. OAuth do Melhor Envio (só o proprietário)
3. Credenciamento NF-e em Goiás
4. Admin auth — **resolvido no ADR 0001** (chave estática, desligada por padrão)
5. CSC por UF (NFC-e) e inutilização de CT-e/MDF-e (serviço inexistente no leiaute 4.00)
