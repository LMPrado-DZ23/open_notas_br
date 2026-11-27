# open_notas_br

[![CI](https://github.com/LMPrado-DZ23/open_notas_br/actions/workflows/ci.yml/badge.svg)](https://github.com/LMPrado-DZ23/open_notas_br/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![API REST](https://img.shields.io/badge/API-REST-brightgreen.svg)](openapi.json)

**Motor e microserviço open source de documentos fiscais brasileiros** — NFS-e
(padrão nacional), NF-e, NFC-e, CT-e e MDF-e. Emissão multi-tenant por API REST,
auditoria de XML, geração local de DANFSe/DANFE/DACTE/DAMDFE e etiquetas de volume,
apuração com guias plugáveis, fila de trabalho e webhook assinado.

> Feito para plugar em qualquer ERP, CRM, e-commerce ou plataforma de serviços.
> Integração nativa com **[DZ23](https://dz23.com.br)** e **[Brizu](https://brizu.com.br)**;
> qualquer sistema terceiro usa a mesma API com `X-API-Key`.

**Palavras-chave:** NFS-e, NF-e, NFC-e, CT-e, MDF-e, nota fiscal eletrônica, SEFIN,
SEFAZ, DANFSe, DANFE, DACTE, DAMDFE, Reforma Tributária, IBS, CBS, certificado
digital A1, assinatura XMLDSig, Melhor Envio, etiqueta de envio, Python, FastAPI,
multi-tenant, open source, Brasil.

> ### ✅ Emissão real validada contra a SEFIN
>
> Uma NFS-e foi **autorizada pela Produção Restrita** com este código, assinada com
> certificado ICP-Brasil A1 real, e depois **cancelada** — ciclo completo:
> emitir → consultar → DANFSe → cancelar. Ver
> [`docs/REFERENCIAS.md` §15](docs/REFERENCIAS.md), que lista as nove rejeições
> reais que levaram até lá e o que cada uma ensinou.


## Autopreenchimento no checkout

Duas consultas públicas, gratuitas e com cache, para o formulário se preencher
sozinho antes de emitir:

```bash
# CEP -> endereço completo, com o código IBGE que a nota exige
curl "$API/v1/cep/01001-000" -H "X-API-Key: $CHAVE"
# {"cep":"01001000","logradouro":"Praça da Sé","bairro":"Sé",
#  "municipio":"São Paulo","uf":"SP","codigo_ibge":"3550308","fonte":"viacep"}

# CNPJ -> razão social, município e IBGE
curl "$API/v1/cnpj/11222333000181" -H "X-API-Key: $CHAVE"  # troque pelo CNPJ a consultar
# {"razao_social":"...","municipio":"AGUAS LINDAS DE GOIAS","codigo_municipio_ibge":"5200258"}
```

| Recurso | Comportamento |
|---|---|
| Fonte do CEP | ViaCEP (primária) → BrasilAPI (reserva) |
| Cache | acerto 30 dias; "não encontrado" 5 min |
| Serviço público fora do ar | 503 pedindo preenchimento manual — o checkout não quebra |
| CEP inexistente | 404 (distinto de 503: fonte fora do ar não é CEP inválido) |

O `codigo_ibge` do CEP é o elo com a emissão: é o `municipio_ibge` que a DPS
precisa. Sem ele o fluxo obrigaria a digitar o código IBGE à mão.

## Frete automático pelo carrinho

`app/frete/` traz OAuth2 do Melhor Envio e cotação por CEP com lista de produtos
(peso, dimensões, valor segurado). O modelo comercial é **frete cotado e pago pelo
cliente final**: cotar é somente leitura; comprar a etiqueta usa o saldo do lojista.

### O frete é cobrado à parte, não compõe a NFS-e

Decisão de modelagem, igual ao padrão de e-commerce:

- **O frete é uma cobrança do pedido**, não do serviço. O cliente paga produto +
  frete no checkout; o lojista compra a etiqueta com o saldo do Melhor Envio.
- **A NFS-e continua sendo só o serviço.** Embutir frete no valor do serviço
  tributaria a entrega como serviço — e a base do ISS ficaria maior do que o
  serviço prestado.
- Em NF-e (mercadoria), o frete aparece no grupo `transp`/`modFrete`, nunca como
  item da nota. São coisas diferentes e o código as mantém separadas.

Por isso `POST /v1/fretes/cotacao` é **somente leitura**: cota e devolve preço e
prazo. Não existe compra automática — comprar gasta dinheiro da loja e só faz
sentido depois do pagamento.

### Rotas

| Rota | O que faz |
|---|---|
| `GET /v1/fretes/oauth/iniciar` | devolve a URL de autorização do Melhor Envio |
| `GET /v1/fretes/oauth/callback` | troca o `code` e guarda o token **cifrado** |
| `GET /v1/fretes/status` | autorizado? expira quando? |
| `POST /v1/fretes/cotacao` | cota o carrinho pelo CEP do cliente |
| `DELETE /v1/fretes/credencial` | revoga os tokens do tenant |

O `state` do OAuth é **assinado** (HMAC com a chave-mestra) e carrega o tenant:
um `state` forjado, de outra loja ou com mais de 15 minutos é recusado. O token é
selado com AES-256-GCM e `aad` do tenant — o blob de uma loja não abre em outra.

> **[A VALIDAR]** As rotas existem e estão testadas com transporte simulado, mas a
> chamada **real** ao Melhor Envio depende de o lojista autorizar o aplicativo.
> Até lá, `POST /fretes/cotacao` responde 409 explicando o próximo passo.


## Subir em um comando

```bash
cp .env.example .env      # opcional em dev; obrigatório em produção
docker compose up --build
```

Serviços: `api` (FastAPI), `worker` (ARQ), `postgres` 16, `redis` 7, mais o
serviço one-shot `migrate` que aplica as migrações antes da API e do worker
subirem.

```bash
curl http://localhost:8081/health
```

```json
{"status":"ok","versao":"0.2.0","ambiente":"development","uptime_segundos":7.531,
 "verificacoes":{"database":{"ok":true,"detalhe":null},"redis":{"ok":true,"detalhe":null}}}
```

Portas no host (configuráveis, escolhidas fora das padrão para não colidir com
outros projetos locais): API `8081`, PostgreSQL `55434`, Redis `56379`.

## Fluxo mínimo: tenant → credencial → configuração fiscal

```bash
# 1) cria o tenant e recebe a API key UMA única vez
curl -X POST http://localhost:8081/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"slug":"barbearia-centro","nome":"Barbearia Centro LTDA"}'

# 2) usa a chave para ver o próprio tenant
curl http://localhost:8081/v1/me -H "X-API-Key: nb_..."

# 3) configura o município de emissão
curl -X PUT http://localhost:8081/v1/me/config-fiscal \
  -H "Content-Type: application/json" -H "X-API-Key: nb_..." \
  -d '{"municipio_ibge":"3550308","uf":"SP","aderente_emissor_nacional":true}'
```

A API key aparece **apenas** na resposta de criação/rotação: o servidor guarda só
o SHA-256. Perdeu a chave, rotaciona.

## Arquitetura

```
                       ┌──────────────────────────────────────────┐
   parceiro / ERP ───▶ │  API FastAPI  (app/api)                  │
   X-API-Key           │  ├── /health, /health/live, /version     │
                       │  └── /v1/tenants, /v1/me/*               │
                       └───────────────┬──────────────────────────┘
                                       │  tenant_id vem SÓ da credencial
                       ┌───────────────▼──────────────────────────┐
                       │  Domínio                                 │
                       │  tenants · certificates · tax · nfse ·   │
                       │  danfse · danfe · assessment · batches · │
                       │  webhooks · integrations/{dz23,brizu}    │
                       └───────────────┬──────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  PostgreSQL 16                  Redis + ARQ                    Adapters
  (JSONB, multi-tenant)          (fila, cache, batimento)        SEFIN/ADN,
                                                                prefeitura, Serpro
                                                                ([A VALIDAR])
```

Decisões estruturais que sustentam o resto estão em
[docs/ARQUITETURA.md](docs/ARQUITETURA.md); as decisões com trade-off estão em
[docs/DECISOES.md](docs/DECISOES.md).

### Estrutura de diretórios

```
open_notas_br/
├── docker-compose.yml        # api + worker + postgres + redis + migrate
├── Dockerfile                # python:3.12-slim, usuário não-root
├── .env.example              # todas as variáveis, nenhum segredo real
├── alembic/versions/         # migrações (0001 = nove tabelas base)
├── app/
│   ├── main.py               # app FastAPI, middleware, lifespan
│   ├── core/                 # config, crypto (AES-256-GCM), security, logging, redis
│   ├── db/                   # base, session, models
│   ├── tenants/              # schemas, repository, service
│   ├── api/v1/               # health, tenants
│   ├── worker/               # ARQ (ping + heartbeat) e healthcheck
│   ├── certificates/         # Fase 2: cofre A1 + XMLDSig
│   ├── cnpj/  tax/  nfse/    # Fase 3
│   ├── danfse/ danfe/ assessment/  # Fase 4
│   ├── batches/ webhooks/    # Fase 5
│   └── integrations/{dz23,brizu}/  # Fase 6
├── src/notasbr/              # biblioteca de auditoria de XML (sem dependências)
├── tests/                    # 212 testes
├── docs/                     # arquitetura, decisões, escopo, referências, roadmap
└── openapi.json              # contrato gerado do FastAPI
```

`src/notasbr` é a biblioteca de **auditoria** de NF-e/NFC-e/CT-e herdada da
versão anterior do projeto. Ela continua sem dependências e é usada para conferir
o XML que o motor gerar ou receber. O serviço é o extra `app`.

## Stack e por quê

| Escolha | Por quê | Trade-off aceito |
|---|---|---|
| **Python 3.12 + FastAPI** | tipagem, OpenAPI nativo, asyncio | menos performático que Go em pico extremo; irrelevante para emissão fiscal |
| **PostgreSQL 16** | JSONB para payload fiscal, constraint real, transação confiável | exige serviço extra no compose |
| **SQLAlchemy 2.0 async + Alembic** | migração versionada e reversível | mais cerimônia que SQL puro |
| **ARQ** em vez de Celery | já é asyncio ponta a ponta; mesmo loop e mesma conexão Redis | ecossistema menor que Celery |
| **AES-256-GCM (`cryptography`)** | AEAD: confidencialidade + detecção de adulteração no mesmo passo | gestão de chave-mestra é responsabilidade do operador |
| **WeasyPrint** (Fase 4) | HTML→PDF com layout fiel e CSS | peso de dependências nativas no container |
| **Docker + compose** | ambiente reproduzível com um comando | requer Docker |

## Segurança

- **Nenhum segredo no repositório.** `.gitignore` bloqueia `.env`, `*.pfx`,
  `*.p12`, `*.pem`, `*.key`, `*.crt`. O `.env.example` traz só placeholders.
- **Chave-mestra obrigatória em produção.** Sem `MASTER_ENCRYPTION_KEY` e com
  `ENVIRONMENT=production`, a aplicação **não sobe**. Em desenvolvimento, gera
  chave efêmera em memória e avisa no log.
- **Certificado A1 nunca em claro.** Serializado com AES-256-GCM, com `aad`
  amarrado ao `tenant_id` — um envelope não pode ser movido de uma conta para
  outra. Descriptografia só em memória (Fase 2).
- **API key só como hash.** SHA-256 de 256 bits de entropia real, comparado em
  tempo constante.
- **Multi-tenant estrito.** `tenant_id` vem exclusivamente da credencial; nenhuma
  rota aceita `tenant_id` do corpo. Há teste dedicado a vazamento entre tenants.
- **XML com DTD é recusado** pela biblioteca de auditoria (defesa contra expansão
  de entidade).


## Integração com DZ23 e Brizu

Os dois parceiros têm rota dedicada, porque o payload de cada um é diferente. O
conector traduz; o serviço fiscal é o mesmo (mesmo certificado, mesma
idempotência, mesmo registro).

**Idempotência entre sistemas**: a `idempotency_key` é `dz23:<evento_id>` ou
`brizu:<evento_id>`. Reenvio do mesmo evento devolve **200** com a nota existente,
não cria segunda nota. O prefixo evita colisão entre parceiros que usem o mesmo
identificador.

### DZ23 — venda/fatura paga

```bash
curl -X POST http://127.0.0.1:8081/v1/integracoes/dz23/vendas \
  -H "X-API-Key: <chave do tenant>" \
  -H "Content-Type: application/json" \
  -d '{
    "evento_id": "venda-1234",
    "valor": 150.00,
    "descricao": "Corte + barba",
    "competencia": "2026-11",
    "cliente": {"nome": "Ana Silva", "documento": "11144477735"},
    "pedido_id": "PED-77"
  }'
```

| Campo | Obrigatório | Uso |
|---|---|---|
| `evento_id` | sim | vira `idempotency_key` |
| `valor` | sim | aceita número ou `"R$ 1.234,56"` |
| `descricao` | sim | descrição do serviço na nota |
| `competencia` | não | `AAAA-MM`; padrão é o mês corrente |
| `cliente` | não | `nome`, `documento`, `email` viram tomador |
| `pedido_id` | não | guardado como `referencia_externa` |

### Brizu — atendimento/agendamento pago

Mesmo contrato, com `servico` no lugar de `descricao` e `agendamento_id` no lugar
de `pedido_id` — é o vocabulário da plataforma.

```bash
curl -X POST http://127.0.0.1:8081/v1/integracoes/brizu/atendimentos \
  -H "X-API-Key: <chave do tenant>" \
  -H "Content-Type: application/json" \
  -d '{"evento_id": "ag-9876", "valor": 90.00, "servico": "Escova"}'
```

### Respostas

| Código | Significado |
|---|---|
| `201` | nota autorizada |
| `200` | evento já processado; devolve a nota existente |
| `422` | payload inválido **ou** tenant sem config fiscal/certificado |

A distinção importa: `422` com `{"motivo": "tenant_sem_pre_requisito"}` significa
que o parceiro não deve retentar — falta cadastro do lado do tenant. Qualquer
retentativa com o mesmo `evento_id` é segura.

### Webhook de volta

Configurado em `POST /v1/me/webhook`. Assinatura
`X-Notasbr-Signature: t=<timestamp>,v1=<hmac>` sobre `"<timestamp>.<corpo>"`.
Verificação de referência em `scripts/receptor_webhook.py` — validar o timestamp
é obrigatório, senão um corpo capturado pode ser reenviado.

## Estado de maturidade: o que pode e o que não pode ir a produção

Esta seção existe para não haver dúvida sobre o que está pronto.

### Pronto e verificado

| Área | Evidência |
|---|---|
| `docker compose up` sobe API, worker, PostgreSQL e Redis | 4 containers `healthy`, `/health` 200 |
| **567 testes** passando, cobertura total **85%** | `pytest --cov=app --cov=notasbr` |
| Módulos fiscais e de segurança ≥ 80% | servico 85%, dps 91%, signer 89%, adapter 80%, tax/rtc 90%, certificates 97%, core/crypto 100%, core/security 100%, tenants 93/100% |
| Fluxo fim-a-fim mockado | `python -m scripts.demo_e2e` → **18/18 verificações** |
| Cofre A1 AES-256-GCM, assinatura XMLDSig | testes de cifra/decifra e validação de assinatura |
| Webhook HMAC-SHA256 com retry/backoff | receptor real recebeu e validou a assinatura |
| Idempotência em emissão, lote e parceiros | reenvio devolve 200 com a nota existente |
| Configuração documentada sem divergir do código | teste compara `.env.example` com `Settings` |

### Produção restrita (homologação) — exige A1 real

O que foi **executado de fato**, com A1 ICP-Brasil e certificado do solicitante (25/11/2026), está em
[`docs/REFERENCIAS.md` §15](docs/REFERENCIAS.md): NFS-e **autorizada** pela Produção Restrita, com
consulta, DANFSe e cancelamento aceito.

| Item | Estado medido |
|---|---|
| Emissão na SEFIN | ✅ **real, autorizada** em Produção Restrita (§15); mTLS e `GET /dps/{id}` confirmados (§11) |
| `cStat` do documento | ✅ persistido (`codigo_status = 100`) desde §78 — antes só existia dentro do XML. `protocolo` fica nulo **de propósito**: a NFS-e Nacional não emite número de protocolo |
| Cancelamento e eventos | ✅ evento aceito pela SEFIN na nota de 25/11 (§15) |
| DANFSe | ✅ PDF gerado (4.014 bytes) na nota autorizada; leiaute conferido contra NT 008 v1.02 |
| Produção fiscal | ❌ **nunca**. Produção Restrita é ambiente de teste; não é prova de produção |

> **Produção Restrita ≠ produção.** Uma nota autorizada em homologação prova o contrato e a assinatura,
> não a habilitação do emitente nem o credenciamento em produção. A emissão em produção segue bloqueada
> pelo preflight de rota (§77 da auditoria) e pela ausência de credenciamento.

### Representação de NF-e (pronta)

`POST /v1/representacoes?formato=...` recebe o XML **já autorizado** e devolve o
PDF, sem gravar nada. Formatos: `danfe`, `danfe_simplificado`, `etiquetas`
(NF-e), `cupom` (NFC-e), `dacte` (CT-e), `damdfe` (MDF-e) e `danfse` (NFS-e). Serve para quem emite a NF-e
no próprio ERP e usa o serviço só para o documento auxiliar e a logística.

As etiquetas de volume seguem as imagens de referência: `Volume i/n`,
`Peso (kg)`, `Nota fiscal`, `Coleta`, código de barras Code128
(`<prefixo><nota>V<volume>`, ex. `EMPRE0000123V1`), `DESTINATÁRIO` e `REMETENTE`.
`transp/vol/qVol` é quantidade de volumes: um grupo com `qVol=2` gera duas
etiquetas.

### Não pronto

| Item | Situação |
|---|---|
| Emissão de NF-e | **pilha completa até o fio**: geração, assinatura (RSA-SHA1 fixo no XSD), validação PL_010h, envelope `enviNFe`, envelope SOAP 1.2, cliente com classificação de erro, transporte HTTP mTLS e ciclo de autorização. **Chamada real pendente de credenciamento em GO** — nenhum teste tocou a SEFAZ |
| Emissão de NFC-e | representação (cupom, QR local) pronta; **sem CSC e sem transmissão** |
| Emissão de CT-e / MDF-e | **geração, assinatura e validação contra o XSD oficial** prontas, com rotas `POST /v1/transportes/cte` e `/mdfe`. Transmissão ao autorizador pendente de credenciamento |
| NFP-e | **fora de escopo** — não há padrão nacional publicado (ver `docs/DOCUMENTOS-FISCAIS.md`) |
| Etiquetas de volume por volume | **pronto** (`formato=etiquetas`) |
| MAN/DNA, DAS e guia municipal reais | provedores são determinísticos, sem integração oficial |
| Catálogo `cClassTrib` como validação de entrada | importado; ainda não bloqueia valor inválido na emissão |

Pedir representação de documento não implementado devolve **422 com a lista do que
existe** — nunca PDF incompleto.

## Detalhes por fase

**Pronto e verificado nesta máquina**

- `docker compose up` sobe os 4 serviços, com `migrate` aplicando as migrações antes.
- `/health` retorna 200 com banco e Redis reais (e 503 quando algum cai — testado).
- Migração inicial com as 9 tabelas, sem drift (`alembic check`).
- Multi-tenant com API key, rotação, isolamento e configuração fiscal por município.
- Worker ARQ com batimento e healthcheck próprio.
- 526 testes passando; `openapi.json` gerado do app (34 rotas, 43 schemas).

**Caminho real da emissão (Fase 2 concluída, Fase 3 parcial)**

O fluxo completo funciona: **tenant → configuração fiscal → upload do A1 →
DPS montada → assinada → enviada → XML autorizado persistido**.

| Peça | Estado |
|---|---|
| URLs base por ambiente (SEFIN e ADN) | implementadas, com allowlist de host |
| `POST /nfse` com `dpsXmlGZipB64` | implementado |
| `GET /dps/{id}`, `GET /nfse/{chave}` | implementados, 404 = "não existe" |
| `POST/GET /nfse/{chave}/eventos` | implementados |
| ADN: distribuição por NSU e eventos | implementados |
| mTLS com certificado A1 | implementado (`ssl` + PEM temporário privado) |
| Cofre A1: abrir PFX, validade, CNPJ, fingerprint | implementado e testado |
| Selagem do PFX com AES-256-GCM + `aad` por tenant | implementado e testado |
| `POST /v1/me/certificados` (upload, listar, ativar, remover, saúde) | implementado |
| DPS 1.01 montada (leiaute anterior e NT 009) | implementado |
| Assinatura XMLDSig (RSA-SHA256, C14N exclusiva, sem prefixo) | implementado e testado |
| `POST /v1/emissoes` idempotente | implementado |
| Timeout de emissão tratado como **ambíguo** (consulta antes de reenviar) | implementado |
| CNPJ alfanumérico (IN RFB 2.229/2024) | implementado, validado contra o exemplo oficial |
| Consulta de CNPJ com cache/fallback, simulação IBS/CBS | **falta** (Fase 3) |
| DANFSe/DANFE, apuração, lotes, webhooks, conectores | **falta** (Fases 4–9) |

### Experimente agora, sem certificado real

Com `NFSE_ADAPTER=mock` a SEFIN é substituída por um dublê determinístico; todo o
resto — assinatura, DPS, idempotência, persistência — roda de verdade.

```bash
NFSE_ADAPTER=mock docker compose up -d --build
```

```bash
# 1) tenant
TENANT=$(curl -s -X POST localhost:8081/v1/tenants \
  -H "Content-Type: application/json" \
  -d '{"slug":"minha-barbearia","nome":"Minha Barbearia LTDA"}')
KEY=$(echo "$TENANT" | python -c "import json,sys; print(json.load(sys.stdin)['api_key'])")

# 2) configuração fiscal do município
curl -s -X PUT localhost:8081/v1/me/config-fiscal \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  -d '{"municipio_ibge":"3550308","uf":"SP","ambiente":"homologacao",
       "codigo_tributacao_nacional":"010701","serie_dps":"1","aliquota_iss":0.05}'

# 3) certificado A1
curl -s -X POST localhost:8081/v1/me/certificados \
  -H "X-API-Key: $KEY" \
  -F "arquivo=@meu-certificado.pfx" -F "senha=SUA_SENHA" -F "apelido=meu-a1"

# 4) emitir
curl -s -X POST localhost:8081/v1/emissoes \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  -d '{"idempotency_key":"venda-0001","valor":"85.00",
       "descricao":"Corte de cabelo masculino",
       "tomador_nome":"Cliente","tomador_documento":"11144477735"}'
```

Resposta (dublê; a chave real tem 50 dígitos e vem da SEFIN):

```json
{"invoice_id":"...","status":"authorized","ja_existia":false,
 "chave":"67180625606939268291970514058092113782995512000000",
 "documento":{"tem_xml_autorizado":true}}
```

Repetir o `POST` com a mesma `idempotency_key` devolve **200** com
`ja_existia: true` e a mesma chave — sem nota duplicada.

Para valer de verdade, troque para `NFSE_ADAPTER=sefin`, use um A1 real e comece
por **homologação** (`ambiente: "homologacao"`).

**Depende de validação humana antes de qualquer produção**

- **Nada foi exercitado contra a SEFIN real**: não há certificado A1 nem
  credenciamento neste ambiente. O contrato está implementado, não homologado.
- **Versão do leiaute:** a produção usa o leiaute anterior até 30/11/2026 e passa
  à NT 009 em 01/12/2026; a homologação já está na NT 009. O adapter escolhe por
  data e ambiente.
- **Lista de municípios com `aderenteEmissorNacional = 1`** não verificada.
- **Cota e contrato da API Serpro** não exercitados.
- **MDF-e** entra na Fase 8; **etiquetas de volume** já estão prontas; **NFP-e** foi removido do escopo.

### Para emitir de verdade, você precisa de

1. **CNPJ ativo** com credenciamento no Sistema Nacional (para NFS-e nacional).
2. **Certificado digital A1** (`.pfx`/`.p12`) e a senha.
3. **Inscrição municipal** e o **código de tributação nacional** do serviço
   cadastrados no município — sem isso a SEFIN recusa com `E0312`.
4. **Município aderente** ao padrão nacional; se não for, a emissão é pelo
   webservice da prefeitura, que é outro adapter.

Comece apontando `ENVIRONMENT` e `SEFIN_*_BASE_URL` para **homologação**. Emitir
em produção com o primeiro teste é o caminho mais curto para uma nota real
errada.

## Desenvolvimento

```bash
pip install -e ".[app,dev,pdf,assinatura]"
docker compose up -d postgres redis
python -m pytest                  # os testes de integração exigem o banco acima
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head    # DATABASE_URL no ambiente
python -m alembic check           # falha se modelo e migração divergirem
```

Os testes de integração criam o banco `notasbr_test`, aplicam a migração real e
truncam as tabelas entre casos. Sem PostgreSQL acessível, eles são **pulados com
motivo** — nunca aprovados silenciosamente.

## Documentação

- [Escopo e limites](docs/ESCOPO.md)
- [Documentos fiscais e etiquetas](docs/DOCUMENTOS-FISCAIS.md)
- [Arquitetura](docs/ARQUITETURA.md)
- [Decisões (ADRs)](docs/DECISOES.md)
- [Referências e etiquetas de confiança](docs/REFERENCIAS.md)
- [Roadmap das fases](docs/ROADMAP.md)
- [Matriz de cobertura fiscal](docs/MATRIZ-COBERTURA.md) — o que existe por documento e qual
  prova sustenta (teste × chamada real × bloqueado). Leia antes de acreditar em qualquer tabela.
- [Coleção Postman](docs/postman_collection.json) — gerada do contrato; python -m scripts.gerar_postman --check reprova se divergir.
- [Modos de operação](docs/MODOS-DE-OPERACAO.md) — auto-hospedado x serviço hospedado, sem paywall nem chamada obrigatória ao mantenedor.
- [Onboarding do serviço hospedado](docs/ONBOARDING-HOSPEDADO.md) — passo a passo com as lacunas reais (escopos, expiração, auditoria de uso).
- [Operação](docs/OPERACAO.md) — backup, restore, migrations e rollback, rotação de chave e
  resposta a incidente, com o modo de falha de cada componente (fail-open × fail-closed).

## Etiquetas de confiança

Toda referência a endpoint oficial, schema, código de erro ou regra
governamental carrega uma das marcas:

- **[CONFIRMADO]** — verificado em arquivo local, com caminho.
- **[INFERIDO]** — inferência a partir de padrão observado.
- **[A VALIDAR]** — depende de documentação/homologação que não posso executar aqui.

Trecho **[A VALIDAR]** sempre vive atrás de um adapter substituível, com interface
explícita. Nenhuma lacuna é preenchida com suposição silenciosa.

## Licença

MIT. Veja [LICENSE](LICENSE).

## Estado fiscal verificado

Medido por comando, não por memória. A fonte de verdade é `docs/auditoria_inicial.md` §15
e `docs/PAINEL.md` (regenerável com `python -m scripts.gerar_painel`).

| Documento | Geração | Assinatura | Transmissão | Consulta/Eventos | PDF |
|---|---|---|---|---|---|
| **NFS-e** | ✅ | ✅ | ✅ **real** (SEFIN homologação) | ✅ **real** | ✅ |
| NF-e | ✅ | ✅ | ❌ credenciamento | ✅ **status real** (GO, ES, SC, TO) | ✅ |
| NFC-e | ❌ | ❌ | ❌ | ❌ | ✅ |
| CT-e | ✅ | ✅ | ❌ credenciamento | ✅ **status real** (SVRS) | ✅ |
| MDF-e | ✅ | ✅ | ❌ credenciamento | ✅ **status real** (SVRS) | ✅ |

**O que isso significa na prática**: só a NFS-e emite de verdade hoje. A NF-e tem toda a
pilha construída e testada com transporte falso — o que prova que o pedido é montado
corretamente, **não** que a SEFAZ o aceita.

**Bloqueios externos** para mudar isso: credenciamento NF-e em Goiás, OAuth do Melhor
Envio, e `pip-audit` (exige ADR).
