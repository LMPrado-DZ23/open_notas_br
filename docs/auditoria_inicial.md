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
| 2 | modelos de município/credencial/webservice | AUSENTE | `Base.metadata` com `app.db.models` importado tem **10 tabelas** (batch_jobs, fiscal_documents, frete_credenciais, invoice_events, invoices, tax_assessments, tenant_certificates, tenant_fiscal_configs, tenants, webhook_deliveries); faltam exatamente ['municipios_nfse', 'credenciais_municipais', 'webservices_sefaz']. Correção de método: a primeira medição retornou 0 tabelas porque os modelos não estavam importados — evidência refeita. |
| 3 | transporte SOAP DF-e | AUSENTE | ocorrências de soap/SOAPAction: 0; existem `app/nfe/gerador.py`, `assinatura.py`, `lote.py` (geração+assinatura+XSD, sem envio) |
| 4 | CalculoAudit | AUSENTE | `CalculoAudit` no código=False; `app/tax/rtc.py` calcula sem auditar |
| 5 | RFC 7807 / circuit breaker / DLQ / rate limit | PARCIAL (RFC 7807 agora ativo) | errors.py=True (módulo testado, handler NÃO registrado); circuit=False; DLQ=False; rate limit=True |
| 6 | hash SHA-256 de XSD no boot | **IMPLEMENTADO (modo WARN)** | verificação de hash de schema=False; schemas versionados sem hash em `tests/fixtures/schemas/` |
| 7 | `Idempotency-Key` por header | **IMPLEMENTADO E TESTADO** | `idempotency_key` existe no body (`app/nfse/schemas.py`); header presente=False |

**Conclusão**: nenhuma das 7 está completa. O item 5 é o único com código novo
(módulo RFC 7807, testado isolado, sem efeito em rotas). Os outros exigem
implementação nova, não correção.

### 5a. RFC 7807 — handler registrado (Etapa B, parte 1)

- `app/main.py`: `@app.exception_handler(StarletteHTTPException)` devolve
  `application/problem+json` preservando **status** e **`detail`**, e repassa os
  headers originais (`WWW-Authenticate`, `Retry-After`, `Allow`).
- Regressão zero comprovada: **921 testes passando** com o handler ativo.
- 3 testes de contrato HTTP em `tests/test_errors_rfc7807.py` (`TestHandlerHTTP`).
- **Ainda ausente**: rate limit por tenant, circuit breaker e DLQ recuperável.

### 5b. Rate limit — núcleo implementado (Etapa B, parte 2)

- `app/core/ratelimit.py`: janela deslizante por tenant com `Protocol` de storage
  (`ArmazenamentoMemoria` para teste/execução single-process; Redis entra na mesma
  interface).
- **Não está ligado ao middleware**: plugar muda comportamento de todas as rotas e
  exige suíte inteira para provar regressão zero. Falta esta etapa.
- 12 testes em `tests/test_ratelimit.py`: janela, bloqueio, `Retry-After`,
  isolamento entre tenants, custo>1, falha aberta com storage fora do ar e
  validação de configuração.
- **Bug encontrado pelo smoke test antes de virar código commitado**: a primeira
  versão incrementava só quando a requisição "cabia", então o total congelava no
  limite e `restante == 0` era lido como permitido — o limitador nunca bloqueava.
  Decisão corrigida para incrementar sempre e comparar com o limite.
- **Segundo bug**: `custo > 1` não era aplicado (eu passava `janela*custo` como TTL
  em vez de incrementar N vezes). Pego pelo teste, não em produção.

## 12. Estado fiscal por documento (capacidade × evidência)

Separado por etapa porque "tem DANFE" não significa "emite NF-e". Cada célula cita o
arquivo/símbolo que comprova.

### NFS-e (padrão nacional)

| Etapa | Estado | Evidência |
|---|---|---|
| Geração (DPS) | ✅ | `app/nfse/dps.py`; valida no `DPS_v1.01.xsd` |
| Assinatura XMLDSig | ✅ | `app/nfse/signer.py` (exclusive C14N + SHA-256, KeyInfo só folha) |
| Transmissão | ✅ **real** | `POST /v1/emissoes` → `201 authorized`, chave `5200258…7690` na Produção Restrita, 25/11/2026 |
| Consulta | ✅ **real** | `GET /v1/emissoes/{id}` → `authorized`; contrato `GET /dps/{id}` e `GET /nfse/{chave}` confirmados com A1 real |
| Cancelamento/eventos | ✅ **real** | `POST .../cancelamento` → `200 cancelled`; 16 tipos de evento validados no XSD |
| PDF (DANFSe) | ✅ | `app/danfse/` → 4.014 bytes no teste real |

### NF-e (modelo 55)

| Etapa | Estado | Evidência |
|---|---|---|
| Geração | ✅ | `app/nfe/gerador.py`, chave de 44 posições com DV módulo 11 |
| Assinatura | ✅ | `app/nfe/assinatura.py` (RSA-SHA1 + C14N inclusiva, exigidos pelo XSD) |
| Validação XSD | ✅ | `nfe_v4.00.xsd` do PL_010h; 20 testes |
| Envelope de lote | ✅ (estrutural) | `app/nfe/lote.py` → `enviNFe` valida no schema |
| **Transmissão SOAP** | ❌ | **não existe**; zero ocorrências de soap/SOAPAction |
| Consulta / eventos / inutilização / CC-e | ❌ | não existem |
| Contingência | ❌ | não existe |
| PDF (DANFE) | ✅ | `app/danfe/a4.py`, `danfe_simplificado`, `etiquetas` |

### NFC-e (modelo 65)

| Etapa | Estado | Evidência |
|---|---|---|
| Geração do XML | ❌ | não existe gerador próprio |
| QR Code / CSC | 🌗 | QR local em `app/danfe/nfce.py` (representação); **CSC não implementado** |
| Transmissão | ❌ | não existe |
| PDF (cupom) | ✅ | `app/danfe/nfce.py`, 80 mm |

### CT-e (57/67)

| Etapa | Estado | Evidência |
|---|---|---|
| Geração do XML | ❌ | não existe |
| Transmissão / eventos | ❌ | não existe |
| PDF (DACTE) | ✅ | `app/danfe/cte.py` |

### MDF-e (58)

| Etapa | Estado | Evidência |
|---|---|---|
| Geração do XML | ❌ | não existe |
| Transmissão / encerramento | ❌ | não existe |
| PDF (DAMDFE) | ✅ | `app/danfe/mdfe.py`, com aviso `[A VALIDAR]` no rodapé |

**Leitura**: só a NFS-e tem ciclo completo validado contra serviço real. NF-e tem
geração, assinatura e validação de schema, **sem transmissão**. NFC-e, CT-e e MDF-e
têm apenas representação impressa.

### 6a. Integridade dos XSD (Etapa G)

- `app/core/schemas.py`: `gerar_manifesto`, `verificar`, `ModoVerificacao.WARN|STRICT`.
- `data/xsd_manifest.json`: 21 schemas com hash SHA-256, versionado — alterar um XSD
  aparece no diff do commit, não só na runtime.
- `scripts/gerar_manifesto_xsd.py`: gera com `--apply`; sem a flag mostra o diff.
- 13 testes em `tests/test_schemas_integridade.py`, incluindo um que confere o
  manifesto real contra os arquivos do repositório.
- Divergência cobre três casos: hash diferente, **arquivo ausente** e **arquivo não
  manifestado** — este último porque schema novo sem registro é tão suspeito quanto
  alterado.
- **Decisão registrada**: modo padrão é `WARN`, não aborto no boot. O R3 do v10.0
  pede abortar, mas nem todo schema aqui tem procedência oficial confirmada (o
  PL_010h veio da referência canônica, não do ZIP do Portal). Derrubar a API por
  schema não confirmado trocaria risco de integridade por risco de indisponibilidade.
  `STRICT` fica disponível para quando a procedência estiver confirmada.
- **Bug de portabilidade pego pelo teste**: `str(relative_to)` produz `\\` no
  Windows e `/` no Linux; o manifesto gerado aqui não casaria no CI. Corrigido com
  `as_posix()`.

### 13. Etapa 2 — estabilização: mock em produção bloqueado

- `app/core/config.py`: `model_validator` recusa `ENVIRONMENT=production` com
  `NFSE_ADAPTER=mock`, com mensagem que diz o que usar.
- Motivo (regra 11 / P4): dublê em produção não falha — responde **sucesso com dado
  inventado**, o pior modo de falha num sistema fiscal. Nota com aparência de
  autorizada e nenhum documento real.
- 5 testes em `tests/test_mock_em_producao.py`: bloqueia em produção, permite em
  `test`, `development` e `staging` (onde o dublê é legítimo), e aceita produção com
  `sefin`.
- Verificado: a suíte inteira (954 testes) usa mock em ambiente `test` e continua
  passando.

### 4a. Auditoria de cálculo — fatia 1 (Etapa C)

- `app/tax/auditoria.py`: `hash_de`, `LaudoCalculo` (hash de entrada, de saída e do
  laudo completo), `TabelaConsultada` com vigência, `tabela_vigente`.
- 18 testes em `tests/test_tax_auditoria.py`.
- Determinismo verificado: mesma entrada → mesmo hash; ordem de chaves irrelevante;
  `Decimal("10.0")` e `Decimal("10.00")` normalizam igual (senão o teste falharia por
  formatação, não por cálculo).
- **Sobreposição de vigência levanta erro em vez de escolher**: duas versões vigentes
  ao mesmo tempo é defeito de cadastro, e escolher uma em silêncio calcularia com a
  tabela errada — exatamente o que a auditoria deve impedir.
- **Pendente (fatia 2)**: tabela `CalculoAudit` com persistência, retenção de 5 anos,
  `tenant_id`, `data_emissao`, consulta por `trace_id` e endpoint admin. O laudo já
  serializa tudo que a tabela precisa; falta o armazenamento e a ligação ao fluxo de
  emissão.

### 4b. `CalculoAudit` — fatia 2, tabela e migração (Etapa C)

- `app/db/models/tax.py`: `CalculoAudit` com 15 colunas e 4 índices
  (`tenant_id`, `trace_id`, `hash_laudo`, e composto `tenant_id+data_emissao`).
- `alembic/versions/0003_calculo_audit.py`: upgrade/downgrade simétricos, com
  `server_default` para que a coluna exista em linha antiga sem backfill manual.
- Guarda o **laudo completo** (entrada, saída, regras, tabelas com versão), não só os
  hashes: hash prova que algo não mudou, não diz o que era. Em fiscalização é preciso
  mostrar o conteúdo; o hash prova que não foi editado depois.
- `invoice_id` com `ON DELETE SET NULL`: apagar a nota não apaga a prova de que o
  cálculo existiu.
- ✅ **`service` implementado e testado contra Postgres real**:
  `app/tax/auditoria_service.py` com `registrar`, `por_trace`, `por_id`,
  `do_documento`, `verificar_integridade`. 11 testes de integração em
  `tests/test_tax_auditoria_db.py` (não mock: usam `sessao_db`).
- `registrar` **não faz commit**: o laudo precisa ser gravado na mesma transação do
  documento. Commitado à parte, uma emissão que falhasse depois deixaria laudo de um
  cálculo que nunca virou nota.
- Isolamento verificado: `por_trace`/`por_id` de outro tenant devolvem vazio/`None`;
  `por_id` de outro tenant devolve `None` e não 403, porque 403 já revelaria que o id
  existe.
- `verificar_integridade` recalcula os hashes do que está gravado: edição por SQL
  manual faz o recálculo não bater. Testado.
- **Bug pego pelos testes de persistência**: `TabelaConsultada.para_dict()` devolvia
  `date` cru, que JSONB não serializa. O laudo em memória funcionava; gravar quebrava.
  Corrigido com ISO na origem.
- ✅ **endpoint implementado**: `app/api/v1/auditoria.py` com
  `GET /v1/tax/audit/{id}`, `GET /v1/tax/audit?trace_id=` e
  `GET /v1/tax/audit/{id}/integridade`. Rotas passaram de 46 para **49**; OpenAPI
  regenerado (o teste de sincronia confere).
- Não existe rota de escrita, de propósito: laudo se grava no fluxo de emissão, nunca
  por API. Aceitar laudo do cliente transformaria a prova em declaração.
- ✅ `app/tax/integracao_emissao.py`: `da_emissao` monta o laudo a partir dos dados da
  emissão (município, UF, regime, cTribNac, alíquota, base, tomador PJ → valor do ISS).
  11 testes em `tests/test_tax_integracao_emissao.py`, incluindo determinismo.
- A entrada guarda **só o que influencia o tributo**, não o payload inteiro: campo
  irrelevante polui a auditoria e aumenta a superfície de dado pessoal.
- Valor ilegível vira `None` em vez de explodir — não inventar número.
- ✅ **ligado ao fluxo**: `POST /v1/emissoes` chama `da_emissao` + `auditoria_service.registrar`
  logo após a fatura existir, na mesma transação.
- ✅ **gravação provada por teste** (`tests/test_tax_laudo_na_emissao.py`, banco real):
  a emissão cria exatamente 1 laudo, com `entrada["base_calculo"] == "10.00"`,
  `data_emissao`, `trace_id` e integridade recalculada OK; reenvio idempotente
  (201 depois 200) **não** cria segundo laudo.
- Item 4 **COMPLETO**: persistência auditável, versão das regras/tabelas, hash de
  entrada e saída, tenant, data de emissão, consulta e ligação ao fluxo — tudo verificado
  por execução.
- **VERIFICADO no Postgres** (containers `open-notas-br-postgres-1`, porta 55434):

  ```
  alembic upgrade head    -> 0001->0002, 0002->0003
  alembic downgrade -1    -> 0003->0002 (current: 0002)
  alembic upgrade head    -> 0002->0003 (current: 0003 head)
  ```

  Round-trip completo, sem erro. Tabela confirmada com **15 colunas** por
  `information_schema`: `id, tenant_id, invoice_id, trace_id, versao_formato,
  hash_entrada, hash_saida, hash_laudo, data_emissao, regras, tabelas, entrada,
  saida, created_at, updated_at` — `tenant_id`, hashes e JSONB todos `NOT NULL`.

### 5c. Circuit breaker — núcleo implementado (Etapa H, parte 1)

- `app/core/circuit.py`: `CircuitBreaker` com estados `FECHADO`/`ABERTO`/`MEIO_ABERTO`,
  `limite_falhas`, `espera_s`, `retry_after_s`, `resetar`. Sem dependência nova —
  `aiobreaker` exigiria ADR (R9) e não traz nada que 90 linhas não resolvam aqui.
- 10 testes em `tests/test_circuit.py` com relógio injetado (sem `sleep`).
- **Só falha transitória conta.** Rejeição fiscal definitiva não abre o circuito: o
  serviço está no ar e respondendo; abrir por erro do nosso lado pararia de emitir.
- Circuito **por UF**: queda em GO não pode parar SP. Testado.
- **Ainda ausente**: ligação ao worker real, DLQ com replay autenticado e o endpoint
  admin `POST /v1/admin/dlq/{id}/replay`.

### 2a. `municipios_nfse` — tabela criada e verificada (Etapa D)

- `app/db/models/municipio.py`: `MunicipioNFSe` + enums `ProvedorNFSe` (17 valores) e
  `EncodingXML`. 19 colunas.
- `alembic/versions/0004_municipios_nfse.py`: upgrade/downgrade **executados** no
  Postgres (0004 → 0003 → 0004, `current` em `0004 head`).
- **Constraints testadas por INSERT real**, não só escritas:
  - `codigo_ibge='520025'` (6 dígitos) → `ERROR ... ck_municipios_nfse_ibge_7_digitos`
  - `fonte_url='http://...'` → `ERROR ... ck_municipios_nfse_fonte_https`
  - linha válida → insere normalmente
- `fonte_url` NOT NULL e `https://` obrigatório: R3 exige origem rastreável, e URL fiscal
  em texto claro é falha de segurança.
- `homologado` nasce **falso**: nada é "homologado" só por estar cadastrado.
- **Pendente**: `credenciais_municipais`, `webservices_sefaz`, seed IBGE e as rotas de
  gestão.

### 2b. `webservices_sefaz` — tabela criada e verificada (Etapa D)

- `app/db/models/webservice_sefaz.py` + migration `0005`. 13 colunas.
- Migration **executada**: 0005 → 0004 → 0005, `current` em `0005 head`.
- **Constraints testadas por INSERT real**:
  - `url='http://x'` → `ERROR ... ck_webservices_sefaz_url_https`
  - segundo registro com mesma `(uf, ambiente, servico)` →
    `ERROR ... uq_webservices_sefaz_endpoint`
- Enum `ServicoSefaz` com 10 serviços (autorização, retorno, status, distribuição,
  evento, inutilização para NF-e; recepção/evento para CT-e e MDF-e).
- `fonte_url` NOT NULL e `https://`: P2/R3 — endpoint por UF só é confiável se der para
  mostrar de onde veio.
- **Bug pego na execução**: `Enum(... length=4)` para `VersaoSOAP` estourava
  `ValueError: 4 < 7` (o nome `SOAP_11` tem 7 caracteres). Corrigido para `length=8`.
- **Pendente**: `credenciais_municipais`, seed IBGE e o seed de endpoints das 27 UFs
  (nenhum endpoint foi inserido — a tabela está vazia de propósito, porque popular URL
  sem fonte verificada violaria P2).

### 2c. `credenciais_municipais` (Etapa D)

- `app/db/models/credencial_municipal.py` + migration `0006`. 13 colunas.
- Migration **executada**: 0006 → 0005 → 0006, `current` em `0006 head`.
- **FK testada por INSERT real**: tenant inexistente →
  `ERROR ... fk_credenciais_municipais_tenant_id_tenants`.
- Segredos em `LargeBinary` (`usuario_ws_criptografado`, `senha_ws_criptografada`,
  `token_ws_criptografado`) — **ciphertext, nunca texto claro** (R4/P3). Conferido em
  `information_schema`.
- `ultimo_numero_rps` BIGINT para incremento sob `SELECT ... FOR UPDATE`: sem o lock,
  duas emissões simultâneas leem o mesmo número e o município recusa a segunda por
  duplicidade — falha intermitente que só aparece com carga.
- `ativa` em vez de DELETE: revogar sem perder a ligação com notas já emitidas.
- `UNIQUE (tenant_id, codigo_ibge)`: uma credencial por tenant e município.
- **Pendente**: serviço que sela/abre com `app/core/crypto.py` (AAD = tenant + IBGE), o
  lock propriamente dito, seed IBGE e rotas de gestão.

### 2d. Serviço de credenciais (Etapa D)

- `app/nfse/credenciais.py`: `salvar`, `segredo`, `por_municipio`, `reservar_numero_rps`,
  `desativar`. 10 testes de integração contra Postgres em `tests/test_nfse_credenciais.py`.
- **AAD por município** (`aad_do_tenant(tenant_id) + "|" + codigo_ibge`): blob copiado
  para outro tenant **não abre** — GCM falha na autenticação. Testado.
- **Selo verificado byte a byte**: o teste confirma que o texto claro não aparece no
  ciphertext gravado.
- **Rotação preserva segredo não informado**: trocar só a senha não apaga o token.
- **Numeração** com `with_for_update()`; credencial inativa recusa reserva.
- **Três bugs pegos pelos testes**:
  1. `Cofre` espera **32 bytes crus**, não base64 (erro `tem 44`).
  2. `aad_do_tenant` é **função de módulo**, não método de `Cofre`.
  3. `senha_ws_criptografada` (feminino) vs `usuario_ws_criptografado`: concatenar sufixo
     devolvia `None` em silêncio para senha. Corrigido com mapa explícito.
- **Defeito de infraestrutura de teste encontrado**: `municipios_nfse` não está na lista
  de truncate do `conftest`, então dado vaza entre testes. Contornado com helper
  idempotente; a correção definitiva é incluir as tabelas novas no truncate.

### 14. Defeito de infraestrutura de teste corrigido

- `tests/suporte.py`: a lista `TABELAS` era **escrita à mão com 9 nomes** enquanto o
  metadata tem **14**. Ficavam fora do `TRUNCATE`: `calculo_audit`,
  `credenciais_municipais`, `frete_credenciais`, `municipios_nfse`, `webservices_sefaz`.
- Consequência real: dado vazava entre testes. Um teste passava **por causa da sobra do
  anterior** — pior que falhar, porque o verde não significava nada.
- Corrigido na raiz: `TABELAS = tuple(sorted(Base.metadata.tables))`. Tabela nova entra
  no truncate automaticamente, sem ninguém lembrar de editar a lista.
- Verificado: `len(TABELAS) == 14` e os testes de credencial/auditoria passam sem o
  helper idempotente precisar mascarar a sobra.

### 2e. Seed de municípios (Etapa D)

- `scripts/seed_municipios.py`: lê a API oficial do IBGE
  (`servicodados.ibge.gov.br/api/v1/localidades/municipios`), normaliza e faz upsert por
  `codigo_ibge`.
- **Dois modos**: `--cache` (arquivo versionado, determinístico, sem rede) e `--fetch`
  (baixa da API — ato deliberado). Teste e execução offline usam o cache.
- **Idempotência verificada por execução dupla no Postgres**:
  - 1ª execução: `inseridos: 3 | atualizados: 0 | inalterados: 0`
  - 2ª execução: `inseridos: 0 | atualizados: 0 | inalterados: 3`
  - `SELECT count(*)` = 3 (não 6)
- **Nada de "5.570" no código**: o script imprime `municípios na fonte: N` com o número
  real do arquivo. Constante fixa faria o teste passar quando a fonte muda.
- Preserva `provedor` e `homologado` de linha já existente: re-seed não rebaixa município
  homologado para o padrão.
- `fonte_url` gravada na própria linha (R3): a origem fica no registro, não só no script.
- **Bug pego na execução**: `session_factory` não existe — o nome é `obter_sessionmaker`.
- **Pendente**: carregar o cache real (5.570+) com `--fetch`, e as rotas de gestão.
