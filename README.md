# open_notas_br

Motor e microserviço de **documentos fiscais brasileiros**: emissão e gestão de
NFS-e (padrão nacional), auditoria de XML, geração local de DANFSe, apuração com
guias plugáveis e entrega de webhook assinada. Pluga em qualquer ERP, CRM ou site
por API REST, fila e webhook, com isolamento multi-tenant por `X-API-Key`.

> **Estado:** Fase 1 de 6 concluída — fundação (containers, migração, multi-tenant,
> healthcheck). Emissão, certificados, DANFSe e conectores entram nas fases
> seguintes. Leia **[o que está pronto e o que não está](#o-que-está-pronto-e-o-que-não-está)**
> antes de usar.
>
> **Escopo ampliado (após a Fase 1):** NF-e, NFC-e, CT-e, MDF-e e NFP-e, além de
> DANFE A4, **DANFE Simplificado – Etiqueta** e **etiqueta de envio por volume**
> (estilo marketplace). Ver [docs/DOCUMENTOS-FISCAIS.md](docs/DOCUMENTOS-FISCAIS.md)
> e as Fases 7–9 no [roadmap](docs/ROADMAP.md).

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

## O que está pronto e o que não está

**Pronto e verificado nesta máquina**

- `docker compose up` sobe os 4 serviços, com `migrate` aplicando as migrações antes.
- `/health` retorna 200 com banco e Redis reais (e 503 quando algum cai — testado).
- Migração inicial com as 9 tabelas, sem drift (`alembic check`).
- Multi-tenant com API key, rotação, isolamento e configuração fiscal por município.
- Worker ARQ com batimento e healthcheck próprio.
- 283 testes passando; `openapi.json` gerado do app.

**Caminho real da emissão (Fase 2/3, em andamento)**

O adapter da SEFIN Nacional já aponta para a **API real**, com o contrato
confirmado em implementação de referência (ver
[docs/REFERENCIAS.md](docs/REFERENCIAS.md#7-contrato-confirmado-da-api-real-atualização)):

| Peça | Estado |
|---|---|
| URLs base por ambiente (SEFIN e ADN) | implementadas, com allowlist de host |
| `POST /nfse` com `dpsXmlGZipB64` | implementado |
| `GET /dps/{id}`, `GET /nfse/{chave}` | implementados, 404 tratado como "não existe" |
| `POST/GET /nfse/{chave}/eventos` | implementados |
| ADN: distribuição por NSU e eventos | implementados |
| mTLS com certificado A1 | implementado (`ssl` + PEM temporário privado) |
| Cofre A1 (abrir PFX, validade, CNPJ, fingerprint) | implementado e testado |
| Selagem do PFX com AES-256-GCM + `aad` por tenant | implementado e testado |
| Timeout de emissão tratado como **ambíguo** (consulta antes de reenviar) | implementado |
| CNPJ alfanumérico (IN RFB 2.229/2024) | implementado, validado contra o exemplo oficial |
| Montagem e assinatura da DPS | **falta** (próximo passo) |
| Endpoint de upload de certificado | **falta** (próximo passo) |

O que falta para você "só conectar o certificado": montar a DPS assinada
(XMLDSig) e expor `POST /v1/me/certificados`. São os dois itens da Fase 2.

**Depende de validação humana antes de qualquer produção**

- **Nada foi exercitado contra a SEFIN real**: não há certificado A1 nem
  credenciamento neste ambiente. O contrato está implementado, não homologado.
- **Versão do leiaute:** a produção usa o leiaute anterior até 30/11/2026 e passa
  à NT 009 em 01/12/2026; a homologação já está na NT 009. O adapter escolhe por
  data e ambiente.
- **Lista de municípios com `aderenteEmissorNacional = 1`** não verificada.
- **Cota e contrato da API Serpro** não exercitados.
- **NFP-e, MDF-e e etiquetas** entram nas Fases 7–9.

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
