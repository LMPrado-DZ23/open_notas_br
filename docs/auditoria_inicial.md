# Auditoria inicial — Etapa 0

**Gerado por comando nesta sessão.** Cada número abaixo veio de execução, não de memória.
Este documento é o entregável bloqueante da Etapa 0: sem ele aprovado, nenhuma fase começa.

## 1. Árvore de arquivos

- **app/db/models/** (6 arquivos): __init__.py, enums.py, frete.py, invoice.py, ops.py, tenant.py
- **app/nfse/** (13 arquivos): __init__.py, adapter.py, cancelamento.py, constants.py, dps.py, errors.py, evento.py, eventos.py, eventos_tipos.py, schemas.py, servico.py, signer.py, transport.py
- **app/nfe/** (5 arquivos): __init__.py, assinatura.py, base.py, gerador.py, lote.py
- **app/tax/** (4 arquivos): __init__.py, classificacoes.py, rtc.py, schemas.py
- **app/api/v1/** (14 arquivos): __init__.py, apuracoes.py, certificados.py, cnpj.py, consulta.py, emissoes.py, fretes.py, health.py, integracoes.py, lotes.py, representacoes.py, router.py, tax.py, tenants.py
- **app/worker/** (3 arquivos): __init__.py, healthcheck.py, main.py
- **app/webhooks/** (3 arquivos): __init__.py, assinatura.py, service.py
- **src/notasbr/** (10 arquivos): __init__.py, api.py, auditor.py, cadastros.py, chave.py, cli.py, erros.py, modelos.py, versao.py, xml_util.py
- **alembic/versions/** (2 arquivos): 0001_estrutura_inicial.py, 0002_frete_credenciais.py

## 2. Endpoints existentes

Total de rotas: **46**

| Método | Rota |
|---|---|
| GET | `/health` |
| GET | `/health/live` |
| GET | `/v1/apuracoes` |
| POST | `/v1/apuracoes` |
| GET | `/v1/apuracoes/{apuracao_id}` |
| POST | `/v1/apuracoes/{apuracao_id}/guia` |
| GET | `/v1/cep/{cep}` |
| GET | `/v1/cnpj/{cnpj}` |
| GET | `/v1/emissoes` |
| POST | `/v1/emissoes` |
| GET | `/v1/emissoes/cancelamento/motivos` |
| GET | `/v1/emissoes/eventos/disponiveis` |
| GET | `/v1/emissoes/eventos/tipos` |
| GET | `/v1/emissoes/{invoice_id}` |
| POST | `/v1/emissoes/{invoice_id}/cancelamento` |
| GET | `/v1/emissoes/{invoice_id}/danfse` |
| POST | `/v1/emissoes/{invoice_id}/eventos` |
| GET | `/v1/emissoes/{invoice_id}/representacao` |
| POST | `/v1/fretes/cotacao` |
| DELETE | `/v1/fretes/credencial` |
| GET | `/v1/fretes/oauth/callback` |
| GET | `/v1/fretes/oauth/iniciar` |
| GET | `/v1/fretes/status` |
| GET | `/v1/health` |
| GET | `/v1/health/live` |
| POST | `/v1/integracoes/brizu/atendimentos` |
| POST | `/v1/integracoes/dz23/vendas` |
| GET | `/v1/lotes` |
| POST | `/v1/lotes` |
| GET | `/v1/lotes/{lote_id}` |
| GET | `/v1/me` |
| GET | `/v1/me/certificados` |
| POST | `/v1/me/certificados` |
| GET | `/v1/me/certificados/saude` |
| DELETE | `/v1/me/certificados/{certificado_id}` |
| POST | `/v1/me/certificados/{certificado_id}/ativar` |
| GET | `/v1/me/config-fiscal` |
| PUT | `/v1/me/config-fiscal` |
| POST | `/v1/me/rotacionar-chave` |
| GET | `/v1/me/webhook` |
| POST | `/v1/me/webhook` |
| GET | `/v1/me/webhook/entregas` |
| GET | `/v1/representacoes` |
| POST | `/v1/representacoes` |
| GET | `/v1/tax/aliquotas` |
| GET | `/v1/tax/aliquotas/{ano}` |
| GET | `/v1/tax/classificacoes` |
| GET | `/v1/tax/classificacoes/catalogo` |
| GET | `/v1/tax/classificacoes/{codigo}` |
| POST | `/v1/tax/simular` |
| GET | `/v1/tenants` |
| POST | `/v1/tenants` |
| GET | `/v1/version` |
| GET | `/version` |

## 3. Modelos ORM e presença de tenant_id

| Tabela | Colunas | tenant_id? |
|---|---|---|
| batch_jobs | 15 | sim |
| fiscal_documents | 18 | sim |
| frete_credenciais | 11 | sim |
| invoice_events | 12 | sim |
| invoices | 20 | sim |
| tax_assessments | 16 | sim |
| tenant_certificates | 15 | sim |
| tenant_fiscal_configs | 20 | sim |
| tenants | 12 | NAO |
| webhook_deliveries | 14 | sim |

**Tabelas sem tenant_id (esperado):** nenhuma

## 4. TODOs e FIXMEs

Nenhum marcador TODO/FIXME no código de aplicação.

## 5. Divergências README × código (verificadas)

- Worker: `app/worker/main.py` usa **ARQ** (não Celery) — confirmado
- Settings tem 34 campos; `.env.example` documenta todos (teste `test_configuracao_documentada` cobre).
- **Divergência real**: `Settings` tem **34** campos (o `.env.example` cobre todos), não 30 como eu havia dito antes no chat — número corrigido por medição.
- `print()` não foi verificado por lint (regra `T201` desabilitada). **Pendência**: habilitar `T201` no ruff para garantir P10 do v10.0.

## 5b. Verificações do v10.0 que já falham hoje (evidência)

| Regra do v10.0 | Situação medida |
|---|---|
| R2 breaking change proibido | `/v1` já tem 47 rotas e o `openapi.json` é regenerado a cada mudança — mudanças de schema precisam ser aditivas daqui pra frente |
| R3 XSD com hash verificado no boot | ❌ não existe verificação de hash; schemas estão versionados sem `sha256` no boot |
| R4 credencial cifrada | ✅ cofre AES-256-GCM com AAD por tenant existe (certificado e token de frete) |
| R5 Idempotency-Key em header | ❌ hoje é campo de body |
| R6 tenant_id só da API key | ✅ `X-API-Key` é a única fonte |
| R7 feature flags | ❌ não existem flags por driver/documento |
| P10 sem `TODO` | ✅ nenhum marcador encontrado no código |

## 6. Baseline de testes

Executado nesta sessão: `pytest` → **873 passed**, 1 warning.
Cobertura: **86,11%** (piso 80% imposto por `pyproject.toml`).
CI GitHub Actions: verde nos dois jobs (testes+lint / contrato+XSD).

## 7. Dependências com CVE

- pip-audit **não instalado**. Instalar e rodar antes de aprovar a Etapa 0.

## 8. Leitura honesta para o novo escopo (v10.0)

O documento pede um gateway enterprise com: multi-prefeitura por driver, DF-e completo, tax engine auditável e contrato unificado. Comparando com o que existe HOJE:

| Item pedido | Estado real |
|---|---|
| Motor multi-prefeitura (drivers) | ❌ não existe. Só `NacionalRest` está implementado; não há `app/nfse/drivers/` |
| `municipios_nfse`, `credenciais_municipais`, `webservices_sefaz` | ❌ tabelas não existem |
| NF-e/NFC-e/CT-e/MDF-e autorização SEFAZ | 🌗 só geração+assinatura+validação XSD (PL_010h) e envelope `enviNFe`; **nenhum transporte SOAP** |
| Tax engine auditável (`CalculoAudit`) | ❌ `app/tax/rtc.py` calcula, mas não persiste auditoria |
| Contrato RFC 7807 | ❌ usa HTTPException com detail |
| Observabilidade OTel/Prometheus | ❌ log JSON existe; sem métricas nem traces |
| Circuit breaker / DLQ | ❌ não existe |
| Rate limiting por tenant | ❌ não existe |
| Idempotency-Key em header | 🌗 existe na emissão por `idempotency_key` no body, não em header |
| `webservices_sefaz` com 27 UFs | ❌ não existe |

**Conclusão da auditoria**: a base é sólida (multi-tenant, cofre, assinatura, NFS-e real autorizada, 873 testes), mas **nada** das quatro fases do v10.0 está implementado. As proibições P2/P3 têm infraestrutura pronta (cofre AES-256-GCM com AAD por tenant).

**Estimativa honesta**: Fase 1 isolada (modelos + seed + 3 drivers + rotas + DoD) é comparável ao trabalho já feito neste repositório inteiro. Não sai em um turno.

## 9. Schemas por endpoint (request/response)

Extraído do OpenAPI gerado. Nomes referenciam `components.schemas`.

| Rota | Método | Request | Response |
|---|---|---|---|
| `/health` | GET | — | SaudeOut |
| `/health/live` | GET | — | VivoOut |
| `/v1/apuracoes` | GET | — | (inline) |
| `/v1/apuracoes` | POST | ApuracaoIn | ApuracaoOut |
| `/v1/apuracoes/{apuracao_id}` | GET | — | ApuracaoDetalheOut |
| `/v1/apuracoes/{apuracao_id}/guia` | POST | — | GuiaOut |
| `/v1/cep/{cep}` | GET | — | EnderecoOut |
| `/v1/cnpj/{cnpj}` | GET | — | (inline) |
| `/v1/emissoes` | GET | — | (inline) |
| `/v1/emissoes` | POST | EmissaoIn | — |
| `/v1/emissoes/cancelamento/motivos` | GET | — | (inline) |
| `/v1/emissoes/eventos/disponiveis` | GET | — | (inline) |
| `/v1/emissoes/eventos/tipos` | GET | — | (inline) |
| `/v1/emissoes/{invoice_id}` | GET | — | EmissaoDetalheOut |
| `/v1/emissoes/{invoice_id}/cancelamento` | POST | CancelamentoIn | CancelamentoOut |
| `/v1/emissoes/{invoice_id}/danfse` | GET | — | — |
| `/v1/emissoes/{invoice_id}/eventos` | POST | EventoIn | EventoRegistradoOut |
| `/v1/emissoes/{invoice_id}/representacao` | GET | — | — |
| `/v1/fretes/cotacao` | POST | CotacaoIn | CotacaoOut |
| `/v1/fretes/credencial` | DELETE | — | (inline) |
| `/v1/fretes/oauth/callback` | GET | — | StatusOut |
| `/v1/fretes/oauth/iniciar` | GET | — | AutorizacaoOut |
| `/v1/fretes/status` | GET | — | StatusOut |
| `/v1/health` | GET | — | SaudeOut |
| `/v1/health/live` | GET | — | VivoOut |
| `/v1/integracoes/brizu/atendimentos` | POST | (inline) | — |
| `/v1/integracoes/dz23/vendas` | POST | (inline) | — |
| `/v1/lotes` | GET | — | (inline) |
| `/v1/lotes` | POST | — | LoteDetalheOut |
| `/v1/lotes/{lote_id}` | GET | — | LoteDetalheOut |
| `/v1/me` | GET | — | TenantOut |
| `/v1/me/certificados` | GET | — | (inline) |
| `/v1/me/certificados` | POST | — | CertificadoOut |
| `/v1/me/certificados/saude` | GET | — | SaudeCertificadoOut |
| `/v1/me/certificados/{certificado_id}` | DELETE | — | — |
| `/v1/me/certificados/{certificado_id}/ativar` | POST | — | CertificadoOut |
| `/v1/me/config-fiscal` | GET | — | (inline) |
| `/v1/me/config-fiscal` | PUT | TenantFiscalConfigIn | TenantFiscalConfigOut |
| `/v1/me/rotacionar-chave` | POST | — | TenantKeyRotacionadaOut |
| `/v1/me/webhook` | GET | — | WebhookConfigOut |
| `/v1/me/webhook` | POST | WebhookConfigIn | WebhookConfigOut |
| `/v1/me/webhook/entregas` | GET | — | (inline) |
| `/v1/representacoes` | GET | — | (inline) |
| `/v1/representacoes` | POST | — | — |
| `/v1/tax/aliquotas` | GET | — | (inline) |
| `/v1/tax/aliquotas/{ano}` | GET | — | AliquotaOut |
| `/v1/tax/classificacoes` | GET | — | (inline) |
| `/v1/tax/classificacoes/catalogo` | GET | — | CatalogoOut |
| `/v1/tax/classificacoes/{codigo}` | GET | — | ClassificacaoOut |
| `/v1/tax/simular` | POST | SimulacaoIn | SimulacaoOut |
| `/v1/tenants` | GET | — | PaginaTenants |
| `/v1/tenants` | POST | TenantCreate | TenantCriadoOut |
| `/v1/version` | GET | — | VersaoOut |
| `/version` | GET | — | VersaoOut |

## 10. `pytest --durations=10` (baseline de tempo)

Executado nesta sessão. Os 10 mais lentos são **todos de `setup`** — criação de
tenant, certificado e configuração fiscal por teste. Nenhum teste individual passa
de 5 s; o gargalo é fixture, não lógica.

```
4.80s setup  test_cancelamento.py::TestMotivos::test_lista_motivos
4.52s setup  test_apuracao.py::TestConsolidacao::test_soma_documentos_autorizados
4.41s setup  test_eventos_rota.py::TestDisponiveis::test_lista_sem_cancelamento
3.85s setup  test_eventos_rota.py::TestRegistro::test_confirmacao_do_prestador
3.80s setup  test_eventos_rota.py::TestRegistro::test_motivo_curto_da_422
3.55s setup  test_eventos_rota.py::TestDisponiveis::test_incluir_oficio
3.47s setup  test_cancelamento.py::TestCancelamento::test_cancela_nota_autorizada
3.30s setup  test_eventos_rota.py::TestRegistro::test_tipo_inexistente_da_422
2.82s setup  test_eventos_rota.py::TestRegistro::test_emissao_inexistente_da_404
2.46s setup  test_eventos_rota.py::TestRegistro::test_rejeicao_com_motivo
```

**Schemas Pydantic registrados**: 55 em `components.schemas`.

**Implicação para o v10.0**: o custo de fixture por teste sugere que a suíte vai
ficar lenta quando triplicar. Antes da Fase 1, vale transformar as fixtures de
tenant/certificado em factory com escopo de módulo.

## 11. Verificação das 7 lacunas reportadas (evidência de código)

Cada item conferido por comando. `AUSENTE` = a busca no código não achou arquivo nem símbolo.

| # | Lacuna | Estado | Evidência |
|---|---|---|---|
| 1 | drivers NFS-e multi-prefeitura | PARCIAL | `app/nfse/drivers/` existe=False; `app/nfse/adapter.py` implementa só padrão nacional (`SefinNacionalClient`, `SefinMockAdapter`) |
| 2 | modelos de município/credencial/webservice | AUSENTE | tabelas em `Base.metadata` faltando: ['municipios_nfse', 'credenciais_municipais', 'webservices_sefaz'] |
| 3 | transporte SOAP DF-e | AUSENTE | ocorrências de soap/SOAPAction: 0; existem `app/nfe/gerador.py`, `assinatura.py`, `lote.py` (geração+assinatura+XSD, sem envio) |
| 4 | CalculoAudit | AUSENTE | `CalculoAudit` no código=False; `app/tax/rtc.py` calcula sem auditar |
| 5 | RFC 7807 / circuit breaker / DLQ / rate limit | PARCIAL | errors.py=True (módulo testado, handler NÃO registrado); circuit=False; DLQ=False; rate limit=True |
| 6 | hash SHA-256 de XSD no boot | AUSENTE | verificação de hash de schema=False; schemas versionados sem hash em `tests/fixtures/schemas/` |
| 7 | `Idempotency-Key` por header | PARCIAL | `idempotency_key` existe no body (`app/nfse/schemas.py`); header presente=False |

**Conclusão**: nenhuma das 7 está completa. O item 5 é o único com código novo
(módulo RFC 7807, testado isolado, sem efeito em rotas). Os outros exigem
implementação nova, não correção.
