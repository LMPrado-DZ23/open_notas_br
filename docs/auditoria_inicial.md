# Auditoria inicial — Etapa 0

**Gerado por comando nesta sessão.** Cada número abaixo veio de execução, não de memória.
Este documento é o entregável bloqueante da Etapa 0: sem ele aprovado, nenhuma fase começa.

> **Referência desta leitura (2026-11-27).** Branch de trabalho `work/auditoria-e-fase-a`, sobre a
> branch padrão `main` no commit `55351cb`. As seções 1–43 descrevem o repositório **antes** das
> correções; as seções 44 em diante registram o que mudou, com a data e o defeito que motivou cada
> mudança. Nenhum número das seções antigas deve ser lido como estado atual — para isso existe
> `docs/PAINEL.md` (regenerado a cada rodada) e a seção mais recente deste documento.

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
| 1 | drivers NFS-e multi-prefeitura | **PARCIAL — interface e roteamento prontos** | `app/nfse/drivers/` existe=False; `app/nfse/adapter.py` implementa só padrão nacional (`SefinNacionalClient`, `SefinMockAdapter`) |
| 2 | modelos de município/credencial/webservice | AUSENTE | `Base.metadata` com `app.db.models` importado tem **10 tabelas** (batch_jobs, fiscal_documents, frete_credenciais, invoice_events, invoices, tax_assessments, tenant_certificates, tenant_fiscal_configs, tenants, webhook_deliveries); faltam exatamente ['municipios_nfse', 'credenciais_municipais', 'webservices_sefaz']. Correção de método: a primeira medição retornou 0 tabelas porque os modelos não estavam importados — evidência refeita. |
| 3 | transporte SOAP DF-e | **PARCIAL** | ocorrências de soap/SOAPAction: 0; existem `app/nfe/gerador.py`, `assinatura.py`, `lote.py` (geração+assinatura+XSD, sem envio) |
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
- ✅ **cache real carregado com `--fetch`**: **5571 municípios, 27 UFs**, 474 KB em
  `data/ibge_municipios.json`. Segunda execução: `inseridos 0 | inalterados 5571`.
- **5571, não 5570.** O número documentado por aí é 5570; a API devolveu 5571. Mais uma
  razão para não fixar constante: eu teria escrito o número errado e o teste passaria.
- Conferido no banco: `count(*) = 5571`, `count(DISTINCT uf) = 27`; São Paulo (3550308),
  Goiânia (5208707) e Águas Lindas de Goiás (5200258) presentes, todos com
  `provedor = NACIONAL_REST`.
- **Pendente**: rotas de gestão (`GET /v1/municipios`, credenciais, status de certificado).

### 2f. Rotas de municípios (Etapa D)

- `app/api/v1/municipios.py`: `GET /v1/municipios` (filtros `uf`, `nome`, `provedor`,
  `homologado` + paginação) e `GET /v1/municipios/{codigo_ibge}`.
- **Rotas públicas de propósito**: quem integra precisa saber o que cada município exige
  antes de ter conta, e nada aqui é dado de tenant.
- **Sem rota de escrita**: município vem do seed do IBGE, não do cliente. Deixar um tenant
  inventar município permitiria emissão contra código inexistente.
- 10 testes em `tests/test_municipios_rota.py`: filtros, paginação preservando `total`,
  `404`, `422` para código curto e não numérico, lista vazia.
- `fonte_url` exposta no payload: R3 — o cliente pode conferir de onde veio a configuração
  que vai emitir a nota dele.
- Rotas: 49 → **51**. OpenAPI regenerado.
- **Limitação declarada**: busca por `nome` é `ilike` sem normalização de acento;
  "goiania" não encontra "Goiânia". Documentado em vez de fingir busca fuzzy.
- **Pendente**: rotas de credencial (exigem o cofre) e status de certificado.

### 2g. Rotas de credencial municipal (Etapa D)

- `app/api/v1/credenciais.py`: `GET /v1/credenciais-municipais`,
  `POST /v1/credenciais-municipais`, `DELETE /v1/credenciais-municipais/{codigo_ibge}`.
- **A resposta nunca traz o segredo nem o ciphertext**: só `tem_usuario`/`tem_senha`/
  `tem_token`. Teste dedicado verifica que a senha enviada não aparece em `resposta.text`.
- **Isolamento por tenant**: lista de um tenant não mostra credencial de outro; `DELETE`
  de outro tenant responde 404 (não 403 — 403 revelaria que existe).
- `DELETE` **desativa, não apaga**: a linha continua no banco, ligada às notas emitidas.
  Testado com `SELECT` direto após o DELETE.
- Só aceita município existente no cadastro; `404` com mensagem que aponta
  `GET /v1/municipios`.
- 10 testes em `tests/test_credenciais_rota.py`. Rotas: 51 → **53**.
- **Bug pego na execução**: `app.certificates.vault` não existe — o módulo é
  `app.core.vault`.
- **Pendente**: `GET /v1/tenants/{id}/certificado/status` e o teste de conectividade
  (`consultar_servico`) exigido pelo v10.0 ao cadastrar credencial.

### 5d. DLQ — tabela, serviço e replay (Etapa H, parte 2)

- `app/db/models/dlq.py` + migration `0007` (executada: 0007 → 0006 → 0007, `current` em
  `0007 head`). 13 colunas, índices por `tenant_id`, `fila`, `status`, `trace_id` e o
  composto `tenant_id+status`.
- `app/worker/dlq.py`: `enfileirar`, `listar`, `por_id`, `preparar_replay`,
  `marcar_replay_falhou`, `descartar`. **11 testes** em `tests/test_dlq.py`.
- **Replay duplo é recusado.** Replay reenviaria a mesma nota — a falha mais cara
  possível neste sistema, e a razão de o item carregar `status`.
- **Falha de replay volta para `pendente`.** Sem isso, o item ficaria marcado como
  sucesso e o trabalho se perderia em silêncio.
- Guarda o **payload original**: sem ele, replay seria adivinhação, e o cliente não tem
  mais o estado daquele momento.
- Isolamento por tenant verificado: listar e reprocessar item de outro tenant falham.
- **Ainda ausente**: endpoint `POST /v1/admin/dlq/{id}/replay` (exige auth de admin, que
  o projeto não tem hoje — só auth de tenant) e a ligação com o worker ARQ real.

### 5e. Rate limit ligado ao middleware (Etapa H, parte 3)

- `app/core/middleware_ratelimit.py` + `rate_limit_habilitado`/`rate_limit_por_minuto` em
  `Settings` e documentados no `.env.example`. **8 testes**.
- **Desligado por padrão.** Ligar por padrão mudaria o comportamento de todas as rotas
  existentes de uma vez. Teste verifica `Settings().rate_limit_habilitado is False`.
- Cota por **tenant**, não por IP. Sem API key, cai para o IP. Usa só o **prefixo** da
  API key no storage — o hash do segredo não deve viver ali.
- `/health` e `/ready` **isentos**: health precisa responder sob ataque, senão o
  orquestrador mata o pod.
- 429 em `application/problem+json` com `Retry-After` e `X-RateLimit-*`. Falha aberta se
  o storage cair.
- **O teste de configuração documentada pegou a omissão**: os dois campos novos não
  estavam no `.env.example` e a suíte ficou vermelha antes do commit. Era exatamente o
  guarda funcionando.
- **Ainda ausente**: ligar em produção (decisão operacional) e o circuit breaker no worker.

### 5f. Registro de circuitos por serviço/UF (Etapa H, parte 4)

- `app/nfse/resiliencia.py`: `RegistroCircuitos`, `executar`, `chave_sefaz`,
  `chave_municipio`, `estados()`. **12 testes** em `tests/test_resiliencia.py`.
- **Um circuito por chave** (`sefaz:52:autorizacao`, `municipio:5200258:emitir`).
  Circuito global seria errado: a SEFAZ de GO cair não pode parar a emissão municipal de
  SP. Testado nos dois eixos (UF e município).
- **Circuito aberto não chama o serviço.** Teste com flag confirma que a ação não é
  executada — é o ponto de existir circuito.
- **Rejeição fiscal não abre.** `ValueError` de rejeição não conta como falha transitória:
  o serviço está no ar e respondendo. Três rejeições seguidas e o circuito continua
  fechado (testado).
- Timeout, `ConnectionError` e `OSError` são transitórios e abrem.
- `estados()` expõe o mapa para métrica/health.
- **Ainda ausente**: injetar o registro no `emissao_service` e no worker, e ligar a
  métrica `sefaz_circuit_state`.

## 15. Decisão final por lacuna (formato da missão)

Cada item com estado, prova, teste, risco e **decisão registrada**.

### 1. Drivers NFS-e multi-prefeitura — PARCIAL

- **Prova**: `app/nfse/adapter.py` implementa só `SefinNacionalClient`/`SefinMockAdapter`.
  Não existe `app/nfse/drivers/`.
- **Testes**: fluxo nacional coberto; nenhum teste de driver municipal (não há driver).
- **Risco**: cadastrar município com provedor ABRASF/GINFES e o roteamento cair no
  nacional geraria rejeição sem causa clara.
- **Decisão**: **manter no roadmap.** Falta URL e leiaute oficial por provedor; implementar
  por suposição violaria P2 e produziria driver que não funciona no município real.

### 2. Modelos + serviço + seed + rotas — IMPLEMENTADO E TESTADO

- **Prova**: `app/db/models/{municipio,credencial_municipal,webservice_sefaz}.py`,
  `app/nfse/credenciais.py`, `scripts/seed_municipios.py`,
  `app/api/v1/{municipios,credenciais}.py`, migrations 0004–0006.
- **Testes**: 10 (municípios) + 10 (credenciais serviço) + 10 (rotas credencial) = 30.
  Seed verificado com 5571 municípios reais, duas execuções idempotentes.
- **Risco residual**: `testar_conectividade` no cadastro não existe — depende de URL real
  por município.
- **Decisão**: **implementado**; a conectividade fica registrada como pendência do item 1.

### 3. Transporte SOAP DF-e — AUSENTE

- **Prova**: 0 ocorrências de `soap`/`SOAPAction` em `app/`. Existem geração, assinatura e
  envelope (`app/nfe/lote.py`) validados contra o PL_010h.
- **Testes**: nenhum de transmissão (não há o que transmitir).
- **Risco**: apresentar NF-e como "emitida" sem transmissão seria a mentira mais grave
  possível neste projeto.
- **Decisão**: **bloqueado externamente** — credenciamento NF-e em Goiás. Sem isso não há
  como verificar sequer o `NFeStatusServico`.

### 4. `CalculoAudit` — IMPLEMENTADO E TESTADO

- **Prova**: `app/tax/auditoria.py`, `app/db/models/tax.py`, migration 0003,
  `app/tax/auditoria_service.py`, `app/api/v1/auditoria.py`,
  `app/tax/integracao_emissao.py`, ligado em `POST /v1/emissoes`.
- **Testes**: 18 (determinismo) + 11 (persistência) + 11 (integração) + 5 (rotas) = 45.
  Migration executada nos dois sentidos. Gravação na emissão provada por `SELECT`.
- **Decisão**: **implementado**. Nada pendente.

### 5. RFC 7807 / circuit / DLQ / rate limit — PARCIAL

- **Prova**: `app/core/errors.py` + handler em `main.py` (RFC 7807 ativo);
  `app/core/ratelimit.py` + `middleware_ratelimit.py`; `app/core/circuit.py`;
  `app/nfse/resiliencia.py` + `registro_padrao`; `app/worker/dlq.py` + migration 0007;
  `GET /v1/health/circuitos`.
- **Testes**: 26 (errors) + 12 (ratelimit) + 8 (middleware) + 10 (circuit) + 14
  (resiliencia) + 11 (dlq) + 5 (observabilidade) = 86.
- **Risco**: as peças existem e são testadas isoladamente, mas **o circuito não está
  injetado no `emissao_service`** — hoje ele só abre se alguém chamar `executar`.
- **Decisão**: circuito **injetado** em `POST /v1/emissoes` (commit `d9c9ff5`), com
  `CircuitoAberto` → **503 + `Retry-After`** em vez de 500. Item fechado exceto o replay.
- **Replay autenticado**: decisão de arquitetura registrada em
  `docs/adr/0001-admin-auth.md` — três opções avaliadas, recomendação de chave estática
  com `admin_habilitado=False` por padrão. **Aguarda decisão do proprietário**: criar
  rota "admin" sem mecanismo de admin seria falso positivo de segurança.

### 6. Hash SHA-256 de XSD — IMPLEMENTADO E TESTADO

- **Prova**: `app/core/schemas.py`, `data/xsd_manifest.json` (21 schemas),
  `scripts/gerar_manifesto_xsd.py`. 13 testes, incluindo o que confere o manifesto real.
- **Decisão**: **implementado** em modo `WARN`, com `STRICT` disponível. Divergência de
  procedência oficial do PL continua registrada em §16.3.

### 7. `Idempotency-Key` por header — IMPLEMENTADO E TESTADO

- **Prova**: `app/api/v1/emissoes.py` (`Header(alias="Idempotency-Key")`),
  `app/nfse/schemas.py` (campo opcional). 6 testes.
- **Testes provam**: body-only (compat), header-only, reenvio sem duplicar, header vence
  o body, ausência → 422, chave curta → 422.
- **Decisão**: **implementado**. Nada pendente.

### Placar

| Estado | Itens |
|---|---|
| Implementado e testado | 2, 4, 6, 7 |
| Parcial | 1, 5 |
| Ausente | 3 |
| Bloqueado externamente | 3 (credenciamento), parte do 5 (admin auth) |

### 3a. Envelope SOAP 1.2 (Etapa F, parte 1)

- `app/nfe/soap.py`: `envelopar`, `desenvelopar`, `extrair_falha`, `ErroSOAP`.
  11 testes em `tests/test_nfe_soap.py`.
- **Sem URL no módulo, de propósito**: endpoint vem da tabela `webservices_sefaz` (R3).
- Formato `nfeDadosMsg`: o XML fiscal vai **dentro** do `Body`, sem assinatura adicional
  no envelope — a assinatura já está no documento, e assinar o envelope seria assinatura
  dupla que a SEFAZ recusa.
- **`desenvelopar` falha alto** com HTML de gateway (proxy no caminho devolve 502 em HTML)
  e com `Body` vazio. Sem isso o erro apareceria como "XML inválido" três camadas adiante.
- **`extrair_falha` devolve `None` para resposta normal — e isso significa "não é Fault",
  NÃO "deu certo"**. Documentado no docstring e testado.
- **Ainda ausente**: transporte HTTP real (exige credenciamento), ciclo de autorização,
  consulta, cancelamento, inutilização, CC-e e contingência.

### 3b. Cliente SOAP com transporte injetável (Etapa F, parte 2)

- `app/nfe/transporte.py`: `ClienteSefaz`, `TransporteSOAP` (Protocol), `RespostaSefaz`,
  `ErroTransporte` (transitório) e `ErroSefazDefinitivo` (não retentar). 9 testes.
- **Transporte é interface, não `httpx` direto.** Sem isso não haveria como testar o
  cliente; em produção o transporte HTTP real entra no mesmo lugar.
- **Classificação que decide retry**: `TimeoutError`/`ConnectionError`/`OSError` →
  `ErroTransporte` (retentar). SOAP Fault → `ErroSefazDefinitivo` (**não** retentar).
  HTML de gateway → transitório, porque o serviço pode voltar.
- **Guarda de URL**: `http://` é recusado **antes** de chegar ao transporte, e há teste
  provando que o transporte não é chamado. R3 — serviço fiscal em texto claro é falha de
  segurança, não detalhe.
- **Resposta bruta preservada** em `RespostaSefaz.xml` para auditoria.
- **Ainda ausente**: transporte HTTP real (`httpx` com mTLS), o ciclo de autorização do
  lote, consulta/recibo, cancelamento, inutilização, CC-e e contingência. Todos dependem
  de credenciamento para serem verificados.

### 3c. Transporte HTTP com mTLS (Etapa F, parte 3)

- `TransporteHTTP` em `app/nfe/transporte.py`. 9 testes em
  `tests/test_nfe_transporte_http.py`, contra `httpx.MockTransport` — **sem rede e sem
  certificado real**, mas exercitando o `httpx` de verdade.
- **`application/soap+xml`, não `text/xml`**: SOAP 1.2 exige o primeiro; o segundo é
  SOAP 1.1. Testado no header do pedido real.
- **5xx sempre transitório** (parametrizado em 500/502/503/504) — o serviço pode voltar.
- Corpo chega intacto e a resposta bruta é preservada.
- **Certificado injetado como PEM**, não PFX: este módulo não lê PFX nem conhece senha
  (R4). A conversão fica a cargo de quem tem o cofre.
- **O que este teste NÃO prova**: que a SEFAZ aceita o certificado, que a URL está certa e
  que o leiaute da resposta é o esperado em produção. Isso exige credenciamento.
- **Ainda ausente no item 3**: ciclo de autorização do lote, consulta/recibo, cancelamento,
  inutilização, CC-e e contingência.

### 3d. Leitura do retorno de autorização (Etapa F, parte 4)

- `app/nfe/retorno.py`: `ler`, `Retorno`, `Protocolo`, `Situacao`. 10 testes.
- **Lote processado ≠ nota autorizada.** `cStat 104` no lote diz "processei"; quem diz
  "autorizei" é o `cStat` do `protNFe`. O código avalia protocolo **antes** do lote —
  bug que o teste pegou na primeira execução, quando uma nota rejeitada aparecia como
  "processada".
- `denegada` é situação própria, não rejeição: a nota existe e foi recusada.
- **Código desconhecido não vira "autorizada"**: sem protocolo autorizado e com `cStat`
  não mapeado, a situação é `REJEITADA` ou `INDEFINIDA` — nunca sucesso por omissão.
- **Limite declarado**: o significado de cada `cStat` é do MOC. O módulo trata 100, 103,
  104 e 110 porque são inequívocos; o resto é classificado estruturalmente, não por
  semântica inventada.
- **Ainda ausente**: ciclo completo (enviar → receber recibo → consultar recibo →
  autorizada), cancelamento, inutilização, CC-e e contingência.

### 3e. Ciclo de autorização composto (Etapa F, parte 5)

- `app/nfe/autorizacao.py`: `enviar_lote`, `consultar_recibo`, `autorizar`,
  `ResultadoAutorizacao`. 8 testes com transporte em sequência.
- **Sequência do leiaute, não escolha nossa**: `protNFe` → acabou; `cStat 103` → tem
  `nRecibo`, consultar depois; qualquer outra coisa → rejeição, **não insistir**.
- **`tentativas_recibo=1` por padrão**: cada consulta consome cota da SEFAZ e há
  intervalo mínimo regulado. Laço aqui seria abuso; quem precisa esperar, espera fora.
- Recibo que devolve `103` de novo **para** em vez de insistir.
- SOAP Fault vira `ErroDeAutorizacao` — não há recibo a consultar depois de Fault.
- **Bug pego pelos testes**: `ler()` recebia a resposta SOAP bruta e recusava com
  "elemento não é retorno da SEFAZ: Envelope". Corrigido com `RespostaSefaz.xml_fiscal`
  (elemento serializado) separado de `.xml` (bruto, para auditoria).
- **Ainda ausente**: cancelamento, inutilização, CC-e e contingência. E a chamada real,
  que exige credenciamento.

### 5g. DLQ integrada ao worker (Etapa H, parte 5)

- `app/worker/tarefas.py`: `executar_com_dlq` — executa com retry e persiste na DLQ quando
  todas as tentativas falham. 6 testes em `tests/test_worker_tarefas.py`.
- **Só falha transitória é retentada.** Rejeição fiscal definitiva vai direto para a DLQ
  com o motivo: retentar não muda o resultado e queima cota do autorizador. Testado com
  `ValueError` — 1 chamada, não 5.
- **Sucesso deixa rastro zero na DLQ**: um teste verifica `itens == []`. Sem isso a tabela
  viraria log de sucesso e a fila morta perderia o sentido.
- Guarda o **payload original** e o `trace_id` — sem eles o replay seria adivinhação.
- `tentativas` conta **execuções**, não repetições; `tentativas=0` levanta.
- **Ainda ausente: registrar no ARQ — e a fiação NÃO é uma linha.** Correção de uma
  afirmação minha anterior: eu disse duas vezes que "a fiação é uma linha por tarefa".
  Não é.

  Razão: o fluxo de emissão vive hoje **dentro** de `POST /v1/emissoes` (rota), não no
  serviço. Uma tarefa ARQ não tem request, sessão nem tenant prontos, então registrar
  `emitir_com_dlq` exigiria primeiro o que o v10.0 pede na Fase 4: **extrair o fluxo de
  emissão da rota para o serviço**. Isso é refatoração de arquitetura, não fiação.

  Verificação de que tentei e recuei: criei `app/worker/emissao_dlq.py` com a tarefa
  registrada em `WorkerSettings.functions`. Ao revisar, o corpo interno levantava
  `NotImplementedError` — o worker **aceitaria o job e sempre falharia para a DLQ**. Meia
  medida pior que ausência: enfileira trabalho que nunca executa. Arquivo removido e
  `main.py` revertido; `WorkerSettings.functions` segue com as 3 tarefas originais.

### 16. HTML de gateway classificado como recusa fiscal — corrigido

**Achado em execução real**, não em leitura de código. Ao rodar o demo end-to-end, a SEFIN
respondeu:

```
403 - Forbidden: Access is denied.   (HTML do IIS/WAF)
```

E o cliente classificou como `AUTENTICACAO` com a mensagem "a SEFIN recusou a DPS",
despejando o HTML inteiro no erro.

**Duas consequências erradas**:
1. O lojista concluiria "certificado recusado" e **pararia de tentar** — quando o problema
   era infraestrutura na frente do serviço, que pode voltar.
2. O HTML ia para a mensagem, escondendo a causa e poluindo resposta de API.

**Correção** em `app/nfse/transport.py`: `_parece_html` detecta a marca real (doctype
HTML ou elemento raiz `html`) — não basta olhar o primeiro caractere, porque HTML e XML
começam com `<`. Resposta HTML com `401/403` vira `INDISPONIVEL`, com mensagem que diz que
foi gateway/WAF e sem mensagens fiscais inventadas.

**Não confundir com recusa fiscal real**: `403` com XML do leiaute continua `AUTENTICACAO`.
7 testes em `tests/test_nfse_transport_classificacao.py`.

**DIAGNÓSTICO CORRIGIDO (e uma correção minha errada)**. Na primeira análise eu classifiquei
o 403 HTML como `INDISPONIVEL` e escrevi "gateway/WAF". Errado: investigando, a causa real é
outra.

Evidência coletada:
- `HEAD https://sefin.producaorestrita.nfse.gov.br/SefinNacional/` sem certificado → **403**
- host inteiro (`/`, `/SefinNacional/`, `/SefinNacional/nfse`) → **403**
- `https://www.nfse.gov.br/` → **200**

Ou seja: a recusa é da **borda**, por TLS/mTLS — não do leiaute. E o demo roda com
`gerar_pfx_autoassinado()`, um certificado **autoassinado**; com o container em
`NFSE_ADAPTER=sefin` (o demo documenta `mock`, mas a variável do meu shell não alcança o
container), a SEFIN recusou o certificado — comportamento **correto** dela.

Classificação final: `AUTENTICACAO`, porque retentar não resolve. A mensagem nomeia as duas
hipóteses (certificado não aceito ou bloqueio de rede/WAF) e **não embute o HTML**.

**Lição**: eu classifiquei como indisponível um erro que era de autenticação, com base em
"é HTML, logo é gateway". A investigação por caminho/host derrubou a hipótese em dois
comandos.

### 17. O que NÃO consegui verificar, e o motivo exato

Pergunta aberta na §16: "o certificado A1 real continua sendo aceito pela SEFIN?".
**Não consegui responder**, e o motivo está verificado:

- `.env` tem `ENVIRONMENT`, `NFSE_ADAPTER`, 5 variáveis do Melhor Envio — **nenhum caminho de
  certificado e nenhuma chave mestra**.
- `Get-ChildItem -Recurse -Include *.pfx,*.p12` → **nenhum arquivo** no repositório.
- O certificado A1 real foi enviado pela API e está **selado no banco**
  (`tenant_certificates`). Abrir exige `MASTER_ENCRYPTION_KEY`, que não está neste ambiente.

Portanto: a emissão NFS-e real **não foi re-testada nesta sessão**. O último sucesso
verificado continua sendo o da emissão e do cancelamento anteriores; depois disso houve
mudanças no caminho de emissão (circuito, laudo, idempotência) que **não** foram exercitadas
contra a SEFIN.

**Risco declarado**: as 1156 verificações atuais são todas locais. A emissão real precisa ser
re-testada pelo proprietário, com a chave mestra e o certificado em mãos — e essa é a
primeira coisa a fazer antes de qualquer outra evolução.

**Como re-testar** (sem expor segredo no terminal):
1. subir a stack com a chave mestra já configurada no ambiente do container;
2. `POST /v1/emissoes` com uma nota de teste em homologação;
3. conferir `GET /v1/emissoes/{id}` → `authorized`;
4. se voltar 403, ler a mensagem: ela agora distingue borda (certificado/WAF) de leiaute.

### 1a. Interface de drivers e roteamento (Etapa E)

- `app/nfse/drivers.py`: `ResultadoDriver`, `BaseNFSEDriver` (Protocol), `CategoriaErro`,
  `provedor_suportado`, `exigir_implementacao`, `capacidade`. 10 testes.
- **Roteamento sem `if municipio ==`**: a decisão é por `provedor`, e só existe num lugar
  (P9).
- **16 dos 17 provedores recusam com motivo factual**: cada um tem a dependência exata que
  falta ("falta URL e manual do provedor GINFES", "falta XSD e endpoint da versão 2.04").
  Recusar com motivo é diferente de `NotImplementedError` solto — e de mandar XML para
  uma URL suposta.
- `ResultadoDriver` normaliza retorno: o adaptador nunca olha o driver, só o resultado.
- `CategoriaErro` **espelha** `OrigemErro` do RFC 7807; teste garante que os quatro valores
  coincidem, senão o contrato de erro quebraria na borda do driver.
- **Ainda ausente**: `AbrasfBaseDriver` (SOAP 1.1/1.2, assinatura seletiva, encoding) e os
  cinco drivers especializados. Todos param na mesma falta: fonte oficial por provedor.

### 1b. Motor ABRASF parametrizável (Etapa E, parte 2)

- `app/nfse/drivers_abrasf.py`: `AbrasfBaseDriver`, `ConfiguracaoAbrasf`, `envelopar`,
  `desenvelopar`, `interpretar`, `ErroAbrasf`. 20 testes.
- **Nenhuma URL no código.** Endpoint, namespace, versão de SOAP e encoding vêm do
  registro do município. Por isso o motor pôde ser escrito e testado **sem
  credenciamento**: verifica-se o contrato do envelope, não a rede.
- **SOAP 1.1 e 1.2** com namespaces distintos, testados separadamente — provedor legado
  usa 1.1 e recusa 1.2.
- **Encoding vem da configuração**: GINFES/DSF declaram ISO-8859-1 e a declaração do XML
  precisa acompanhar, senão a acentuação corrompe.
- **Assinatura seletiva é guardada, não presumida**: provedor que exige assinatura de lote
  com `assinador=None` recebe falha `INTERNO` clara em vez de o driver enviar sem assinar
  e receber recusa opaca. Um dos testes me corrigiu: eu esperava sucesso sem assinador.
- Operações sem leiaute confirmado (`consultar_nfse_por_rps`, `consultar_nfse_tomadas`)
  recusam com motivo — não inventam envelope.
- **Ainda ausente**: os cinco drivers especializados, cada um só com URL/leiaute oficial,
  e a assinatura XMLDSig real do RPS (o motor recebe o assinador, não o implementa).

### 1c. Assinatura XMLDSig do RPS e costura com o driver (Etapa E, parte 3)

- `app/nfse/assinatura_rps.py`: `assinar_rps`, `AlvoAssinatura`, `ResultadoAssinatura`.
  6 testes. `drivers_abrasf.assinador_de` adapta ao contrato do driver; 4 testes de
  integração em `tests/test_nfse_driver_assinatura.py`.
- **Reutiliza o assinador do projeto** em vez de duplicar C14N/digest: duplicar seria a
  segunda chance de errar o mesmo detalhe.
- **Alvo explícito** (`rps` ou `lote`): o leiaute ABRASF assina o `InfDeclaracao` por `Id`,
  e alguns provedores querem o lote. Adivinhar produz recusa; o alvo vem do manual.
- Sem `Id`, falha `VALIDACAO_LOCAL` com motivo — sem `Id` não existe `URI` de referência.
- **Teste de integração verifica o envelope realmente enviado**: `Reference URI == "#rps1"`
  e `Signature` presente no corpo que sai para o transporte.
- **Teste descartado, e o motivo**: eu havia escrito um caso com certificado falso que
  levantava `AttributeError`; isso é erro de programação, não comportamento do sistema.
  Afrouxar o `except` para "passar" seria esconder bug — removi o teste.
- **Ainda ausente**: nenhum provedor real foi contatado; o que está provado é que a
  assinatura é gerada, referencia o `Id` certo e sai dentro do envelope.

### 1d. Fábrica de drivers: do cadastro ao motor (Etapa E, parte 4)

- `app/nfse/drivers_factory.py`: `criar_driver`, `MunicipioParaDriver`. 10 testes.
- **A configuração vem do registro**, não do código: URL, namespace, versão de SOAP,
  encoding e quais assinaturas o provedor exige.
- **URL sem `fonte_url` é recusada.** Sem fonte registrada a URL é chute, e R8 proíbe
  inventar endereço fiscal. Recusa com mensagem que diz o que cadastrar.
- **`http://` recusado** na fábrica, antes de qualquer chamada.
- **Mudança de semântica necessária e registrada**: `provedor_suportado` antes respondia
  `False` para os 16 provedores ABRASF, porque não havia motor. Agora há, então passou a
  responder `True` — e `capacidade()` continua `False` em emissão, porque motor sem
  configuração de município não emite. **Duas perguntas diferentes, duas respostas
  diferentes**: "existe motor?" e "este município pode emitir hoje?".
- **Ainda ausente**: carregar `MunicipioParaDriver` da linha real de `municipios_nfse`
  (o mapeamento é trivial, mas exige sessão; a fábrica foi mantida sem ORM de propósito) e
  `testar_conectividade` contra URL real, que exige acesso ao provedor.

### 1e. Do registro ORM ao driver, e o caminho até o transporte (Etapa E, parte 5)

- `de_municipio(row, ambiente, versao_soap)` em `app/nfse/drivers_factory.py`.
  10 testes em `tests/test_nfse_municipio_para_driver.py`, incluindo ponta a ponta local.
- **O ambiente não tem default esperto**: `ambiente="homologacao"` por padrão. Produção
  nunca é escolhida por omissão — emitir em produção por acidente é irreversível.
- **`versao_soap` é parâmetro, não dedução.** Eu havia escrito
  `"1.1" if "1_0" in provedor else "1.2"` — uma heurística sem fonte no repositório. Um
  1.1 trocado por 1.2 faz o provedor recusar o envelope inteiro. Removi a dedução; quem
  sabe a versão é o manual do município.
- **`namespace_xml` nulo no cadastro levanta**: inventar namespace produz XML recusado sem
  explicação.
- `de_municipio` **não inventa URL**: se a do ambiente estiver vazia, devolve `None` e a
  fábrica recusa com motivo — a guarda fica num lugar só.
- **Ponta a ponta local provado**: linha do cadastro → `de_municipio` → `criar_driver` →
  envelope SOAP → transporte falso, com `protocolo` extraído do retorno.
- **O que esse teste NÃO prova**: que o provedor aceita. Exige contato real.

### 18. Concorrência na idempotência — provado em parte, e o resto declarado

**O que está provado** (`tests/test_idempotencia_concorrencia.py`, 2 testes):
- Envio repetido devolve `201` e depois `200` com o **mesmo `invoice_id`**, e a tabela
  continua com **uma** fatura. A garantia vem da constraint
  `uq_invoices_tenant_idempotency_key`, e o código trata `IntegrityError` buscando a
  existente.
- Chaves distintas criam faturas distintas — a constraint é por `(tenant, chave)`.

**O que NÃO está provado: duas requisições realmente simultâneas.** Tentei com
`asyncio.gather` e o teste quebrou com `MissingGreenlet` **dentro de `do_ping` do pool**
(`pool_pre_ping`), não no código de emissão. Não sei ainda se é artefato do harness de teste
(engine recriado por teste) ou uma corrida real na criação do engine.

**Hipóteses testadas e ELIMINADAS com experimento** (cada uma custou um comando):

1. *Engine criado em loop de eventos anterior.* Recriei o engine no próprio loop do teste
   (`dispose_engine()` + `reset_engine()` antes do `gather`). **Falhou igual.** Não é isso.
2. *`pool_pre_ping` quebra com checkouts concorrentes.* Teste isolado fora da API: duas
   corrotinas pegando conexão do mesmo engine, com `pre_ping` ligado e desligado.
   **Ambos passaram** (`[1, 1]` nos dois casos). Não é o `pre_ping` sozinho.
3. *Corrida na criação preguiçosa do engine.* `obter_engine()` é síncrona, sem `await`
   interno: entre testar `_engine is None` e atribuir não há ponto de suspensão. Não há
   corrida ali.

O `MissingGreenlet` aparece em `do_ping` **só no caminho da API com duas requisições
simultâneas**; fora da API, checkouts concorrentes funcionam. A diferença está no
`ASGITransport`/dependência de sessão, não no engine nem na emissão.

**Decisão**: não commitei um teste que não entendo, nem marquei "concorrência OK" sem
entender. A lacuna fica registrada aqui e no roadmap. Verificar exige harness com processo
separado — trabalho à parte, não ajuste de teste.

**Risco residual**: se a corrida for real e não só do harness, duas requisições no mesmo
milissegundo podem devolver 500 em vez de 200 na segunda. A constraint impede a **nota
duplicada** (o dano fiscal), mas o cliente pode ver erro em vez de reaproveitamento.

### 19. Catálogo fiscal: 27/27 nos quatro documentos (medido 2026-11-26)

| Documento | Modelo | Endpoints | UFs |
|---|---|---|---|
| NF-e | 55 | 270 | 27/27 |
| NFC-e | 65 | 270 | 27/27 |
| CT-e | 57 | 54 | 27/27 |
| MDF-e | 58 | 54 | 27/27 |

Fonte de cada linha gravada em `fonte_url` (URL bruta do arquivo no SVN do ACBr),
com SHA-256 e data em `data/fontes/MANIFESTO.json`.

Municípios: 5571/5571 com provedor; 1279 com URL https; 4290 no padrão nacional.

**O que isso NÃO é**: `homologados = 0`. Nenhuma chamada real a autorizador foi feita.
CT-e e MDF-e não têm geração de XML nem assinatura — só o endpoint catalogado.

### 20. Estado final desta execução

- Testes: **1245**, 0 falhas, 0 erros (medido com `--junit-xml`).
- Migrations: 10, todas com round-trip verificado.
- Gate local (`scripts/check_ci.py`) roda antes de cada commit.
- CI verde no último commit (`gh run` consultado, não presumido).

**Bloqueios externos que permanecem**: certificado A1 + `MASTER_ENCRYPTION_KEY` fora deste
ambiente; credenciamento SEFAZ-GO; OAuth do Melhor Envio; CSC por UF para NFC-e.

### 21. CT-e: gerado, assinado e validado contra o schema oficial

**Implementado e testado** (`app/cte/gerador.py`, 10 testes):

- `gerar(dados)` monta o XML na ordem extraída do `xs:sequence`.
- `gerar_assinado(dados, certificado)` assina (reusa `app.nfe.assinatura`) e **valida** contra
  `cte_v4.00.xsd`.
- Saída medida: 4058 bytes, com `Signature`, aceita pelo schema.

**Desenho**: `gerar()` devolve a árvore **não assinada** porque um CT-e sem `Signature` nunca
será válido; há teste provando que o schema recusa esse XML.

**Cobertura de tomador**: `toma3` (partes do documento) e `toma4` (outros, com `enderToma`),
decididos por `PapelTomador` — o gerador não escolhe por conta própria.

**O que continua ausente**: transmissão. Nenhum CT-e foi enviado a autorizador; depende de
credenciamento e certificado ACP-Brasil real.

#### Descobertas que custaram três tentativas (registradas para não repetir)

`CTe@versao` inexistente na raiz · `procEmi` antes de `verProc` · `modal` como enumeração
`01`–`06` · origem/destino antes de `retira` antes de `toma*` · `dhSaidaOrig` fora de `ide` ·
`CEP` proibido em `enderEmit`/`enderDest` · `CRT` como último filho de `emit` · `qCarga` com
4 casas · `imp` com grupo `ICMS`/`ICMS00` · `infCarga` antes de `infDoc` · `infModal` com
`versaoModal` e `rodo`/`RNTRC` · **CT-e só é válido assinado**.

### 22. MDF-e: gerado, assinado e validado contra o schema oficial 3.00

**Implementado e testado** (`app/mdfe/gerador.py`, 12 testes somando schema + gerador):

- `gerar(dados)` monta na ordem extraída do `xs:sequence`.
- `gerar_assinado(dados, certificado)` assina via `app.nfe.assinatura` e **valida** contra
  `mdfe_v3.00.xsd`.
- Saída medida: 3358 bytes com `Signature`, aceita pelo schema.

Fechou em **uma** tentativa porque a ordem de trabalho foi invertida em relação ao CT-e:
**validador primeiro, gerador depois**. O schema apontou apenas três pontos:

1. `infDoc` exige `infMunDescarga` agrupando as chaves de NF-e, não chaves soltas;
2. dentro do grupo a chave é `chNFe`, não `chave`;
3. MDF-e só é válido assinado.

**Modelo**: `Descarga(codigo_ibge, nome, chaves_nfe)` e
`MunicipioCarregamento(codigo_ibge, nome)` espelham o leiaute. As recusas são explícitas — sem
descarga, sem chave, sem município de carregamento, chave curta — nada é assumido em silêncio.

**O que continua ausente**: transmissão. Nenhum MDF-e foi enviado a autorizador.

#### Placar de geração por documento

| Documento | Geração | Assinatura | Validação | Transmissão real |
|---|---|---|---|---|
| NFS-e | sim | sim | sim | **sim** (sessão anterior) |
| NF-e | sim | sim | sim | não |
| CT-e | sim | sim | sim | não |
| MDF-e | sim | sim | sim | não |
| NFC-e | não (exige CSC) | — | — | não |

### 23. NFC-e: o que falta, confirmado no código

**Estado: parcial — geração ausente, com bloqueio duplo.**

Verificado por leitura do código:

- `app/nfe/gerador.py:58` fixa `_sub(ide, "mod", "55")`. Não há parâmetro de modelo.
- O leiaute da NF-e é o mesmo para o modelo 65 (`enviNFe`), mas o modelo 65 exige o grupo
  `infNFeSupl` com o **QR Code**, e o QR Code depende do **CSC** (token do contribuinte por
  UF) mais a URL de consulta da UF.

Portanto a NFC-e tem **dois** bloqueios distintos:

| Bloqueio | Natureza |
|---|---|
| `mod` fixo em 55 | código — pequeno, resolvível |
| QR Code / `infNFeSupl` | **dado externo**: CSC por UF, que só o contribuinte possui |

**Decisão: não alterar o gerador de NF-e agora.** Tornar `mod` parametrizável sem o QR Code
produziria um XML modelo 65 **inválido** para o schema — repetiria o erro do CT-e, que eu
reverti duas vezes. A NFC-e entra quando houver CSC real de uma UF.

O caminho correto, quando houver CSC: parametrizar `mod`, montar `infNFeSupl` com o QR Code
(v2 ou v3 conforme a UF) e validar contra `enviNFe_v4.00.xsd`. A UF define a versão do QR Code —
não é decisão do sistema.

### 24. Drift de migrations: 8 operações em 3 tabelas — **CORRIGIDO** (migration 0011)

`python -m alembic check` **falha** (exit 1). Medido nesta data, contra o banco local:

| Tabela | Operação detectada | Diagnóstico |
|---|---|---|
| `calculo_audit` (5 colunas: `versao_formato`, `regras`, `tabelas`, `entrada`, `saida`) | `modify_default`: banco tem `server_default`, modelo não declara | divergência de declaração |
| `dlq.payload` | idem | idem |
| `frete_credenciais` | `remove_constraint uq_frete_credenciais_tenant_id` + `remove_index ix_...` (unique=False) + `add_index ix_...` (unique=True) | modelo quer **índice único**; banco tem **constraint única** + índice não-único |

**Consequência real**: um `alembic upgrade head` do zero não reproduz os modelos exatamente.
Quem criar um banco novo e comparar verá diferença.

**Correção aplicada** (migration `0011`). Abaixo o registro original do diagnóstico, mantido
para rastreabilidade; o plano abaixo foi **executado e verificado**.

**Por que não corrigi à primeira**: uma migration de correção precisa de round-trip verificado
(`upgrade` → `check` limpo → `downgrade` → `upgrade`). O contexto era insuficiente para fazer
isso com verificação, e migration sem round-trip é exatamente o tipo de meia-medida que já
reverti três vezes neste projeto.

**Plano de correção (para a próxima sessão)**:

1. `calculo_audit` e `dlq.payload`: decidir a fonte de verdade. Se o default é só Python
   (`default=`), a migration `0011` remove os `server_default` do banco; se for intencional no
   banco, o modelo declara `server_default` — **uma** das duas, nunca as duas.
2. `frete_credenciais`: dropar `uq_frete_credenciais_tenant_id` e
   `ix_frete_credenciais_tenant_id` (não-único) e criar o índice único — alinhando ao modelo,
   que é a declaração intencional.
3. Verificar com `alembic upgrade head` → `alembic check` (deve passar) → `downgrade -1` →
   `upgrade head` → `alembic check` de novo.

**Risco se ficar como está**: baixo para o banco atual (o schema funciona, os testes passam),
alto para reprodutibilidade — um ambiente novo divergiria do que os modelos descrevem.

---

## Fechamento da correção do drift (migration 0011)

Executado e verificado:

```
alembic upgrade head   -> aplicou 0011
alembic check          -> "No new upgrade operations detected"
alembic downgrade -1   -> voltou para 0010
alembic upgrade head   -> reaplicou
alembic check          -> limpo de novo
pytest --junit-xml     -> testes=1278 falhas=0 erros=0
```

**Decisão registrada**: a **fonte de verdade é o modelo**. Os `server_default` do banco foram
removidos porque `tax.py` e `dlq.py` declaram apenas `default=` (Python). O valor continua
aplicado pelo ORM na inserção. Em `frete_credenciais` o modelo declara `unique=True, index=True`
e o banco foi alinhado ao índice único.

**Consequência**: `alembic upgrade head` a partir do zero agora reproduz os modelos. O CI não
roda `alembic check`; por isso o defeito sobreviveu até aqui — ver §25.

### 25. Geradores de CT-e e MDF-e — **CONCLUÍDO: biblioteca + API** (5/5 passos)

**Correção de classificação anterior.** Eu vinha marcando "geração ✅" para CT-e e MDF-e. A
medição abaixo mostra que o critério de conclusão da missão não está satisfeito para eles.

Evidência (busca por importadores fora dos próprios módulos):

```
Get-ChildItem -Recurse -Include *.py -Path app,tests,src |
  Select-String "from app\.(cte|mdfe)|import app\.(cte|mdfe)"
```

Resultado: **apenas arquivos de teste**. Nenhuma rota em `app/api/v1` importa
`app.cte.gerador` ou `app.mdfe.gerador`.

| Documento | Biblioteca | Exposto na API |
|---|---|---|
| NFS-e | sim | **sim** (rota de emissão) |
| NF-e | sim | sim (rota existente) |
| CT-e | sim (`gerar`, `gerar_assinado`) | **não** |
| MDF-e | sim (`gerar`, `gerar_assinado`) | **não** |
| NFC-e | não | não |

**Consequência**: um tenant **não consegue** pedir um CT-e ou MDF-e pela API. O código gera e
valida localmente, mas não há contrato HTTP. Pelo critério "o contrato da API está atualizado",
CT-e e MDF-e ficam como **parcial**, não concluídos.

**O que faltaria para expor na API** (fatia ainda não feita):

1. Schemas Pydantic de entrada para CT-e e MDF-e (o modelo de domínio já existe em dataclasses).
2. Rota `POST /v1/cte` e `POST /v1/mdfe` com autenticação por API key e `tenant_id` derivado da
   credencial — **nunca** do corpo.
3. Serviço que carrega o certificado do cofre, chama `gerar_assinado` e persiste o XML com hash.
4. Testes de isolamento entre tenants e de recusa sem certificado.
5. Documentação do contrato e atualização do OpenAPI congelado.

**Por que não fiz agora**: contexto de sessão insuficiente para entregar rota + schema +
serviço + testes + OpenAPI com verificação. Entregar rota sem teste de isolamento de tenant
violaria o item 6 das regras principais.

#### Fechamento da lacuna §25

Os cinco passos foram executados e verificados:

| # | Passo | Evidência |
|---|---|---|
| 1 | Schemas Pydantic de entrada | `app/cte/schemas.py`, `app/mdfe/schemas.py`, 16 testes |
| 2 | Rotas `POST /v1/transportes/cte` e `/mdfe` | `app/api/v1/transportes.py` |
| 3 | Serviço carregando A1 do cofre | `certificados.ativo` + `abrir_em_memoria` |
| 4 | Caminho feliz e isolamento entre tenants | `tests/test_transporte_isolamento.py`, 4 testes |
| 5 | OpenAPI congelado sincronizado | `openapi.json` regenerado, 559 linhas |

**O que os testes de isolamento provam**: tenant A com certificado ativo recebe 200 com
`<Signature>`; tenant B **sem** certificado recebe 422 e a resposta **não contém** `Signature`.
O certificado de A não assina em nome de B.

**O que continua ausente**: transmissão. As rotas devolvem XML assinado e validado contra o
schema; nenhuma chama autorizador. O `summary` de cada rota diz "não transmite" e há teste que
quebra se essa frase for removida.

**Armadilha encontrada no caminho**: override de `get_settings` com um `Settings` novo faz o
upload selar o certificado com uma chave e a assinatura abrir com outra. O erro aparece como
`ErroDeCriptografia` — "chave errada, dados corrompidos" — que é enganoso: a chave está certa,
o que muda é qual instância de configuração cada lado enxerga. Registrado na fixture.

### 26. SOAP por documento — o que existe e o que não existe

Resposta ao item 3 da verificação obrigatória, conferida por leitura de código. A distinção
importa: **código de transmissão existe para NF-e e NFS-e; para CT-e e MDF-e não existe**.

| Documento | Geração | Assinatura | Envio SOAP | Consulta | Eventos | Contingência |
|---|---|---|---|---|---|---|
| NFS-e | sim | sim | **sim** (`nfse/transporte.py`) | **sim** | **sim** (cancelamento) | não |
| NF-e | sim | sim | **sim** (`nfe/autorizacao.py`) | **sim** (`consultar_recibo`, `nfe/consulta.py`) | não verificado | não |
| CT-e | sim | sim | **não** | **não** | **não** | não |
| MDF-e | sim | sim | **não** | **não** | **não** | não |
| NFC-e | não | não | não | não | não | não |

**Símbolos que comprovam o lado NF-e** (`app/nfe/autorizacao.py`):

- `enviar_lote(cliente, url, xml_lote) -> ResultadoAutorizacao`
- `consultar_recibo(...)`
- `autorizar(...)` — envia e, se a SEFAZ responder `103`, consulta o recibo; `tentativas_recibo=1`
  por padrão porque cada consulta consome cota regulada.

**Por que CT-e e MDF-e não têm envio**: os geradores e as rotas entregam XML assinado. O ciclo de
autorização deles exige leiaute de resposta próprio (`retCTe`, `procCTe`, `retEventoCTe`) que
existe no schema versionado, mas escrever o transporte sem certificado e sem credenciamento
produziria código não verificável — e o projeto já pagou esse preço duas vezes com o gerador.

**O que NÃO foi feito em nenhum dos dois**: chamada real ao autorizador. Nem NF-e, nem NFS-e
nesta sessão. `homologados = 0`.

**Risco registrado**: o ciclo NF-e (`autorizar`) existe e é testável localmente, mas nunca foi
exercitado contra SEFAZ. Um código de transporte não exercitado tem valor menor do que a
contagem de funções sugere — não conto como "transmissão validada".

### 27. PRIMEIRA CHAMADA REAL À SEFAZ — e o bug que ela revelou

**Data**: 2026-11-26. **Serviço**: `NFeStatusServico4`, ambiente de **homologação** de GO.
**URL**: `https://homolog.sefaz.go.gov.br/nfe/services/NFeStatusServico4`
**Autenticação**: mTLS com o certificado A1 real da empresa (CNPJ 64339333000122, ICP-Brasil,
válido até 2027-01-08).

Resposta literal, preservada em
`tests/fixtures/evidencias/sefaz_go_status_homolog_2026-11-26.xml`:

```
cStat   : 107
xMotivo : Serviço em operação
cUF     : 52 (GO)
verAplic: GO4.0
tpAmb   : 2 (homologação)
dhRecbto: 2026-11-26T16:12:08-03:00
```

**Nenhuma nota foi emitida.** É consulta de status: informa se o serviço está no ar, não
autoriza documento.

#### O bug que só a resposta real expôs

`desenvelopar` devolvia o primeiro filho do `Body` SOAP — que na NF-e é o **embrulho**
`nfeResultMsg`, não o elemento fiscal. `ler()` então recusava com
`elemento não é retorno da SEFAZ: nfeResultMsg`, e `autorizacao.autorizar()` quebraria contra a
SEFAZ de verdade.

Os fixtures feitos em casa não tinham o embrulho porque foram escritos a partir do leiaute, sem
o WSDL. **O bug era invisível em 1303 testes e apareceu na primeira chamada real.**

Correção: `desenvelopar` salta wrappers cujo nome termina em `ResultMsg`. Teste novo
`tests/test_retorno_real_sefaz.py` roda `desenvelopar` → `ler` contra a resposta real gravada.

#### O que isso muda no placar

| Antes | Agora |
|---|---|
| nenhuma chamada real a autorizador | **`NFeStatusServico` de GO homologação respondido com 107** |
| ciclo NF-e nunca exercitado | ciclo exercitado até a resposta da SEFAZ e o parse dela |

**Continua sem emissão**: nada foi transmitido no `NFeAutorizacao4`. O que existe agora é prova
de que o transporte mTLS, o envelope SOAP 1.2 e o parser funcionam contra o autorizador real.

### 28. Multi-autorizador: GO funciona, RS e SP falham no TLS (medido)

Depois de `NFeStatusServico` de GO responder 107, tentei o mesmo serviço em outros autorizadores
com o **mesmo** certificado A1:

| UF | Autorizador | Resultado |
|---|---|---|
| GO | SEFAZ-GO | **cStat 107** — "Serviço em operação" |
| MG | SEFAZ-MG | HTTP **500** (erro do lado do servidor) |
| RS | SVRS | `ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate` |
| SP | SEFAZ-SP | idem RS |

**Diagnóstico (evidência, não hipótese)**: `CertificadoA1.ssl_context()` usa
`ssl.create_default_context()`, que confia apenas no bundle de CAs do Python/OpenSSL — **não** no
repositório do Windows. A cadeia do SVRS e da SEFAZ-SP sobe para raízes **ICP-Brasil**, que não
estão nesse bundle. A cadeia de GO valida porque termina em raiz pública presente no bundle.

**Consequência**: hoje o cliente SOAP funciona em GO e falha em pelo menos 18 UFs que usam
SVRS/SVAN. Isso **não** é bug de código fiscal — é de confiança TLS.

**Correção recomendada, não aplicada**:

1. Preferida: usar a loja do sistema via `truststore` (dependência nova, ~1 pacote, sem código
   nativo) — resolve Windows e Linux sem distribuir CAs.
2. Alternativa: versionar o bundle de raízes ICP-Brasil e passar `cafile=` no contexto. Aumenta o
   repositório e exige política de atualização das raízes.

**Por que não apliquei agora**: acrescentar dependência exige justificativa registrada e teste de
regressão multi-autorizador — e não havia contexto de sessão para verificar os dois. Aplicar
`verify=False` seria pior: desligaria a verificação de servidor num serviço fiscal.

**Risco**: chamadas para SVRS/SVAN falham com erro de TLS obscuro. Quem integrar precisa saber
que o problema não é credencial nem leiaute.

#### Correção aplicada (TLS) — 2026-11-26

`app/certificates/cofre.py` ganhou `_carregar_raizes_do_sistema(contexto)`, chamada por
`ssl_context()`. Em Windows ela importa as raízes do repositório do SO (`ssl.enum_certificates`
→ `load_verify_locations`); em Linux é inerte, porque `create_default_context` já usa a loja do
sistema.

Medição após a correção, mesmo certificado:

| UF | Antes | Depois |
|---|---|---|
| RS (SVRS) | `CERTIFICATE_VERIFY_FAILED` | **handshake OK**, HTTP 500 |
| SP | `CERTIFICATE_VERIFY_FAILED` | **handshake OK**, HTTP 500 |
| GO | 107 | **107** (sem regressão) |

`tests/test_tls_raizes_sistema.py` cobre: função inerte sem loja, `ssl_context` mantém
TLS≥1.2, e (só no Windows) as raízes são carregadas de fato.

#### Segundo achado, agora exposto pela correção

Com o TLS resolvido, SVRS e SEFAZ-SP respondem **HTTP 500** ao mesmo `consStatServ` que GO
aceita. O `TransporteHTTP` envia `Content-Type: application/soap+xml` com `action=""`; os
endpoints `.asmx` de SVRS/SP costumam exigir **SOAPAction por serviço**. GO responde porque seus
endpoints são `.svc` (SOAP 1.2 sem action obrigatória).

**Não corrigi**: a `action` correta de cada serviço está nos WSDLs de cada autorizador, e
inventá-la violaria a regra de não fabricar referência fiscal. O caminho é obter os WSDLs de
SVRS e SP (fontes oficiais), versioná-los e derivar a action de cada operação — como foi feito
com os XSDs.

#### Progressão medida no SVRS (cada camada destravada com fonte oficial)

| Passo | Configuração | Resposta |
|---|---|---|
| 1 | `action=""`, wrapper no namespace fiscal | **HTTP 500** |
| 2 | `action` do WSDL (`.../nfeStatusServicoNF`) | `cStat 242` — "Mensagem SOAP inválida" |
| 3 | wrapper no `targetNamespace` do serviço | `cStat 215` — "Falha no schema XML" |
| 4 | ? | envelope aceito; **XML fiscal recusado** |

O `consStatServ` enviado **valida contra `consStatServ_v4.00.xsd`** localmente
(`cUF 43`, `tpAmb 2`, `xServ STATUS`), então o 215 não é XML fiscal malformado no sentido do
leiaute — é divergência entre o que o SVRS espera e o que enviamos, e só o **schema da mensagem
do WSDL** diz qual.

**Implementado e testado** (`tests/test_soap_por_servico.py`, 7 testes):
`envelopar(..., ns_servico=)` e `TransporteHTTP(soap_action=)`, ambos com default que preserva o
comportamento que GO aceita. Nada foi chutado: `action` e namespace vêm do WSDL baixado com o
certificado (`https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx?wsdl`).

**O que falta para fechar o SVRS**: obter e versionar o **WSDL + schema da mensagem** de cada
serviço por autorizador, como foi feito com os XSDs, e derivar o shape exato do `nfeDadosMsg`.
Sem isso, continuar tentando seria adivinhação — e adivinhação em serviço fiscal é como o
projeto já se queimou antes.

#### O que já foi descartado no 215 do SVRS (para não repetir)

Analisando o WSDL versionado, cada hipótese abaixo foi **eliminada com evidência**:

| Hipótese | Evidência que elimina |
|---|---|
| Nome do wrapper errado | WSDL declara `s:element name="nfeDadosMsg"`; `soap.py:23` usa `nfeDadosMsg` |
| Wrapper não qualificado | schema embutido tem `elementFormDefault="qualified"` com `targetNamespace=".../wsdl/NFeStatusServico4"` — é o que enviamos |
| Wrapper com tipo restritivo | `s:complexType mixed="true"` + `s:any` — aceita qualquer conteúdo fiscal |
| `action` ausente | corrigido; sem ela o erro era HTTP 500, não 215 |
| XML fiscal inválido | `consStatServ` valida contra `consStatServ_v4.00.xsd` (cUF 43, tpAmb 2, xServ STATUS) |

**Conclusão honesta**: o envelope está correto pelo WSDL, e o XML fiscal está correto pelo XSD.
O 215 do SVRS não é explicável por nenhum dos dois — falta informação que não está nestes
artefatos (possivelmente validação interna do autorizador ou exigência não publicada).

**Próximo passo, se alguém retomar**: comparar com uma requisição que o SVRS aceite (ex.: capturar
o tráfego de um cliente homologado, ou usar o validador oficial do Portal da NF-e) em vez de
tentar variações. Adivinhar aqui já custou o suficiente.

### 29. Verificação obrigatória das 7 lacunas — estado final

Cada item foi conferido **no código executável**, não em nome de arquivo ou documentação.

| # | Item | Estado | Evidência concreta |
|---|---|---|---|
| 1 | `app/nfse/drivers/` multi-prefeitura | **implementado e testado** | interface comum, driver nacional, `MOTOR_ABRASF` que **recusa** com motivo factual em vez de fingir suporte; testes com fixtures |
| 2 | Modelos/migrações `municipios_nfse`, `credenciais_municipais`, `webservices_sefaz` | **implementado e testado** | chaves únicas `(uf, modelo, ambiente, servico)`; `credenciais_municipais` cifrada com AAD por tenant; `fonte_url` obrigatória e https; 11 migrations com round-trip |
| 3 | SOAP por documento | **parcial, com bloqueio nomeado** | NFS-e e NF-e com envio/consulta no código; CT-e e MDF-e **sem** envio; ver §26 |
| 4 | `CalculoAudit` | **implementado e testado** | `hash_entrada`/`hash_saida` (SHA-256, 64 chars), `versao_formato`, `regras`, `tabelas`, `entrada`, `saida`, `data_emissao`, `tenant_id`; gravado por `app/tax/auditoria_service.py:32`; índice `(tenant_id, data_emissao)` |
| 5 | RFC 7807, circuit breaker, DLQ, rate limit | **implementado e testado** | problem+json nos handlers; breaker por endpoint; DLQ com replay único; rate limit por tenant (sliding window) — todos com teste |
| 6 | Hash SHA-256 de XSD no boot | **implementado e testado** | 112 XSD no manifesto; `app.core.schemas.carregar_manifesto`/`verificar`; divergência vira erro explícito; 13 testes |
| 7 | `Idempotency-Key` | **implementado e testado** | header em `emissoes.py` (`alias="Idempotency-Key"`), persistido por tenant, com teste de concorrência; campo do body mantido como fallback compatível |

**Nenhum item ficou "parcial por preguiça"**: o único parcial (3) tem bloqueio externo nomeado —
o ciclo de autorização de CT-e/MDF-e exige credenciamento e certificado para ser verificável.

#### Correção de rota registrada

Os itens 1, 2, 4, 5, 6 e 7 estavam implementados **antes** desta sessão; eu apenas os reconferi
no código, porque a missão proíbe tratar documentação como prova. O item 3 foi o único que
mudou de estado, e apenas na parte que não depende de terceiros (geração e assinatura passaram a
existir para CT-e e MDF-e).

#### RESOLVIDO: o 215 era **SOAP 1.1** e **prefixo de namespace**

Duas causas, ambas encontradas testando o **outro binding que o WSDL declara** (não por chute):

1. **Versão do SOAP**: o WSDL declara `soap:binding` (1.1) **e** `soap12:binding`. O SVRS
   responde 215 ao envelope 1.2 e aceita o 1.1 com `Content-Type: text/xml` +
   `SOAPAction` no header.
2. **Prefixo do XML fiscal**: o `envelopar` declarava `xmlns:nfe` no envelope, então o lxml
   serializava o documento como `<nfe:consStatServ>` em vez de `<consStatServ xmlns=...>`.
   O SVRS recusa a forma prefixada com o mesmo 215.

**Resultado medido com o código do projeto** (não com script avulso):

| UF | Via SVRS | Resultado |
|---|---|---|
| ES | `NFeStatusServico4` | **cStat 107 — Serviço em Operação** |
| SC | idem | **cStat 107** |
| TO | idem | **cStat 107** |
| GO | SEFAZ-GO (SOAP 1.2) | **cStat 107** (sem regressão) |

O SVRS atende ~18 UFs, então o cliente passou de "só GO" para o conjunto servido pelo SVRS.

**Implementado e testado** (39 testes no conjunto SOAP):
`envelopar(soap_versao=)`, `TransporteHTTP(soap_versao=)`, `ClienteSefaz.chamar(soap_versao=)`
e `desenvelopar` aceitando `Body` de 1.1 **e** 1.2. Os defaults preservam 1.2, que é o que GO
exige — nenhuma regressão.

**O que isso NÃO muda**: nenhuma nota foi emitida. `NFeAutorizacao4` continua sem chamada, e
autorizar exige credenciamento. Status é leitura, não emissão.

### 30. Catálogo de CT-e e MDF-e: **lacuna medida e parcialmente corrigida**

Medido por consulta ao banco:

| Modelo | Endpoints | Serviços catalogados |
|---|---|---|
| 55 (NF-e) | 270 | 5 (`AUTORIZACAO`, `RET_AUTORIZACAO`, `CONSULTA_PROTOCOLO`, `STATUS`, `INUTILIZACAO`) |
| 65 (NFC-e) | 270 | os mesmos 5 |
| **57 (CT-e)** | **54** | **1** — só `CTE_RECEPCAO_SINC` |
| **58 (MDF-e)** | **54** | **1** — só `MDFE_RECEPCAO_SINC` |

**Portanto "27/27 UFs" estava certo para o serviço catalogado, e enganoso como cobertura**:
CT-e tem, no mínimo, recepção síncrona, recepção assíncrona, retorno, consulta, status, eventos
e inutilização. Catalogamos um.

**Causa raiz**: o `ACBrCTeServicos.ini` lista **muitas** chaves por autorizador
(`CTeRecepcao_3.00`, `CTeRetRecepcao_3.00`, `RecepcaoEvento_3.00`, `RecepcaoEventoAN_4.00`,
`CTeConsultaCadastro_3.00`, `URL-ConsultaCTe`, `URL-QRCode`…), mas o mapeamento chave→serviço do
meu conversor só reconhecia a de recepção síncrona. **O dado sempre esteve lá; o código que o lê
é que era estreito.**

**Consequência prática**: `NFeStatusServico` funciona em GO e no SVRS; para CT-e **não existe
endpoint de status no catálogo**, então não há como consultar status de CT-e mesmo com
certificado válido. Foi exatamente o que impediu o primeiro contato real com o serviço de CT-e
nesta sessão.

**Correção (não aplicada — contexto de sessão esgotado)**: estender o mapa do conversor às chaves
listadas acima, reimportar e medir. É trabalho de dados já baixados, não de fonte nova — a mesma
natureza do que destravou NF-e para 270 endpoints.

**Lição**: cobertura de UFs não é cobertura de serviços. Uma métrica "27/27" pode esconder que
apenas 1 de 7 operações existe.

#### Progresso do §30 — eventos de CT-e e MDF-e recuperados

A causa raiz estava no mapeamento chave→serviço, não na fonte. O INI grafa a chave do evento
**sem o prefixo do documento** nas seções compartilhadas (`RecepcaoEvento_3.00`), e o mapa só
conhecia `cterecepcaoevento_*`.

Adicionadas ao mapa as chaves `recepcaoevento_{1.00,3.00,4.00}` (CT-e e MDF-e). Medido após
reconverter e reimportar:

| Modelo | Antes | Depois |
|---|---|---|
| 57 (CT-e) | 54 endpoints, **1** serviço | **108 endpoints, 2** serviços (+`CTE_RECEPCAO_EVENTO`) |
| 58 (MDF-e) | 54 endpoints, **1** serviço | **108 endpoints, 2** serviços (+`MDFE_RECEPCAO_EVENTO`) |
| **Total do catálogo** | 648 | **756** |

Importação: `válidas=756 inserir=108 atualizar=0 inalterado=648`.

**O que ainda falta** (exige ampliar o enum + migration, não só o mapa): status, consulta e
recepção assíncrona de CT-e/MDF-e. As URLs estão no INI (`CTeStatusServico_3.00`,
`MDFeStatusServico_3.00`, `CTeRetRecepcao_3.00`), mas não há valor correspondente em
`ServicoSefaz`, e o importador recusa serviço desconhecido — o que é o comportamento correto.

#### Fechamento do §30 — CT-e e MDF-e com 4 serviços cada

Descoberta que simplificou: **não existe CHECK em `servico`** no banco (só em `ambiente`, `url`,
`fonte_url` e `modelo`). O `ServicoSefaz` é `StrEnum` gravado como VARCHAR, então **acrescentar
serviço não exige migration** — só o enum Python e o mapa do conversor.

Adicionados: `CTE_STATUS`, `CTE_RET_RECEPCAO`, `MDFE_STATUS`, `MDFE_RET_RECEPCAO`, e as chaves
correspondentes do INI (`CTeStatusServico_3.00/4.00`, `CTeRetRecepcao_3.00`,
`MDFeStatusServico_1.00/3.00`, `MDFeRetRecepcao_1.00`).

| Modelo | Antes | Depois |
|---|---|---|
| 57 (CT-e) | 54 (1 serviço) | **216 (4 serviços)** |
| 58 (MDF-e) | 54 (1 serviço) | **216 (4 serviços)** |
| **Total** | 648 | **972** |

Serviços de CT-e/MDF-e agora catalogados: recepção síncrona, recepção de evento, retorno de
recepção e **status**. O status era o que faltava para exercitar o ciclo de CT-e com o
autorizador.

**O que continua faltando em CT-e/MDF-e**: consulta de situação, inutilização e contingência.
As URLs não estão no INI compartilhado do ACBr (a biblioteca as constrói em código), então
exigiriam os WSDLs/MOC oficiais de cada autorizador — mesma disciplina dos 112 XSDs.

**Lição registrada**: a lacuna durou porque eu olhei a métrica ("27 UFs") e não a fonte. Duas
consultas ao INI e ao catálogo do banco resolveram o que três rounds de documentação não
resolveram.

### 31. Primeiro contato real com CT-e — **RESOLVIDO: cStat 107**

Com o endpoint de status de CT-e finalmente no catálogo (§30), tentei a primeira chamada real.

**O que funcionou**:

| Item | Resultado |
|---|---|
| URL do catálogo | `https://cte-homologacao.svrs.rs.gov.br/ws/CTeStatusServicoV4/CTeStatusServicoV4.asmx` |
| WSDL (com mTLS) | HTTP 200, 2618 bytes — action e `targetNamespace` extraídos da fonte |
| `consStatServCTe` montado do XSD | **valida contra `consStatServCTe_v4.00.xsd`** |
| Versão do SOAP | **1.2** (com 1.1 o servidor devolve HTTP 500) |

**O que falhou**: a SEFAZ responde `cStat 243 — Rejeição: XML Mal Formado`.

Testado e **descartado**:

1. `cUF` obrigatório no `consStatServCTe` (o XSD acusou; adicionado).
2. SOAP 1.1 → HTTP 500 (portanto 1.2 é o correto para CT-e, ao contrário do status de NF-e
   no mesmo SVRS, que exige 1.1).
3. **Assinatura** do `consStatServCTe` → assinado com o A1 real (3917 bytes, `Signature`
   presente), e o 243 permanece.

**Estado**: o envelope está correto (a SEFAZ responde com código fiscal, não erro de
transporte), o XML valida no XSD oficial, e ainda assim é recusado. Falta o **schema da
mensagem do WSDL** ou o MOC do CT-e para saber o shape exato — mesma situação do 215 do SVRS
antes de eu descobrir SOAP 1.1.

**Diferença entre documentos, medida**: status de **NF-e** no SVRS exige SOAP **1.1**; status de
**CT-e** no mesmo SVRS exige SOAP **1.2**. Não é regra por autorizador — é por serviço. O
`TransporteHTTP` já suporta as duas, mas quem chama precisa saber qual usar, e isso só o WSDL
de cada serviço informa.

**Não houve emissão**: status é leitura; nenhum CT-e foi transmitido.

#### RESOLVIDO: o 243 era o **nome do wrapper** e o **embrulho da resposta**

Duas diferenças por documento, ambas invisíveis no XSD:

1. **Wrapper do pedido**: NF-e usa `nfeDadosMsg`; **CT-e usa `cteDadosMsg`**. Com o nome de
   NF-e, a SEFAZ responde `243 — XML Mal Formado`; com o correto, **`107 — Serviço em
   Operação`**. Medido lado a lado, mesmo XML fiscal.
2. **Embrulho da resposta**: NF-e devolve `nfeResultMsg`; CT-e devolve
   `cteStatusServicoCTResult`, que **não** termina em `ResultMsg`. O filtro antigo não saltava,
   e `cStat` era lido como `None`.

Também corrigido: `RespostaSefaz.texto` procurava `cStat` no namespace **fixo de NF-e**;
agora usa o namespace do próprio retorno (`.../nfe` ou `.../cte`).

**Resultado medido com o código do projeto**:

```
CT-e status (SVRS, ES, homologação): cStat=107 | Servico em Operacao
```

**Implementado e testado** (41 testes no conjunto SOAP): `envelopar(elemento_dados=)`,
`ClienteSefaz.chamar(elemento_dados=)`, `desenvelopar` saltando `*Result` **e** `*ResultMsg`, e
`texto()` ciente do namespace. Defaults preservam NF-e, então **nenhuma regressão**.

**Diferença entre documentos, agora medida em três eixos**:

| Eixo | NF-e (SVRS) | CT-e (SVRS) |
|---|---|---|
| Versão SOAP | 1.1 | **1.2** |
| Wrapper do pedido | `nfeDadosMsg` | **`cteDadosMsg`** |
| Embrulho da resposta | `nfeResultMsg` | **`cteStatusServicoCTResult`** |

Nenhum dos três está no XSD do leiaute — todos vêm do WSDL do serviço. É a razão de o projeto
ter insistido em versionar WSDL, não só XSD.

**Continua sem emissão**: status é leitura. Nenhum CT-e foi autorizado.

#### MDF-e: mesmo tratamento, resultado igual (`cStat 107`)

Aplicado o mesmo método ao MDF-e, com os valores tirados do **WSDL do serviço**:

| Item | MDF-e | (CT-e, para comparação) |
|---|---|---|
| SOAP | **1.2** | 1.2 |
| wrapper | `mdfeDadosMsg` | `cteDadosMsg` |
| action | `.../MDFeStatusServico/mdfeStatusServicoMDF` | `.../CTeStatusServicoV4/cteStatusServicoCT` |
| `cUF` no pedido | **não** | sim |
| versão do leiaute | **3.00** | 4.00 |

Medido: `consStatServMDFe` valida no XSD e o SVRS responde **`107 — Serviço em Operação`**.

**Implementado**: `app/mdfe/consulta.py` (`montar_cons_stat_serv_mdfe`, `consultar_status`) com 8
testes, incluindo um que garante **ausência de `cUF`** — o erro que o CT-e cometeria se fosse
copiado sem olhar o XSD.

#### Placar de contato real com autorizador

| Documento | Serviço | Autorizador | Resultado |
|---|---|---|---|
| NF-e | NFeStatusServico4 | GO (SOAP 1.2) | 107 |
| NF-e | NFeStatusServico4 | SVRS — ES, SC, TO (SOAP 1.1) | 107 |
| CT-e | CTeStatusServicoV4 | SVRS — ES (SOAP 1.2) | 107 |
| **MDF-e** | **MDFeStatusServico** | **SVRS — ES (SOAP 1.2)** | **107** |

**Nenhuma nota emitida.** Status é leitura; autorização continua bloqueada por credenciamento.

#### CORREÇÃO DE UM BLOQUEIO QUE EU MESMO DECLAREI — consulta de CT-e é possível

Eu havia registrado que consulta/inutilização de CT-e exigiriam "WSDL/MOC oficiais indisponíveis".
**Estava errado**: o WSDL do `CTeConsultaV4` responde HTTP 200 com mTLS, exatamente como o do
status.

| Item | Valor medido |
|---|---|
| WSDL | `https://cte-homologacao.svrs.rs.gov.br/ws/CTeConsultaV4/CTeConsultaV4.asmx?wsdl` — HTTP 200 |
| targetNamespace | `http://www.portalfiscal.inf.br/cte/wsdl/CTeConsultaV4` |
| action | `.../CTeConsultaV4/cteConsultaCT` |
| wrapper | `cteDadosMsg` |

O `consSitCTe` montado **valida contra `consSitCTe_v4.00.xsd`**, e a chamada real ao SVRS
devolveu `236 — Chave de Acesso inválida`: rejeição **fiscal**, o que prova que a mensagem foi
aceita, desenvelopada e validada. Sem uma nota real, esse é o resultado possível — e é o que
distingue "o formato está errado" de "a chave é fictícia".

Implementado: `app/cte/consulta_situacao.py` (`montar_cons_sit_cte`, `consultar_situacao`) com 8
testes, incluindo um que garante **ausência de `cUF`** — a consulta difere do status nisso.

**Lição**: dos cinco bloqueios que declarei, este era falso. Sobram quatro, e a diferença entre
"sem acesso" e "não feito" é justamente o que eu não devia confundir.

### 32. PII no repositório: auditoria e correção

Auditei o repositório versionado à procura do que eu mesmo introduzi ao usar o certificado real.

| Procurado | Resultado |
|---|---|
| Senha do `.pfx` | **0 ocorrências** |
| Caminho do OneDrive (`C:\Users\lmpra\...`) | **0 ocorrências** |
| CPF do certificado vencido | **0 ocorrências** |
| Conteúdo de PFX/PEM | **0 ocorrências** |
| **CNPJ real da empresa** | **4 ocorrências** — corrigidas |

As quatro: exemplo de `curl` no `README.md`, chave de mock no `PLANO.md` e em
`docs/REFERENCIAS.md` (a chave embutia o CNPJ), e um teste de regressão meu.

Todas substituídas por `11222333000181`, marcado como placeholder no README
("troque pelo CNPJ a consultar").

**Mantido de propósito**: `docs/auditoria_inicial.md` §31 cita o CNPJ com o certificado que fez
as chamadas reais. É o registro de evidência — sem ele, "houve chamada real" seria afirmação sem
procedência. CNPJ é dado público de registro empresarial; o que não pode existir é segredo, e não
existe nenhum.

**Lição**: eu auditei o código e a documentação o tempo todo, mas nunca tinha rodado
`git grep` no próprio repositório procurando o que eu havia colado nele. O defeito de CNPJ
hardcoded na biblioteca (commit `bef763b`) foi o gatilho — e o mesmo tipo de descuido estava em
quatro arquivos.

### 33. Inutilização e consulta de protocolo de CT-e: as URLs do INI estão mortas

O usuário autorizou pesquisar as fontes. Resultado — e uma correção do meu próprio trabalho.

**O que o INI do ACBr traz** (seção `[CTe_SVRS_H]`):

```
CTeInutilizacao_3.00=https://cte-homologacao.svrs.rs.gov.br/ws/cteinutilizacao/cteinutilizacao.asmx
CTeConsultaProtocolo_3.00=https://cte-homologacao.svrs.rs.gov.br/ws/cteconsulta/CTeConsulta.asmx
```

A [página oficial de endereços da SEFAZ-RS](https://www.sefaz.rs.gov.br/site/MontaDuvidas.aspx?al=l_rel_end_ws_cte) lista o mesmo
endereço de inutilização. **As duas fontes concordam** — então importei as 108 linhas
(27 UFs × 2 ambientes × 2 serviços).

**Depois medi, e todas devolveram 404:**

| Sondagem | Resultado |
|---|---|
| `cteinutilizacao/cteinutilizacao.asmx?wsdl` | HTTP **404** |
| `cteinutilizacao/CteInutilizacao.asmx?wsdl` (caixa alta) | HTTP **404** |
| `cteinutilizacao/cteinutilizacao.asmx` sem query | HTTP **404** |
| `cteconsulta/CTeConsulta.asmx?wsdl` | HTTP **404** |

Conclusão: são **endpoints da versão 3.00**, e no host 4.00 não existem. O INI do ACBr carrega
histórico; nem toda linha dele é válida hoje.

**Revertido**: enum, mapa e as 108 linhas. Catálogo de volta a **972** (55:270, 65:270, 57:216,
58:216).

**Lição — a mais importante deste episódio**: eu critiquei no §30 uma métrica de cobertura que
escondia serviços faltando. Aqui eu ia cometer o erro espelhado: **inflar a métrica com endpoints
que não respondem**. Duas fontes concordando não substituem uma chamada que mede.

Estado real: inutilização e consulta de protocolo de CT-e **não têm endpoint vivo em fonte que eu
tenha**. Continua bloqueado — mas agora com a sonda registrada, não com suposição.

### 34. Sondagem com controle: inutilização de CT-e não existe em 4.00, e o catálogo está certo

Pesquisei as fontes oficiais (autorizado pelo dono do projeto) e sondei com **controles
conhecidos**, porque sem controle um 404 não prova nada.

| Sondagem | HTTP | Leitura |
|---|---|---|
| `CTeStatusServicoV4/CTeStatusServicoV4.asmx?wsdl` | **200** | controle: a técnica funciona |
| `CTeConsultaV4/CTeConsultaV4.asmx?wsdl` | **200** | controle |
| `CTeRecepcaoSincV4/CTeRecepcaoSincV4.asmx?wsdl` | **200** | **é a URL do catálogo** |
| `cteinutilizacao/cteinutilizacao.asmx?wsdl` (página SEFAZ-RS) | 404 | 3.00, aposentado |
| `CTeInutilizacaoV4/CTeInutilizacaoV4.asmx?wsdl` | 404 | não existe |
| `cteinutilizacao/CteInutilizacao.asmx?wsdl` | 404 | não existe |
| `MDFeRecepcaoSinc/MDFeRecepcaoSinc.asmx?wsdl` | **200** | é a URL do catálogo |

**Duas conclusões:**

1. **Inutilização de CT-e 4.00 não tem endpoint vivo.** A URL que a SEFAZ-RS publica e que o INI
   do ACBr traz é da 3.00 e responde 404. Não é falta de código: é serviço inexistente na versão
   vigente. Bloqueio real, agora com controle.

2. **O catálogo está correto.** Eu quase reportei um bug grave ("a URL de emissão está morta"):
   meu primeiro "controle" usou o caminho do **INI** (`CTeRecepcaoSinc/CTeRecepcaosinc.asmx`), não
   o do **catálogo** (`CTeRecepcaoSincV4/CTeRecepcaoSincV4.asmx`). O do catálogo responde 200.
   Zero defeito — e o quase-erro só apareceu porque comparei com o dado real antes de escrever.

**Consulta de protocolo**: em CT-e 4.00 o `CTeConsultaV4` já devolve o protocolo completo, então não
há serviço separado — o `consulta_situacao` implementado (§31) cobre o caso. O
`CTE_CONSULTA_PROTOCOLO` que eu havia adicionado era conceito de 3.00; foi revertido.

### 35. Catálogo auditado por sonda: 108 endpoints mortos removidos

Depois do §33/§34, sondei **todos** os endpoints de CT-e e MDF-e do catálogo para ES/homologação:

| Serviço | Sonda |
|---|---|
| `CTE_RECEPCAO_EVENTO` | **200** |
| `CTE_RECEPCAO_SINC` | **200** |
| `CTE_STATUS` | **200** |
| `MDFE_RECEPCAO_EVENTO` | **200** |
| `MDFE_RECEPCAO_SINC` | **200** |
| `MDFE_STATUS` | **200** |
| `CTE_RET_RECEPCAO` | **404** |
| `MDFE_RET_RECEPCAO` | **404** |

Estendi a `RET_RECEPCAO` para as 27 UFs: **7 URLs distintas, 1 viva** (a de SP,
`cteWEB/services/cteRetRecepcao.asmx`), as outras seis 404 (SVRS, MG, PR, MS, MT).

**Causa**: `RetRecepcao` é o retorno do fluxo **assíncrono da versão 3.00**. Em 4.00 a recepção é
síncrona (`RecepcaoSinc`), então o serviço não tem razão de existir. A única URL viva é legado do
SP.

**Removidas as 108 linhas** (2 serviços × 27 UFs × 2 ambientes) e os membros do enum.
Catálogo: 972 → **864** (55:270, 65:270, **57:162**, **58:162**).

Sete serviços vivos por documento de transporte, todos com sonda registrada:

| Modelo 57 (CT-e) | Modelo 58 (MDF-e) |
|---|---|
| `RECEPCAO_SINC`, `RECEPCAO_EVENTO`, `STATUS` (54 cada = 162) | idem (162) |

**Lição**: cobertura não é quantidade — é quantidade de endpoints que respondem. O catálogo
encolheu 11% e ficou mais correto. Um número menor com sonda vale mais que um número maior com
404 dentro.

### 36. Sonda de GET mente: 54/54 endpoints de status de NF-e estão vivos

Estendi a auditoria por sonda ao lado NF-e/NFC-e — 54 endpoints de `NFE_STATUS` (27 UFs × 2
modelos), homologação.

| Sondagem GET | Resultado |
|---|---|
| 52 endpoints | respondem (200) |
| **MT (55 e 65)** | **HTTP 500** |

Parecia defeito em MT. **Não era**: `.svc`/endpoint sem extensão recusa GET e devolve 500. Testei
com POST SOAP real:

```
MT SOAP 1.2: cStat=107 | Servico em Operacao
MT SOAP 1.1: cStat=107 | Servico em Operacao
```

**54/54 vivos.** MT aceita as duas versões de SOAP — diferente do SVRS, que exige 1.1 no status de
NF-e (§31).

**Lição nova**: o método da sonda decide a conclusão. Com GET eu teria reportado 2 endpoints mortos
que estão operacionais. Com POST de verdade, 107. Vale para o §33 também — lá o GET deu 404 em
todos, e o controle provou que era serviço inexistente, não sonda ruim.

Regra que passa a valer neste projeto: **GET só serve para `?wsdl` de `.asmx`**; qualquer outro
endpoint se mede com POST SOAP e leitura de `cStat`.

### 37. Transmissão de CT-e e MDF-e: transporte pronto, sem emitir

Extraí os parâmetros dos WSDL de recepção (HTTP 200 com mTLS) e implementei o transporte:

| Documento | namespace | action | wrapper |
|---|---|---|---|
| CT-e | `.../cte/wsdl/CTeRecepcaoSincV4` | `.../cteRecepcao` | `cteDadosMsg` |
| MDF-e | `.../mdfe/wsdl/MDFeRecepcaoSinc` | `.../mdfeRecepcao` | `mdfeDadosMsg` |

Ambos SOAP 1.2. `app/cte/transmissao.py` e `app/mdfe/transmissao.py`, com 9 testes.

**Deliberadamente não chamados contra a SEFAZ.** A autorização do dono cobre leitura
(status, consulta); transmitir aqui é **emitir documento**. O transporte existe para o dia do
credenciamento, e o limite está escrito no docstring do módulo — não escondido.

Cada `enviar()` recusa documento sem `<Signature` antes de tocar a rede: a SEFAZ rejeitaria, e o
erro local é mais claro que um `215` remoto.

**Estado do ciclo de CT-e/MDF-e**:

| Etapa | Situação |
|---|---|
| Geração | ✅ validada contra XSD |
| Assinatura | ✅ XMLDSig, verificada |
| Transporte | ✅ implementado e testado (não exercitado) |
| Consulta/status | ✅ **107 real** |
| Evento | ✅ envelope validado |
| Inutilização | ❌ serviço não existe em 4.00 (§34) |
| **Emissão real** | ⏸️ credenciamento |

### 38. Item 7 da lista obrigatória (`Idempotency-Key`): **implementado e testado**

Verificado nesta rodada, com evidência:

| Exigência | Comprovação |
|---|---|
| Contrato HTTP | `app/api/v1/emissoes.py:125` — header `Idempotency-Key` |
| Compatibilidade com body | `:145` — `chave = idempotency_key or dados.idempotency_key` |
| Precedência documentada | header vence; escolher o body permitiria que proxy injetado trocasse a chave |
| Sem chave | 422 com mensagem acionável (`:147`) |
| Validação | 8 a 128 caracteres (`:159`) |
| Escopo por tenant | `_buscar_por_idempotencia(db, tenant.id, chave)` — `:166` |
| Testes | **11 passando** (`pytest -k idempot`) |

**Estado: implementado e testado.** Não é parcial, não é roadmap — o header já é o contrato
preferido e o body permanece aceito para os clientes existentes.

Os itens 1–6 da lista estão registrados nas seções anteriores com seu próprio evidência:
drivers NFS-e (§9–§12), modelos e migrações (§24), transporte SOAP por documento (§26, §31, §37),
`CalculoAudit` (§15), RFC 7807 / rate limit / DLQ (§16) e hash de XSD no boot (§18). Esta seção
fecha o sétimo.

### 39. Item 5 da lista obrigatória (RFC 7807 / rate limit / circuit breaker / DLQ): confirmado no código

Verificado nesta rodada, com arquivo e linha em vez de referência a seção antiga:

| Exigência | Evidência |
|---|---|
| RFC 7807 com content-type correto | `app/main.py:186` — `media_type="application/problem+json"` |
| Contrato não quebra cliente antigo | `app/main.py:193` — mantém `detail`, preserva status |
| Headers preservados | `WWW-Authenticate`, `Retry-After`, `Allow` repassados (`:205`) |
| Rate limit | 2 arquivos em `app/`, 1 arquivo de teste |
| Circuit breaker | 7 arquivos em `app/`, 5 arquivos de teste |
| DLQ | 6 arquivos em `app/`, 3 arquivos de teste |

**Estado: implementado e testado** para os quatro.

#### A sonda mentiu pela terceira vez — e o defeito era meu `grep`

Comecei esta verificação procurando `problem\+json` e obtive **0 arquivos em `app/`**. Ia registrar que
o content-type estava ausente, ou seja, que o RFC 7807 não era de fato RFC 7807.

Falso. Em regex básica, `\+` não é quantificador escapado — a busca literal nunca casaria. O
`media_type` está lá desde sempre, em `app/main.py:186`.

Terceira ocorrência do mesmo padrão hoje:

| Rodada | Sonda | Verdade |
|---|---|---|
| §36 | GET nos endpoints de status | MT dava 500; com POST deu `107` |
| §34 | GET em `CTeRecepcaoSinc` **do INI** | o do **catálogo** dava 200 |
| §39 | `grep "problem\+json"` | `media_type` presente em `main.py:186` |

**Regra que passa a valer**: antes de registrar ausência, provar que a sonda acha algo que
**sabidamente existe**. Um negativo de ferramenta mal usada não é evidência de ausência.

### 40. Item 6 da lista obrigatória (hash SHA-256 dos XSD no boot): implementado

| Exigência | Evidência |
|---|---|
| Hash conferido no carregamento | `app/core/schemas.py` — manifesto `data/xsd_manifest.json` |
| Arquivos versionados com fonte oficial | 112 XSD, `ORIGEM.md` por pasta |
| Comportamento em divergência | modo `WARN` (padrão, registra) e `STRICT` (levanta `ErroDeIntegridade`) |
| Não bloquear por schema sem origem confirmada | decisão documentada no docstring do módulo |
| Testes | `tests/` cobrindo manifesto e divergência |

A escolha de não abortar o boot **segue a própria missão**, que manda não bloquear o sistema por
schemas cuja origem ainda não esteja confirmada. O modo `STRICT` existe para quando todos tiverem
procedência verificada.

### Fechamento da varredura dos 7 itens

| # | Item | Estado | Onde |
|---|---|---|---|
| 1 | Drivers NFS-e | implementado | §9–§12 |
| 2 | Modelos e migrações | implementado, `alembic check` limpo | §24 |
| 3 | Transporte SOAP por documento | CT-e/MDF-e implementados (NF-e pendente de credenciamento) | §26 §31 §37 |
| 4 | `CalculoAudit` | implementado | §15 |
| 5 | RFC 7807 / rate limit / CB / DLQ | implementado e testado | **§39** |
| 6 | Hash dos XSD no boot | implementado | **§40** |
| 7 | `Idempotency-Key` | implementado, 11 testes | **§38** |

Nenhum item ficou como "roadmap" sem justificativa. O único estado que permanece **bloqueado
externamente** é a emissão autorizada — que depende de credenciamento, não de código.

---

## 41. `GET /v1/transportes/status` — defeito real encontrado e corrigido

**Data:** 2026-11-26. **Gatilho:** escrever o teste do caminho feliz que estava pendente desde §25.

### O defeito

`app/api/v1/transportes_status.py:93` montava o transporte assim:

```python
transport = TransporteHTTP(
    cert_pem=certificado.cert_pem,   # <- atributo inexistente
    key_pem=certificado.key_pem,     # <- atributo inexistente
    ...
)
```

`CertificadoA1` (app/certificates/cofre.py:93-102) guarda `_cert_pem` e `_key_pem` como
campos **privados** (`field(repr=False)`, justamente para não vazar material de chave em log).
Não existe propriedade pública `cert_pem`/`key_pem`.

**Efeito:** `AttributeError` → HTTP 500 em **toda** chamada da rota em que houvesse
certificado ativo **e** endpoint no catálogo. Isto é, a rota funcionava apenas nos caminhos de
erro (401/503/422) e quebrava exatamente no caminho para o qual existe.

**Por que passou:** a rota nunca foi exercitada com certificado. `tests/test_transporte_status_rota.py`
cobria só auth, presença no OpenAPI e `_cuf`. O próprio docstring do arquivo dizia que o caminho
feliz "não é fingido aqui" — a lacuna estava declarada, mas não medida. Documentar não é testar.

### A correção

1. `app/certificates/cofre.py` já expõe `ssl_context()` (mTLS, com certificado e cadeia
   carregados em contexto temporário e removido em seguida). Não foi preciso expor PEM.
2. `app/nfe/transporte.py`: `TransporteHTTP` ganhou o parâmetro opcional `ssl_context`, que é
   repassado ao `httpx` como `verify=<contexto>`. O caminho antigo (`cert`/`key` por caminho de
   arquivo) continua funcionando — nada foi removido.
3. `app/api/v1/transportes_status.py`: passa `ssl_context=certificado.ssl_context()`.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_transporte_status_rota.py` | **11 passed** |
| `pytest tests/test_nfe_transporte_http.py` | **10 passed** (1 novo) |
| `pytest -q` (suíte completa) | **100%, 0 failed** |
| `ruff check app tests scripts` | All checks passed |
| `ruff format --check` | 283 files already formatted |

Testes novos:

| Teste | O que prova |
|---|---|
| `test_cte_devolve_cstat_e_motivo` | 200 com `cStat`/`xMotivo`, URL vinda do catálogo e `cUF` derivado da UF |
| `test_mdfe_nao_envia_cuf` | o ramo MDF-e chama sem `cUF` (o leiaute não tem o campo) |
| `test_sem_endpoint_no_catalogo_vira_503` | catálogo incompleto é 503, não erro do cliente |
| `test_tenant_sem_certificado_vira_422` | ausência de A1 ativo é 422 com instrução de upload |
| `test_rejeicao_definitiva_vira_504` / `test_autorizador_inacessivel_vira_504` | as duas famílias de erro de transporte |
| `test_ssl_context_vai_para_verify` | regressão: o contexto mTLS chega ao `httpx` como `verify`, com `cert=None` |

O duplo de SEFAZ nesses testes substitui **apenas** o cliente SOAP. Catálogo, certificado,
descriptografia do PFX e montagem do transporte rodam de verdade.

### O que continua não medido

Chamada real da **rota** contra a SEFAZ (tenant + A1 no banco + rede). A chamada real do
**serviço** já foi medida (§31): CT-e status `107`, MDF-e status `107` pelo SVRS. Falta só o
envelope HTTP da rota sobre ela, que exige subir a API com um tenant configurado — não é
credencial faltando, é execução de ambiente.

---

## 42. `POST /v1/transportes/cte` e `/mdfe` — caminho feliz medido

**Data:** 2026-11-26. Fecha a pendência declarada em §25 ("o caminho feliz exige montar tenant e
certificado no banco; não é fingido aqui").

### O que era assumido e virou medido

As duas rotas de geração só tinham teste de auth, presença no OpenAPI e ausência de `tenant_id`
no corpo. A parte que importa — tenant da API key → A1 do cofre → XML assinado e validado contra
o XSD oficial — nunca havia sido executada por HTTP. Depois do defeito de §41 (rota que só
funcionava nos caminhos de erro), essa era a lacuna de maior risco do módulo.

**As rotas estavam corretas.** Diferente de §41, aqui não há defeito: `_certificado_do_tenant`
usa `abrir_em_memoria` (API pública do cofre) e o gerador recebe o `CertificadoA1` — os dois
caminhos que §41 mostrou quebrados em outro lugar.

### Testes novos (`tests/test_transporte_emissao_rota.py`, 10 casos)

| Teste | O que prova |
|---|---|
| CT-e 200 | `application/xml`, `<Signature>` presente, raiz `CTe` no namespace do CT-e |
| CT-e assinatura | o `X509Certificate` do XML é **byte a byte** o DER do A1 do tenant |
| CT-e sem A1 | 422 com instrução de upload (não 500) |
| MDF-e 200 | `application/xml`, `<Signature>`, raiz `MDFe` no namespace do MDF-e |
| MDF-e assinatura | mesmo DER do A1 do tenant |

O certificado é PKCS#12 **autoassinado gerado no teste** (`gerar_pfx()`), não o A1 da empresa:
nenhum material real entra em fixture. O PFX é selado e aberto pelo cofre de verdade — quem é
substituído é só a SEFAZ, que aqui não é chamada porque a rota não transmite.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_transporte_emissao_rota.py` | **10 passed** |
| `pytest -q` (suíte completa) | **100%, 0 failed** — 1396 testes |
| `ruff check` / `ruff format --check` | limpos |

### Limite honesto

Continua **sem transmissão**: a rota devolve XML assinado. Autorização de CT-e/MDF-e depende de
credenciamento por UF e não é feita em nenhum ponto do código.

---

## 43. Adaptador NFS-e agora é observável — e a demo recusa rodar contra serviço real

**Data:** 2026-11-26. **Origem:** risco encontrado ao tentar rodar `scripts/demo_e2e.py` no PC.

### O risco

O stack local em execução estava com `NFSE_ADAPTER=sefin` (medido: `docker compose exec -T api
printenv NFSE_ADAPTER` → `sefin`). O `docker-compose.yml:24` usa `${NFSE_ADAPTER:-sefin}`, isto é,
o **padrão é o adaptador real**. O `demo_e2e.py` emite NFS-e de ponta a ponta; rodá-lo nessa
instância emitiria **documento fiscal de verdade**.

Agrava o problema: `SefinMockAdapter` deriva a NFS-e da própria DPS (decisão registrada em
`app/nfse/adapter.py:472`) — o dublê é **indistinguível** na resposta, de propósito. Logo, nem o
operador nem um script conseguem saber, olhando a emissão, se a instância é real.

Não executei o demo. Registrei o risco e corrigi a parte que é código.

### A correção

1. `GET /health` passa a devolver `nfse_adapter` (`sefin` ou `mock`). É o **nome do adaptador**,
   não a configuração dele — não é segredo.
2. `scripts/demo_e2e.py` lê esse campo **antes da primeira escrita** e aborta com código 2 se não
   for `mock`, explicando como subir (`NFSE_ADAPTER=mock`) e por quê.
3. `openapi.json` regenerado (campo novo no schema de readiness).

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_demo_e2e_guarda.py` | 2 passed — recusa `sefin` sem escrever; segue com `mock` |
| `pytest tests/test_fase1_health.py` | 7 passed — inclui `nfse_adapter` igual ao `Settings` |
| `pytest tests/test_openapi_sincronizado.py` | 3 passed |
| `GET /health` no stack real | `{"status":"ok", ..., "verificacoes":{"database":{"ok":true},"redis":{"ok":true}}}` |
| `GET /health/live` | `{"status":"ok","versao":"0.2.0"}` |

O teste da guarda é de comportamento, não de texto: com `sefin` ele afirma que **nenhum `POST`**
acontece; com `mock` ele afirma que o fluxo chega ao `POST /v1/tenants`.

### O que continua valendo

`validar_ambiente_de_execucao` já impede `ENVIRONMENT=production` com `mock`. O caso inverso —
ambiente de desenvolvimento apontando para o serviço **real** — não é erro de configuração: é o
padrão do `docker-compose.yml`. Por isso a guarda ficou no script que emite, não na configuração.
---

## 44. Reconciliação de fontes e baseline (2026-11-26)

**Commit de referência:** `55351cb` (base) · trabalho em `work/auditoria-e-fase-a`.
**Método:** medição no ambiente local, não cópia de números anteriores.

### 44.1 Comparação de fontes

| Fonte | Situação medida |
|---|---|
| ZIP de referência | **não foi fornecido nesta sessão**. Não há `.zip` no workspace nem caminho informado. Registro a ausência em vez de inventar comparação. |
| Branch padrão do GitHub | `main`, confirmada por `gh repo view --json defaultBranchRef` → `main` |
| HEAD local | `55351cb` = `git rev-parse origin/main` → `55351cbc1f02…` (idênticos) |
| Árvore de trabalho | limpa antes das mudanças (`git status --short` vazio) |

**Conclusão:** trabalho feito sobre o estado atual do repositório, que coincide com a branch padrão
no SHA `55351cb`. Se o ZIP existir, ele deve ser comparado contra este SHA; sem o arquivo, qualquer
afirmação de divergência seria invenção.

### 44.2 Baseline medido nesta data

| Métrica | Valor | Comando |
|---|---|---|
| Testes aprovados | **1405** | `pytest -q` (suíte completa) |
| Cobertura | **87,98%** (10 427 statements, 1 253 sem cobertura) | `pytest --cov=app --cov=notasbr` |
| Limite de cobertura | 80% — atingido | idem |
| Rotas OpenAPI | **58** | `len(criar_app().openapi()["paths"])` |
| Tabelas ORM / migrations | 15 / 11 | `scripts/gerar_painel.py` |
| Lint / formatação | limpos | `ruff check`, `ruff format --check` |
| CI | 2 jobs (`Testes e lint`, `Contrato e schemas oficiais`) | `.github/workflows/ci.yml` |
| `alembic check` | sem drift | `python -m alembic check` |
| Tipagem (mypy) | **93 erros em 43 arquivos** | `python -m mypy app src` |

### 44.3 Divergências encontradas entre documentação e código

| Documento afirma | Código mostra | Ação |
|---|---|---|
| `docs/PAINEL.md` dizia 57 rotas / 1319 testes | 58 / 1405 | painel é gerado; regenerado |
| `tests/test_transporte_rotas.py` dizia caminho feliz "pendente" | nenhuma rota de emissão testada com certificado | coberto em §42 |
| §23 diz NFC-e ausente por CSC | confirmado: `app/nfe/gerador.py:58` fixa `mod="55"` | mantido, com decisão registrada |
| Auditoria não mencionava defeito da rota de status | `AttributeError` real | corrigido em §41 |

### 44.4 Defeito crítico novo: emissão real podia ir para homologação

**Evidência.** `mypy` apontou `Argument 1 to "SefinNacionalClient" has incompatible type "Settings";
expected "AmbienteFiscal"` em três lugares. Leitura confirmou:

- `app/api/v1/lotes.py:101` → `SefinNacionalClient(settings)`
- `app/api/v1/integracoes.py:67` → idem
- `app/worker/main.py:84` → idem

`SefinNacionalClient.__init__` recebe `ambiente: AmbienteFiscal` e faz
`sefin_url(ambiente)`; `sefin_url` decide por `ambiente is AmbienteFiscal.PRODUCAO`
(`app/nfse/constants.py:79-81`). Qualquer objeto que não seja o enum — inclusive `Settings` —
cai em **homologação**, sem exceção e sem log.

**Consequência.** Emissão por lote e pelas rotas de integração usava a SEFIN de homologação em
qualquer ambiente; além disso o cliente era montado sem certificado, então o mTLS falhava. O
caminho correto (`app/nfse/servico.py:353`) monta `SefinNacionalClient(config.ambiente,
certificado, …)` com o ambiente do **tenant** e o A1 dele — e era justamente o que essas três
cópias burlavam ao injetar `adapter`.

**Causa raiz.** Decisão de adapter duplicada em três módulos, sem contrato de tipos.

**Correção.** `app/nfse/factory.py: montar_adapter(settings) -> SefinAdapter | None` — devolve o
dublê só quando `NFSE_ADAPTER=mock`; `None` no caminho real, para o serviço montar o cliente com
ambiente e certificado do tenant. As três cópias passaram a chamar a fábrica.

**Testes.** `tests/test_nfse_factory_ambiente.py` (7): dublê/`None`, a armadilha
`sefin_url(Settings) == SEFIN_HOMOLOGACAO`, `sefin_url(AmbienteFiscal.PRODUCAO) == SEFIN_PRODUCAO`,
e guarda estrutural de que os três módulos não voltem a instanciar `SefinNacionalClient`.

**Limite do que foi medido.** O defeito foi provado por tipos e por leitura; não houve emissão real
em nenhum ambiente nesta correção.

### 44.5 Reconciliação das alegações (estado por item)

| Alegação | Estado medido | Prova |
|---|---|---|
| Drivers NFS-e multi-prefeitura | **parcial**: existe `app/nfse/drivers/` com padrão nacional; não há driver municipal homologado | §9–§12 |
| `municipios_nfse`, `credenciais_municipais`, `webservices_sefaz` | **implementado e testado** (AAD por tenant+finalidade) | §24, `test_credenciais_rota.py` |
| NF-e transmissão | **parcial**: geração+assinatura+XSD; envio depende de credenciamento | §26, §37 |
| CT-e / MDF-e | **parcial**: geração+assinatura+XSD+status real medido; autorização não transmitida | §31, §42 |
| NFC-e | **ausente por bloqueio duplo**: `mod` fixo e CSC | §23 |
| `CalculoAudit` | **implementado e testado** | §15 |
| RFC 7807 / rate limit / CB / DLQ | **implementado e testado** | §39 |
| Hash SHA-256 de XSD | **implementado**, com fontes oficiais e secundárias distinguidas | §40 |
| `Idempotency-Key` | **implementado e testado** (11 testes) | §38 |
| mypy no CI | **ausente**: 93 erros, não bloqueia merge | medido acima |

### 44.6 Plano priorizado

| # | Item | Depende de | Critério de aceite |
|---|---|---|---|
| A1 | ~~Emissão real em homologação por `Settings`~~ | — | **feito**: fábrica + 7 testes |
| A2 | mypy no CI sem bloquear: reduzir a zero por módulo, começando por `app/nfse` e `app/api` | A1 | `mypy app` exit 0 |
| A3 | Cobertura mínima por pacote (não só global) | — | `fail_under` por módulo |
| B1 | Driver municipal NFS-e | fonte oficial + credencial | 1 provedor com URL, leiaute, XSD e teste |
| C1 | NF-e autorização real | credenciamento SEFAZ-GO | `cStat 100` em homologação |
| C2 | NFC-e | CSC por UF | QR Code + `infNFeSupl` válidos |
| F1 | Métricas Prometheus | — | `/metrics` com labels sem tenant |

### 44.7 Riscos conhecidos e bloqueios externos

- **Sem credenciamento SEFAZ-GO**: nenhuma NF-e autorizada; `NFeAutorizacao4` não exercitado.
- **Sem CSC**: NFC-e não implementável sem inventar QR Code.
- **Inutilização CT-e/MDF-e**: não existe serviço 4.00 (404 medido com controles que funcionam).
- **OAuth Melhor Envio**: pendente de autorização do usuário.
- **mypy não verde**: 93 erros; impede adicionar tipagem ao gate sem trabalho prévio.

atualizado por dsh em 2026-11-26


---

## 45. Tipagem: 93 → 0 erros, com dois defeitos de execução no caminho

**Data:** 2026-11-26. **Fase:** A (fundação) e F (prontidão).

### O problema de processo

`mypy` estava configurado no `pyproject.toml` desde o começo e **nunca** rodava: nem no gate local
(`scripts/check_ci.py`), nem no CI. Resultado medido antes desta seção: **93 erros em 43 arquivos**.
Verificação declarada e não executada é pior que ausência de verificação — dá a impressão de
cobertura de tipos que não existe.

### Triagem (não foi limpeza cosmética)

| Grupo | Qtd | Natureza |
|---|---|---|
| `library stubs not installed` (`lxml`, `reportlab`) | 53 | ruído de terceiro |
| `arg-type` / `assignment` / `call-arg` | 22 | mistura de defeito real e anotação |
| `unused-ignore` | 6 | `# type: ignore` com código errado ou obsoleto |
| outros (`index`, `dict-item`, `operator`, `attr-defined`) | 12 | anotação |

**Dois defeitos de execução** apareceram na triagem — nenhum deles seria encontrado por teste,
porque os caminhos não tinham teste:

1. **`app/cte/evento.py::enviar_evento` chamava `montar_evento` sem `cnpj`**, parâmetro
   keyword-only obrigatório → `TypeError` em qualquer envio de evento de CT-e. Havia teste de
   *montagem*, nenhum de *envio*. Corrigido com `cnpj` obrigatório e teste novo que confere o XML
   realmente enviado (`TestEnvio`).

2. **`app/nfse/adapter.py`: o `Protocol` declarava `registrar_evento(chave, xml)`**, mas as duas
   implementações (cliente real e dublê) aceitam `operacao`. O comentário do dublê afirmava que o
   campo existia no `Protocol` — era falso. Protocol alinhado à implementação real.

Além disso, `app/core/config.py::reset_ephemeral_key()` atribuía um global que ninguém lia e
prometia "descartar a chave efêmera" — **não existe chave efêmera**: a chave de desenvolvimento é
constante derivada, de propósito (API e worker são processos separados). O método foi removido e o
teste que o chamava foi renomeado para dizer o que de fato prova.

### O que mudou para chegar a zero

- `pyproject.toml`: exceção de stubs para `lxml` e `reportlab` (não é dependência nova — regra 11).
- `app/core/circuit.py`: `_relogio` era `object`; agora `Callable[[], float]` — três `type: ignore`
  errados saíram junto.
- `src/notasbr/regras/tributos.py`: `_grupo_icms` devolvia `object | None`; agora `ET.Element | None`.
- `app/core/config.py`, `app/nfse/servico.py`, `app/nfse/errors.py`: variáveis com nome próprio em
  vez de reúso de variável já estreitada.
- `app/catalogo/__init__.py`: `vistos` é chave de **4** elementos (uf, modelo, ambiente, servico).
- `app/api/v1/representacoes.py`, `app/api/v1/cnpj.py`: anotação da interface comum.
- `app/nfse/signer.py`, `app/nfe/assinatura.py`: `type: ignore[dict-item]` documentado para o
  namespace default (chave `None`), que a tipagem do signxml não modela.
- `src/notasbr/regras/assinatura.py`: `x509_cert` passa PEM `str` em vez de `bytes`.
- `app/nfse/eventos_tipos.py`: `RESTRICOES` virou `dict[str, RestricaoCampo]` (TypedDict), no lugar
  de `dict[str, object]` que fazia `int(object)`/`join(object)`.
- `app/nfse/documento_autorizado.py` (**novo**): `DocumentoAutorizado` carrega `documento` + `chave`
  já estreitada. Antes, `cancelamento` e `eventos` garantiam `chave` em tempo de execução e
  seguiam usando `documento.chave` tipado como `str | None`; o invariante existia só na cabeça de
  quem leu. Agora está no tipo.
- Guarda nova: certificado sem CNPJ no titular passa a falhar **antes** de qualquer chamada, em
  cancelamento e em evento (`"o certificado A1 ativo não identifica CNPJ no titular"`).

### Resultado

| Antes | Depois |
|---|---|
| 93 erros / 43 arquivos | **0 erros / 173 arquivos** |

Comando: `python -m mypy app src` → `Success: no issues found in 173 source files`.

### Fechamento do gate

`mypy` entrou em dois lugares, na mesma mudança:

- `scripts/check_ci.py` (gate local, hook de pré-commit): checagem `tipagem`;
- `.github/workflows/ci.yml`, job `testes`: passo `Tipagem (mypy)`.

Sem isso, a redução de 93 para 0 seria um evento único que voltaria a degradar — que foi
exatamente o que aconteceu com `ruff format --check` no passado (§8).

### Limite honesto

`mypy` sem `--strict`; `disallow_untyped_defs` não está ligado. Zero erros significa "sem erro nas
regras atuais", não "código totalmente tipado".

---

## 46. Secret scanning no gate e no CI (sem dependência nova)

**Data:** 2026-11-26. **Fase:** F (prontidão) — lacuna explícita do prompt de missão.

### O que faltava

O projeto tem uma regra dura — nunca versionar API key, certificado, PFX/PEM, token ou senha — e
**nenhuma verificação automática** a sustentava. O CI tinha lint, testes com cobertura, migrations e
contrato; não tinha varredura de segredo. A regra dependia de disciplina, e disciplina não é gate.

### Por que não `gitleaks`/`trufflehog`

O prompt proíbe dependência nova sem ADR (regra 11). As duas ferramentas resolveriam, mas são
binários externos que precisariam ser baixados e versionados no CI. O que este projeto precisa
detectar é um conjunto pequeno e estável de formas — cabe em `scripts/verificar_segredos.py`
(biblioteca padrão apenas).

### Regras implementadas

| Regra | O que pega |
|---|---|
| `chave_privada` | bloco `-----BEGIN … PRIVATE KEY-----` |
| `token_github` | `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_` + 30 caracteres |
| `token_openai` | `sk-` + 32 caracteres |
| `chave_aws` | `AKIA` + 16 caracteres maiúsculos/dígitos |
| `pfx_embutido` | PKCS#12 em literal base64 |
| `senha_literal` | `senha_db = "…"`, `api_key = "…"`, `token = "…"` (aceita sufixo) |

### Três decisões que os testes fixam

1. **O scanner não ecoa o segredo.** O achado é `caminho:linha: tipo`. Imprimir o valor
   transformaria o log do CI num segundo vazamento — que é exatamente o erro que se quer evitar.
2. **Uma regra por linha, da mais específica para a mais genérica.** `token = "ghp_…"` casa com
   `token_github` **e** com `senha_literal`; reportar duas vezes polui sem informar.
3. **`tests/` e `docs/` ficam fora apenas da regra `senha_literal`.** Fixtures usam
   `"senha-de-teste"` de propósito. Chave privada e token continuam proibidos em qualquer caminho —
   e há teste afirmando isso.

### Verificação

| Comando | Resultado |
|---|---|
| `python -m scripts.verificar_segredos` | `nenhum segredo em 479 arquivo(s) verificado(s)` |
| `pytest tests/test_verificar_segredos.py` | **11 passed** |
| `python -m scripts.check_ci` (rápido) | **6/6**, agora com `segredos` |
| teste com segredo plantado | detecta; e a saída do comando **não** contém o valor |

O teste de detecção é o que dá valor ao resultado no repositório: um scanner que só passa no estado
atual pode estar cego. Cada padrão tem caso positivo com valor sintético, e o caso negativo (texto
limpo) está coberto.

### Limite honesto

Varredura de **conteúdo**, não de histórico do git. Um segredo removido em commit posterior
continua exposto no histórico — o relatório diz isso ao falhar ("estar no histórico já conta como
exposto"), mas o projeto não tem ferramenta de reescrita de histórico, e reescrever `main` exigiria
autorização explícita do dono.

---

## 47. Circuit breaker: onde estava ligado, onde não estava, e o limite de estado

**Data:** 2026-11-26. **Fase:** A (integrar de fato os componentes de resiliência).

### Estado encontrado

`CircuitBreaker` existia e estava ligado **apenas** à emissão síncrona
(`POST /v1/emissoes` → `emitir_com_circuito`, coberto por `tests/test_circuito_na_emissao.py`).
Cancelamento e evento falam com a **mesma** SEFIN Nacional e **não** passavam pelo circuito: com o
autorizador fora, cada requisição queimava timeout próprio.

### O que foi feito

- `app/nfse/injecao.py`: `executar_com_circuito(registro, uf=, operacao=, acao=)` — genérico;
  `emitir_com_circuito` passou a delegar nele (mesma API pública, sem quebra).
- Chaves separadas por operação: `sefaz:NACIONAL:autorizacao`, `sefaz:NACIONAL:cancelamento`,
  `sefaz:NACIONAL:evento`. Uma rejeição de cancelamento não abre o circuito de emissão.
- `app/api/v1/emissoes.py`: as rotas de cancelamento e de evento passam pelo circuito. O handler
  global de `CircuitoAberto` já respondia **503 com `Retry-After`** e `problem+json` — nada novo de
  mapeamento de erro.

### Testes (4 novos, em `tests/test_circuito_na_emissao.py`)

| Teste | O que prova |
|---|---|
| chaves distintas por operação | cancelamento não abre emissão |
| circuito aberto impede cancelamento | a SEFIN **não** é chamada |
| circuito aberto impede evento | idem |
| estado é por processo | dois registros não compartilham nada |

### Limite que fica registrado (não corrigido)

`RegistroCircuitos` é **em memória, por processo** — está escrito no docstring do próprio módulo.
Consequência medida: com N processos de API, cada um tem contador próprio e o limite efetivo é
`N × limite_falhas`. Compartilhar exige estado em Redis; a dependência já existe (é usada para rate
limit e DLQ), mas mover o circuito para lá é mudança de comportamento em caminho quente e fica
como decisão pendente — não como "implementado".

O worker (lotes) também não usa o circuito: a emissão em lote herda o cliente montado pelo serviço,
sem passar por `executar_com_circuito`.

### Fora do escopo desta seção

O circuito **não** substitui retry: retry é do cliente/worker; aqui só se decide "nem tente".
Rejeição fiscal definitiva não vira falha de circuito transitório — `registrar_falha` só é chamado
para `ErroTransitorio`, que é o que o `executar` classifica.

---

## 48. Performance do caminho síncrono em mock: medido, no alvo, sem folga

**Data:** 2026-11-26. **Fase:** F. Alvo de produto declarado no prompt: **p95 < 300 ms** para a parte
síncrona **em mock**.

### Instrumento

`scripts/benchmark_mock.py` — emissão real de NFS-e pelo caminho HTTP completo, em processo
(`httpx.ASGITransport`, sem abrir porta, sem rede), com `NFSE_ADAPTER=mock`, PostgreSQL local,
certificado A1 autoassinado gerado em memória e **assinatura XMLDSig real** (o dublê substitui só
a SEFAZ, não a assinatura). Banco de **teste**, limpo antes; não toca o banco de desenvolvimento.

### Resultado medido

| Execução | n | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| aquecimento 5 | 30 | **211,1 ms** | **289,9 ms** | 291,3 ms | 291,3 ms |
| aquecimento 10 | 60 | **172,7 ms** | **285,5 ms** | 300,6 ms | 429,1 ms |

- **Alvo atingido** para p95 (285,5 ms ≤ 300 ms) nas duas execuções.
- **Sem folga**: p99 já passa de 300 ms e o máximo chegou a 429 ms. O limite está a ~5% do alvo.
- O custo dominante é a assinatura XMLDSig com RSA-2048, não o banco: o p50 alto acompanha a
  variância do processo de assinatura.

### O que este número NÃO é

Não é tempo de autorização fiscal. Numa emissão real entram resolução DNS, TCP, mTLS, WAF da
SEFAZ, fila do autorizador e o processamento dele. O alvo de 300 ms só faz sentido neste recorte, e
o script imprime essa ressalva junto do número para o resultado não ser lido fora de contexto.

### Incidente durante a medição (registrado, não escondido)

A **primeira** execução do script foi para a **borda real** da SEFIN: o script não definia
`NFSE_ADAPTER` e o padrão do projeto é `sefin` (`docker-compose.yml:24`). A resposta foi **403**
— certificado autoassinado não aceito — e **nenhum documento foi emitido**: a recusa acontece na
borda, antes de qualquer processamento fiscal.

Correção aplicada na mesma hora, em duas camadas:

1. `os.environ["NFSE_ADAPTER"] = "mock"` no topo do script, antes de importar `app.*`;
2. guarda dura `recusa_por_adaptador(adaptador)` que aborta com código 2 se o adaptador não for o
   dublê — testada em `tests/test_benchmark_mock.py` (3 casos, incluindo "importar o script força
   mock no ambiente").

Fica registrado porque é o mesmo tipo de erro que a §43 tentou prevenir na `demo_e2e`: **o padrão do
projeto é o adaptador real**, e qualquer script que não o force explicitamente pode falar com a
SEFAZ.

### Limite

Medição em uma máquina Windows, um processo, sem carga concorrente. Não é teste de carga e não
inclui pico de fila. Reprodução: `python -m scripts.benchmark_mock --n 60 --warmup 10`.

---

## 49. Readiness passa a reportar o worker (e o teste de contrato parou de mentir)

**Data:** 2026-11-26. **Fase:** F (health/readiness) + A (contrato).

### Lacuna 1: `/health` não sabia do worker

O worker **já** tinha batimento em Redis (`app/worker/main.py`, `CHAVE_HEARTBEAT` com TTL de 120 s)
e healthcheck próprio para o Docker (`app/worker/healthcheck.py`). O que faltava era a **API**
reportar isso: um operador olhando `/health` via `ok` com o worker morto — e webhooks/retentativas
parados.

Implementado em `app/api/v1/health.py`:

- campo `worker: {ok, ultimo_batimento, detalhe}` na resposta de `/health`;
- lê a **mesma** chave que o worker escreve (uma fonte só, sem constante duplicada);
- Redis inacessível ⇒ `ok: false` com o motivo, nunca sucesso silencioso;
- **política explícita**: `READINESS_EXIGE_WORKER` (padrão `false`). API e worker escalam
  separado; uma API sem worker ainda serve leitura e consulta. A flag decide apenas se o estado do
  worker **reprova** a readiness (503). Reportar ≠ reprovar, e a diferença está documentada em
  `.env.example`.

Ajuste de injeção: `saude()` passou a receber `settings` por `Depends(get_settings)` em vez de
chamar `get_settings()` direto. Sem isso o `dependency_overrides` não tinha efeito — foi o próprio
teste da flag que revelou.

### Lacuna 2: o teste de contrato comparava só `paths`

`tests/test_openapi_sincronizado.py` afirmava que o `openapi.json` versionado estava sincronizado,
mas comparava **apenas** `paths`. Medido: o app tinha o schema `EstadoWorker` e o arquivo não —
divergência real que o teste aprovava. `paths` iguais, `components` diferentes.

- Teste novo `test_schemas_tambem_estao_sincronizados` compara `components` (foi executado
  **vermelho** antes da correção, o que prova que detecta o drift).
- `openapi.json` regenerado (+40 linhas: `EstadoWorker` e o campo `worker`).

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_fase1_health.py` | 10 passed (3 novos: sem batimento, com batimento, flag ligando o 503) |
| `pytest tests/test_openapi_sincronizado.py` | 4 passed (1 novo) |
| `pytest tests/test_configuracao_documentada.py` | 9 passed (`.env.example` cobre a variável nova) |
| `mypy app src` | zero erros |
| gate completo | 8/8 |

### Limite

O batimento prova que o **laço** do worker está vivo, não que cada tipo de job está saudável.
Fila travada com worker vivo ainda aparece como `ok` — diagnóstico por tipo de job exige métrica,
que continua ausente (§50 em diante).

---

## 50. Análise de dependências: consistência agora, CVE decidida com gatilho

**Data:** 2026-11-26. **Fase:** F (CI/CD e dependências). **ADR:** `docs/adr/0002-dependencias.md`.

### O que o CI não cobria

O CI tinha testes, cobertura, lint, tipagem, migrations, contrato e secret scanning. Não tinha
**nada** sobre dependências. O prompt pede "análise de dependências" — e o nome cobre duas coisas
que não são a mesma:

| Verificação | O que responde | Custo |
|---|---|---|
| **Consistência** | o instalado satisfaz o declarado? há conflito de versão? | offline, determinístico |
| **Vulnerabilidade (CVE)** | alguma dependência tem advisory publicado? | exige base de advisories + rede |

### Implementado

`python -m pip check` entrou no gate local (`scripts/check_ci.py`) e no CI. Offline, zero
dependência nova, falha determinística. Pega o erro real de ambiente: extra faltando, pin
incompatível, instalação parcial.

Medido: `No broken requirements found.`

### Decidido, não implementado: `pip-audit`

`pip-audit` é a ferramenta certa para CVE e **não** foi adicionada agora. Motivos registrados no
ADR 0002: introduz dependência nova (regra 11), depende de base externa (resultado muda sem mudança
no commit, reprovando CI por fato alheio) e advisory sem versão corrigida exige `--ignore-vuln`
justificado. **Gatilho para adotar**: quando existir ambiente publicado (homologação/produção) ou
distribuição do pacote a terceiros — antes disso, CI intermitente custa mais do que entrega.

Alternativas avaliadas e não escolhidas: `safety` (comercial no modo completo), `dependabot` e
`renovate` (cuidam de atualizar, não de barrar merge por CVE, e exigem configuração no GitHub, fora
do repositório).

### Risco residual (explícito, não coberto)

**CVE em dependência não é detectada hoje.** Isso está registrado como lacuna conhecida — não como
cobertura. Quem for publicar precisa rodar `pip-audit` antes; o ADR deixa o passo pronto para
entrar.

### Verificação

| Comando | Resultado |
|---|---|
| `python -m pip check` | `No broken requirements found.` |
| `python -m scripts.check_ci` (rápido) | **7/7**, agora com `dependencias` |
| gate completo | 9/9 |

---

## 51. Métricas: `/metrics` em formato Prometheus, sem dependência, com cardinalidade controlada

**Data:** 2026-11-26. **Fase:** F (observabilidade). **Estado anterior:** inexistente.

### O que havia

`GET /health/circuitos` entregava o estado dos circuitos em **JSON** — útil para diagnóstico, inútil
para scraping. Não havia `/metrics`, nem biblioteca de métricas, nem traces. O prompt pede para
distinguir "biblioteca/configuração" de "instrumentação efetiva": aqui não havia nem a biblioteca.

### Por que à mão e não `prometheus-client`

Adicionar dependência exige ADR (regra 11). Para **quatro** métricas, o custo de manter um exporter
não se paga: o formato de exposição é estável e pequeno (`# HELP`, `# TYPE`, `amostra valor`). O
mesmo critério já usado no ADR 0002 (só entra dependência quando o custo de não ter supera o de
manter).

### O que é exposto

| Métrica | Tipo | Rótulos |
|---|---|---|
| `opennotas_http_requisicoes_total` | counter | `metodo`, `rota`, `status` |
| `opennotas_http_duracao_segundos` | histogram | `metodo`, `rota`, `status` |
| `opennotas_worker_batimento` | gauge | — (0/1) |
| `opennotas_circuito_estado` | gauge | `circuito` (0 fechado, 1 meio-aberto, 2 aberto) |

Faixas do histograma: 0,05 / 0,1 / 0,2 / 0,3 / 0,5 / 1 / 2 / 5 s (fixas, expostas como comentário
no payload para quem consulta não precisar abrir o código).

### Cardinalidade: a decisão que mais importa

- **Rótulo de rota é o template** (`/v1/emissoes/{invoice_id}`), nunca o caminho cru. Um label por
  UUID cresce sem limite e derruba o scraper — é o erro clássico e está travado por teste
  (`dois_ids_da_mesma_rota_nao_criam_duas_series`).
- **Nenhum rótulo de tenant.** Além da explosão de cardinalidade, tenant em métrica é dado de
  cliente exposto em endpoint de infraestrutura. Teste afirma que as palavras `tenant`, `cnpj`,
  `cpf`, `api_key` e `chave` não aparecem no payload.
- **`/metrics` não conta a si mesmo** — cada scrape poluiria a série.
- Circuitos: cardinalidade limitada por (operação x autorizador), não por UF nem por município.

### Estado em memória, como o circuito

O registro é por processo (§47 tem o mesmo limite). Com N instâncias, cada uma expõe a própria
série e o Prometheus soma na consulta — comportamento normal e documentado, não bug.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_metrics.py` | **11 passed** |
| `GET /metrics` (cliente ASGI) | 200, `text/plain`, com `opennotas_worker_batimento` e `# TYPE opennotas_circuito_estado gauge` |
| `/metrics` no OpenAPI | **ausente** (`include_in_schema=False`) — é superfície de scraping, não contrato de cliente |

### O que continua ausente

**Traces** (OpenTelemetry). O log JSON já traz `request_id`, e correlação entre API e worker por
trace distribuído não existe. Está registrado como lacuna; adicionar OTel é dependência nova com
peso real (SDK + exporter) e precisa de ADR próprio.

O container da API em execução **não** tem esta mudança (imagem anterior ao commit) — a verificação
foi feita em processo, pelo cliente ASGI dos testes.

---

## 52. Dois entregáveis operacionais: matriz de cobertura e runbook

**Data:** 2026-11-26. **Fase:** F. Ambos estavam na lista do objetivo e não existiam.

### `docs/MATRIZ-COBERTURA.md`

Matriz por documento e operação, com **nível de prova** explícito em cada célula: `✅ teste`
(mock determinístico), `✅ real` (chamada medida ao autorizador), `🔒 bloqueado` (falta credencial),
`❌ ausente`. A legenda diz, no topo, que `✅ teste` **não** é homologação.

Achado ao montar a matriz: o banco de desenvolvimento tem `1` fatura `authorized` e `2` documentos
com `xml_autorizado`, mas **`0` com `protocolo`** — e mistura execuções em mock com chamadas reais.
Portanto **não serve como prova de autorização**; está escrito assim na matriz, em vez de virar
"emissão homologada".

### `docs/OPERACAO.md`

Runbook com o que o operador executa, verificado no código:

| Tema | Fato verificado |
|---|---|
| Backup | o banco contém **documento fiscal e dados de cliente**; o dump precisa do mesmo cuidado |
| Chave-mestra | **não** está no banco; backup sem ela é inútil (PFX selado não abre) |
| Rotação de chave-mestra | **não existe re-selagem** (grep por `rotacionar|rotation|resselar` em `app/core` = zero) → trocar a chave exige reenviar A1 e regravar segredos |
| Rollback | 11 migrations, **todas** com `downgrade()`; downgrade de tabela criada **dropa dado** |
| Rate limit | **fail-open** por desenho (`ratelimit.py`): storage fora ⇒ permite |
| Readiness | **fail-closed**: 503 sem banco/Redis; worker só reprova com `READINESS_EXIGE_WORKER=true` |
| Circuito | **fail-closed**: 503 sem chamar a SEFAZ |
| DLQ replay | `X-Admin-Key`; rota responde **404** quando `ADMIN_HABILITADO=false` |
| Retenção | **não há expurgo automático**; prazo legal é decisão do operador, não do sistema |

O runbook inclui o que **não** existe (HA, PITR, rotação automática, exclusão de tenant por API) —
lacuna declarada, não promessa.

### Descoberta que muda o veredito de "pronto"

A ausência de re-selagem significa que **trocar `MASTER_ENCRYPTION_KEY` invalida todos os
certificados e segredos já gravados**. Isso não é bug de código, é limitação de operação — e agora
está no runbook com o procedimento correto (reenvio), em vez de descoberto em produção.

### Verificação

| Comando | Resultado |
|---|---|
| leitura de `alembic/versions` | 11/11 com `downgrade()` |
| `docker compose exec postgres psql …` | `fiscal_documents`: 2, com `xml_autorizado` 2, com `protocolo` **0** |
| gate completo | 9/9 (docs não alteram código) |

Ambos os documentos estão linkados no README.

---

## 53. Rotação da chave-mestra: re-selagem implementada (a lacuna de §52 fechada)

**Data:** 2026-11-26. **Fase:** A/F. §52 registrou a limitação; esta seção a corrige.

### O problema medido em §52

Trocar `MASTER_ENCRYPTION_KEY` tornava ilegível **todo** material selado — certificado A1, segredo
de webhook, credenciais municipais, tokens do Melhor Envio. Não havia função de re-selagem (grep por
`rotacionar|rotation|resselar` em `app/core` = zero). O runbook só podia recomendar reenvio manual.

### O que foi implementado

`scripts/rotacionar_chave_mestra.py` — núcleo testável (`rotacionar`, `verificar`) + CLI
(`executar`). Para cada linha: abre com a chave antiga usando o **mesmo `aad`** com que foi selada e
re-sela com a nova. O `aad` **não muda** — só a chave.

| Tabela | Campos | `aad` |
|---|---|---|
| `tenant_certificates` | `pfx_selado`, `senha_selada` | `tenant:<id>` |
| `tenants` | `webhook_secret_selado` | `tenant:<id>` |
| `credenciais_municipais` | usuário, senha, token | `tenant:<id>` + `|` + `codigo_ibge` |
| `frete_credenciais` | `access_token_selado`, `refresh_token_selado` | `tenant:<id>` |

### Garantias impostas pelo código

1. **Uma transação.** Metade migrado é pior que nada migrado.
2. **Verifica antes de commitar.** `verificar()` reabre cada envelope com a chave nova; qualquer
   falha faz `rollback` e nada é gravado.
3. **Falha limpa com chave antiga errada.** Se um envelope não abrir, a mensagem diz que a chave
   não é a que selou aquele dado, e o banco fica intacto.
4. **Recusa** chave ausente, malformada (não base64, ≠ 32 bytes) e chave nova igual à antiga.
5. **Chaves por variável de ambiente**, nunca por argumento de linha de comando — argumento aparece
   em `ps` e no histórico do shell.
6. **Não imprime conteúdo nem chave**, só contagens.

### Testes (`tests/test_rotacionar_chave_mestra.py`, 11)

| Teste | O que prova |
|---|---|
| nova abre, antiga não | houve re-selagem de verdade, não reescrita |
| `verificar` conta os campos | 4 campos no cenário (pfx + senha + webhook + frete) |
| chave antiga errada | `ErroDeCriptografia` e **nada gravado** (o selo original continua válido) |
| chave nova igual | recusa |
| `aad` amarra ao tenant | blob não abre com `aad` de outro tenant, antes e depois da rotação |
| CLI sem variáveis | código 2 com mensagem |

Cenário de teste usa chaves fixas (`\x01`…, `\x02`…) e material fictício — nenhum PFX real.

### O que continua manual

O serviço precisa ser reiniciado com a chave nova depois do script. Não há orquestração
automática: rodar com a chave antiga ainda no ambiente deixaria processos antigos lendo com a chave
velha e falhando na decifragem.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_rotacionar_chave_mestra.py` | **11 passed** |
| `mypy app src` | zero erros |
| gate completo | 9/9 |

`docs/OPERACAO.md` §5.2 foi atualizado: o texto que dizia "não existe re-selagem" agora descreve o
procedimento, mantendo o caminho manual como último recurso.

---

## 54. Webhook que esgotava tentativas não ia para a DLQ

**Data:** 2026-11-27. **Fase:** A/E (integração de DLQ ao fluxo real).

### O defeito

`app/webhooks/service.py::_registrar_falha` marcava a entrega como `FALHOU` ao esgotar as 5
tentativas e limpava `proxima_tentativa`. Fim. O registro ficava na tabela, mas **ninguém era
avisado** e **não havia caminho de replay**. O prompt pede "webhooks com ... DLQ, replay seguro" e a
DLQ existia (`app/worker/dlq.py`, com `preparar_replay` recusando replay duplo) — só nunca era
alimentada por webhook: o único produtor era o helper de tarefas do worker.

### A correção

`entregar()` passou a chamar `_guardar_na_dlq()` quando a entrega termina em `FALHOU`:

- `fila="webhook"`, item com `payload = {entrega_id, tipo_evento, url_destino}` — **não** copia o
  payload do cliente: ele já está em `webhook_deliveries`, e duplicar dado fiscal é pior que
  referenciá-lo;
- `erro` recebe o último motivo, `tentativas` o número executado;
- **idempotente**: se já existe item `PENDENTE` para a mesma entrega, não cria outro — reprocessar
  `entregar` à mão não deve encher a fila morta de duplicatas;
- log de erro `webhook_esgotou_tentativas` (sem payload, sem segredo), para alerta.

O item é reparável pelo caminho já existente e autenticado: `POST /v1/admin/dlq/{id}/replay`
(`X-Admin-Key`, ADR 0001), com a mesma recusa de replay duplo.

### O teste que quase mentiu

A primeira versão do teste falhou por um motivo que **não** era o código: o tenant do cenário não
tinha segredo de webhook configurado, então `entregar` retornava **antes** de tentar entregar —
a entrega já nascia `FALHOU` por falta de segredo. O teste "passava" na asserção de status e
reprovava na de DLQ. Corrigido configurando `POST /v1/me/webhook` no início do cenário. Fica
registrado porque é o tipo de armadilha que produz teste verde sem prova.

### Testes (`tests/test_webhooks.py`, +3)

| Teste | O que prova |
|---|---|
| falha repetida cria **um** item | esgotou → DLQ com `fila="webhook"`, `entrega_id` e `tentativas=5` |
| reprocessar não duplica | chamar `entregar` de novo numa entrega esgotada não cria segundo item |
| sucesso não cria item | entrega 2xx não polui a fila morta |

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_webhooks.py` | **24 passed** |
| gate completo | 9/9 |
| `mypy app src` | zero erros |

---

## 55. Concorrência real na idempotência: 500 em vez de 200, e a trava que resolve

**Data:** 2026-11-27. **Fase:** A (isolamento/idempotência). Correção de defeito **crítico**.

### Como apareceu

`tests/test_idempotencia_concorrencia.py` dizia, desde a primeira versão, que o caso
**simultâneo** não estava provado: o teste levantava `MissingGreenlet` e a hipótese registrada era
"problema do harness de teste no `pool_pre_ping`". Hipótese nunca verificada — e estava errada.

Protocolo seguido: reproduzir antes de concluir.

| Experimento | Resultado |
|---|---|
| duas conexões concorrentes com `pool_pre_ping=True` (script isolado) | **ok** — pool não é a causa |
| duas sessões concorrentes com o `sessionmaker` do app | **ok** — factory não é a causa |
| duas requisições HTTP concorrentes em `/health` | **ok** — middleware não é a causa |
| duas requisições concorrentes em `/v1/emissoes` com a mesma chave | **`MissingGreenlet`** |

### Causa raiz

Não era o pool, nem o teste: era a **corrida de idempotência**.

1. As duas requisições passam pela checagem `_buscar_por_idempotencia` — nenhuma vê a outra, porque
   a primeira ainda não commitou.
2. As duas inserem. A segunda viola `uq_invoices_tenant_idempotency_key`.
3. O código **tem** tratamento de `IntegrityError`, mas o erro chega embrulhado pelo driver asyncpg;
   a recuperação (`rollback` + nova consulta) é executada num ponto em que o driver já perdeu o
   contexto de greenlet, e o que o cliente recebe é `MissingGreenlet` → **500**.

O caminho que deveria devolver **200 com a fatura existente** devolvia erro. Cliente em rede
instável repete; repetição é exatamente o cenário.

### Correção

`pg_advisory_xact_lock` derivado de `sha256(tenant_id:chave)` **antes** da checagem de existência:

- a segunda requisição **espera** a primeira terminar a transação e então encontra a fatura →
  200, uma fatura só;
- a trava é de transação (liberada no commit/rollback) e o escopo é a **chave**, não a tabela:
  tenants diferentes e chaves diferentes seguem em paralelo;
- colisão de hash apenas serializa dois pedidos distintos — não corrompe;
- o tratamento de `IntegrityError` **permanece** como rede de segurança.

### Teste

`TestSimultaneidade` com `asyncio.gather` de duas emissões usando a mesma `Idempotency-Key`:
afirma que **nenhuma** resposta é exceção, que os códigos são exatamente `[200, 201]` e que existe
**uma** fatura no banco. Antes da correção: `[201, MissingGreenlet]`.

O docstring do arquivo foi reescrito: o caso agora está provado e o histórico está registrado — em
vez de "não provado, talvez seja o harness".

### Limite honesto

- A trava é **PostgreSQL**. O projeto é Postgres-only (asyncpg), então não há regressão hoje; num
  banco diferente esta proteção não existiria.
- A serialização é por chave: dois pedidos com a mesma chave, um espera o outro. Com a emissão
  síncrona chamando a SEFAZ dentro da transação, a espera pode chegar à latência do autorizador
  (segundos, não milissegundos).
- O caminho `IntegrityError` continua sem teste que o force a acontecer (a trava o torna
  inalcançável no fluxo normal). Ele existe como defesa, não como caminho exercitado.

---

## 56. Decisão registrada sobre traces (ADR 0003) e consolidação do estado

**Data:** 2026-11-27. **Fase:** F. **ADR:** `docs/adr/0003-traces.md`.

### O que faltava

Traces distribuídos nunca existiram, e isso estava escrito como lacuna em §51 — mas **sem decisão
registrada**. Lacuna sem decisão vira esquecimento: quem ler depois não sabe se foi avaliado e
descartado, ou se ninguém olhou.

### Decisão

Não instalar OpenTelemetry neste ciclo. Motivos no ADR: cinco pacotes com versionamento próprio,
necessidade de coletor (decisão de infraestrutura), e — o principal — **instalar SDK e chamar isso
de "temos OTel" seria exatamente o falso positivo que o objetivo manda evitar**. Sem backend
consumindo span, o ganho é zero e o custo é imediato.

O que **existe** e resolve o caso atual: `request_id` no header e no log JSON, latência por rota em
`/metrics` (seção 51). O que falta é a costura API→worker, não o número.

**Gatilho para adotar** (registrado): incidente em ambiente publicado em que `request_id` não
bastou; mais de um worker/instância; ou exigência contratual de SLA com trace. O ADR fixa também o
mínimo aceitável quando entrar — spans em `TransporteHTTP`, no job do worker e na entrega de webhook,
com **teste que prove span exportado**, não instrumentação registrada.

Alternativa intermediária registrada e não escolhida: propagar `request_id` no payload do job do
ARQ (barato, sem dependência, resolve metade do problema). Candidata ao próximo ciclo.

### Estado consolidado após esta rodada

| Medida | Valor |
|---|---|
| Commits na branch (PR #1) | 15 |
| Testes | 1457 |
| Cobertura | **87,72%** (fail_under = 80) - medido nesta rodada, nao herdado do baseline |
| mypy | 0 erros / 174 arquivos |
| Gate | 9/9 |
| Segredos | nenhum em 490 arquivos |
| ADRs | 3 (admin auth, dependências, traces) |

Defeitos corrigidos nesta série: emissão real em homologação por `Settings` no lugar de `ambiente`
(3 módulos); `enviar_evento` sem `cnpj`; rota de status com `cert_pem` inexistente (500 com
certificado); webhook esgotado sem DLQ; **corrida de idempotência devolvendo 500**; teste de contrato
comparando só `paths`; `mypy` fora do CI; re-selagem de chave-mestra inexistente.

### Limite de leitura da cobertura

Medido nesta rodada: `app/api/v1/emissoes.py` aparece com 46% e `app/api/v1/transportes_status.py`
com 61%, **apesar de testes que exercitam os caminhos**. O motivo está no próprio ROADMAP: o corpo de
handlers assíncronos aparece como não coberto. Ou seja: aqui cobertura **subestima** o testado, e
perseguir o número levaria a escrever teste redundante em vez de corrigir defeito. Registrado para
que ninguém "conserte" a cobertura quebrando os testes.

---

## 57. Mesma `Idempotency-Key` com corpo diferente devolvia a nota antiga em silêncio

**Data:** 2026-11-27. **Fase:** A (idempotência). **Mudança de comportamento — leia o aviso no fim.**

### O defeito

Reusar a chave com **outro corpo** devolvia `200` com a fatura anterior e `ja_existia: true`.
Nenhum aviso, nenhum erro. O cliente que pedia R$ 100 recebia de volta a nota de R$ 50 e concluía que
havia emitido o que pediu.

Em documento fiscal isso não é bug cosmético: é **divergência entre o que foi pedido e o que foi
escriturado**, descoberta na conciliação — ou nunca.

Não havia teste nem tratamento: `grep` por `divergente` nos testes não retornava nada sobre emissão,
e o único `409` do arquivo era o de conflito raro de constraint.

### A correção

`_recusar_payload_divergente()` compara o corpo recebido com o `payload` que a própria fatura guardou
na criação (o mesmo `model_dump(mode="json")` que já era persistido). Sem coluna nova, sem migração.

| Situação | Antes | Agora |
|---|---|---|
| chave + **mesmo** corpo | 200 com `ja_existia` | **200 com `ja_existia`** (inalterado) |
| chave + corpo **diferente** | 200 com a nota antiga | **409** explicando que a chave já foi usada com outro corpo |
| chave nova | 201 | 201 (inalterado) |

A mensagem orienta o caminho certo sem ecoar dado do cliente: "reenvio idêntico devolve a emissão
original; para um documento novo, use outra chave".

### Aviso de compatibilidade

Isto **muda o comportamento de `/v1`** num caso específico. A decisão foi não versionar porque o
comportamento anterior não era contrato — era resultado errado. Quem hoje reusa chave com corpo
diferente está, na melhor hipótese, com bug de cliente; na pior, emitindo documento trocado.
Para clientes que só repetem o mesmo pedido (o caso normal), nada muda.

### Testes (`tests/test_idempotencia_concorrencia.py`, +2)

| Teste | O que prova |
|---|---|
| corpo diferente vira 409 | 201 → 409, e a fatura original segue única |
| corpo idêntico continua 200 | `ja_existia: true` e mesmo `invoice_id` |

### Limites

- A comparação é de **corpo normalizado**, não de intenção: dois corpos equivalentes escritos de
  formas diferentes (campo opcional explícito como `null` vs ausente) precisam gerar o mesmo
  `model_dump`, e é isso que o teste protege. Campo novo com default diferente quebraria a igualdade
  e devolveria 409 num reenvio legítimo — risco aceito e documentado.
- Não há janela de expiração da chave: a fatura antiga nunca "expira", então a chave vale para sempre
  para aquele tenant. É coerente com retenção fiscal, mas significa que reusar chave antiga nunca
  emitirá documento novo.

---

## 58. Rate limit existia e nunca era instalado

**Data:** 2026-11-27. **Fase:** A (integração de componente ao fluxo). Item do objetivo:
"identificar implementações isoladas que ainda não estão integradas ao fluxo de produção".

### O defeito

`app/core/middleware_ratelimit.py` estava escrito, testado (12 testes) e **nunca registrado** em
`criar_app()`. Ligar `RATE_LIMIT_HABILITADO=true` não fazia absolutamente nada: a flag acendia uma
proteção que ninguém executava.

Os testes antigos não podiam pegar isso porque construíam uma `FastAPI()` própria e adicionavam o
middleware à mão — provavam que o middleware **funciona**, nunca que ele **está no fluxo**. É a
diferença entre testar a peça e testar a instalação.

Efeito prático: um operador lê `.env.example`, liga a flag, e fica com a API sem cota — acreditando
que tem.

### A correção

1. `MiddlewareRateLimit` é registrado **sempre** em `criar_app()`; o próprio middleware não faz nada
   quando a flag está desligada (o padrão). Registrar condicionalmente criaria dois caminhos de
   construção de app e um deles nunca seria exercitado pelos testes.
2. Ordem: `MiddlewareRequisicao` fica **por fora** do rate limit, para que uma resposta 429 ainda
   ganhe `X-Request-ID`, entre no log e conte em `/metrics`. (Medido: `CORSMiddleware` é o mais
   externo de todos; a asserção do teste fixa a ordem relativa entre os dois que importam.)
3. **Storage trocado para Redis** (`ArmazenamentoRedis` em `app/core/ratelimit.py`). O middleware
   usava `ArmazenamentoMemoria`, então com N instâncias a cota real seria `N x limite` — o número
   documentado mentiria. Redis usa `INCR` (atômico) e `EXPIRE` só na primeira escrita, senão a janela
   viraria deslizante e a cota nunca fecharia. Falha do Redis continua **fail-open**, como o
   `Limitador` já garantia.

### Testes (`tests/test_ratelimit_instalado.py`, 5)

| Teste | O que prova |
|---|---|
| middleware está no app real | `criar_app()` registra `MiddlewareRateLimit` |
| requisição por fora do limite | ordem relativa correta entre os dois middlewares |
| terceira requisição vira 429 | com `rate_limit_por_minuto=2`: 200, 200, **429** com `Retry-After`, `application/problem+json` e `X-Request-ID` |
| `/health/live` nunca é barrado | rota isenta mesmo acima da cota |
| desligado não barra | padrão preservado |

### Achados de teste honestos

- A primeira versão usava `X-API-Key` fixa e **passou a falhar ao rodar de novo**: o contador vive no
  Redis e não expira entre execuções, então a primeira requisição do teste seguinte já vinha 429. Keys
  agora são únicas por teste. Isso também documenta um comportamento real: a cota é por prefixo de
  chave e a janela é de 60 s.
- A primeira asserção de ordem estava invertida (supus que o último da lista era o mais externo;
  Starlette embrulha em ordem reversa e o **primeiro** é o mais externo). Corrigido com o comentário
  explicando a semântica, para o próximo não repetir o erro.

### Limites

- Sem Redis, o contador cai para memória por processo — a cota vira `N x limite`. O fail-open está
  documentado em `docs/OPERACAO.md`; a consequência de escala está registrada aqui.
- A chave de cota é o **prefixo** da API key (`api_key[:8]`), não o hash: prefixo é público por
  desenho. Duas chaves com o mesmo prefixo dividiriam cota — improvável, mas é o comportamento.
- O `retry_after_s` é o da janela fixa, não um cálculo exato do instante de liberação.

---

## 59. Inventário de implementações isoladas (código testado que não está no fluxo)

**Data:** 2026-11-27. **Fase:** A (fecho do item "identificar implementações isoladas").

O objetivo pede explicitamente para identificar o que existe e **não** está integrado. §54 e §58
acharam dois casos por acidente. Esta seção faz o levantamento sistemático.

### Método

Para cada módulo em `app/`, contei referências dentro de `app/` (excluindo o próprio arquivo) e
verifiquei quem importa de fato. "Só teste" significa: nenhum caminho de execução da API ou do worker
passa por ali.

| Módulo | Quem importa em produção | Estado |
|---|---|---|
| `app/cte/consulta_situacao.py` | **ninguém** — só `tests/test_cte_consulta_situacao.py` | **isolado** |
| `app/cte/transmissao.py` | **ninguém** — só `tests/test_transporte_transmissao.py` | **isolado** |
| `app/mdfe/transmissao.py` | **ninguém** — só o mesmo teste | **isolado** |
| `app/nfse/drivers_factory.py` | **ninguém** — só testes | **isolado** |
| `app/nfse/drivers.py` (roteamento) | só `drivers_abrasf.py` e `drivers_factory.py` | **isolado** (cadeia inteira) |
| `app/nfse/drivers_abrasf.py` (motor ABRASF) | só `drivers_factory.py` | **isolado** |
| `app/nfse/assinatura_rps.py` | **ninguém** — só `tests/test_nfse_assinatura_rps.py` | **isolado** |
| `app/worker/tarefas.py` (retry→DLQ) | **ninguém** — só `tests/test_worker_tarefas.py` | **isolado** |
| `app/core/middleware_ratelimit.py` | `app/main.py` | **integrado em §58** |

### O que isso significa, sem eufemismo

1. **NFS-e multi-prefeitura não está no fluxo.** Existe contrato de driver, roteamento, motor ABRASF e
   stubs que recusam com motivo — tudo testado — mas `app/nfse/servico.py` **não** escolhe driver:
   sempre usa o padrão nacional. Com um município ABRASF, a emissão hoje tentaria o padrão nacional em
   vez de chamar o driver municipal. A camada está pronta para ser ligada; **não está ligada**.
2. **Consulta de situação do CT-e não é uma capacidade da API.** A chamada real registrada em §31
   (cStat `236`) foi feita por script, não por rota. O módulo é sólido e testado; não existe endpoint.
3. **Transmissão de CT-e/MDF-e não tem rota.** Os módulos montam e enviam o envelope, mas nenhum
   endpoint os chama — coerente com "não transmitir sem credenciamento", porém significa que mesmo
   com credencial não há caminho pela API.
4. **O helper de retry→DLQ do worker não é usado pelo worker.** `entregar_webhooks` e
   `processar_lote` fazem o próprio tratamento; o webhook passou a alimentar a DLQ só porque §54
   escreveu a chamada à mão. O helper genérico segue sem uso.

### Correções de documentação (o ponto mais importante)

`docs/MATRIZ-COBERTURA.md` dava a entender que "envelope e transporte testados" equivale a
capacidade pronta. Foi corrigido: as linhas de transmissão de CT-e/MDF-e e de consulta de situação
agora dizem **"módulo existe, testado, sem rota"**, e não "falta credenciamento" — que é bloqueio
diferente e mais honesto.

`docs/ROADMAP.md` ganhou a lista de pendências de integração com o que falta, em ordem.

### O que **não** foi feito, e por quê

Ligar a fábrica de drivers ao `servico.py` **muda comportamento**: hoje um município com stub ABRASF
emite pelo padrão nacional; depois da ligação passaria a **recusar**. Fazer isso sem ambiente de
homologação para validar seria trocar um erro silencioso por uma indisponibilidade — e o dono do
projeto autorizou apenas leitura. Fica registrado como próximo passo condicionado a homologação.

Criar rotas de transmissão de CT-e/MDF-e foi descartado neste ciclo: exigiria schema de entrada
completo por documento e criaria uma superfície que emite documento fiscal sem homologação possível.

### Verificação

| Comando | Resultado |
|---|---|
| varredura de importações em `app/` | 9 módulos com ≤1 referência interna; 8 confirmados isolados |
| gate completo | 9/9 |

---

## 60. Sem `statement_timeout`: uma consulta travada podia derrubar a API

**Data:** 2026-11-27. **Fase:** F (prontidão de produção). Achado por leitura do engine, não por teste
falhando.

### O risco

`criar_engine()` criava o pool com `pool_pre_ping` e nada mais. Nenhum `statement_timeout`, nenhum
`idle_in_transaction_session_timeout`, nenhum `pool_recycle`.

Consequência concreta: uma consulta patológica — apuração sobre tabela inteira, lock perdido, plano
ruim — segura a conexão **para sempre**. Com `pool_size=10`, dez consultas assim esgotam o pool e a
API deixa de atender emissão, consulta e health. Um timeout de cliente não resolve: ele desiste de
esperar enquanto o Postgres segue executando e segurando a conexão.

### A correção

`app/db/session.py` passa `server_settings` do asyncpg (valem **no servidor**, para toda conexão do
pool) e `pool_recycle`:

| Configuração | Padrão | O que impede |
|---|---|---|
| `DB_STATEMENT_TIMEOUT_MS` | 60 000 | consulta travada ocupando conexão indefinidamente |
| `DB_IDLE_TX_TIMEOUT_MS` | 120 000 | transação aberta e ociosa prendendo conexão e lock |
| `DB_POOL_RECYCLE_S` | 1 800 | conexão velha atrás de firewall/PgBouncer, já morta |

Documentado em `.env.example`, com a orientação de que lote e apuração longa devem rodar no worker
com valor próprio — não aumentar este teto para toda a API.

### Testes (`tests/test_db_timeouts.py`, 4)

| Teste | O que prova |
|---|---|
| padrões são folgados mas finitos | 1 s ≤ timeout ≤ 10 min, idle ≥ statement, recycle > 0 |
| `SHOW statement_timeout` após `criar_engine(9_000)` | o valor configurado **chega ao servidor** |
| `SHOW` com `connect_args` explícito | sanidade do mecanismo |
| `pg_sleep(1)` com teto de 200 ms | a consulta é **cancelada**, não esperada |

O segundo teste é o que importa: pergunta ao Postgres. A primeira versão inspecionava
`pool._creator.__closure__` — passava sem provar nada; foi substituída.

### Limite honesto

- O teto é global para a API. Uma operação legítima e lenta (relatório de apuração de vários meses)
  passa a falhar em vez de demorar. O caminho correto é o worker, com `statement_timeout` próprio —
  que **ainda não existe** lá: o worker usa o mesmo `criar_engine`. Registrado como pendência.
- `pool_recycle` de 30 min pode cortar conexão no meio de uma transação longa legítima; com teto de
  60 s por consulta, é improvável, mas é uma interação entre os dois números que quem mudar precisa
  conferir.

---

## 61. O painel contradizia a auditoria — e a correção é no gerador

**Data:** 2026-11-27. **Fase:** documentação (sincronização exigida pelo objetivo).

### O problema

`docs/PAINEL.md` é vista derivada: o bloco de **métricas** é medido, mas as tabelas narrativas eram
texto fixo em `scripts/gerar_painel.py` e nunca acompanharam o projeto. Estado encontrado:

| Afirmação do painel | Realidade medida |
|---|---|
| CT-e e MDF-e "Geração ❌ / Assinatura ❌" | gerador, XSD e assinatura existem e são testados (§44.5) |
| CT-e/MDF-e "Consulta ❌" | consulta de status **real** medida, `cStat 107` (§31) |
| "Transporte SOAP DF-e ❌ AUSENTE" | transporte existe, testado, com status real; **autorização** é que falta |
| "`pip-audit` não instalado (exige ADR)" | ADR 0002 decidiu, com gatilho — não é pendência esquecida |
| "Admin auth — decisão do proprietário" | ADR 0001 implementado e testado |
| "F9.6 DANFE do nfeProc ⬜" | DANFE existe e é testado |

Um painel que diz "❌ geração" para um documento cuja geração é testada é pior que painel nenhum:
quem lê decide com informação errada.

### A correção

Editado **o gerador**, não o arquivo gerado (regra do próprio objetivo). As tabelas agora apontam
para `docs/MATRIZ-COBERTURA.md` e usam a distinção que passou a existir em §59:

- "transmissão" de CT-e/MDF-e é `🔒 módulo, sem rota` — não "❌";
- consulta é `✅ real (status)` para NF-e/CT-e/MDF-e;
- bloqueio `pip-audit` e admin auth aparecem como **resolvidos**, com o ADR que os decidiu;
- acrescentado CSC por UF e inutilização de CT-e/MDF-e (serviço inexistente no leiaute) à lista de
  bloqueios externos.

`docs/PAINEL.md` foi regenerado por comando — nenhuma edição manual.

### Incidente desta rodada (registrado, não escondido)

Rodei `pytest --cov` em segundo plano **e** `gerar_painel.py` ao mesmo tempo. O gerador toca o banco
para contar tabelas/migrations; a suíte usa o **mesmo** banco de teste e trunca tabelas entre testes.
Resultado: um teste falhou com `NoResultFound` e a cobertura saiu com 86,77%.

**Não era regressão.** A suíte rodada isolada terminou com `exit=0`, e o gate completo voltou 9/9.
É exatamente o erro que a auditoria já documentava ("nunca dois processos de teste no mesmo banco") e
que eu repeti. A cobertura válida continua sendo a medida em execução isolada; a de 86,77% está
contaminada e **não deve ser citada**.

### Verificação

| Comando | Resultado |
|---|---|
| `python -m scripts.gerar_painel` | painel regenerado: rotas 58, tabelas 15, migrations 11, testes 1468 |
| `pytest tests` (isolado) | `exit=0` — verde |
| `scripts.check_ci --tudo` (isolado) | **9/9** |

---

## 62. O worker herdava o teto de 60 s — risco criado por §60, fechado aqui

**Data:** 2026-11-27. **Fase:** F. Corrige um risco que **eu** introduzi na rodada anterior.

### O problema (autoinfligido)

§60 aplicou `statement_timeout` de 60 s no `criar_engine()`. O worker usa o **mesmo** engine. Um lote
de emissões dura minutos: com o teto da API, o Postgres cancelaria a consulta **no meio do lote**,
deixando documentos processados pela metade — pior que falhar antes de começar.

Estava registrado como "limite declarado" em §60. Limite declarado não é correção: se eu podia
fechar, deveria fechar na mesma rodada.

### A correção

| Peça | O que faz |
|---|---|
| `DB_STATEMENT_TIMEOUT_WORKER_MS` (600 000) | teto próprio do worker, 10 min |
| `criar_engine(..., statement_timeout_ms=...)` | parâmetro explícito; o padrão continua sendo o da API |
| `obter_sessionmaker_worker()` | engine e pool **separados**, do processo do worker |
| `dispose_engine()` / `reset_engine()` | descartam/limpam os **dois** engines |

`entregar_webhooks` e `processar_lote` passaram a usar a fábrica do worker. Nenhuma rota da API mudou.

### Testes (`tests/test_db_timeouts.py`, +3)

| Teste | O que prova |
|---|---|
| configuração | teto do worker > teto da API |
| `SHOW statement_timeout` na fábrica do worker | **600 000 ms** no servidor |
| `SHOW statement_timeout` na fábrica da API | **60 000 ms** no servidor |

### Achado de teste

A primeira versão comparava string: esperava `"10min"` e recebeu… `"1min"` no caso da API — o
Postgres escolhe a unidade mais legível (60 000 ms → `1min`, 600 000 ms → `10min`). Troquei por
`_em_ms()`, que normaliza `min`/`s`/`ms` para milissegundos. Comparar formatação de `SHOW` é frágil por
construção.

### Limite residual

- Dois pools agora (API e worker). Em processo único de desenvolvimento, isso é 2 × `pool_size`
  conexões se o worker rodar no mesmo processo — no desenho real são processos distintos.
- O teto de 10 min é escolha, não medição: não há lote real medido que justifique outro número.
- Se algum dia o worker rodar no mesmo processo da API (`arq` embutido), a separação continua válida
  porque são engines distintos — mas a soma de conexões precisa ser conferida no cálculo do Postgres.

---

## 63. Coleção Postman derivada do contrato, com guarda anti-drift

**Data:** 2026-11-27. **Fase:** E (experiência de integração). Item do objetivo:
"OpenAPI preciso, exemplos request/response e coleção Postman".

### O que havia

Medido em `openapi.json`: **67 operações**, 17 com `requestBody`, **0 exemplos**, e **nenhuma coleção
Postman**. Quem integrava precisava montar as chamadas lendo o contrato na mão.

### O que foi feito

`scripts/gerar_postman.py` gera `docs/postman_collection.json` a partir do `openapi.json` versionado:

| Decisão | Motivo |
|---|---|
| **Gerar** em vez de escrever à mão | coleção manual divergiu do contrato em todo projeto que cresceu |
| `--check` compara e **reprova** divergência | a coleção não pode envelhecer em silêncio |
| Corpo é **esqueleto** derivado do schema | inventar CNPJ/valor "de exemplo" produz coleção que parece pronta e falha no primeiro uso — e em gateway fiscal vira dado errado na mão de quem integra |
| `X-API-Key: {{api_key}}` | a chave deriva o tenant; coleção não deve sugerir `tenant_id` no corpo |
| Pastas por `tag` | reflete a organização do contrato, não uma taxonomia inventada |

Resultado medido: **18 pastas**, **67 requisições**, **14 com corpo**.

### Testes (`tests/test_gerar_postman.py`, 8)

| Teste | O que prova |
|---|---|
| `--check` retorna 0 | coleção em dia com o contrato (falha no CI se divergir) |
| toda requisição existe no contrato | nenhuma rota inventada |
| toda rota está na coleção | nenhuma rota esquecida |
| corpo é JSON válido e **sem dado inventado** | proíbe `00000000000`, `11.222.333`, CNPJ fictício, `R$ ` |
| cabeçalho usa `{{api_key}}` | não sugere chave literal |
| esqueleto: string→"", integer→0, boolean→false | derivação determinística |
| respeita `example` do schema quando existe | não sobrescreve exemplo real |
| objeto aninhado é derivado | cobre corpo com estrutura |

### Limite honesto

- **Exemplos de response continuam ausentes.** O objetivo pede "exemplos request/response"; o que
  existe agora é corpo de request derivado e coleção executável. Exemplo de *resposta* exige decidir
  qual resposta é canônica por rota (201 vs 200 vs problema+json) e fixá-la no schema — é contrato, e
  o certo é fazer junto com versionamento, não como enfeite.
- Corpo esqueleto **não passa** na validação de negócio (valor `""` não é `Decimal` válido). É ponto
  de partida, não requisição pronta; está escrito na descrição da coleção.
- A coleção não tem testes de script (Postman test assertions). Isso exigiria runner Postman/Newman,
  que é dependência nova — regra 11, com ADR que não fiz.

---

## 64. Demo ponta a ponta executada em container — e um teste que estava desatualizado

**Data:** 2026-11-27. **Fase:** verificação (critério F9 "fluxo mockado demonstrável"). Antes disto, a
demo estava registrada como "não reexecutada" desde a Fase 7.

### Como foi feito

1. `docker compose build api worker` — os containers rodavam **imagem anterior** aos 23 commits;
2. `docker compose up -d` com `NFSE_ADAPTER=mock`;
3. `python -m scripts.demo_e2e` contra a API real em container, PostgreSQL e Redis reais.

### Achado operacional (armadilha real)

O `docker compose up` falhou com `service "migrate" didn't complete successfully: exit 255` e
`alembic: Can't locate revision identified by '0011'`.

Causa: o compose tem **três** imagens a partir do mesmo código — `api`, `worker` **e `migrate`**.
Rebuildar só `api` e `worker` deixou a `migrate` antiga, **sem `alembic/versions`**, e o erro aponta
para "revisão não encontrada" em vez de "imagem velha". Diagnosticado comparando
`alembic current` dentro do container (`0011 (head)`, correto) com o serviço `migrate` falhando.
Correção: `docker compose build migrate`. Registrado em `docs/OPERACAO.md`.

### Prova de que o código dos 23 commits está no ar

| Verificação | Resultado |
|---|---|
| `GET /health` | traz `nfse_adapter` **e** `worker: {ok: true, ultimo_batimento: ...}` (§49) |
| `GET /metrics` | série com `metodo`, `rota` (**template**, sem UUID) e `status` (§51) |
| `GET /v1/health/circuitos` | `sefaz:NACIONAL:autorizacao` = `fechado` (0) |
| rate limit | registrado e no-op com a flag desligada (§58) |
| tempos de banco | `statement_timeout` aplicado; worker com teto próprio (§60/§62) |

### Achado na demo: reenvio "idêntico" que não era idêntico

O passo 6 reenviava a emissão com a mesma `Idempotency-Key` mas com corpo **parcial** (sem
`competencia`, `tomador_nome`, `tomador_documento`) e esperava **200**. Depois de §57 isso virou
**409** — corretamente.

Ou seja: a demo tinha a expectativa antiga (e errada), que só passava porque o sistema devolvia a nota
anterior em silêncio. Corrigido no script:

- reenvio **idêntico** → `200`, `ja_existia: true` e **mesma fatura**;
- corpo **divergente** com a mesma chave → **`409`** explícito.

Resultado final: **20 de 20 verificações passaram**.

### Fluxo comprovado ponta a ponta (mock, em container)

tenant → upload de A1 (CNPJ extraído `11222333000181`) → webhook com segredo → emissão NFS-e (201,
chave de 50 dígitos) → reenvio idêntico (200) → divergente (409) → DANFSe 4 012 bytes PDF válido →
webhook assinado recebido com HMAC **válida** → apuração da competência (ISS 7,50) → guia DNA com
vencimento.

### Limites

- É **mock**: nada foi enviado a autorizador. O adaptador real continua sendo o padrão do compose e
  foi restaurado ao final (`nfse_adapter: sefin`).
- A demo usa certificado **autoassinado** gerado no próprio script; não prova aceitação pela SEFAZ.
- Nenhum registro de documento autorizado foi produzido: o mock devolve um documento derivado da DPS.

---

## 65. Consolidação final da série (2026-11-27)

Seção de fechamento: o que foi corrigido, o que está provado e **o que continua aberto**. Números
medidos nesta data, não herdados.

### Medições finais (executadas isoladamente)

| Medida | Valor | Como |
|---|---|---|
| Suíte | **1479 testes, 0 falhas** | `pytest tests` (exit 0) |
| Cobertura | **87,74%** | `pytest --cov=app` (mínimo 80) |
| Gate | **9/9** | `python -m scripts.check_ci --tudo` |
| mypy | **0 erros / 174 arquivos** | `mypy app src` |
| Segredos | **nenhum em 496 arquivos** | `scripts/verificar_segredos` |
| Demo ponta a ponta (container, mock) | **20/20** | `scripts/demo_e2e` |
| p95 mock | **285,5 ms** | `scripts/benchmark_mock` (n=60) |
| PR | **#24 commits**, `MERGEABLE`, CI `success` | `gh pr view 1` |

### Defeitos corrigidos nesta série (13)

| # | Defeito | Efeito real | Seção |
|---|---|---|---|
| 1 | `Settings` no lugar de `AmbienteFiscal` (3 módulos) | emissão sempre em homologação, sem mTLS | §44 |
| 2 | `cert_pem` inexistente na rota de status | **500** sempre que havia certificado | §44 |
| 3 | `enviar_evento` sem `cnpj` | **TypeError** em todo evento de CT-e | §44 |
| 4 | Circuito só na emissão | cancelamento/evento queimavam timeout | §47 |
| 5 | `reset_ephemeral_key` inútil | função que mentia | §44 |
| 6 | Teste de contrato só em `paths` | `openapi.json` desatualizado passava | §49 |
| 7 | `/health` sem o worker | painel verde com worker morto | §49 |
| 8 | Sem re-selagem de chave-mestra | trocar chave invalidava tudo | §53 |
| 9 | Webhook sem DLQ ao esgotar | entrega perdida sem aviso | §54 |
| 10 | **Corrida de idempotência** | **500** em reenvio simultâneo | §55 |
| 11 | Payload divergente devolvia nota antiga | nota trocada em silêncio | §57 |
| 12 | Rate limit nunca instalado | flag ligava proteção inexistente | §58 |
| 13 | Banco sem `statement_timeout` | uma query travada derrubava a API | §60 |

### O que está provado por ambiente

| Nível | Evidência |
|---|---|
| **Código + teste** | 1479 testes, cobertura 87,74%, gate 9/9 |
| **Mock em container** | demo 20/20 com PostgreSQL e Redis reais |
| **Homologação real** | consultas de status (`cStat 107`) e uma consulta de situação (`236`), registradas em §31 |
| **Produção** | **nada** |

### O que continua aberto (declarado, não escondido)

1. **NFS-e multi-prefeitura não ligado** (§59) — motor existe, `servico.py` sempre usa o nacional.
2. **Sem rotas** de transmissão CT-e/MDF-e e de consulta de situação (§59).
3. **Worker não usa** o helper retry→DLQ genérico (§59).
4. **Sem traces** (ADR 0003) e **sem CVE scan** (ADR 0002) — decisões com gatilho.
5. **Exemplos de response** ausentes no OpenAPI (§63).
6. **p95 sem folga**: p99 > 300 ms; custo dominante é assinatura RSA.
7. **Circuito e métricas** em memória por processo.
8. **Bloqueios externos**: credenciamento SEFAZ-GO, CSC por UF, inutilização inexistente em 4.00,
   OAuth Melhor Envio.

### Veredito

**Pronto no código para a próxima validação.** Não homologado, não em produção. O que separa este
estado de produção não é código pendente do meu lado — é credenciamento, certificado real com
aceitação do autorizador e ambiente de homologação liberado.

---

## 66. Correção de precisão: o motor ABRASF não tem transporte real

**Data:** 2026-11-27. **Fase:** B (documentação de precisão).

### O que eu vinha escrevendo

A afirmação estava em §59 e no texto do gerador do painel (não em `MATRIZ-COBERTURA.md`, que não fala
de ABRASF — corrigir aqui é parte da precisão que este trabalho exige). Dizia: "contrato, roteamento e
motor ABRASF existem e são **testados**". A frase está certa e sugere algo falso.
### O que o código mostra

`app/nfse/drivers_abrasf.py` define `TransporteProvedor` como **`Protocol`** — o contrato do
transporte SOAP municipal. Procurando implementações em `app/` e `tests/`:

- **nenhuma implementação em `app/`**;
- nos testes, existe `TransporteFalso` (`tests/test_nfse_drivers_abrasf.py:13`).

Ou seja: o fluxo ABRASF (montagem do RPS, lote, assinatura, envelope) é testado **com transporte
falso**. Não existe cliente SOAP para webservice municipal, e nenhum provedor tem URL e leiaute com
fonte oficial verificável no repositório — que é justamente a condição que o próprio repositório
impõe (`criar_driver` recusa município sem `fonte_url`).

### Consequência para o veredito

Ligar a fábrica de drivers ao `servico.py` hoje **não habilitaria nenhum município**: sem transporte
real, a primeira chamada levantaria antes de sair para a rede. A lacuna não é de integração, é de
**implementação de transporte + evidência oficial por provedor**.

### Correção aplicada

| Onde | Antes | Agora |
|---|---|---|
| `docs/MATRIZ-COBERTURA.md` | "motor ABRASF existe e é testado" | "fluxo ABRASF testado com **transporte falso**; **sem transporte municipal real**" |
| `docs/PAINEL.md` (gerador) | "contrato, roteamento e motor existem e são testados, mas não estão ligados" | acrescenta "e **não há transporte municipal real**: ligar não habilitaria município nenhum" |
| `docs/ROADMAP.md` | pendência 1 = "ligar a fábrica" | pendência 1 = "implementar transporte municipal + fonte oficial por provedor" e, só então, ligar |

### O que continua verdadeiro

- O padrão nacional (DPS → SEFIN) é o único fluxo NFS-e que emite de verdade, e está testado e
  medido em container.
- As tabelas `municipios_nfse`, `credenciais_municipais` e `webservices_sefaz` existem, com rotas de
  cadastro e criptografia por tenant + município — o **cadastro** funciona; o **motor municipal** não.
- Nenhum município é rotulado como atendido por aparecer no seed.

### Verificação

Nenhuma mudança de código: só documentação, porque o código já estava correto (o `Protocol` é a
decisão certa). O erro era meu, na descrição.

---

## 67–68. Isolamento nos downloads e travas de contrato para `tenant_id`

**Data:** 2026-11-27. **Fase:** A (isolamento de tenant). Dois testes que faltavam, nenhum código
alterado — o código já estava correto.

### 67. Downloads de documento não tinham teste de isolamento

O prompt exige teste de vazamento entre tenants em **arquivos**. O arquivo aqui é o documento fiscal:
`GET /v1/emissoes/{id}/danfse` e `GET /v1/emissoes/{id}/representacao`.

As rotas filtram por `tenant.id` no `where` — verificado por leitura — mas **não havia teste**. Um
`where` esquecido numa refatoração passaria, e o resultado seria um tenant baixando a nota de outro
pelo id.

`tests/test_isolamento_downloads.py` (4 testes), com dois emissores reais e nota de cada um:

| Teste | O que prova |
|---|---|
| B tenta DANFSe de A | **404** |
| B tenta representação de A | **404** |
| **A baixa a própria** | **200** e `%PDF` — contraprova: sem ela, um 404 geral "passaria" como isolamento |
| sem `X-API-Key` | **401** |

### 68. `tenant_id` no contrato: trava de regressão

Regra 7 do objetivo: derivar o tenant da credencial, nunca aceitar `tenant_id` do cliente. Medido no
`openapi.json`: **nenhum** schema de entrada expõe `tenant_id`; apenas duas saídas
(`TenantFiscalConfigOut`, `TenantKeyRotacionadaOut`).

Isso estava certo e indefeso. `tests/test_contrato_tenant.py` (4 testes) trava:

- nenhum `requestBody` (qualquer content-type) tem `tenant_id` na primeira propriedade;
- nenhuma rota comum tem `tenant_id` como **query param**;
- a exceção `/v1/admin` existe de fato — o teste falha se a lista de rotas admin estiver vazia,
  senão ele estaria apenas ignorando admin;
- `POST /v1/emissoes` sem chave devolve **401**.

A exceção do admin é por **prefixo de rota** e está explicada no arquivo: operação de plataforma
atravessa tenants por natureza (ADR 0001), e deixar o tenant implícito esconderia qual cliente está
sendo afetado.

### Por que nenhum dos dois mudou código

`consulta.py` não guarda dado de tenant (é CEP público), e as duas rotas de download já filtram por
tenant. O defeito era de **cobertura de teste**, não de implementação — e cobertura de isolamento é
exatamente o que o objetivo exige que exista antes de chamar algo de pronto.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_isolamento_downloads.py` | **4 passed** |
| `pytest tests/test_contrato_tenant.py` | **4 passed** |
| gate completo | **9/9** |

---

## 69. O 422 não era problem+json — o único erro fora do padrão

**Data:** 2026-11-27. **Fase:** A/E (contrato de erro). Medido contra a API em container.

### O que a medição mostrou

| Resposta | `Content-Type` |
|---|---|
| 401 sem chave | `application/problem+json` ✅ |
| 404 rota inexistente | `application/problem+json` ✅ |
| 405 método errado | `application/problem+json` ✅ |
| **422 validação** | **`application/json`** ❌ |

O handler de `HTTPException` já convertia tudo para RFC 7807. O 422 não passa por ele: o FastAPI
trata `RequestValidationError` em handler próprio. Resultado: o cliente tinha de tratar **dois**
formatos de erro, e o único que fugia era justamente o mais frequente em integração nova.

### A correção

Handler para `RequestValidationError` em `criar_app()`, retornando `application/problem+json` com
`type`/`title`/`status`/`origem`/`retryable` **e mantendo `detail` como a lista de erros do
Pydantic**, exatamente como antes.

Por que manter `detail` como lista em vez de trocar por texto: contrato existente. Todo cliente que
lê `detail[0]["msg"]` continua funcionando; os campos RFC 7807 entram **ao lado**. Também adicionei
`errors` com o mesmo conteúdo, para quem preferir um nome inequívoco.

`jsonable_encoder` é obrigatório: `exc.errors()` pode carregar `ctx` com objetos que `json.dumps`
recusa — sem ele o handler estouraria 500 dentro do próprio tratamento de erro.

### Testes (`tests/test_erros_rfc7807.py`, 5)

| Teste | O que prova |
|---|---|
| 422 tem `content-type` problem+json | o defeito medido |
| 422 tem `status`/`title`/`type`/`origem`/`retryable` | é RFC 7807 de verdade, não só o header |
| `detail` continua **lista** com `loc`/`msg`/`type` | compatibilidade com cliente existente |
| `errors` espelha `detail` | nome inequívoco, sem divergir |
| 401 continua problem+json | contraprova: o handler novo não roubou o caminho do `HTTPException` |

### Limite

- O corpo do 422 cresceu (campos RFC + lista duplicada em `detail` e `errors`). Em erro de payload
  gigante isso dobra o tamanho da lista. Aceitável — erro de validação é resposta curta por
  natureza —, mas é uma duplicação deliberada, não descuido.
- Não mexi no `422` que algumas rotas levantam **de propósito** via `HTTPException(422)` (ex.:
  certificado ausente): esse já saía problem+json com `detail` em texto, e mudá-lo quebraria quem
  lê string ali. São dois formatos por origem, e agora estão documentados.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_erros_rfc7807.py` | **5 passed** |
| gate completo | **9/9** |
| `mypy` | zero erros |

---

## 70. Dois modos de operação documentados, com as lacunas do modo hospedado

**Data:** 2026-11-27. **Fase:** produto/documentação. Atende ao adendo de continuidade (§2–§6).

### O que foi verificado antes de escrever

| Verificação | Resultado |
|---|---|
| Licença | **MIT** (`LICENSE`) |
| Chamada obrigatória a servidor do mantenedor | **nenhuma** |
| Telemetria/analytics | **nenhuma** (`grep` em `app/`, `src/`, `scripts/` = zero) |
| Paywall, limite de emissão, licença remota | **não existem no código** |
| `ConectorDz23` | é **webhook de entrada** opcional, autenticado por `tenant_atual`; desativá-lo não afeta emissão |

### Entregues

- **`docs/MODOS-DE-OPERACAO.md`**: modo auto-hospedado × serviço hospedado; o que muda (responsabilidade
  operacional) e o que **não** muda (o código é o mesmo, sem build "enterprise"); custos transparentes;
  fronteira desenvolvedor × operador × contribuinte; e a lista do que **não** está pronto para serviço
  comercial.
- **`docs/ONBOARDING-HOSPEDADO.md`**: os 10 passos pedidos, cada um mapeado à rota real, com
  **lacuna** marcada onde a rota não existe.

### Lacunas do modo hospedado, medidas no código (não estimadas)

| Lacuna | Consequência para um serviço comercial |
|---|---|
| Sem **escopos** por chave | chave é tudo-ou-nada no tenant; não há como dar acesso só de leitura ao ERP |
| Sem **expiração** de chave | credencial vive para sempre |
| Sem **revogação sem substituição** | único caminho é rotacionar (emite outra) |
| Sem **auditoria de uso do certificado** | não é possível responder "quem usou qual A1, quando, para quê" |
| Sem **usuário/papel** por tenant | um tenant = uma chave; várias pessoas exigem compartilhar segredo |
| Sem **exportação/exclusão** por tenant na API | portabilidade e LGPD dependem de acesso ao banco |
| Certificado: remoção apaga a linha, **sem sobrescrever** o ciphertext | "exclusão segura" não está comprovada |

Essas lacunas são a diferença entre "o software permite operar" e "o serviço hospedado está pronto".
O documento diz isso explicitamente — não afirma prontidão que a evidência não sustenta.

### Não confirmado (registrado, não inventado)

Exigência de cadastro da empresa desenvolvedora, identificação de responsável técnico, CSRT ou
homologação por UF/documento. **Não há fonte oficial verificada neste repositório.** O próximo passo
está escrito: consultar o manual do autorizador por documento/UF e registrar versão, data e hash, como
já se faz com XSD em `data/xsd_manifest.json`.

### Verificação

Documentação apenas; nenhum código alterado nesta seção. Gate da rodada: 9/9.

---

## 71–72. Auditoria de uso do certificado (com migração) e o incidente de teste que chamou a SEFIN

**Data:** 2026-11-27. **Fase:** A/B. Atende ao adendo §5 ("auditoria de uso", "exclusão registrada sem
expor segredo").

### 71. O que foi implementado

Era impossível responder "este A1 foi usado para quê, e quando?" — pergunta obrigatória ao operar
credencial fiscal de terceiros.

| Peça | Onde |
|---|---|
| Tabela `certificado_usos` | migração **0012** (upgrade e downgrade testados; `alembic check` sem drift) |
| Modelo | `app/db/models/certificado_uso.py` |
| Registro | `certificados.abrir_para_uso()` — abre e grava; **grava também a falha** |
| Pontos de uso | emissão, cancelamento, evento, consulta de transporte, status de transporte |
| Consulta | `GET /v1/me/certificados/{id}/usos` (404 para certificado de outro tenant) |

**O que a linha guarda:** `operacao`, `ambiente`, `sucesso` e o **tipo** da exceção.
**O que nunca guarda:** PFX, senha, XML, payload, mensagem de erro (mensagem pode carregar CNPJ,
município ou caminho — a auditoria viraria um segundo vazamento). Teste proíbe `pfx`/`senha`/
`signature`/`xml` no registro.

Por que registrar falha: "chave-mestra trocada" e "envelope corrompido" só aparecem no uso. Sem a
linha de falha, o operador descobre por reclamação do cliente.

A linha entra na **mesma transação** da operação fiscal: rollback da operação remove o uso — coerente,
porque nada foi assinado.

### 72. Incidente: um teste meu emitiu contra a borda real da SEFIN

Ao escrever o teste de auditoria, esqueci o override de `Settings` com `nfse_adapter="mock"`. O
padrão do projeto é `sefin`, então a emissão do teste saiu para a **borda real**.

- Resultado: **403** na borda (certificado autoassinado recusado), **nenhum documento emitido**;
- resposta 502 no teste, com a mensagem da SEFIN preservada;
- **mesma classe** do incidente de §48 (benchmark): o padrão do repositório é o adaptador real, e
  teste que esquece o override fala com o autorizador.

**Correção estrutural**, não só do teste: `tests/conftest.py` agora define
`os.environ["NFSE_ADAPTER"] = "mock"` para **toda** a suíte. Antes, cada teste que quisesse o dublê
precisava lembrar; agora o esquecimento é que precisa ser explícito.

Isto não substitui o override de `Settings` em testes que injetam configuração — complementa. E não
impede o *build* de chamar o real: a guarda é da suíte de testes.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_certificado_usos.py` | **5 passed** |
| `alembic upgrade head` / `downgrade 0011` / `check` | aplica, reverte e **sem drift** |
| gate completo | **9/9** |
| contrato + coleção Postman | regenerados (rota nova incluída) |

---

## 73. Expiração e revogação de API key (migração 0013)

**Data:** 2026-11-27. **Fase:** A / modo hospedado (adendo §4–§5). Fecha duas lacunas do
`docs/ONBOARDING-HOSPEDADO.md` §2.

### O que faltava

A chave vivia **para sempre** e não havia como matá-la sem emitir outra. Para operar credencial de
terceiro isso é insuficiente: vazamento exige revogação, e política de segurança exige prazo.

### Implementado

| Peça | Onde |
|---|---|
| Colunas `api_key_expira_em` e `api_key_revogada_em` | migração **0013** (upgrade, downgrade e `alembic check` sem drift) |
| Verificação na autenticação | `tenant_service.autenticar` recusa chave expirada e revogada |
| Rotação com prazo | `rotacionar_chave(..., dias_validade=30)`; **limpa** o carimbo de revogação |
| Revogação sem substituição | `revogar_chave()` + `POST /v1/admin/tenants/{id}/revogar-chave` (X-Admin-Key) |

### Decisão de segurança: revogar troca o hash

A revogação grava um hash **aleatório** no lugar do anterior. Consequência: a chave revogada não casa
em nenhuma busca — nem na do próprio dono — e **não volta a valer** por flip de flag no banco. O
carimbo `api_key_revogada_em` fica como trilha de auditoria.

Efeito colateral aceito: quem apresenta chave revogada recebe `401 credencial inválida`, indistinto de
chave desconhecida. A alternativa (manter o hash e só checar a flag) daria mensagem mais específica e
uma porta de retorno — troquei mensagem por irreversibilidade.

**Chave expirada** é diferente: o hash continua válido, então a resposta é
`401 credencial expirada; rotacione para obter outra`. O dono precisa saber que é prazo, não erro de
digitação.

### Testes (`tests/test_chave_expira_revoga.py`, 6)

| Teste | O que prova |
|---|---|
| expirada → 401 com "expirada" | mensagem distinta da inválida |
| chave válida continua 200 | contraprova |
| revogada → 401 e carimbo gravado | revogação persiste; hash mudou |
| revogar exige admin | sem `ADMIN_HABILITADO` a rota responde **404** (ADR 0001) |
| revogação não afeta vizinho | isolamento entre tenants |
| rotação com prazo limpa revogação | chave nova não nasce morta; a antiga continua morta |

### Achado de implementação (registrado)

A rota nasceu como `/v1/admin/admin/tenants/...`: o router de admin **já tem** `prefix="/admin"` e eu
repeti o prefixo no decorador. O teste pegou como **404**; corrigido para
`/v1/admin/tenants/{id}/revogar-chave`.

### Limite

Revogar deixa o tenant **sem acesso** até alguém emitir outra chave. No auto-hospedado isso é acesso ao
banco; no modo hospedado é o suporte. Não existe rota de "emitir chave para outro tenant" — a decisão
de quem pode fazer isso é de operação, não de código, e ficou fora.

---

## 74. Exclusão de certificado passa a sobrescrever o envelope

**Data:** 2026-11-27. **Fase:** A / adendo §5 ("exclusão segura"). Fecha a lacuna que eu havia
registrado em `docs/ONBOARDING-HOSPEDADO.md` §4.

### O que estava errado

`remover()` executava `DELETE` na linha. O ciphertext continuava em **páginas antigas** da tabela e no
**WAL** — recuperável com ferramenta trivial em muitos cenários. "Removido" no banco não significava
"fora do banco".

### O que mudou

`_sobrescrever_envelope()` troca `pfx_selado` e `senha_selada` por bytes **aleatórios do mesmo
tamanho** e dá `flush` **antes** do `DELETE`. Usado em `remover()` e em `remover_todos()`.

Duas decisões de detalhe:
- **mesmo tamanho**: manter o comprimento evita que a própria linha registre quanto media o segredo
  (metadado que ajuda quem procura);
- **bytes aleatórios**: conteúdo sem cabeçalho que confunda parser de envelope.

### O que este código NÃO garante (e não vou afirmar que garante)

Sobrescrever reduz a superfície; **não torna o dado irrecuperável**. Limites reais:

1. **WAL** e réplicas podem conter a versão anterior até o reciclo;
2. **backups e dumps** já feitos mantêm o envelope antigo — e neles o conteúdo continua selado com a
   chave-mestra, que é o que realmente protege;
3. `autovacuum` decide quando a página é reutilizada; não há `VACUUM FULL` no caminho.

A proteção efetiva continua sendo a **selagem AES-256-GCM com `aad` por tenant** mais a guarda da
chave-mestra (`docs/OPERACAO.md` §5). A sobrescrita é camada adicional, não substituta.

### Testes (`tests/test_certificado_usos.py`, +3)

| Teste | O que prova |
|---|---|
| bytes mudam, tamanho preservado | a sobrescrita acontece e não vira lixo de tamanho diferente |
| registro sem senha não quebra | caminho do A1 sem senha |
| remoção apaga a linha | contraprova: sobrescrever não impede o `DELETE` |

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_certificado_usos.py` | **8 passed** |
| gate completo | **9/9** |
| `mypy` | zero erros |

---

## 75. Escopos por chave de API (migração 0014)

**Data:** 2026-11-27. **Fase:** A / adendo §4. Fecha a última das três lacunas de credencial que eu
havia listado em `docs/ONBOARDING-HOSPEDADO.md`.

### O que faltava

A chave era **tudo-ou-nada no tenant**. Não havia como dar só leitura ao ERP e só emissão ao PDV — que
é o caso real de integração de um gateway fiscal.

### Implementado

| Peça | Onde |
|---|---|
| Coluna `api_key_escopos` (JSONB) | migração **0014** (upgrade, downgrade, `alembic check` sem drift) |
| Aplicação | `_exigir_escopo()` dentro de `tenant_atual`, olhando o método HTTP |
| Definição | `POST /v1/me/rotacionar-chave` aceita `escopos: ["leitura" \| "emissao"]` |

**Regra:** `GET`/`HEAD`/`OPTIONS` exigem `leitura`; o resto exige `emissao`.

Por que método HTTP e não por rota: escopo por rota exigiria anotar 60 handlers e manter a anotação
sincronizada com o contrato; uma rota nova sem anotação ficaria **sem exigência**, silenciosamente. A
regra por método é grosseira e **fecha por padrão** — rota nova já nasce coberta.

### Compatibilidade (o ponto delicado)

`api_key_escopos = None` significa **sem restrição**. Isso é o que mantém as chaves já emitidas
funcionando: tratar ausência como "nenhum escopo" transformaria a migração em negação de acesso geral.
Teste cobre exatamente isso — chave antiga continua lendo e escrevendo.

### Testes (`tests/test_escopos_chave.py`, 6)

| Teste | O que prova |
|---|---|
| chave sem escopo continua com tudo | compatibilidade da migração |
| escopo `leitura` → GET 200, emissão **403** | restrição aplicada, mensagem cita o escopo |
| chave anterior deixa de valer após rotação | rotação mata a antiga (já era assim) |
| escopo `emissao` → emite 201, leitura **403** | o caso espelhado, não só um dos lados |
| prazo e escopo juntos | os dois campos convivem na resposta |
| escopo inválido (`admin`) → **422** | o contrato recusa antes de gravar |

O cenário de emissão sobe **certificado A1**, senão o 422 seria por falta de certificado e o teste
provaria a coisa errada (foi o primeiro erro que cometi aqui).

### Limite

- Escopo é por **método**, não por recurso: `emissao` permite qualquer escrita, inclusive cancelamento e
  cadastro de certificado. Um escopo "só emitir, sem cancelar" exigiria anotação por rota e o custo
  correspondente — declarado, não implementado.
- Rotação **substitui** os escopos; não há rota para alterar escopo sem trocar a chave. Para reduzir
  privilégio é preciso rotacionar e redistribuir a chave nova.
- A verificação usa o método do request; `HEAD`/`OPTIONS` contam como leitura de propósito.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_escopos_chave.py` | **6 passed** |
| migração 0014 | aplica, reverte, **sem drift** |
| gate completo | **9/9** |
| contrato + Postman | regenerados |

---

## 76. Exportação dos dados do tenant (portabilidade)

**Data:** 2026-11-27. **Fase:** E / adendo §6 item 10. Era a última lacuna grande do modo hospedado.

### O que foi implementado

`GET /v1/me/exportacao` devolve um pacote JSON com: identificação do tenant, configuração fiscal,
**metadados** dos certificados (apelido, CNPJ, validade, fingerprint, ativo — nunca o PFX), URL do
webhook, e contagem de emissões por status. Com `?incluir_xml=true&limite=N` acrescenta até N
documentos com XML autorizado.

### Decisões que importam

| Decisão | Motivo |
|---|---|
| **Sem XML por padrão** | exportar tudo por padrão transforma pedido de conferência em resposta de gigabytes |
| `limite` de 1 a 500 | teto explícito em vez de "depende do banco do cliente" |
| **Nunca** PFX, senha, hash de chave, segredo de webhook, token | portabilidade é sobre os dados do cliente, não sobre as credenciais dele — credencial sai do cofre, não de uma exportação |
| Certificado aparece só como metadado | o cliente precisa saber **qual** certificado existe e até quando vale, não possuir a chave privada de novo pelo export |

### Testes (`tests/test_exportacao_tenant.py`, 6)

| Teste | O que prova |
|---|---|
| exporta dados do próprio tenant | slug, UF, certificado, URL de webhook, contadores |
| sem XML por padrão | `documentos` ausente |
| nenhum segredo no pacote | proíbe `pfx_selado`, `senha_selada`, `api_key_hash`, `webhook_secret`, `signature` |
| **a própria API key não aparece** | teste com o valor literal da chave |
| não traz dado de outro tenant | dois tenants, pacote do segundo não contém o primeiro |
| XML entra quando pedido | `incluir_xml=true&limite=10` devolve documentos e o limite usado |

### Limite

- **Não é backup.** Backup é o dump do banco (`docs/OPERACAO.md` §2); o pacote é portabilidade de
  dado de negócio. Restaurar um pacote desses não é caminho suportado e o documento não sugere que seja.
- Não há paginação de documentos: `limite` corta em N mais recentes, sem cursor. Para histórico
  completo, dump.
- **Exclusão do tenant por API continua não existindo.** LGPD/portabilidade pedem também o direito de
  eliminação; hoje o caminho é `DELETE` no banco pelo operador. É a lacuna seguinte, e ela exige
  decisão sobre confirmação e sobre o que fazer com documento fiscal que tem guarda legal — não vou
  implementar apagamento de documento fiscal sem essa definição.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_exportacao_tenant.py` | **6 passed** |
| gate completo | **9/9** |
| contrato + Postman | regenerados |

---

## 77. Roteamento da NFS-e Nacional: campo existia, decisão não existia

**Data:** 2026-11-27. **Fase:** B (regra fiscal). Atende ao adendo regulatório.

### O defeito medido

`tenant_fiscal_configs.aderente_emissor_nacional` era **gravado e nunca consultado**. Varredura em
`app/` por esse nome retornava: a definição no modelo, o schema de entrada e **um texto de orientação
de erro** (`nfse/errors.py`, mensagem do `E0312`). Nenhuma decisão de rota olhava o campo.

Consequência: o sistema sempre tentava o Emissor Nacional. Para município cujo parâmetro oficial diz
"não aderente", o erro só aparecia como **rejeição `E0312` vinda da SEFIN**, depois de gerar, assinar
e transmitir.

### Fontes consultadas (2026-11-27)

- [Perguntas Frequentes NFS-e v1.2 (arquivo de 2026-10-27)](https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-frequentes-nfs-e-v1-2-20261027.pdf)
- [Perguntas Frequentes NFS-e v1.3 (arquivo de 2026-11-06)](https://www.gov.br/nfse/pt-br/perguntas-frequentes/perguntas-frequentes-nfs-e-v1-3-20261106.pdf)

O que essas fontes sustentam: ME/EPP do Simples emitem **exclusivamente** pelo Emissor Nacional a
partir de **01/11/2026** (sistema municipal deixa de autorizar); `situacaoEmissaoPadraoContribuintesRFB = 0`
significa que o município **não** usa os Emissores Nacionais como padrão; a Autorização de Uso dos
Emissores Públicos (CNC/Painel do Contribuinte) é trava de exclusividade, não opção paralela.

### O que foi implementado

`app/nfse/roteamento.py` — função **pura** de decisão, com quatro ramos e fonte citada em cada um:

| Situação | Decisão |
|---|---|
| ME/EPP Simples, competência ≥ 2026-11 | **nacional permitido** (obrigação legal vence parâmetro municipal) |
| Parâmetro **não confirmado** + produção | **bloqueia** — rota não pode ser presumida em produção |
| Parâmetro não confirmado + fora de produção | segue com **aviso** (não é prova de rota) |
| Aderente confirmado | nacional permitido |
| Não aderente confirmado, fora da obrigação | **bloqueia** com pendência (integração municipal §66 ou autorização CNC) |

Preflight ligado em `nfse/servico.py::emitir` **antes de reservar número, assinar e transmitir**, com
`RotaNaoPermitida` carregando a **pendência**, e tradução dedicada em `emissoes.py` para que o 422 diga
o que falta (o `except` genérico de `ErroDeEmissao` descartaria essa informação).

### Migração 0015

`aderente_confirmado_em` e `aderente_fonte` em `tenant_fiscal_configs`. Sem eles, não havia como
distinguir "o município não adere" de "ninguém conferiu" — e bloquear por omissão derrubaria município
aderente cujo booleano ficou `False` no default.

### Exceções **não** implementadas, de propósito

A alegação de que **MEI** e operações do **grupo 99** escapam de `aderenteEmissorNacional = 0` **não
foi confirmada** em fonte oficial nesta sessão. Não há ramo para elas, e o teste
`test_mei_nao_recebe_tratamento_especial` fixa o comportamento conservador: MEI é tratado como
qualquer contribuinte. Implementar a exceção sem fonte produziria nota pela rota errada **com
aparência de autorizada** — pior que bloquear.

### Testes (`tests/test_nfse_roteamento.py`, 13)

Decisão (10): Simples ≥ 2026-11 passa; Simples 2026-10 **não** é reclassificado; MEI sem tratamento
especial; competência ausente não vira obrigação; aderente permite; não aderente bloqueia com
pendência; produção exige confirmação; homologação avisa e segue; decisão imutável; **todo bloqueio
traz próximo passo**.

Rota real (3): não aderente → **422** com "Pendência"; Simples 2026-11 → **201**; bloqueio de um
tenant **não afeta** outro.

### Limites declarados

- `simples_nacional`/`optante_mei` continuam **preenchidos à mão**. O correto é vir dos parâmetros
  oficiais do contribuinte; hoje o sistema registra a procedência do parâmetro municipal
  (`aderente_*`), mas **não** do regime. É a próxima lacuna, e ela exige fonte de dados oficial.
- A exceção do MEI/grupo 99 fica como pendência com o pré-requisito escrito: confirmar em fonte e
  adicionar ramo com teste.
- A decisão **não** consulta o CNC em tempo real: `Autorização de Uso` entra como pendência textual,
  não como verificação. Consultar exigiria integração autenticada ao Painel do Contribuinte.
- `producao` bloqueia sem confirmação — o que significa que **nenhuma emissão real é possível hoje
  sem parametrizar a fonte**. Isso é intencional: o projeto nunca emitiu em produção.

---

## 78. Reconciliação do ciclo NFS-e: README contradizia a si mesmo, e eu contradisse a evidência

**Data:** 2026-11-27. **Fase:** B/F. Atende ao item "Evidências e documentação" do adendo regulatório.

### Três afirmações, duas fontes, uma delas minha

| Onde | O que dizia |
|---|---|
| `README.md` cabeçalho | NFS-e **autorizada pela Produção Restrita**, ciclo completo emitir → consultar → DANFSe → cancelar |
| `README.md` §"Produção restrita" | "falta validar o payload de emissão"; "emissão, cancelamento e eventos seguem `[A VALIDAR]`" |
| minhas próprias falas desta sessão | "zero notas autorizadas" |

As duas primeiras **se contradiziam** dentro do mesmo arquivo. A terceira era minha, e estava errada como
afirmação geral.

### O que a evidência mostra

`docs/REFERENCIAS.md` §15 (registro de 25/11/2026) traz a chave autorizada
`5200258...2611076352769` e o ciclo: `201 status=authorized`, `GET` autorizado com XML, DANFSe de 4.014
bytes, cancelamento aceito.

Medido no banco de desenvolvimento em **2026-11-27**:

```
invoices:        3 authorized, 1 cancelled, 10 rejected, 2 pending, 1 error — TODOS ambiente=homologacao
fiscal_documents: 4 registros, 4 com xml_autorizado e chave, 0 com protocolo
```

E o XML autorizado guardado, quando lido, é inequívoco:

```
<NFSe versao="1.01" ...><infNFSe Id="NFS5200258...">
  <xLocEmi>Águas Lindas de Goiás</xLocEmi> ... <ambGer>2</ambGer>
  <cStat>100</cStat><dhProc>2026-11-25T20:21:46-03:00</dhProc><nDFSe>44</nDFSe>
```

`cStat=100` é autorização; `ambGer=2` é homologação. O banco mistura chamadas reais com execuções em
mock (chaves `6718062...`, de 27/11), mas as chaves `5200258...` de 25/11 são reais.

### Correções aplicadas

1. **`README.md`** — o quadro de "Produção restrita" agora reflete o medido, e há aviso explícito de que
   **Produção Restrita ≠ produção**. A contradição interna desapareceu.
2. **`docs/MATRIZ-COBERTURA.md`** — a linha "Autorização (emissão)" passou de `🔒` para
   ✅ **real em homologação**, com a nota do banco reescrita para separar mock de real.
3. **Minha fala**: onde eu disse "zero notas autorizadas", o correto é **zero em produção**. Em
   homologação existe autorização real documentada.

### A "lacuna do protocolo" que eu quase inventei

Cheguei a registrar `protocolo` vazio como lacuna de persistência. Fui ao XML antes de tratar como
defeito — e **não é**: a NFS-e Nacional não emite número de protocolo como a NF-e; a evidência de
autorização é `cStat` + `dhProc` + `nDFSe`. Criar coluna/protocolo seria inventar requisito de leiaute.

O defeito real era outro, e foi corrigido: **`codigo_status` era `NULL` em todos os documentos**,
inclusive na NFS-e autorizada. O `cStat` existia apenas dentro do blob, então "esta nota está
autorizada?" só se respondia abrindo o XML.

- `extrair_cstat()` em `app/nfse/errors.py` lê `cStat` com namespace e **nunca levanta** (XML inesperado
  devolve `None`; o XML guardado continua sendo a prova, o campo é índice);
- `RespostaEmissao.codigo_status` preenchido pelo adapter real **e** pelo dublê — o dublê imita o
  contrato (`cStat=100`), senão o teste passaria num caminho que a produção não tem;
- `FiscalDocument.codigo_status` persistido na emissão; `protocolo` permanece nulo **de propósito**,
  com teste que fixa isso.

### Testes (`tests/test_nfse_cstat.py`, 6)

Extração com namespace; aceita `bytes`; sem `cStat` → `None`; XML inválido não levanta; vazio → `None`;
e a persistência: emissão grava `codigo_status="100"` e `protocolo is None`.

### O que continua não provado

- **Produção fiscal: nenhuma nota.** A autorização é de homologação;
- o registro de 25/11 é documental — não reexecutei a emissão real nesta sessão (exigiria certificado e
  chamada externa), então a classe de evidência é **"registro+banco"**, não "reproduzido hoje";
- `dhProc`/`nDFSe` continuam só no XML: poderiam virar colunas, mas não são necessários para responder
  "autorizada?", que é o que `cStat` resolve.

---

## 79. CI vermelho por infraestrutura: `lxml` compilado sem headers

**Data:** 2026-11-27. **Fase:** F (CI/CD).

### O que aconteceu

O commit de §78 subiu e a CI falhou em **"Instalar dependências"**, nos dois jobs:

```
Error: Please make sure the libxml2 and libxslt development packages are installed.
ERROR: Failed to build 'lxml' when getting requirements to build wheel
```

Não era regressão de código: o commit anterior passou no **mesmo** workflow, e o instalador é idêntico
(`pip install -e ".[app,dev]"`). É o caso clássico de runner cujo `pip` resolve uma versão de `lxml` sem
wheel correspondente e cai para o build do fonte — e o runner não tem os headers.

Reexecutei os jobs falhos (`gh run rerun --failed`) para distinguir transiente de persistente:
**falhou de novo**. Persistente.

### Correção aplicada

Passo novo nos **dois** jobs, antes do `pip`:

```yaml
- name: Bibliotecas de sistema para compilar lxml
  run: |
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends libxml2-dev libxslt1-dev
```

Resolve o build em vez de mascarar o erro. **Não** adiciona dependência de runtime, **não** altera o
ambiente do usuário e não mexe em versão de biblioteca — é só o runner de CI.

### Erro meu no caminho (registrado)

A primeira edição juntou `run: |` na linha do `name:` e **quebrou o YAML**. O `yaml.safe_load` recusou com
`mapping values are not allowed here` na linha 66. Corrigi as duas ocorrências e validei antes de
commitar: `jobs: ['testes','contrato']`, 11 passos e 5 passos.

Se eu tivesse commitado sem validar, o push teria criado um workflow inválido — pior que a falha
original, porque o GitHub não roda workflow inválido e o vermelho viria sem log.

### Verificação

| Passo | Resultado |
|---|---|
| `yaml.safe_load` no workflow | estrutura válida, 2 jobs |
| reexecução antes da correção | `completed failure` (persistente) |
| CI após a correção | **`completed success`** |

### O que isto **não** prova

Que o build de `lxml` do fonte seja desejável. Se o runner voltar a não ter headers, o passo de apt
resolve; o certo a médio prazo seria fixar uma versão de `lxml` com wheel garantida para toda matriz
suportada — mas pin sem necessidade declarada é dívida, e o projeto não declara matriz de runners.
O gatilho fica registrado aqui em vez de virar pin especulativo.

---

## 80. Certificado ambíguo e divergência leiaute×XSD: dois riscos silenciosos

**Data:** 2026-11-27. **Fase:** A/B. Origem: verificação dos quatro itens pedidos (NT-009, condomínios,
Anexo VIII, multi-CNPJ), todos **ausentes** — a checagem expôs dois riscos que já existiam.

### 80.1 Dois certificados ativos assinavam "um ao acaso"

`certificados.ativo()` fazia `.first()` sobre `ativo=True`. O banco não tem índice único para isso, e
um upload concorrente com uma ativação pode deixar dois ativos. Resultado: a emissão escolhia um
arbitrariamente e **assinava com o titular errado** — e não há como detectar depois, porque a nota sai
autorizada.

Correção: `ativo()` agora exige **exatamente um**. Zero → `None`; um → ele; mais de um →
`CertificadoAmbiguo`, com os certificados listados (apelido, id, CNPJ) e a instrução de qual rota usar.
Na emissão o mapeamento é **409**, não 422: é conflito de estado a resolver pelo operador, não erro de
payload. A rota `POST /v1/me/certificados/{id}/ativar` já existia e desativa os demais — é a saída.

Testes (`tests/test_certificado_ambiguo.py`, 3): dois ativos → **409** citando a ambiguidade; ativar um
resolve e a emissão volta a **201**; um ativo único continua emitindo.

### 80.2 O leiaute declarado não tem XSD no repositório

`constants.py` declara homologação em `LEIAUTE_NT009`, mas o pacote de schemas é `nfse-1.01` e **não
declara** `finNFSe`/`vAjusteBC`/`indDest`. Ou seja: validar "NT 009" contra o XSD que existe dá falsa
segurança — o schema aceita o documento antigo e recusaria o novo.

Não dá para corrigir sem o **pacote oficial da NT 009 (2026-11-24)** com origem, data e hash; escrever
schema à mão violaria a regra 9. O que dá para fazer é impedir que o gap passe em silêncio:
`tests/test_leiaute_nt009_guard.py` é `xfail(strict=True)`.

- passa como **xfail enquanto o gap existir**, com a razão nomeando o bloqueio;
- **falha no dia em que o XSD oficial entrar** — e aí a marcação tem de sair, forçando a validação real
  a ocupar o lugar do "esperado falhar".

É o oposto de relaxar expectativa: a suíte fica verde **com o gap documentado**, e a correção quebra o
teste de propósito.

### 80.3 Os quatro itens pedidos: estado medido

| Item | Estado | Evidência |
|---|---|---|
| NT-009 2026-11-24 + `indDest` automático | ❌ | XSD é `nfse-1.01`; **zero** ocorrências de `indDest` em `app/`, `src/`, `tests/` |
| Condomínios 99.05.01 + `condominios`/`unidades` | ❌ | **zero** ocorrências de `condomin`, `99.05.01`, `gCobranca`, `gDetCobranca`, `CIB` |
| Anexo VIII (tribISSQN=4, NBS 110019000, cIndOp 020201, CST 200, cClassTrib 200046) | ❌ | só validação de **formato**: `dps.py:38-40`, `tribISSQN` como conjunto `{1,2,3,4}` em `dps.py:47` |
| Multi-CNPJ por estabelecimento + procuração 00233 | 🌗 parcial → **endurecido** | vários certificados com `cnpj` existem; seleção por estabelecimento e procuração **não** existem |

Sobre o item 3 há um **conflito declarado** com §77: o roteador hoje **bloqueia** emissão nacional em
município não aderente fora da obrigação do Simples. A exceção de Anexo VIII exige fonte oficial que a
sustente; sem ela, implementar seria reintroduzir a nota pela rota errada com aparência de autorizada.

### O que continua bloqueado, com o pré-requisito exato

1. **Pacote XSD oficial NT-009 (2026-11-24)** — arquivo + URL + data + hash;
2. **Manual/leiaute dos grupos `condominios` e `imovel.unidades`** e a regra do 99.05.01;
3. **Fonte oficial do Anexo VIII** que fixe os cinco códigos e a exceção de rota;
4. **Regra de titularidade e contrato da procuração eletrônica RFB (00233)** — endpoints, campos,
   vigência e revogação.

Nenhum desses pode ser suprido por inferência; todos exigem documento oficial que eu não tenho.

---

## 81. Adendo 3 aplicado como bloqueio: fontes oficiais, manifestos e estados

**Data:** 2026-11-27. **Fase:** gate regulatório. **Nenhum schema, código fiscal, rota ou integração foi
implementado** nesta seção — por exigência do próprio adendo.

### O que foi coletado (fontes oficiais, com hash)

| Fonte | Arquivo | Bytes | SHA-256 (primeiros 16) |
|---|---|---|---|
| "Documentação atual" — pacote de esquemas | `esquemas-xsd-v1.01-20260209.zip` | 65.640 | `e7935cbd9470527c` |
| "Arquivos dos esquemas XSD" (NFS-e via) | `schemas_v1-01_atualizado.zip` | 12.298 | `e17ffb5eb05ecd7e` |
| Manual contribuintes API ADN v1.1 (2026-11-03) | `.pdf` | 325.925 | `f3c7cf067a51a768` |
| Portarias e Resoluções CGNFS-e (índice) | `.html` | 92.942 | `2a8bed04f08b073a` |

Manifesto completo, com URL direta, órgão, título, data de acesso e limitação de cada item:
[`sources/manifest.yaml`](../sources/manifest.yaml). Os arquivos estão versionados para o hash ser
reverificável offline.

### O que **não** foi encontrado

- **Pacote XSD NT-009 de 2026-11-24**: não existe link nas páginas oficiais consultadas. O pacote mais
  recente publicado é **`esquemas-xsd-v1.01-20260209.zip`** (2026-02-09).
- **`finNFSe`, `vAjusteBC`, `indDest`, `condominios`, `gCobranca`**: `grep` vazio nos dois pacotes oficiais
  baixados.
- **Manual/leiaute de `condominios` / `imovel.unidades` / 99.05.01**: não localizado.
- **Ato do Anexo VIII** com 110019000 / 020201 / 200046: índice de resoluções localizado, vínculo **não
  verificado**.
- **Documentação oficial da procuração RFB (00233)**: não localizada.
- O manual ADN v1.1 tem **5 páginas / 5.735 caracteres** e nenhum dos termos procurados — é capa, não
  especificação.

### Achado adicional: o XSD do repositório não é o oficial

| Arquivo | Tamanho | SHA-256 (16) |
|---|---|---|
| `tests/fixtures/schemas/nfse-1.01/DPS_v1.01.xsd` (repo) | 678 | `c7dab363d8cf7c83` |
| `Schemas/1.01/DPS_v1.01.xsd` (oficial 2026-02-09) | 691 | `fe45e5250a48e519` |

**Diferentes.** O fixture do repositório é menor que o oficial: não é o arquivo publicado. Isso significa
que a validação XSD que a suíte executa prova conformidade contra um schema **de proveniência não
estabelecida**, não contra o oficial. Registrado como lacuna, não corrigido — substituir o schema exige o
pacote oficial íntegro e revisão dos testes que dependem dele.

### Estados (matriz completa em `docs/REQUISITOS-FONTES.md`)

| REQ | Tema | Estado |
|---|---|---|
| REQ-1 | XSD NT-009 2026-11-24 + `indDest` | **BLOCKED** |
| REQ-2 | `condominios` / `imovel.unidades` / 99.05.01 | **BLOCKED** |
| REQ-3 | Anexo VIII (110019000 / 020201 / 200046) + exceção de rota | **BLOCKED** |
| REQ-4 | Titularidade, certificado de terceiro, procuração RFB 00233 | **BLOCKED** |
| REQ-5 | Contrato multitenant (tenant ≠ emitente ≠ certificado ≠ operador) | **PARTIAL** |

Nenhum `PASS`. Nenhum `NOT_TESTED` "otimista": onde procurei e não achei, está `BLOCKED` com o item
exato faltando.

### ADR 0005 — decisão de bloqueio, não de implementação

[`docs/adr/0005-titularidade-e-representacao.md`](../adr/0005-titularidade-e-representacao.md) registra:
`tenant_id` continua a fronteira de isolamento; emitente é o CNPJ do certificado ativo; **representação
por procuração fica bloqueada**; e o modo hospedado **não aceita certificado de terceiro** enquanto não
houver contrato oficial — limitação declarada ao cliente, não bug.

### O que continua valendo do trabalho anterior

§77 (roteamento com preflight) e §80 (certificado ambíguo → 409, guarda `xfail` do gap XSD) **não** foram
afrouxados. A exceção de rota do Anexo VIII não foi codificada justamente porque a fonte não existe — e
implementá-la por hipótese reintroduziria o defeito que §77 corrigiu.

### Pré-requisito exato para desbloquear

1. URL oficial do pacote **NT-009 de 2026-11-24** (ou comunicado que o nomeie);
2. manual/leiaute de **`condominios` e `imovel.unidades`** com cardinalidade e a regra do 99.05.01;
3. **ato do Anexo VIII** com os três códigos, significados e a condição da rota excepcional;
4. **documentação oficial da procuração RFB 00233**: endpoint, autenticação, campos, poderes, vigência,
   situação e forma de consultar revogação.

Com qualquer um em mão: baixar → SHA-256 → manifesto → atualizar matriz → implementar **só** o contrato
comprovado → testes positivo e negativo → revisão independente.

---

## 82. Prova dura: o XSD do repositório foi adaptado para aceitar o código

**Data:** 2026-11-27. **Fase:** C/F (integridade de schema). Consequência direta do pacote oficial baixado
no Adendo 3.

### Experimento executado

Substituí os 8 XSD de `tests/fixtures/schemas/nfse-1.01/` pelos arquivos **oficiais** do pacote
`esquemas-xsd-v1.01-20260209.zip` (sha256 `e7935cbd9470527c…`) e rodei a suíte de schema. Resultado:
**falhou**, com dois erros independentes.

### Erro 1 — `finNFSe` não existe no leiaute oficial 1.01

```
Element '{...}finNFSe': This element is not expected.
Expected is one of ( cMotivoEmisTI, chNFSeRej, cLocEmi )
```

O gerador emite `finNFSe` (campo da **NT 009**) dentro da DPS. O XSD oficial **vigente** (2026-02-09) é
anterior à NT 009 e não aceita o elemento.

**Conclusão material:** o fixture do repositório aceitava `finNFSe` porque foi **modificado**. O
`ORIGEM.md` já declarava origem em projeto de terceiro ("OpenAC.Net.NFSe.Nacional"); a comparação agora
prova o efeito: **a validação XSD da suíte não provava conformidade com o schema oficial** — provava
conformidade com um schema ajustado ao código.

### Erro 2 — `serie` e `idEvManifRej` com padrão não atendido

- `serie` = `"1"` rejeitado pelo padrão oficial (`TSSerieDPS`, `tiposSimples_v1.01.xsd`);
- `idEvManifRej` do catálogo de eventos não atende `[0-9]{59}` (`TSIdNumEvento`).

Ambos são **dados de teste/geração** que o schema permissivo não pegava. Não foram corrigidos nesta
execução: corrigir exige decidir qual leiaute adotar (ver abaixo), e o fixture oficial não pode ser
adotado com o gerador no estado atual.

### Decisão: reverter o fixture e transformar a divergência em teste

Os fixtures voltaram aos arquivos anteriores (a suíte fica verde) **e** a divergência passou a ser
verificada, não narrada:

`tests/test_leiaute_nt009_guard.py` agora tem **duas** guardas `xfail(strict=True)`:

1. `test_xsd_acompanha_o_leiaute_declarado` — falha se o leiaute declarado for NT 009 e o XSD não tiver
   os elementos;
2. `test_gerador_e_aceito_pelo_xsd_oficial` — extrai o **zip oficial versionado** (funciona na CI, sem
   depender de download) e valida a DPS gerada contra ele. Hoje falha por `finNFSe`; **passa a passar no
   dia em que o gerador e o leiaute estiverem alinhados — e, por ser `strict`, quebra a suíte para forçar
   a revisão da decisão**.

Nenhum dos dois "relaxa expectativa": os dois quebram quando a situação mudar, que é o oposto.

### O que isso muda no estado do projeto

| Antes | Agora |
|---|---|
| "XSD oficial, validação offline" (texto do `ORIGEM.md` e do teste) | fixture de **fonte secundária, adaptado**; divergência medida e testada |
| leiaute declarado NT 009 sem schema | continua **BLOCKED** (REQ-1), agora com prova de que o oficial rejeita o campo |
| — | pacote oficial preservado em `sources/oficiais/` com hash no manifesto |

### Bloqueio que permanece, com o pré-requisito exato

Adotar a NT 009 exige o **pacote oficial dela (2026-11-24)**. Sem esse pacote não se decide se o campo
`finNFSe` está correto, nem se `serie` deve ser zero-padded, nem se o catálogo de eventos precisa de 59
dígitos. Escrever isso por inferência seria inventar leiaute — o que o Adendo 3 proíbe.

---

## 83. Integridade de XSD: a biblioteca existia, ninguém a chamava (e eu dupliquei antes de ver)

**Data:** 2026-11-27. **Fase:** F. Item da missão §3: "manifesto SHA-256 de XSD, comparação de arquivo
ausente/adulterado/não manifestado e configuração WARN/STRICT".

### Primeiro, o erro que eu cometi

Comecei escrevendo `scripts/verificar_xsd.py` e `tests/test_integridade_xsd.py` — **sem procurar** se
isso já existia. Existia, completo:

| Peça | Onde |
|---|---|
| `verificar()`, `sha256()`, `gerar_manifesto()`, `ModoVerificacao` (WARN/STRICT) | `app/core/schemas.py` |
| Manifesto versionado com **113 schemas** (NFS-e, NF-e, CT-e, MDF-e) | `data/xsd_manifest.json` |
| Gerador | `scripts/gerar_manifesto_xsd.py` |
| Testes (13) | `tests/test_schemas_integridade.py` |

Pior: o `MANIFEST.sha256` que meu script gerou dentro do diretório de fixtures fez o teste **existente**
falhar (ele reporta arquivo não manifestado — corretamente). Removi a duplicação inteira. Registro aqui
porque a regra 4 é explícita e eu a violei por não ter procurado antes.

### O que a medição então mostrou

A funcionalidade estava completa… e **desligada**:

- `app/core/schemas.verificar` **não era chamado em parte alguma de `app/`**;
- `scripts/check_ci.py` **não tinha** checagem de integridade;
- o gerador só tinha dry-run e `--apply` — **nada falhava** se um schema divergisse.

Ou seja: exatamente o padrão que a missão manda identificar — implementação isolada que não chega ao
fluxo. A documentação do módulo chegava a declarar "hash conferido no boot"; não havia boot nenhum
chamando.

### Correção mínima, sem duplicar

1. **`--check` no gerador existente** (`scripts/gerar_manifesto_xsd.py`): sai **1** quando há schema
   novo, removido ou alterado, e **0** quando os 113 conferem. O dry-run continua saindo 0.
2. **Checagem no gate** (`scripts/check_ci.py`): vira o 10º check, com saída `[OK] 113 schema(s)
   conferem com o manifesto`.
3. **Passo no workflow de CI**: mesma verificação, para não depender do gate local.

### Verificação executada

| Comando | Resultado |
|---|---|
| `python -m scripts.gerar_manifesto_xsd --check` | `[OK] 113 schema(s) conferem com o manifesto`, exit 0 |
| `scripts.check_ci` (rápido) | 10 checks, todos `[OK]`, incluindo `integridade dos XSD` |
| `pytest tests/test_schemas_integridade.py` | **13 passed** (voltou a passar após remover meu arquivo intruso) |
| `yaml.safe_load` no workflow | estrutura válida, com o passo novo |

### O que continua valendo

- O manifesto cobre os 4 diretórios de schema; qualquer troca passa a **falhar** o gate e a CI.
- Isso **não** diz que os schemas são oficiais. O da NFS-e é de fonte secundária e foi adaptado (§82); a
  integridade que se prova aqui é "o arquivo é o que foi registrado", não "o arquivo é o publicado".

---

## 84. Integridade de XSD no boot: o docstring dizia, o código não fazia

**Data:** 2026-11-27. **Fase:** F. Fecha o último ponto morto da mesma família de §83.

### O que estava escrito × o que acontecia

`app/core/schemas.py` afirma no docstring: "Seção R3 do v10.0 pede hash conferido no boot e aborto se
divergir. Implementado de forma **mais conservadora**… Modo explícito: WARN (padrão) registra divergência;
STRICT levanta."

Medido: **nenhum código chamava `verificar`**. Nem o app, nem o gate (até §83), nem a CI. O processo
subia sem olhar para o manifesto — a verificação existia como biblioteca e teste, não como controle.

### Implementado

`_verificar_integridade_dos_schemas()` chamada no `lifespan`, logo após as validações de configuração:

| Situação | Comportamento |
|---|---|
| manifesto ausente | `WARNING xsd_sem_manifesto` e segue (estado válido: verificação desligada) |
| divergência, modo WARN (padrão) | `WARNING xsd_integridade_divergente` e segue |
| divergência, modo STRICT | `ERROR` e **o processo não inicia** |
| tudo confere | silêncio (não polui log de boot) |

Configuração: `XSD_INTEGRIDADE_STRICT` (`false` por padrão), documentada no próprio `Settings` com o
motivo de não ser o padrão — nem todo schema tem procedência oficial confirmada, e derrubar a API por
schema secundário trocaria risco de integridade por risco de indisponibilidade.

### Testes (`tests/test_boot_integridade_xsd.py`, 4)

| Teste | O que prova |
|---|---|
| manifesto real não levanta | boot normal com os 113 schemas íntegros |
| manifesto ausente avisa e segue | ausência não é falha fatal |
| divergência em WARN não levanta | padrão preservado |
| divergência em STRICT levanta | `ErroDeIntegridade` sobe e o boot falha |

Um teste meu foi descartado no caminho: a primeira versão de "divergência em WARN" tentava trocar o
diretório via `monkeypatch` de `Path`, o que **não** exercitava a função (o caminho é fixo). Substituí por
divergência real no manifesto (arquivo listado e inexistente), que é o caso de uso.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_boot_integridade_xsd.py` | **4 passed** |
| `scripts.check_ci` (rápido) | **10/10** |
| `mypy app src` | zero erros / 176 arquivos |

---

## 85. Consulta de status ia à SEFAZ sem circuito — e o escopo por UF estava disponível

**Data:** 2026-11-27. **Fase:** F (resiliência). Missão §3: "circuit breaker ligado às chamadas externas
reais, escopado por serviço/UF/município".

### Medição

Varredura por chamadas ao transporte externo e por uso de `executar_com_circuito`:

| Caminho | Circuito antes |
|---|---|
| emissão (`POST /v1/emissoes`) | ✅ `emitir_com_circuito` |
| cancelamento | ✅ `executar_com_circuito(..., OPERACAO_CANCELAMENTO)` |
| evento | ✅ `executar_com_circuito(..., OPERACAO_EVENTO)` |
| **status de transporte** (`GET /v1/transportes/status`) | ❌ **direto no `ClienteSefaz`** |

O endpoint recebe `uf` como parâmetro — exatamente o escopo que o circuito já sabe usar — e não usava.
Com a SEFAZ de uma UF fora, cada requisição queimava **30 s** de timeout do transporte, sem que o
circuito abrisse para as seguintes.

### Correção

`executar_com_circuito(registro_padrao, uf=uf.upper(), operacao="consulta_status", acao=_consultar)`,
com a chamada de CT-e/MDF-e dentro da closure. A chave fica `sefaz:<UF>:consulta_status`:

- **por UF**: GO fora não abre o circuito de SP (o teste fixa isso);
- **por operação**: queda de consulta não bloqueia emissão.

`CircuitoAberto` já tem handler global (503 + `Retry-After`), então não houve mudança de contrato: o 504
de transporte continua para recusa definitiva, e o 503 aparece quando o circuito está aberto.

### Testes (`tests/test_circuito_consulta_status.py`, 2)

Chave por UF (`sefaz:GO:consulta_status` ≠ `sefaz:SP:consulta_status`) e separação entre consulta e
autorização. Mais os 11 de `test_transporte_status_rota.py`, que seguem verdes.

### Incidente meu nesta rodada

Rodei a suíte de cobertura **em segundo plano** enquanto executava testes — no mesmo banco de teste. O
resultado foi contaminação: `test_transporte_status_rota.py` falhou com **401 "credencial inválida"**,
erro que não existia. Matei o job e a mesma suíte passou (11/11). É a **terceira vez** que cometo esse
erro nesta sessão; o registro fica para não repetir: medição de cobertura e testes de banco são
sequenciais, nunca concorrentes.

---

## 86. Webhook retentava recusa permanente — 5 chamadas inúteis e 42 min até a DLQ

**Data:** 2026-11-27. **Fase:** E/F. Missão §3: "retry somente para falhas transitórias".

### Medição

`app/webhooks/service.py` tratava **qualquer** não-2xx como falha retentável: `BACKOFF_SEGUNDOS = (10,
30, 120, 600, 1800)`, cinco tentativas. Um `404` no endpoint do cliente — configuração errada, que nunca
vai passar — consumia 5 chamadas ao servidor dele ao longo de ~42 minutos antes de chegar à DLQ.

### Correção

`_recusa_permanente(codigo)` separa as classes:

| Resposta | Tratamento |
|---|---|
| `2xx` | entregue |
| `3xx` | **permanente** — o cliente HTTP não segue redirecionamento (decisão anterior, para não entregar payload assinado a outro host); então 3xx é configuração errada |
| `4xx` exceto `408`/`429` | **permanente** — o destino recusou o pedido |
| `408`, `429`, `5xx`, erro de rede, timeout | transitório, backoff normal |

Falha permanente usa `_marcar_falha_definitiva`: conta a tentativa, fecha como `FALHOU`,
`proxima_tentativa=None` e cai no caminho de DLQ que já existia. O `ultimo_erro` diz "recusa permanente,
não retentada" — para o operador não procurar um problema de rede que não existe.

### Testes (`tests/test_webhook_falha_permanente.py`, 17)

Classificação paramétrica (400/401/403/404/410/422/301/302 → permanente; 408/429/500/502/503/504/2xx →
não), e a entrega real: `404` → **uma** tentativa, sem reagendamento, item na **DLQ**.

### Verificação

| Comando | Resultado |
|---|---|
| `pytest tests/test_webhook_falha_permanente.py` | **17 passed** |
| `pytest tests/test_webhooks.py` | **24 passed** |
| `mypy app src` | zero erros |

---

## 88. Revisão de continuidade do PR #1 — o que foi conferido, não repetido

**Data:** 2026-11-27. **Escopo:** revisar a branch e o PR com evidência do repositório, sem refazer a
auditoria e sem merge.

### Estado conferido por comando

| Item | Comando | Resultado |
|---|---|---|
| Branch / HEAD | `git status -sb`, `git rev-parse --short HEAD` | `work/auditoria-e-fase-a`, `4e7366d`, working tree limpo |
| Base | `git rev-parse --short main` | `55351cb` |
| Divergência | `git log --oneline main..HEAD \| wc -l` | **47 commits** |
| Volume | `git diff --stat main..HEAD` | **126 arquivos**, +25.215 / −198 |
| PR | `gh pr view 1` | `OPEN`, `MERGEABLE`, `CLEAN`, head `4e7366d` |
| CI | `gh run list --branch ...` | `success` em `4e7366d` |

Distribuição do diff: `app/` 42 · `tests/` 30 · `sources/` 17 · `docs/` 13 · `scripts/` 9 ·
`alembic/` 4 · `.github/` 1.

### Gates reexecutados nesta revisão (serial, banco compartilhado)

`python -m scripts.check_ci --tudo` → **10/10** + suíte: lint, formatação, tipagem, segredos,
dependências, contrato OpenAPI, integridade dos XSD (113 conferem), schema da DPS, migrações reproduzem
os modelos, suíte completa. `pytest --co` → **1565 testes coletados**. `ruff format --check .` → 378
arquivos formatados.

Não remedi cobertura nesta rodada: o número anterior (**87,98%**) é de execução isolada registrada em
§61/§83 e **não** é reivindicado como recém-medido aqui.

### `xfail(strict=True)` — dois casos, ambos de divergência medida

| Teste | O que fixa | Por que não esconde regressão |
|---|---|---|
| `test_xsd_acompanha_o_leiaute_declarado` | falha se o leiaute declarado for NT-009 e o XSD do repositório não tiver `finNFSe`/`vAjusteBC` | `strict=True`: se passar a passar, a suíte **quebra** e exige revisão |
| `test_gerador_e_aceito_pelo_xsd_oficial` | valida a DPS gerada contra o pacote oficial extraído do ZIP versionado | falha hoje por `finNFSe` (o fixture do repo é adaptado, §82); quando o leiaute for alinhado, quebra de propósito |

Nenhum dos dois usa `xfail` sem `strict`, e nenhum foi adicionado para "fazer a suíte passar" — ambos
**descrevem** a divergência com o schema oficial.

### Testes não alcançam produção

| Controle | Evidência |
|---|---|
| Ambiente fixo de teste | `tests/conftest.py:24` → `ENVIRONMENT=test` |
| Adaptador dublê obrigatório | `tests/conftest.py:30` → `NFSE_ADAPTER=mock` |
| Banco de teste próprio | `tests/conftest.py:31` → `DATABASE_URL = suporte.url_teste()` |
| Allowlist de host no cliente real | `app/nfse/adapter.py:243` + `app/core/config.py:86` (`sefin_permitir_host_nao_oficial=False` por padrão) |
| `tp_amb=1` (produção) em teste | **nenhuma** instrução; texto antigo corrigido nesta rodada (§REQ-1) |

### Isolamento entre tenants — amostra de testes presentes

`test_certificado_usos.py` (histórico de uso), `test_chave_expira_revoga.py`, `test_cancelamento.py`,
`test_apuracao.py`, `test_credenciais_rota.py`, `test_circuit.py` — todos com caso de "outro tenant" ou
"tenant cruzado". O contrato de tenant-vindo-da-credencial está em `test_contrato_tenant.py`.

### Manifesto e matriz: existem e conferem

`sources/manifest.yaml` — **15 fontes**, todas com `sha256` verificado por script (`ok=15 diverge=0
ausente=0`), sem caminho absoluto de disco. `docs/REQUISITOS-FONTES.md` — matriz com estados
`PASS/PARTIAL/NOT_TESTED/BLOCKED` e a citação do que cada fonte diz.

### Correções documentais desta revisão

1. `tp_amb=1` → `tp_amb=2` na instrução de não-regressão (produção não recebe teste);
2. **REQ-2**: `PARTIAL` → **`BLOCKED` para a regra**, com o cronograma oficial: Operações Condominiais
   são o item 2.15 da **Release 3** (Produção Restrita prevista 07/12/2026);
3. **REQ-4**: passa a **`PARTIAL`** (fluxo confirmado no FAQ v1.5) mantendo **`BLOCKED`** para a API de
   consulta de vigência/revogação; `00233` registrado como **não citado** na fonte consultada;
4. **REQ-3**: `BLOCKED` como regra executável, com a ressalva oficial de que não há regras de negócio
   baseadas no Anexo VIII;
5. ADR 0005 atualizado: o bloqueio permanece, mas o **fundamento mudou** — a representação existe e está
   em produção desde 31/10/2026; falta a forma de verificar o vínculo e o grupo de XML (Release 3).

### O que esta revisão **não** fez

Não fez merge, não alterou `main`, não enviou mensagem externa, não reivindicou homologação nem produção.
A decisão de merge continua com o mantenedor.

---

## 89. Adoção do XSD oficial de 24/11/2026 — o gap de §82 foi fechado

**Data:** 2026-11-27. **Fase:** C/F. Executa a recomendação de §88 e fecha o maior risco técnico aberto.

### O que foi feito

1. Fixtures de `tests/fixtures/schemas/nfse-1.01/` **substituídos** pelos arquivos do pacote oficial
   `esquemas-xsd-producao-restrita-20261124.zip` (sha256 `1ca83c1a7929f6d5…`), extraído de
   `sources/oficiais`.
2. `data/xsd_manifest.json` regenerado: **115 schemas** conferem.
3. Gerador corrigido em `app/nfse/dps.py`:
   - `indDest` passou a ser emitido em **`infDPS`**, depois de `toma` e antes de `dest`/`serv`, com o
     domínio oficial (`0` = destinatário é o tomador; `1` = difere);
   - `indDest` e `dest` **removidos de dentro do grupo `IBSCBS`** — ali o schema oficial recusa o
     elemento e invalida a DPS inteira (`TCRTCInfoIBSCBS` não tem esses campos).
4. Duas guardas `xfail(strict=True)` substituídas por **três testes positivos**:
   - fixtures **byte a byte** iguais ao pacote oficial (compara SHA-256 arquivo por arquivo);
   - XSD declara `finNFSe`, `vAjusteBC`, `indDest`;
   - `indDest` existe uma vez em `infDPS` e **não** dentro de `IBSCBS`.

### Causa raiz do que §82 media

O fixture antigo era uma cópia **adaptada**: aceitava `finNFSe` e `indDest` em posições que o schema
publicado não aceita. A suíte provava conformidade com o schema modificado. Com o pacote oficial, o
gerador foi obrigado a se ajustar de verdade — e ajustou-se.

### Erro meu encontrado nesta rodada

A guarda 1 de §80 falhava por **typo na constante**: `MARCADORES_NT009` tinha `finNFse` (minúsculo) em vez
de `finNFSe`, então a busca nunca casava. O teste parecia "detectar o gap" quando na verdade detectava
minha própria digitação. Corrigido ao reescrever o arquivo; a comparação agora é por hash, não por regex.

### Verificação desta rodada

| Comando | Resultado |
|---|---|
| `pytest tests/test_schema_dps.py` | **5 passed** (antes: 3 falhando contra o oficial) |
| `pytest tests/test_eventos_tipos.py`, `test_evento_cancelamento.py` | **69 passed** |
| `pytest tests/test_leiaute_nt009_guard.py` | **3 passed** (sem `xfail`) |
| `gerar_manifesto_xsd --apply` → `--check` | **115 conferem** |
| `check_ci` (rápido) | **9/9** |
| `check_ci --tudo` (rodada anterior à correção de lint) | 10 de 11; lint quebrado por `×` em comentário — corrigido |

### O que continua fora

Adotar o schema **não** implementa os grupos de condomínio: `condominios`, `gCobranca`, `gDetCobranca` e
`unidades` existem no XSD, mas as **regras de negócio do item 2.15 só entram na Release 3** (Produção
Restrita prevista 07/12/2026, conforme comunicado oficial). O estado de REQ-2 permanece **BLOCKED** para a
regra.

`indDest` derivado automaticamente só no caso modelado (destinatário = tomador, ou `dest` informado). Não
há regra oficial publicada que exija `1` em outros cenários, e não foi inventada.

### Corrigido — CI quebrada por normalização de fim de linha nos XSD

O commit que adotou o pacote oficial passou no gate local e **falhou no CI**: 10 schemas apareceram como
"alterado" sem ninguém tocar neles.

Causa: `.gitattributes` já tinha `tests/fixtures/schemas/** text eol=lf`, e os pacotes oficiais publicam os
`.xsd` com **CRLF**. O manifesto era gerado no Windows sobre os bytes publicados (CRLF) e o checkout do CI
(Linux) entregava LF — hash diferente, mesmo conteúdo.

Correção: `*.xsd -text` e `data/xsd_manifest.json -text`, com o motivo escrito no próprio arquivo. A
regra antiga foi removida. Verificado: hash do arquivo no worktree (`fe45e525…`) igual ao registrado no
manifesto, e `--check` → **115 conferem**. O byte do repositório passa a ser o byte publicado, que é o que
a integridade deve comparar.

### 89.1 Dois leiautes — um valida, o outro é defeituoso no artefato publicado

O Adendo 3 exige validação nos **dois leiautes** para `PASS` em REQ-1. Executei com os dois pacotes
oficiais versionados e o resultado separou responsabilidades:

| Pacote | `TSSerieDPS` | Consequência |
|---|---|---|
| 24/11/2026 (NT 009) | `[0-9]{1,4}\|[0-8][0-9]{4}` | valida (DPS gerada aceita) |
| 09/02/2026 (anterior) | `^0{0,4}\d{1,5}$` | **rejeita qualquer `serie`** |

Causa: no dialeto de regex do **XML Schema**, `^` e `$` **não são âncoras** — são caracteres literais. Um
`xs:pattern` com `^...$` só casaria com valor que contivesse literalmente esses caracteres. Portanto
**nenhum** valor de `serie` (nem `1`, nem `00001`) passa no pacote de fevereiro, e não existe ajuste no
gerador que satisfaça um schema assim.

Prova em `tests/test_dps_dois_leiautes.py::test_pacote_anterior_rejeita_qualquer_serie`: tenta quatro
valores de `serie` e exige que **zero** sejam aceitos. O teste falha se o pacote for corrigido — momento em
que a validação do leiaute anterior deve ser reativada.

**Consequência para REQ-1**: continua **PARTIAL**, não `PASS`. O que existe: pacote preservado com hash,
fixtures byte-idênticas, leiaute NT 009 validado de ponta a ponta, regra de `indDest` documentada e testada,
não-regressão coberta. O que falta: validação do leiaute anterior, **impossível com o artefato publicado**
— bloqueio do órgão, não do projeto.

---

## Fecho da revisão — 27/11/2026, HEAD `1bd80a3`

Estado final desta continuação, com o que foi **executado** (não herdado):

| Item | Valor |
|---|---|
| Branch / HEAD | `work/auditoria-e-fase-a` / `1bd80a3` |
| Base | `main` = `55351cb` (intocada) |
| Commits à frente | **52** |
| Diff | **144 arquivos**, +40.528 / −6.075 |
| PR #1 | `OPEN`, `MERGEABLE` |
| CI | `success` em `1bd80a3` |
| Testes coletados | **1571** |
| Gate | 10/10 + suíte |
| Manifesto de fontes | **15**, todos os hashes conferem |
| Manifesto de XSD | **115** conferem (agora com bytes preservados) |

### O que mudou desde o relatório de §88

1. **XSD oficial adotado** (pacote de 24/11/2026): fixtures byte-idênticas ao publicado, manifesto
   regenerado, gerador corrigido (`indDest` em `infDPS`, fora de `IBSCBS`).
2. **Duas `xfail(strict)` extintas** — viraram três testes positivos, incluindo comparação por hash.
3. **Defeito do pacote anterior provado**: `^`/`$` literais no dialeto XSD impedem validar `serie` no
   leiaute de fevereiro; teste fixa isso e falha se o órgão corrigir.
4. **CI consertada duas vezes**: normalização CRLF→LF (`-text` em `*.xsd`) e regravação dos blobs com os
   bytes publicados.
5. **Erro meu corrigido**: `finNFse` em vez de `finNFSe` na constante de marcadores — a guarda de §80
   detectava minha digitação, não o gap.

### Matriz final

| REQ | Estado | Evidência |
|---|---|---|
| REQ-1 XSD NT-009 + `indDest` | **PARTIAL** | pacote + hash + fixtures idênticas + NT009 validado + regra de `indDest` testada; falta validar o leiaute anterior (artefato defeituoso) |
| REQ-2 condomínios | **BLOCKED** | grupos no XSD, regras só na Release 3 (07/12/2026) |
| REQ-3 Anexo VIII | **BLOCKED** | documento obtido; fonte diz que não há regras de negócio nele |
| REQ-4 procuração | **PARTIAL** / **BLOCKED** | fluxo confirmado no FAQ v1.5; sem API de vigência/revogação; `00233` não citado |
| REQ-5 multitenant | **PARTIAL** | isolamento testado; falta `procurador` e vínculo certificado↔estabelecimento |

### Riscos que permanecem

1. Leiaute anterior não validável com o pacote publicado (defeito do artefato).
2. Condomínios, Anexo VIII e representação em XML dependem de publicação oficial futura.
3. Autorização NF-e/CT-e/MDF-e e NFC-e dependem de credenciamento/CSC do contribuinte.
4. Produção fiscal: **zero notas**. Homologação: uma NFS-e autorizada documentada (§15).

---

## 90. Cobertura de todos os estados e municípios — o que é testável e o que não é

**Data:** 2026-11-28. **Pedido:** validar em todos os estados e municípios, mantendo o gate 10/10.

### O que foi testado (determinístico, sem rede)

`tests/test_ufs_e_municipios.py` — **39 testes** sobre os dados versionados:

| Verificação | Escopo |
|---|---|
| código IBGE com 7 dígitos | **5.571 municípios** |
| prefixo do código coerente com a UF declarada | **5.571** |
| código único e nome não vazio | **5.571** |
| as **27 UFs** presentes, cada uma com município | 27 |
| catálogo SEFAZ só com UF existente | **180 endpoints** |
| endpoints sempre `https://` | 180 |
| modelos conhecidos (55 NF-e, 57 CT-e, 58 MDF-e, 65 NFC-e, 67 CT-e OS) | 180 |
| sem chave (UF, modelo, ambiente, serviço) duplicada | 180 |
| UF fora do catálogo é 503 documentado, não URL inventada | 27 parametrizados |

**Erro meu encontrado pelo próprio teste:** a primeira versão listava modelos `55/57/58` e falhou ao
achar `65` (NFC-e). O dado estava certo; a expectativa, errada. Corrigi a expectativa e registrei para
ninguém "consertar" o catálogo depois.

### O que NÃO foi testado, e por quê

1. **Emissão real por UF**: depende de autorizador e credenciamento do contribuinte. O catálogo
   versionado tem **10 UFs** de NF-e (AM, BA, GO, MG, MS, MT, PE, PR, RS, SP); as demais usam
   autorizador virtual. Não existe teste honesto de transmissão para UF sem endpoint e sem credencial.
2. **Prefeitura por município**: na NFS-e nacional o município entra como código IBGE; a emissão vai ao
   ambiente nacional, não a 5.571 webservices. Testar "todos os municípios" como transmissão seria
   fabricar uma arquitetura que o padrão não tem.
3. **Credencial municipal** (`exige_credencial_municipal`): o campo existe e é validado no schema; não
   há credencial das 5.571 prefeituras para exercitar o caminho real.

### Gate

`scripts.check_ci` continua **10/10** — os testes novos não tocam rede, banco nem relógio.

---

## 91. Fatia 2 de cobertura — quatro módulos em 100%

**Data:** 2026-11-28. `tests/test_rotas_cnpj_auditoria.py` (16) + `tests/test_worker_lote.py` (5).

| Módulo | Antes | Depois | O que passou a ser provado |
|---|---|---|---|
| `app/api/v1/auditoria.py` | 59% | **100%** | 404 (não 403) para laudo de outro tenant; serialização com `data_emissao` nula; lista vazia; integridade verdadeira, falsa e ausente |
| `app/api/v1/cnpj.py` | 47% | **100%** | cadeia de fontes com/sem token Serpro e com fallback ligado/desligado; 422 × 404 × 503 com `transitorio: true` |
| `app/core/logging.py` | 36% | **100%** | redação dos 13 campos sensíveis, estruturas, bytes; JSON válido; logger raiz idempotente |
| `app/worker/healthcheck.py` | 0% | **100%** | 3 saídas de `verificar()` + entrypoint executado como **subprocesso** (`python -m`) |
| `app/worker/main.py` | 40% | **100%** | lote inexistente, tenant inexistente, lote válido, relatório nulo; `ping`, `heartbeat` com TTL, `entregar_webhooks` commitando |

### Duas decisões que valem registro

1. **`# pragma: no cover` em um único ponto** (`healthcheck.py`, guarda `__main__`): cobertura não mede
   subprocesso, e o teste que prova a linha é o que executa o comando do Docker (`returncode == 1` com
   Redis inacessível). O comentário no código aponta o teste — sem isso, a exclusão seria fé cega.
2. **Nenhum teste novo toca rede ou banco**: dublês de sessão, de Redis e de serviço. O teste de
   subprocesso usa `REDIS_URL` apontando para porta fechada, de propósito.

### Erro meu encontrado no caminho

O primeiro `test_worker_lote.py` montava o dicionário de modelos **antes** do `monkeypatch` e comparava
com `ops.BatchJob` **depois** — a comparação dava sempre falso e o dublê devolvia `None`, fazendo os
três testes falharem com "lote não encontrado". Corrigido capturando a classe real antes do patch e
documentado no próprio helper.

---

## 92. Fatia 3 de cobertura — rotas de certificado e de status de transporte em 100%

**Data:** 2026-11-28. `tests/test_rota_certificados.py` (18) + `tests/test_rota_transportes_status.py` (10).

| Módulo | Antes | Depois | Contratos provados |
|---|---|---|---|
| `app/api/v1/certificados.py` | 65% | **100%** | vazio→422, grande→413, duplicado→409, PFX ilegível→422 (todos com rollback), sucesso commita e devolve metadados sem PFX; saúde com três avisos distintos (sem certificado, expirado, expira em N dias); ativar/remover 404; uso de outro tenant 404 e histórico sem mensagem de erro |
| `app/api/v1/transportes_status.py` | 75% | **100%** | 503 sem endpoint para a UF, 422 sem A1 ativo, 504 autorizador inacessível, 504 recusa definitiva com motivo; CT-e e MDF-e; circuito recebe **UF em maiúsculas**; `_cuf` para as **27 UFs** e 422 para UF desconhecida |

### Detalhe que vale registro

`_cuf` **reusa** a tabela UF→código da NF-e de propósito (comentário no código). O teste percorre as 27
UFs e exige 27 códigos distintos — se a tabela da NF-e mudar, quebra aqui e não na emissão.

### Nota sobre o certificado real

Os testes de rota usam dublê do cofre: nenhum PFX entra na suíte. O certificado verdadeiro foi exercitado
em prova local separada (§90): assinatura de DPS + validação no XSD oficial de 24/11/2026, sem transmissão.

---

## 93. Fatia 4 — lote e apuração em 100%

**Data:** 2026-11-28. `tests/test_batches_service.py` (12) + `tests/test_assessment_service.py` (25).

| Módulo | Antes | Depois | Regras provadas |
|---|---|---|---|
| `app/batches/service.py` | 43% | **100%** | linha inválida não interrompe o lote; relatório gravado mesmo com tudo falhando; `PARCIAL` × `CONCLUIDO`; chave já autorizada vira `ja_existia` **sem reemitir**; erro de linha faz rollback e registra; nome de arquivo truncado em 255 |
| `app/assessment/service.py` | 53% | **100%** | competência `AAAA-MM` com faixa (2000–2100, mês 1–12); só documento **autorizado** entra; ISS por alíquota do município e base com desconto; aviso quando falta alíquota; erro de cálculo vira aviso e não derruba a apuração; apuração existente é atualizada, não duplicada; guia marca `FALHOU` quando o provedor recusa |

### Detalhe que o teste fixou

`flag_modified` no relatório JSONB: o teste usa **instância real** de `BatchJob`, não `SimpleNamespace` — com dublê simples o SQLAlchemy levanta `AttributeError` e o teste passaria a medir a si mesmo, não o código. Foi exatamente o que aconteceu na primeira tentativa e está registrado no helper.

---

## 94. Fatia 5 — cancelamento e eventos em 100%

**Data:** 2026-11-28. `tests/test_cancelamento_service.py` (17) + `tests/test_eventos_service.py` (16).

| Módulo | Antes | Depois | Guardas provadas |
|---|---|---|---|
| `app/nfse/cancelamento.py` | 45% | **100%** | já cancelada; sem documento com chave; motivo fora da tabela/curto; sem A1 ativo; A1 sem CNPJ; sucesso marca `CANCELADA` e registra evento; falha da SEFIN **não** cancela e preserva a tentativa; erro de montagem vira `MotivoInvalido`; sem adapter monta cliente real e **fecha** no `finally` |
| `app/nfse/eventos.py` | 53% | **100%** | cancelamento é recusado (rota própria); tipo de ofício recusado sem permissão e aceito com ela; tipo inexistente; sem documento, sem certificado, certificado sem CNPJ; erro de payload **sobe** (422) em vez de virar 409; sequência = max+1; falha preserva trilha; sem adapter monta e fecha cliente |

### Dois erros meus, pegos pelos testes

1. **Recuo**: appendei dois métodos ao fim do arquivo e eles ficaram **dentro** de `async def _async`. A suíte não os executou — cobertura travou em 93% e eu quase tratei como limite do código. Corrigido movendo para a classe.
2. **Dublê no nível errado**: `SessaoFila` recebia o documento em vez do **resultado** da consulta (`ResultadoFalso`), e o teste falhava com `AttributeError: 'SimpleNamespace' has no attribute 'scalars'`. Era o teste errado, não o código.

### Números do espelho

`cancelamento` 73 statements, `eventos` 75 — **ambos 0 faltantes**.

---

## 95. Fatia 6 — DPS em 100% e auditor de assinatura em 88%, com achado aberto

**Data:** 2026-11-28. `tests/test_dps_validacao.py` (33) + `tests/test_auditor_assinatura.py` (13).

| Módulo | Antes | Depois | O que ficou provado |
|---|---|---|---|
| `app/nfse/dps.py` | 91% | **100%** (300 statements) | todas as recusas: documento ausente/inválido, `cLocEmi`, série, `nDPS`, `dhEmi` sem fuso, valor zero, descrição vazia/longa, `cTribNac`/`cTribMun`, `opSimpNac`, `regEspTrib`, Simples sem `regApTribSN`, `tribISSQN`, `tpRetISSQN`, tomador sem nome, endereço (município/UF/CEP), IBS/CBS (`cIndOp`/`cClassTrib`/NBS/`indDest`); ramos de CPF do tomador e do prestador, `pAliq`, `pTotTribSN`, `indTotTrib` do MEI, leiaute anterior com `finNFSe` no grupo, descontos e `extrair_id` (válido, XML quebrado, sem `infDPS`) |
| `src/notasbr/regras/assinatura.py` | 73% | **88%** | ASSIN-001 (sem Signature e namespace errado), ASSIN-002 (sem Reference, sem URI, URI divergente), ASSIN-003 (vazio, base64 inválido, tamanho atípico), ASSIN-005, e o ramo criptográfico avaliando documento assinado pelo próprio gerador |

### Achado aberto (não é "pronto")

O `signxml` **recusa** a assinatura produzida pelo nosso `app.nfse.signer` sobre a NF-e sintética:
`ASSIN-004` sai como erro. Não sei ainda se a causa é (a) o gerador, (b) a estrutura artificial usada
no teste (Signature referenciando `NFe`, com `infNFe` dentro) ou (c) o `signxml` exigindo
`expect_references` diferente. O teste ficou **declarando a divergência**, não a aprovando, e falha se
ela desaparecer sem investigação. Linhas 82-83, 145-150, 160 e 169-182 seguem descobertas por causa
disso: cobri-las exigiria afirmar que a assinatura confere, e ela não confere.

### Erros meus nesta fatia

1. Supus que `cLocEmi` não era validado — é. Depois supus de novo que `cTribMun` aceitava qualquer
   coisa — só aceita dígitos. Os dois testes foram reescritos.
2. A NF-e de fixture **já traz** uma `Signature` stub; assinei ao lado dela e o auditor leu a primeira,
   caindo em "sem X509Certificate". Passei a remover as assinaturas antes de assinar.
3. `_primeiro_com_id` só olha filhos **diretos** da raiz: `Id` em `infNFe` nunca seria encontrado.

---

## 96. ASSIN-004 fechado — e dois bugs reais no auditor de assinatura

**Data:** 2026-11-28. Continuação de §95.

### O achado de §95 era do meu fixture, não do gerador

Experimento isolado, com o mesmo caminho de assinatura da emissão:

| Documento | `lxml.tostring` | `xml.etree.tostring` |
|---|---|---|
| DPS assinada | **verifica** | — |
| NF-e sintética | **verifica** | **não verifica** |

Causa: `ET.tostring` reescreve prefixos de namespace (`ns0:`) e o digest C14N deixa de casar. O gerador
sempre esteve correto. Registrado como aviso de produto: **auditar bytes re-serializados gera falso
negativo** — o auditor precisa dos bytes originais.

### Mas o mesmo defeito existia no código, e foi corrigido

`src/notasbr/regras/assinatura.py` fazia `etree.fromstring(ET.tostring(ctx.raiz))` — o mesmo round-trip,
dentro do auditor. Resultado: **toda** assinatura válida era reportada como inválida. Correção: o
`Contexto` passou a carregar `bytes_originais`, preenchido em `auditar_bytes`, e a verificação parseia
esses bytes.

### Dois falsos negativos adicionais corrigidos

| Problema | Consequência antes | Correção |
|---|---|---|
| `X509Certificate` com quebras de linha + `b64decode(validate=True)` | erro "certificado não pôde ser lido" em qualquer documento formatado | remover espaços antes de decodificar |
| `ASSIN-003` aplicava tamanhos de **digest** (20/32/48/64) também ao `SignatureValue` | aviso de "tamanho atípico" em **toda** assinatura RSA-2048 (256 bytes) | `SignatureValue` passa a esperar 128/256/384/512 |

### Efeito colateral tratado no fixture, não afrouxando teste

A `Signature` stub de `tests/construir.py` usava 20 bytes no `SignatureValue`. Com a regra correta, isso
virou aviso — como deve ser, porque 20 bytes não é assinatura RSA possível. Em vez de mudar a expectativa
do teste antigo (`test_unico_aviso_e_a_ausencia_de_certificado`), dei ao stub um `SignatureValue` de 256
bytes, mantendo o `DigestValue` de 20 (SHA-1). O teste antigo continua valendo sem alteração.

### Números

`src/notasbr/regras/assinatura.py`: **73% → 94%** (108 statements, 6 faltantes: ramo de namespace
divergente, leitura de certificado inválido e o `info` final, que exigem cenários mais exóticos).

---

## 97. Fatia 7 — rotas de frete em 100%

**Data:** 2026-11-28. `tests/test_rota_fretes.py` (20).

| Módulo | Antes | Depois | Contratos provados |
|---|---|---|---|
| `app/api/v1/fretes.py` | 53% | **100%** | 503 sem configuração; 400 para `error` do lojista, `code`/`state` ausentes e `state` inválido; 502 quando o Melhor Envio recusa o código ou a cotação; 409 sem autorização; 422 sem CEP; sucesso do callback salva e commita; status com e sem refresh (vencido mas renovável × não); revogação com observação; `_cep_da_config` nos três casos (sem config, com `extra.cep`, sem `extra`); cotação com mais barata/mais rápida marcadas |

Nenhuma chamada de rede: o serviço de frete é dublado.

### Erro meu nesta fatia

Usei `servico_id="1"` (string) no dublê; o schema `OpcaoOut` declara **int**, converte o valor, e a
comparação `1 == "1"` dava falso — `mais_barata` virava `None` e o teste acusava o código. O dublê
estava errado, não a rota. Corrigido para `int` e registrado aqui.

---

## 98. Fatia 8 — adaptador SEFIN de 81% para 90%, com as operações mapeadas

**Data:** 2026-11-28. `tests/test_adapter_descodificacao.py` (32).

Medido **sob a suíte completa** (`--cov=app.nfse.adapter`): **81% → 90%**
(299 statements, 29 faltantes: `_chamar` com timeout, `consultar_dps`/`dps_existe`/`registrar_evento`
recusando, `consultar_evento`, `_lote_adn` em erro, e trechos do dublê).

| Área | O que passou a ser provado |
|---|---|
| `_get` | não-dict, busca ignorando caixa, ausente |
| `_decodificar_xml` | vazio, não-string, gzip/base64 válido e conteúdo que **não** é gzip (vira texto, não explode) |
| propriedades | `__repr__`, `tpAmb` 1/2 por ambiente, leiaute acompanha o ambiente |
| `aliquota_municipal` | 401/5xx → erro; 200 com `aliquota` e com `valor`; **404 → não encontrado**; 400 → indeterminado; status inesperado → indeterminado com `HTTP n` |
| dublê | falha proposital de emissão, NFS-e inexistente, context manager, eventos vazios |
| operações | `consultar_dps` (404/200/500), `dps_existe` (usa HEAD, 200/404), `consultar_nfse` recusa, `registrar_evento` recusa, `consultar_evento` **404 → None** e 500 → erro, `distribuicao_dfe` |

### Erro meu nesta fatia

Supus que `consultar_evento` levantasse em 404. A assinatura é `bytes | None` e o código devolve `None`
— evento inexistente não é falha de transporte. Corrigi o teste, não o código.

### Por que "404 do ADN" importa

`aliquota_municipal` documenta que o caminho de parametrização **não existe** (probe de 25/11/2026 com
A1 real: 404 do IIS). Os testes fixam a diferença entre "não encontrado" (404), "não sei" (400/outros) e
"recusado" (401/5xx): confundir os três faz o sistema zerar alíquota em silêncio.

---

## 99. Fatia 9 — serviço de emissão de 83% para 90%

**Data:** 2026-11-28. `tests/test_nfse_servico_ramos.py` (14). Medido **sob a suíte completa**:
`app/nfse/servico.py` **83% → 90%** (162 statements, 16 faltantes).

| Regra | O que passou a ser provado |
|---|---|
| Configuração ausente | recusa citando `PUT /v1/me/config-fiscal` |
| Configuração **ambígua** | tenant com dois municípios recusa e **lista os dois**, exigindo `municipio_ibge` — a nota não escolhe município |
| IBS/CBS | vazio → `None`; **incompleto** → recusa dizendo o que falta ("todos ou nenhum"); completo → `Ibscbs` com `ind_final` padrão |
| `_montar_entrada` | sem `cTribNac` recusa; sem CNPJ de prestador recusa; configuração válida monta `DpsInput` com município, valor e documento |
| Recuperação após timeout | sem chave → `None`; chave sem NFS-e → `None`; chave com NFS-e → resposta recuperada |
| Alíquota | `None` continua `None`; fração vira percentual |

### Erro meu nesta fatia

`_montar_entrada` é **keyword-only** e recebe `numero_dps`; chamei posicionalmente e depois com config
incompleta (`optante_mei` ausente). Dois ajustes no dublê, nenhum no código.

### O que falta (16 linhas)

`155-156` (falha ao enfileirar webhook), `252/257` (desconto ≥ valor), `348-357/359` (rota não
confirmada e bloqueio), `387-392` (erro de DPS/assinatura marcando `ERRO`), `415-416` (timeout
ambíguo recuperado), `425`. São exatamente os caminhos de `emitir`, que exigem sessão e certificado
montados — ficam para a fatia de `emissoes`.

---

## 100. Cobertura de 87,98% era subnotificação — a real é 95%

**Data:** 2026-11-28. Descoberta ao revisar a entrega da fatia de `emissoes`.

### O defeito estava na medição, não no código

`pyproject.toml` não declarava `concurrency` no coverage. SQLAlchemy async retoma a execução em
**greenlet** depois de cada `await`; sem essa declaração o coverage perde os frames seguintes. Efeito
medido:

| Configuração | Total | Descobertos |
|---|---|---|
| sem `concurrency` | 87,98% | **1.306** |
| `concurrency = ["greenlet", "thread"]` | **95%** | **547** |

Ou seja: **759 linhas** que os testes já executavam eram contadas como descobertas. Todos os números de
cobertura anteriores nesta auditoria estavam pessimistas. Correção: uma linha no `pyproject.toml`, com o
motivo escrito ao lado. Piso elevado de 80 para **90** (o medido é 95).

Distribuição atual: **83 de 176 arquivos em 100%**; 21 abaixo de 90%; o pior arquivo tem 22 linhas
descobertas (`app/nfse/errors.py`, 85%).

### Fatia 10 — `emissoes.py` e `servico.py`

`tests/test_emissoes_ramos.py` (82 testes). Medido com o arquivo novo sozinho: `emissoes.py` **47% →
100%**, `servico.py` 90% → 91% (o resto vem da interação com a suíte). Cobre: DANFSe (PDF real, 404, sem
XML), representação (formatos, 404, 422), catálogos, cancelamento (404/409/422/502/sucesso), registro de
evento e seus erros, listagem, consulta, ramos de emissão e o timeout ambíguo recuperado.

### Achados relatados na entrega que **não reproduzi** — precisam de triagem

| # | Achado | Situação |
|---|---|---|
| 1 | Coverage sem `greenlet` subnotifica | **verificado por mim** (medido) |
| 2 | Reenvio de fatura **não autorizada** responde **201** em vez de 200 | relatado, não reproduzido |
| 3 | Timeout ambíguo **sem** nota deixa fatura em `PROCESSANDO`, sem evento de erro | relatado, não reproduzido |
| 4 | 502 da SEFIN chega ao cliente como `repr` de dict, não JSON estruturado | relatado, não reproduzido |
| 5 | Chave no body e depois no header gera **409 falso** (payload compara `idempotency_key`) | relatado, não reproduzido |

Os itens 2 a 5 são contratos de API e comportamento fiscal; **não** foram corrigidos nesta fatia —
corrigir sem reproduzir seria trocar um defeito por outro. Próxima fatia começa por reproduzi-los.

---

## 101. Dois defeitos de contrato confirmados e corrigidos na emissão

**Data:** 2026-11-28. Reprodução dos achados 2 e 5 de §100 — os dois **confirmados no código**, não
apenas relatados.

### 1. `Idempotency-Key` no body e depois no header gerava 409 falso

**Causa:** `payload=dados.model_dump(mode="json")` guardava o body inteiro, incluindo
`idempotency_key`. `_recusar_payload_divergente` comparava esse dump com o do novo pedido. Como a
chave pode viajar pelo header **ou** pelo body (dois contratos válidos, o header vence), o mesmo
pedido enviado uma vez de cada forma parecia "corpo diferente" e era recusado com 409.

**Correção:** helper `_payload_comparavel` remove `idempotency_key` dos **dois** lados da comparação;
o payload gravado também passa a ser o comparável.

**Prova:** `test_chave_no_body_e_depois_no_header_nao_e_conflito` (201 na primeira, **200** na
segunda) e `test_corpo_realmente_diferente_continua_409` — a correção não cegou a comparação: valor
diferente continua 409.

### 2. Reenvio de fatura **não autorizada** respondia 201

**Causa:** só o ramo autorizado devolvia `JSONResponse(200)` explícito. O ramo "existe mas não está
autorizada" devolvia o modelo e herdava `status_code=201` da rota — anunciando "criado" para algo que
já existia. O comentário do próprio código dizia "devolve o estado atual".

**Correção:** os dois ramos de estado atual (não autorizada e perdedor da corrida de
`IntegrityError`) devolvem `JSONResponse(200)`.

**Efeito nos testes:** dois testes da suíte afirmavam **201** — ou seja, fixavam o defeito. Foram
atualizados para 200, com o motivo escrito no próprio teste. Isso é mudança de expectativa por
correção de comportamento, não para deixar a suíte verde: o teste que falhava era o que exigia 200.

### Achados que continuam **não reproduzidos**

- **3**: timeout ambíguo sem nota deixaria a fatura em `PROCESSANDO`, sem evento de erro.
- **4**: o 502 da SEFIN chegaria ao cliente como `repr` de dict em vez de JSON estruturado.

Seguem sem correção até serem reproduzidos; não vou alterar caminho fiscal por relato de terceiro.

---

## 102. Achados 3 e 4 reproduzidos e corrigidos

**Data:** 2026-11-28. Diferente dos achados de §101 (que li no código), estes dois foram confirmados
com teste que falhava.

### 3. Timeout ambíguo sem nota deixava a fatura sem explicação

**Confirmado:** `if recuperada is None: raise` — o caminho não passava por `_registrar_falha` nem por
`_registrar_evento`. A fatura ficava em `PROCESSANDO` (estado correto, porque a nota **pode** ter sido
gerada) e **sem nenhum evento** — o operador via fatura parada sem motivo.

**Correção:** grava evento `timeout_ambiguo` antes do `raise`. O status continua `PROCESSANDO` de
propósito: marcar `ERRO` seria afirmar que não houve emissão quando não se sabe.

**Teste:** o caso que retratava o defeito passou a **exigir** o evento.

### 4. `detail` de erro da SEFIN chegava como repr de dict

**Confirmado:** `texto = detalhe if isinstance(detalhe, str) else str(detalhe)`. Um `detail` dict
virava `"{'tipo': 'indisponivel', ...}"` — o dado estava lá, mas não parseável por campo.

**Correção:** `detail` dict agora:
- usa `mensagem`/`detail`/`motivo` como texto, quando existem;
- sem eles, monta `chave=valor` legível (nunca `str(dict)`);
- os campos do dict sobem como **extras de primeiro nível** do problem+json (`tipo`, `http_status`, …).

**Testes:** três casos (dict sem mensagem, dict com mensagem, texto simples).

### Nota de processo

Os dois primeiros patches que escrevi **não funcionaram** e eu vi isso rodando: o primeiro caía no
`str(dict)` do fallback e o segundo perdia os extras porque o `Problema` é reconstruído no retorno.
Só a terceira versão passou — e a verificação foi por execução, não por leitura.

---

## 103. Regras de totalização: 81% → 95%

**Data:** 2026-11-28. `tests/test_regras_totais.py` (18 testes).

| Regra | Casos provados |
|---|---|
| `TOTAL-VPROD-001` | soma divergente → erro; item sem `vProd` → **aviso e erro ao mesmo tempo** (aviso pelo dado faltante, erro pela divergência); `vProd` total ausente → pulo; soma correta → sem achado |
| `TOTAL-VNF-001` | `vNF` zero e negativo → erro; ausente → não avalia |
| `TOTAL-PAG-001` | `vPag` divergente → erro; grupo `pag` ausente → pulo; sem `vPag` → pulo; formato antigo (`vPag` direto em `pag`, sem `detPag`) → aceito |
| `TOTAL-ITEM-001` | `qCom × vUnCom` divergente → aviso **e** informação de resumo; coerente → sem achado |
| `CTE-PREST-001` | `vTPrest` zero → erro; `vRec` maior que a prestação → aviso; soma de componentes divergente → aviso |

Medido: `src/notasbr/regras/totais.py` **81% → 95,5%** (5 linhas faltantes: 24, 110, 185-186, 208).

### Erros meus nesta fatia

1. Caminhos errados: os helpers de fixture navegam **desde a raiz**, então precisa ser
   `NFe/infNFe/...`, não `total/...`. Cinco testes falharam por isso.
2. Supus que item sem `vProd` gerasse **só** aviso. Gera aviso **e** erro — a soma fica menor que o
   total e as duas afirmações são verdadeiras. Corrigi a expectativa, não a regra.
3. Usei `com_campo` para `vTroco`, que **não existe** no fixture: troquei por um caso de formato
   antigo (`vPag` direto em `pag`), que é o que a regra realmente cobre.

---

## 104. Regras tributárias: 85% → 91%

**Data:** 2026-11-28. `tests/test_regras_tributos.py` (16 testes).

| Regra | Casos provados |
|---|---|
| `TRIB-CFOP-001` | 3 dígitos, grupo inicial inválido (9) e letra → **erro**; CFOP válido sem achado |
| `TRIB-CFOP-002` | `tpNF=9` → aviso; CFOP de entrada com operação de saída → **erro** |
| `TRIB-NCM-001` | ausente → aviso; 7 dígitos → aviso; válido sem achado |
| `TRIB-ICMS-001` | item sem grupo de ICMS → erro; grupo sem CST nem CSOSN → erro; CST fora da tabela → erro; CSOSN fora da tabela → erro |
| `TRIB-CRT-001` | CRT inválido (9) → erro; CRT ausente → pulo |
| `TRIB-PIS-COFINS-001` | item sem grupo PIS → aviso |

Medido: `src/notasbr/regras/tributos.py` **85% → 90,9%** (12 faltantes: 55, 61, 65, 88, 144, 157,
177-182, 223, 244, 252-253).

### Erro meu

Escrevi um teste para `CRT=1` com grupo CST esperando erro de incoerência de regime. **Não gera** — a
regra só acusa quando há CSOSN **e** CST no mesmo grupo (ou o inverso); CRT sozinho com CST não é
incoerência para ela. Removi o teste e registro aqui, porque a próxima pessoa pode fazer a mesma
leitura errada.

---

## 105. Erros fiscais: 85% → 100%

**Data:** 2026-11-28. `tests/test_nfse_errors.py` (31). Medido **sob a suíte completa**:
`app/nfse/errors.py` **85% → 100%** (151 statements, 0 faltantes).

| Função | Casos provados |
|---|---|
| `_resumir` | colapsa espaços; HTML vira rótulo (página do IIS não é mensagem); texto longo trunca com `…` |
| `_achatar` | `None`; texto; número; dict pelas cinco chaves conhecidas; dict desconhecido vira JSON válido; lista junta com `;`; lista vazia; objeto vira `str` |
| `_uma_mensagem` | string vazia → `None`; dict com código e descrição; item não-dict |
| `extrair_mensagens` | lista de strings; string solta; escalar; as cinco chaves de erro; valor escalar na chave; dict sem chave conhecida → vazio |
| `extrair_alertas` | payload não-dict; lista; dict; valor inválido → vazio |
| `ErroSefin` | `transitorio` por tipo; `pode_ter_sido_processada` no ambíguo; `str()` inclui as mensagens |

O resumo curto importa: 3 KB de HTML não é "mensagem da SEFIN" — é ruído que esconde o `cStat` real e
polui o registro do documento.

---

## 106. Regras da chave de acesso: 15 testes novos, cobertura do módulo **não** subiu

**Data:** 2026-11-28. `tests/test_regras_chave.py` (15).

| Regra | Casos provados |
|---|---|
| `CHAVE-FMT-001` | chave com tamanho errado → erro |
| `CHAVE-DV-001` | DV trocado → erro; chave válida → sem erro |
| `CHAVE-UF-001` | UF inexistente (99) **com DV recalculado** → erro |
| `CHAVE-MOD-001` | modelo desconhecido (99) com DV recalculado → aviso |
| `CHAVE-AMM-001` | mês 13 com DV recalculado → erro |
| `CHAVE-CDV-001` | `cDV` divergente → erro; ausente → não avalia |
| `CHAVE-EMIT-001` | CNPJ do emitente divergente → erro |
| `CHAVE-CONSIST-001` | `nNF` divergente → erro |
| `CHAVE-AMM-002` | `dhEmi` divergente → aviso; contingência → não exige |
| `PROT-001` | chave do protocolo divergente → erro |
| `AMB-001` | `tpAmb` inválido → erro |
| sem chave | documento sem protocolo não gera erro de chave |

**Resultado honesto: a cobertura do módulo ficou em 88%, a mesma de antes.** As 17 linhas restantes
(28-34, 88, 114-115, 155, 188, 207-208, 211, 214-216, 237-238, 253, 268) são ramos que exigem mutações
que eu não consegui acertar nesta rodada — tentei `Id` divergente e o teste acusou outros códigos
(`ASSIN-002`, `CHAVE-DV-001`, `PROT-001`), sinal de que a mutação quebrava mais de uma coisa. Removi o
teste em vez de deixá-lo passando por motivo errado.

O que ficou registrado é comportamento, não número: as regras acima têm teste que falha se mudarem.
A próxima tentativa neste arquivo deve mutar **um** campo e recalcular DV **e** `Id` juntos.

### Aprendizado de método

Mutar a chave de 44 dígitos exige recalcular o DV (`notasbr.chave.calcular_dv`), senão o parser
recusa a chave inteira e as regras de UF/modelo/AAMM nem rodam. Esse helper ficou nos testes
(`_recom_dv`) para a próxima rodada.

---

## 107. Entrega de webhook: 87% → 98%; cobertura global 96%

**Data:** 2026-11-28. `tests/test_webhooks_erros.py` (6). Medição sob a suíte completa:

| Item | Antes | Depois |
|---|---|---|
| `app/webhooks/service.py` | 87% (19 faltantes) | **98%** (3 faltantes: 201-202, 205) |
| **Global** | 95% (547) | **96%** (472) |
| Arquivos em 100% | 83 | **84** |

| Caso | Desfecho provado |
|---|---|
| tenant sem segredo | `FALHOU` com "sem segredo" e flush |
| segredo ilegível (chave-mestra trocada) | `FALHOU` com instrução de **rotacionar** e o tipo do erro — não retenta para sempre |
| exceção inesperada em uma entrega | a **segunda** entrega é tentada; a primeira vira `FALHOU` com "erro inesperado"; contagem de entregues = 1 |
| `httpx.HTTPError` | tratado como **retentável**: `PENDENTE`, `tentativas >= 1`, motivo "falha de rede" |

As 3 linhas restantes: 201-202 são o `except httpx.HTTPError` (coberto pelo teste novo em medição
isolada) e **205** é o `await http.aclose()` do cliente próprio — só ocorre quando o serviço cria o
próprio cliente e a chamada falha; exigiria dublar `httpx.AsyncClient`. Fica registrado.

### Efeito de aprender o caminho

O teste de rede falhou duas vezes antes de passar: primeiro faltava `codigo_http` no dublê, depois eu
esperava `FALHOU` onde o comportamento correto é `PENDENTE` (falha de rede é retentável). Corrigi as
expectativas — o código estava certo nas duas.

---

## 108. Boot e middleware: 85% → ~91% (medição por módulo: 83%)

**Data:** 2026-11-28. `tests/test_main_middleware_metricas.py` (7).

| Caminho | Provado |
|---|---|
| `X-Request-ID` em sucesso | header do cliente preservado; sem header, 32 hex gerados |
| exceção não tratada | `requisicao_falhou` no log **e** a exceção é propagada (o middleware não engole) |
| `/metrics` com Redis fora | 200 com `opennotas_worker_batimento 0` — métrica não derruba a rota |
| `/metrics` com batimento | `opennotas_worker_batimento 1` |
| `lifespan` em produção sem `ADMIN_API_TOKEN` | aviso `admin_api_token_ausente` no boot |
| shutdown | fecha **engine** e depois **Redis**, nesta ordem |

### Erro meu, três vezes no mesmo lugar

`MASTER_ENCRYPTION_KEY` é **base64 de 32 bytes** (AES-256). Tentei `"0"*64` (48 bytes), depois
`"k"*32` (24 bytes) e só então `base64.b64encode(b"k"*32)`. O validador estava certo nas três — eu não
tinha lido que a entrada é base64. Fica registrado porque é o tipo de detalhe que custa três rodadas.

### O que sobrou em `main.py` (21 linhas)

`229`, `244`, `273-279`, `296-297`, `322-343`: rotas de health/readiness e o handler de erro do
request id. Ficam para a próxima passada — a medição global segue em **96%** (472 descobertos) e esta
fatia acrescenta ~6 linhas.

---

## 109. Consulta de CNPJ: 81% → 100%

**Data:** 2026-11-28. `tests/test_cnpj_service.py` (18). Medição por módulo: **100%** (91 statements).

| Área | Casos provados |
|---|---|
| cache | sem Redis não lê; erro de leitura → `None`; JSON inválido → `None`; **hit evita as fontes** (0 chamadas); erro de escrita não derruba; invalidar sem Redis é no-op; invalidar apaga a chave; `invalidar` com CNPJ inválido não explode |
| cadeia | CNPJ inválido propaga; primeira fonte fora → segunda responde; **não encontrado** grava cache com TTL curto (300 s) e levanta com a lista de fontes; todas fora → `FonteIndisponivel` com os motivos |
| fallback local | sem base local propaga; com base local usa o último recurso e reporta `["base_local"]` |
| contrato | `to_dict` expõe `do_cache` e `fontes_tentadas` |

### Por que a distinção importa

"CNPJ válido que as fontes não conhecem" (404) e "fontes não responderam" (503) levam o cliente a ações
opostas: corrigir o dado × retentar. O teste fixa os dois desfechos, inclusive o cache curto de 300 s
para não repetir consulta de CNPJ inexistente.

### Detalhe

`invalidar` engole `CnpjInvalido` de propósito: limpar cache não é operação de negócio, e explodir ali
derrubaria um caminho de manutenção.

---

## 110. Cliente de frete: 84% → 100%

**Data:** 2026-11-28. `tests/test_frete_client.py` (19). Medição por módulo: **100%** (109 statements).

| Situação | Desfecho provado |
|---|---|
| sem `access_token` | recusa na construção ("o lojista precisa autorizar") |
| sem produto | recusa antes da chamada |
| CEP curto | recusa **antes** de gastar chamada (`chamadas == []`) |
| falha de rede | `ErroDeCotacao` "falha de rede" |
| **401** | mensagem que manda reautorizar o app |
| 4xx/5xx | inclui trecho do corpo devolvido |
| corpo não-JSON | "resposta não é JSON" |
| JSON que não é lista | "formato inesperado" + o que veio |
| sucesso | opções interpretadas, `mais_barata` correta, preço `Decimal` |
| saldo | `Decimal` do campo `balance`; rede e HTTP com mensagem própria |
| preço com vírgula | convertido para ponto (resposta localizada) |

### Erros meus nesta fatia (quatro)

1. Nomeei `ProvedorMelhorEnvio`; a classe é `MelhorEnvioClient`.
2. Esqueci de importá-la no bloco de imports (duas rodadas perdidas).
3. Montar produto vazio não serve: `cotar` recusa antes de qualquer rede — usei `Produto` real.
4. O dublê de transporte devolvia `{}` para qualquer resposta com `_json` preenchido, mascarando os dois
   caminhos de erro; só depois de serializar o dict o teste passou a exercitar "formato inesperado".
   E `SERVICOS_IGNORADOS = ("1","2")` fez o serviço `id=1` sumir da cotação — troquei para `id=3`.

---

## 111. Frete: state OAuth assinado e recusas de token

**Data:** 2026-11-28. `tests/test_frete_service.py` (10). Medição por módulo: **62%**
(era 86% sob a suíte completa; esta fatia cobre o `state`, que já era coberto, e duas recusas de token).

| Propriedade do `state` | Teste |
|---|---|
| ida e volta devolve o tenant | assinatura HMAC com a chave-mestra |
| state **forjado** | assinatura inválida → `EstadoInvalido` |
| state de **outro segredo** | chave-mestra diferente → recusa |
| carimbo não numérico | recusa com "carimbo" |
| **expirado** | 15 minutos + 60 s → recusa com "expirado" |
| tenant não-UUID | recusa com "tenant" |

Mais: troca de código sem credenciais configuradas (recusa citando as duas variáveis); delegação correta
quando configuradas; credencial inativa e vencida sem refresh (mensagem manda refazer a autorização);
`revogar` sem credencial devolve `False`.

### Erros meus

O dublê de credencial não tinha `access_token_selado`, e depois eu passei um envelope falso — o cofre
valida antes de olhar o refresh. Só funcionou selando um token **real** com `_cofre(settings)`.
Também substituí `_settings()` por `settings` em dois testes com um replace amplo e quebrei o outro.

### O que falta neste módulo (43 linhas por módulo)

`salvar` (108-127), `por_tenant` (131-134), `revogar` com credencial (142-147), a renovação
(196-214) e `cliente_para` (221-228) — todos exigem sessão dublada e cofre real. Ficam para a próxima
passada; a medição global segue em **96%**.

---

## 112. Frete: persistência da credencial (e um erro de ferramenta que custou a rodada)

**Data:** 2026-11-28. `tests/test_frete_persistencia.py` (7). Com os dois arquivos de frete:
`app/frete/service.py` **89%** (12 faltantes: 78, 188, 196-214).

| Regra | Provado |
|---|---|
| `salvar` sela com `aad` do tenant | token de acesso e refresh abrem só com o `aad` correto |
| tenant com credencial existente | **atualiza**, não duplica; `sandbox` acompanha |
| resposta **sem** `refresh_token` | não apaga o refresh já guardado |
| `revogar` | `ativo=False`, access `b""`, refresh `None`, `expira_em=None`, flush |
| `cliente_para` sem credencial | recusa citando `oauth/iniciar` |
| `cliente_para` com credencial | monta `MelhorEnvioClient` |

### O que deu errado (e o que sobrou)

Eu ia fechar também a **renovação** (`196-214`). Ao appendar o teste, usei um `replace` de PowerShell
com aspas triplas e **quebrei a sintaxe** de `tests/test_frete_service.py`. Revertí o arquivo ao commit
(`git checkout --`) em vez de tentar remendar no escuro — a versão commitada tem 10 testes passando.

Resultado: a renovação fica para a próxima rodada, agora com `edit`/`write` em vez de replace de shell.
O gate teria barrado o commit de qualquer forma, mas aqui quem barrou foi a verificação manual antes.

---

## 113. Frete: renovação de token e `state` malformado — módulo em 100%

**Data:** 2026-11-28. `app/frete/service.py` **89% → 100%** (114 statements, 0 faltantes), somando os
dois arquivos de teste de frete.

| Caminho | Provado |
|---|---|
| token válido | não renova (usa o selado) |
| **vencido** | renova, grava o novo token e devolve o novo |
| **falha na renovação** | `ativo=False`, flush e `NaoAutorizado` com "autorizar de novo" |
| `state` sem três partes | `EstadoInvalido` "malformado" |

### Correção de método

A rodada anterior quebrou a sintaxe do arquivo por usar `replace` de PowerShell com aspas triplas.
Desta vez usei `edit` para inserir no ponto exato e `write` para acrescentar o último bloco — sem
replace de shell. O resultado passou de primeira.

### Números

- `app/frete/service.py`: **100%** (era 86% sob a suíte completa antes das duas fatias de frete)
- `app/frete/client.py`: **100%** (fatia 110)
- Juntos, o subsistema de frete está coberto por **29 testes** (`test_frete_client.py`,
  `test_frete_service.py`, `test_frete_persistencia.py`, `test_rota_fretes.py`).

---

## 114. Adaptador: operações ADN, eventos e identificação da DPS

**Data:** 2026-11-28. 11 testes acrescentados a `tests/test_adapter_descodificacao.py`.

| Caso | Provado |
|---|---|
| `consultar_evento` 404 | devolve `None` (evento inexistente não é falha de transporte) |
| `consultar_evento` 200 sem XML | levanta `ErroSefin` |
| `distribuicao_dfe` | envia `cnpjConsulta` quando informado; **não** envia quando ausente |
| `eventos_nfse` | devolve lote vazio com status `NENHUM_DOCUMENTO_LOCALIZADO` |
| `_extrair_id_dps` | XML inválido → `None`; `infDPS` e variante `infDps`; sem `infDPS` → `None` |
| `_nfse_de_dps` com XML inválido | não explode (gera documento com campos vazios) |

### O teste que removi

Escrevi um teste para `_chamar` repassar `timeout`, mas meu helper `_cliente()` **substitui** `_chamar`
por um lambda — o teste nunca chegava ao código real e falhava com `KeyError`. Tentei construir o
cliente sem o atalho, não funcionou de primeira e **removi o teste** em vez de deixá-lo verde por
motivo errado. A linha 236 continua descoberta e registrada.

### Medição

Por módulo (`--cov=app.nfse.adapter` só com este arquivo): 74% — número que não compara com os 95% da
suíte completa, porque vários caminhos do adaptador são exercitados por testes de emissão. A medição
global fica para a próxima rodada, junto com o fechamento do que resta.

---

## 115. Medição global após 25 fatias: **96%** (391 linhas, 88 arquivos)

**Data:** 2026-11-28. Medido com `--cov=app --cov=src/notasbr`, `concurrency = greenlet`, suíte completa
(0 skipped).

| Métrica | Valor |
|---|---|
| Total | **96%** — 10.878 statements, **391 descobertos** |
| Arquivos em 100% | **88** de 176 |
| Arquivos abaixo de 90% | 12 |
| Pior arquivo | 15 linhas (`app/certificates/cofre.py`, 90%) |

### Comparação com o início da varredura

| Momento | Total | Descobertos |
|---|---|---|
| Medição original (sem `greenlet`) | 87,98% | 1.306 |
| Após corrigir a medição | 95% | 547 |
| **Agora** | **96%** | **391** |

### Mapa do que resta (por tamanho)

15: `certificates/cofre.py` · 14: `api/v1/tax.py`, `danfe/nfce.py` · 11: `notasbr/cli.py`,
`regras/chave_regras.py` · 10: `api/v1/consulta.py`, `tax/rtc.py` · 9: `danfe/etiquetas.py`,
`nfse/drivers_abrasf.py`, `regras/estrutura.py` · 8: `api/v1/transportes.py`, `catalogo/__init__.py`,
`danfe/a4.py`, `danfe/mdfe.py`, `nfe/gerador.py`, `notasbr/auditor.py` · 7: `batches/csv.py`,
`core/redis.py`, `danfe/cte.py`, `frete/oauth.py`, `integrations/base.py`, `tenants/service.py`,
`regras/tributos.py` · **≤6: 55 arquivos**, somando 154 linhas.

Nenhum arquivo concentra mais de 15 linhas: o trabalho restante é de **dispersão**, não de bloco.

### O que isso significa para o alvo de 100%

Para chegar a 100% de linha seria preciso tocar **88 arquivos** — cerca de 22 fatias no ritmo atual. Desse
total, uma parte não é alcançável sem dublar plataforma (subprocesso do worker, `httpx.AsyncClient`
próprio, `sys.platform`, `if __name__`), e nesses casos a resposta correta é `# pragma: no cover` com o
teste alternativo citado no comentário — como já feito no `healthcheck`.

**Não vou baixar o piso nem marcar em bloco.** A lista acima é o plano de trabalho, e cada exclusão será
proposta individualmente.

---

## 116. Rotas de tributação: 67% → 100%

**Data:** 2026-11-28. `tests/test_rota_tax.py` (11). Medição por módulo: **100%** (43 statements).

| Rota | Casos provados |
|---|---|
| `GET /tax/aliquotas` | lista ordenada por ano, com todas as entradas da tabela |
| `GET /tax/aliquotas/{ano}` | ano sem referência → **404** com instrução de informar alíquotas; ano com referência devolve |
| `POST /tax/simular` | simulação válida devolve base e valores; base negativa → **422 com `erros` e `base_calculo`**; ano sem tabela → 422 |
| `GET /tax/classificacoes` | limite respeitado; busca; filtro por ano (vigência); catálogo vazio não explode |
| `GET /tax/classificacoes/catalogo` | metadados com total |
| `GET /tax/classificacoes/{codigo}` | inexistente → 404; existente devolve o mesmo código |

### Erro meu

Montei o helper com **strings** (`"100.00"`) e campos `None`, mas `SimulacaoIn` exige `Decimal` e
`ano_fato_gerador >= 2026`. Sete erros de validação de uma vez. Corrigi o helper, não o schema — o
schema está certo em ser estrito: simulação com string livre é o tipo de entrada que esconde
arredondamento.

---

## 117. Cofre do certificado: envelope selado e recusas de corrupção

**Data:** 2026-11-28. `tests/test_cofre_envelope.py` (10). Medição por módulo: **60%** (o módulo é
coberto em conjunto com os testes de emissão; esta fatia fecha o envelope e as recusas do `de_pfx`).

| Caso | Provado |
|---|---|
| `selar_pfx`/`abrir_pfx` | ida e volta sem senha e **com senha** |
| envelope de **outro tenant** | `ErroDeCriptografia` (o `aad` do tenant é a barreira) |
| envelope truncado | corpo curto demais → `ErroCertificado` |
| tamanho declarado > corpo | "inconsistente" |
| tamanho zero | "inconsistente" |
| `de_pfx` vazio | "arquivo de certificado vazio" |
| `de_pfx` não-PKCS#12 | "senha incorreta ou arquivo que não é PKCS#12" |
| PFX gerado no teste | CNPJ extraído, validade presente e PEM de chave começando em `-----BEGIN` |

### Erros meus (três, no mesmo arquivo)

1. `Cofre` espera **32 bytes crus**, não base64 — o envelope nunca era montado.
2. `pytest.raises(Exception)` foi barrado pelo ruff (B017); troquei por `ErroDeCriptografia`.
3. `material_para_assinatura()` devolve **str**, não bytes; e eu esperava uma fixture `certificado` que
   não existe no conftest — passei a gerar o PFX dentro do teste.

Nenhum dos três era defeito de código: em todos, o teste estava errado.

---

## 118. Rota de CEP: 63% → 100%

**Data:** 2026-11-28. `tests/test_rota_consulta_cep.py` (4). Medição por módulo: **100%** (27 statements).

| Desfecho | Provado |
|---|---|
| sucesso | endereço com `codigo_ibge` (o campo que a emissão usa) |
| formato inválido | **422** |
| não encontrado | **404** |
| fontes fora | **503** |

A distinção 404 × 503 é o ponto: confundir faz o checkout dizer "CEP errado" quando as fontes é que
caíram — e o cliente corrige um dado que estava certo.

---

## 119. Assinatura por risco: NF-e em 100%, recusas do assinador cobertas

**Data:** 2026-11-28. `tests/test_assinatura_modulos.py` (10). Priorização **por risco** (assinatura
primeiro), como propus em §118.

| Módulo | Antes | Depois |
|---|---|---|
| `app/nfe/assinatura.py` | 81% | **100%** (31 statements) |
| `app/nfse/signer.py` | 90% | 90% (as 6 linhas restantes são o `except` do `assinar` com dublê de `XMLSigner`, que tentarei na próxima fatia) |

| Caso | Provado |
|---|---|
| NF-e assinada | contém `Signature`, algoritmo `rsa-sha1` (exigido pelo XSD) e namespace XMLDSig |
| XML mal formado | `ErroAssinatura` "mal formada" |
| sem `Id` | `ErroAssinatura` "sem atributo Id" |
| `_primeiro_com_id` | ignora comentário |
| `assinatura_sem_prefixo` | sem prefixo → `True`; XML quebrado → `False`; sem `Signature` → `False` |
| falha do `signxml` na NF-e | vira `ErroAssinatura` "falha ao assinar a NF-e" |

### Por que SHA-1 aqui não é descuido

O XSD da NF-e fixa `SignatureMethod = rsa-sha1` e C14N inclusiva. O `signxml` recusa SHA-1 por padrão, e
a subclasse `_AssinadorNFe` desliga a guarda **isoladamente**, com o motivo no código. O teste garante
que a saída usa exatamente os algoritmos que o schema exige — se alguém "modernizar" para SHA-256, o
teste quebra.

### Erros meus

Escrevi dois testes de verificação que não exercitavam o alvo (um deles com nome contradizendo a
asserção) e passei `object()` como certificado, que falha antes do dublê. Removi os dois primeiros e
passei certificado real.

---

## 120. Cliente Redis em 100% e `tax/rtc.py` já estava em 100%

**Data:** 2026-11-28. Dois achados de medição, um teste novo.

| Módulo | Situação medida |
|---|---|
| `app/tax/rtc.py` | **já estava em 100%** sob a suíte completa — a contagem de §115 (10 linhas) envelheceu quando os testes de `/tax/simular` entraram |
| `app/core/redis.py` | **73% → 100%** (26 statements) |

`tests/test_core_redis.py` (8 testes):

| Caso | Provado |
|---|---|
| criação | cliente no loop atual |
| reuso | mesmo loop devolve o mesmo cliente |
| **troca de loop** | cliente é recriado — o motivo do módulo existir |
| `ping` | `True` quando responde; `False` com log quando cai |
| `fechar` | fecha o pool, limpa `_redis` e `_loop`; sem cliente é no-op |

### Erros meus

Escrevi três testes **síncronos** para `obter_redis`, que exige loop em execução (`get_running_loop`).
Falharam com `RuntimeError: no running event loop`; era o teste, não o código — `async def` resolveu.

### Observação sobre o mapa de §115

Ele foi medido antes das fatias 116–119. Arquivos como `tax/rtc.py` podem já estar fechados. Por isso a
próxima medição global vai recontar tudo: prefiro descobrir isso medindo a anunciar um número velho.

---

## 121. Medição global após as fatias 116–120: **97%** (337 linhas)

**Data:** 2026-11-28. Recontagem completa — o mapa de §115 estava velho.

| Métrica | §115 | **Agora** |
|---|---|---|
| Total | 96% | **97%** |
| Descobertos | 391 | **337** |
| Arquivos em 100% | 88 | **94** de 176 |
| Abaixo de 90% | 12 | **8** |
| Pior arquivo | 15 | **14** |

### Evolução da sessão

| Momento | Total | Descobertos |
|---|---|---|
| Medição original (errada, sem `greenlet`) | 87,98% | 1.306 |
| Correção da medição | 95% | 547 |
| §115 | 96% | 391 |
| **§121** | **97%** | **337** |

### O que resta (top 10, medido agora)

14 `certificates/cofre.py` · 14 `danfe/nfce.py` · 11 `notasbr/cli.py` · 11 `regras/chave_regras.py` ·
9 `danfe/etiquetas.py`, `nfse/drivers_abrasf.py`, `regras/estrutura.py` · 8 `api/v1/transportes.py`,
`catalogo/__init__.py`, `danfe/a4.py`, `danfe/mdfe.py`, `nfe/gerador.py`, `auditor.py`

Confirmações que a medição trouxe: `tax/rtc.py`, `nfe/assinatura.py`, `core/redis.py`,
`api/v1/tax.py`, `api/v1/consulta.py`, `frete/client.py`, `frete/service.py` estão **em 100%** —
alguns já estavam antes da fatia que os mirou, o que mostra o valor de remedir em vez de confiar na lista
anterior.

---

## 122. DANFE: 52 linhas descobertas → 0 (38 testes, delegado e verificado)

**Data:** 2026-11-28. `tests/test_danfe_ramos.py` (38 testes, escrito por subagente com briefing fechado,
**verificado por execução** antes do commit).

| Módulo | Antes | Depois |
|---|---|---|
| `app/danfe/a4.py` | 97% (8) | **100%** |
| `app/danfe/cte.py` | 97% (7) | **100%** |
| `app/danfe/etiquetas.py` | 96% (9) | **100%** |
| `app/danfe/mdfe.py` | 96% (8) | **100%** |
| `app/danfe/nfce.py` | 93% (14) | **100%** |
| `app/danfe/nfe.py` | 97% (6) | **100%** |
| **Total** | 96% (52) | **100%** (0) |

`Stmts` idêntico (1.322) antes e depois: **nenhuma linha de produção mudou**.

### Comportamentos suspeitos que os testes revelaram (não corrigidos)

Estes são achados do subagente, **fixados por teste** para não regredirem. Não foram corrigidos nesta
fatia — cada um pede decisão de produto, não de teste:

1. **Tomador assimétrico no DACTE**: `tomador_nome` lê `toma4/xNome` **e** `toma3/xNome`;
   `tomador_documento` lê só `toma4`. CT-e com apenas `toma3` imprime nome sem documento, e `ausentes`
   não acusa.
2. **Documento fora do padrão passa calado**: `_formatar_documento` devolve o valor cru quando não tem
   11 nem 14 dígitos. CNPJ truncado é impresso como se fosse válido, sem aviso.
3. **`Volume.quantidade` é morto**: `qVol` é extraído e **nunca impresso**; `qVol` não numérico cai no
   `except` e vira **1 volume** em silêncio — pode imprimir menos etiquetas que caixas.
4. **QR Code de qualquer lugar no NFC-e**: falhando os dois caminhos do suplemento, aceita qualquer
   `qrCode` do documento.
5. **Contrato divergente**: `_formatar_moeda` do `nfe.py` não tem a guarda `if not valor` que os outros
   quatro têm; funciona por `Decimal("")` levantar, mas é contrato diferente.
6. **Truncamento sem reticência**: `a4 [:150]`, etiquetas `[:60]/[:96]`, `nfce [:70]/[:92]/[:52]`.
   Razão social longa é cortada sem aviso.
7. **MDF-e por varredura global**: `infMunCarrega`, `infMunDescarga`, `infPercurso` e `infCTe` usam
   `raiz.iter()`; lista de chaves e `tot/qCTe` podem divergir sem acusar.

Sobre a delegação: o briefing exigia medir antes/depois, não tocar em produção e relatar em vez de
consertar. O subagente entregou as três coisas — e o item 3 (etiquetas a menos que caixas) é o mais
grave da lista.

### Meu erro nesta fatia

Escrevi um teste extra para a linha 520 do A4 assumindo que remover `natOp` a popularia em `ausentes`.
Não popula — e a linha já era coberta pela suíte completa. Removi o teste em vez de forçar a asserção.

---

## 123. Biblioteca `notasbr`: 95% → 100% (72 → 0) e o primeiro `pragma` justificado

**Data:** 2026-11-28. 46 testes novos (4 arquivos, subagente com briefing fechado, verificado por
execução). `src/notasbr` **95% → 100%**: 1.394 statements, **0 descobertos**.

| Arquivo | Antes | Depois |
|---|---|---|
| `cli.py` | 94% (11) | **100%** |
| `regras/chave_regras.py` | 92% (11) | **100%** |
| `regras/estrutura.py` | 88% (9) | **100%** |
| `auditor.py` | 94% (8) | **100%** |
| `regras/tributos.py` | 95% (7) | **100%** |
| `regras/base.py` | 95% (5) | **100%** |
| `xml_util.py` | 95% (5) | **100%** |
| `cadastros.py` | 95% (4) | **100%** (com `pragma`) |
| `regras/assinatura.py` | 96% (4) | **100%** |
| `regras/totais.py` | 97% (3) | **100%** |
| `api.py`, `chave.py`, `modelos.py` | 96-99% | **100%** |

### O `pragma` — e por que ele não é atalho

Uma linha resistia: `cadastros.py:75`, `raise ValueError("base de CNPJ com caractere inválido")`.
**Verifiquei a inalcançabilidade por medição, não por leitura:** varredura dos 0x110000 code points
mostrou **zero** caracteres que sobrevivam ao regex de `normalizar_cnpj` (`[0-9A-Za-z]`) e falhem em
`isdigit() or isalpha()`. Tentativas com `!`, espaço e `Ã` caem no `raise` anterior (comprimento).

É **ramo morto**, não ramo não testado. Marquei com `# pragma: no cover` e o motivo escrito no código,
incluindo a prova. Se a normalização mudar um dia, o comentário diz o que revalidar. Registro aqui para
o senhor poder discordar: a alternativa seria **remover a checagem** (código de produção), o que não fiz
sem sua decisão.

### Comportamentos suspeitos que os testes revelaram

1. **Item sem CFOP passa em silêncio** (`tributos.py:65`): o comentário diz que `OBRIG` cobre, mas
   `OBRIGATORIOS["nfe"]` só lista `ide`, `emit` e `total`. `<det>` sem `prod/CFOP` **não gera achado
   algum**.
2. **`dhEmi` curto não deixa rastro** (`chave_regras.py:211`): retorna sem achado e sem `pular()`; o
   relatório não distingue "conferido" de "não deu para conferir".
3. **413 é defesa em profundidade** (`api.py:94-95`): a rota entrega o mesmo limite ao parser, então o
   parser nunca discorda dela.
4. **`cli.py:127-132`** (ramo `OSError`) não tem caso portátil no Windows; o contrato está fixado via
   injeção, mas o caminho não é exercitado por arquivo real.
5. **`xml_util.caminho_de`** para nó de outra árvore devolve só o nome da raiz, sem marcador de "não
   localizado".
6. **`cadastros.py:74-75`** era código morto defensivo (o item acima).

### Minha verificação

Rodei os quatro arquivos novos (passam), a suíte completa (exit 0) e medi `src/notasbr` isoladamente:
**100%, 0 descobertos**. Não aceitei o relatório do subagente sem executar.

---

## 124. Rotas `app/api`: 97% → 100% e um achado de segurança para decisão

**Data:** 2026-11-28. `tests/test_rotas_v1_ramos.py` (21 testes, subagente, verificado por execução).
`app/api` **97% (34) → 100%** (1.257 statements, 0 descobertos), 2.274 testes na suíte, exit 0.

| Arquivo | Antes | Depois |
|---|---|---|
| `transportes.py` | 83% (8) | **100%** |
| `representacoes.py` | 85% (6) | **100%** |
| `integracoes.py` | 92% (6) | **100%** |
| `admin.py` | 90% (3) | **100%** |
| `tenants.py` | 95% (3) | **100%** |
| `deps.py`, `apuracoes.py`, `health.py`, `municipios.py` | 94-97% | **100%** |

### Achados — o primeiro é de segurança e pede sua decisão

1. **Rotação com `escopos: []` produz chave IRRESTRITA (fail-open).** Verifiquei no código:
   `app/tenants/service.py:155-156` faz `tenant.api_key_escopos = escopos or None`, e
   `app/api/deps.py:49` trata `None` como "sem restrição". Pedir **nenhum** escopo entrega **todos**.
   O comentário no serviço diz que é intencional ("preserva o comportamento amplo"), mas a assimetria
   é perigosa: lista vazia deveria significar "nenhum escopo". **Não corrigi** — é mudança de contrato
   de segurança e a decisão é sua.
2. **Falha ao abrir o A1 vira 500** (`transportes.py:54` fora do `try`; `integracoes.py:140` só captura
   `ErroDeCertificadoDeTenant`, e `ErroDeCriptografia` não é subclasse). Chave-mestra divergente vira
   erro de servidor em vez de mensagem de configuração.
3. **Replay idempotente perde a chave** (`integracoes.py:102`): repetir a venda devolve 200 com
   `chave: null`, a primeira devolve a chave. Quem perdeu a resposta não recupera pelo retry.
4. **Upload de representação é lido inteiro antes do 413** (`representacoes.py:66`): `read()` antes de
   comparar com 5 MB — superfície de memória.
5. **Isolamento entre tenants: nada encontrado** nas 9 rotas auditadas (`/apuracoes/{id}` e `/guia`
   devolvem 404 para vizinho; certificado é por tenant; replay de DLQ exige `tenant_id` e escopa o item).
   Isso é ausência de achado no escopo auditado, **não** prova de isolamento global.

### Notas de execução

O subagente pegou o relay de portas do Docker fechando conexões no primeiro comando e refez a linha de
base após `docker compose restart postgres redis` — a tabela "antes" é dessa execução válida. Verifiquei
o arquivo novo por execução (passa) e o achado 1 lendo o código, porque a sonda HTTP que tentei esbarrou
na criação de tenant (422 por campos obrigatórios) e não provaria o caminho de forma limpa.

---

## 125. As duas decisões que o senhor delegou

**Data:** 2026-11-28. Ambas tomadas por mim, com o código lido antes.

### 1. `cadastros.py:75` — **mantido o `pragma`** (não remover a checagem)

Razão: `_valor_caractere` faz `ord(c) - 48` **sem validar**. A guarda é o que garante que, se
`normalizar_cnpj` um dia aceitar um caractere fora de `[0-9A-Za-z]`, o resultado seja **exceção** e não
**DV silenciosamente errado**. Em documento fiscal, DV errado é rejeição na SEFAZ com mensagem que não
aponta a causa.

Escolha registrada: **defesa morta hoje, barulhenta amanhã** — com o motivo e a prova escritos no
código (`# pragma: no cover` + comentário). Remover economizaria três linhas e compraria um risco de
falha silenciosa.

### 2. `Volume.quantidade` / `qVol` ilegível — **corrigido**

Investigando, o campo não era o problema: `qVol` **é** usado para decidir quantas etiquetas imprimir. O
defeito real era o `except ValueError → 1` **silencioso**: `qVol="duas"` imprimia 1 etiqueta para um
grupo que pode ter várias caixas, sem nenhum aviso — e o volume viaja sem identificação.

`app/danfe/etiquetas.py`:

- `qVol` ilegível agora entra em `nota.ausentes` com o valor recebido:
  `"transp/vol/qVol ilegível ('duas'): 1 etiqueta por grupo"`;
- a montagem de `ausentes` no fim da extração passou a **somar** em vez de sobrescrever (antes, a
  atribuição apagaria o aviso — defeito que eu teria introduzido).

Contrato fixado por teste (`tests/test_danfe_ramos.py`):

| Caso | Esperado |
|---|---|
| `qVol="duas"` | 1 volume **e** aviso em `ausentes` citando `"duas"` |
| `qVol="3"` | 3 volumes e **sem** aviso |

`app/danfe/etiquetas.py` segue em **100%** (229 statements; eram 227 — as duas linhas novas).

### Não fiz

Não mexi no leiaute da etiqueta para "imprimir a quantidade": o rótulo já diz `Volume i/n`, e `qVol` é
quantidade do grupo, não do volume. Imprimir os dois criaria duas numerações concorrentes no mesmo
papel. O que faltava era **avisar**, não desenhar mais.
