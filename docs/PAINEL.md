# Painel (vista derivada)

> Gerado por `python -m scripts.gerar_painel` em 2026-11-26. **Não editar à mão.**
> Fonte de verdade da intenção: `PLANO.md`. Do estado: código + testes medidos agora.

## Baseline medida

| Métrica | Valor |
|---|---|
| Rotas | 55 |
| Tabelas ORM | 15 |
| Migrations | 7 (head `0007`) |
| Testes aprovados | 1143 |
| Municípios no seed | 5571 (IBGE, 27 UFs) |
| Postgres de teste | porta 55434, db `notasbr` |

## Lacunas do documento v10.0

| # | Lacuna | Estado | O que falta |
|---|---|---|---|
| 1 | Drivers NFS-e multi-prefeitura | 🌗 PARCIAL | só padrão nacional; falta URL/leiaute oficial por provedor |
| 2 | Modelos município/credencial/webservice + rotas | ✅ | conectividade no cadastro (sem endpoint real por município) |
| 3 | Transporte SOAP DF-e | ❌ AUSENTE | credenciamento NF-e em GO |
| 4 | `CalculoAudit` | ✅ | — |
| 5 | RFC 7807 / circuit / DLQ / rate limit | 🌗 PARCIAL | injetar circuit no fluxo, admin auth, métrica |
| 6 | Hash SHA-256 de XSD | ✅ | substituir pelo ZIP oficial do Portal Nacional |
| 7 | `Idempotency-Key` por header | ✅ | — |

## Fatias do plano original (F9)

| Fatia | Estado |
|---|---|
| F9.0 Plano canônico | ✅ |
| F9.1 Cotação Melhor Envio real | ⚠️ bloqueado (OAuth do proprietário) |
| F9.2 NF-e XML + XSD + assinatura | ✅ |
| F9.3 SOAP SEFAZ-GO | ⬜ |
| F9.4 Autorização NF-e | ⬜ |
| F9.5 Contingência | ⬜ |
| F9.6 DANFE do nfeProc | ⬜ |

## Estado fiscal por documento

| Documento | Geração | Assinatura | Transmissão | Consulta | PDF |
|---|---|---|---|---|---|
| NFS-e | ✅ | ✅ | ✅ real | ✅ real | ✅ |
| NF-e | ✅ | ✅ | ❌ | ❌ | ✅ |
| NFC-e | ❌ | ❌ | ❌ | ❌ | ✅ |
| CT-e | ❌ | ❌ | ❌ | ❌ | ✅ |
| MDF-e | ❌ | ❌ | ❌ | ❌ | ✅ |

## Bloqueios externos

1. `pip-audit` não instalado (exige ADR pela R9)
2. OAuth do Melhor Envio (só o proprietário)
3. Credenciamento NF-e em Goiás
4. Modelo de admin auth (**decisão do proprietário**)
