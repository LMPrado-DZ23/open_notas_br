# Operação — backup, restore, migrations, chaves e incidentes

**Referência:** `work/auditoria-e-fase-a` (base `55351cb`), 2026-11-26.
**Escopo:** procedimentos que o operador executa. Cada afirmação aqui foi verificada no código —
o que **não** existe está declarado como não existente, não como "a fazer".

> Este documento não substitui decisão jurídica. Onde há obrigação legal envolvida (retenção,
> exportação, exclusão), o texto diz o que o **sistema** faz e o que fica a cargo do operador.

## 1. O que o banco guarda (e por isso precisa de backup)

| Dado | Onde | Sensibilidade |
|---|---|---|
| Tenants, API keys (só hash), configuração fiscal | `tenants`, `tenant_fiscal_config` | credencial (hash) e dado de cliente |
| Certificados A1 | `tenant_certificates.pfx_selado` | **PKCS#12 selado** — sem a chave-mestra é lixo |
| Segredos de webhook e credenciais municipais | tabelas correspondentes | selados com a mesma chave-mestra |
| XML assinado e **autorizado**, protocolo | `fiscal_documents.xml_assinado` / `xml_autorizado` / `protocolo` | documento fiscal; dado de cliente |
| Faturas, eventos, lotes, apurações | `invoices`, `invoice_events`, `batch_jobs`, `apuracao*` | dado de cliente |
| Laudos de cálculo (`CalculoAudit`) | `calculo_audit` | dado de cliente + regra aplicada |
| Fila morta | `dlq` | payload de job que falhou |

**Consequência direta:** o backup do banco **contém documento fiscal e dados de cliente**. Ele
precisa do mesmo cuidado do banco: acesso restrito e criptografia em repouso no destino.

## 2. Backup

```bash
# Lógico, comprimido, com o schema inteiro.
pg_dump --format=custom --no-owner --file=notasbr-$(date +%F).dump "$DATABASE_URL"
```

Regras que vêm do desenho do sistema:

1. **A chave-mestra NÃO está no banco.** `MASTER_ENCRYPTION_KEY` é variável de ambiente
   (`app/core/config.py`). Sem ela, todo `pfx_selado` e todo segredo selado do backup é
   inutilizável. Guarde a chave em cofre separado do backup — nunca junto.
2. **Backup não versionado no git** (`*.dump` deve ficar fora do repositório).
3. Frequência e retenção: **decisão do operador**. O sistema não impõe nem sugere periodicidade.

## 3. Restore

```bash
createdb notasbr_restaurado
pg_restore --no-owner --dbname=notasbr_restaurado notasbr-AAAA-MM-DD.dump
DATABASE_URL=postgresql+asyncpg://…/notasbr_restaurado alembic upgrade head
```

Verificação mínima depois do restore (nesta ordem):

1. `GET /health` → `status: ok`, `database.ok: true` (e `worker.ok` conforme o worker subir);
2. `GET /version` → versão e ambiente esperados;
3. leitura de um documento por um tenant de teste (garante que o dado voltou, não só o schema);
4. se houver certificado: uma emissão **em mock** (`NFSE_ADAPTER=mock`) prova que o
   `pfx_selado` volta a abrir com a chave-mestra restaurada. Sem a chave correta, esta etapa
   falha com erro de decifragem — é o teste que distingue "restaurei" de "restaurei e funciona".

## 4. Migrations e rollback

- 11 migrations, **todas com `downgrade()`** (verificado arquivo a arquivo em `alembic/versions`).
- `alembic upgrade head` é o caminho normal; `alembic check` responde "as migrations reproduzem
  os modelos?" e roda no gate local e no CI.
- Rollback de uma revisão: `alembic downgrade -1`.

**Riscos do downgrade, por tipo de operação já existente na série:**

| Migration | O que o downgrade faz | Risco |
|---|---|---|
| `0008`, `0009`, `0011` | altera tipo/default/índice | baixo, mas exige janela: tabela reescrita |
| `0004`, `0005`, `0007`, `0010` | cria tabela | downgrade **dropa** a tabela e o dado dentro dela |
| `0001` | estrutura inicial | drop de tudo |

Ou seja: rollback de schema **não** é rollback de dados. Antes de descer, faça backup — o
downgrade de uma tabela criada é irreversível para o conteúdo.

## 5. Chaves

### 5.1 Chave de API do tenant

- `POST /v1/me/rotacionar-chave` emite chave nova e invalida a anterior; o valor aparece **uma
  vez** e o banco guarda apenas o hash.
- Rotação não afeta dados nem documentos já emitidos.

### 5.2 Chave-mestra (`MASTER_ENCRYPTION_KEY`)

- Protege certificados, segredos de webhook e credenciais municipais.
**Re-selagem existe desde 2026-11-26** (`scripts/rotacionar_chave_mestra.py`, auditoria §53). Ela
reabre cada envelope com a chave antiga — usando o **mesmo `aad`** com que foi selado — e sela de
novo com a nova, em uma transação, verificando tudo antes do commit.

```bash
MASTER_ENCRYPTION_KEY=<antiga> \
MASTER_ENCRYPTION_KEY_NOVA=<nova> \
python -m scripts.rotacionar_chave_mestra
# depois: atualizar MASTER_ENCRYPTION_KEY do serviço para a nova e reiniciar
```

Cobre certificados A1 (`pfx_selado` + `senha_selada`), segredo de webhook do tenant, credenciais
municipais (usuário/senha/token) e tokens do Melhor Envio. Se qualquer envelope não abrir com a
chave antiga informada, **nada é gravado** — significa que a chave não é a que selou aquele dado.

**Antes de 2026-11-26 não havia re-selagem**: quem já operava com a versão anterior precisava
reenviar A1 e regravar segredos à mão. Esse caminho continua válido como último recurso.
- Em produção, `master_key()` **recusa subir** sem a variável; em teste/desenvolvimento usa chave
  derivada de constante pública e loga aviso (`master_key_ausente_usando_chave_de_desenvolvimento`).

## 6. Incidentes

| Sintoma | Diagnóstico | Ação |
|---|---|---|
| Emissão retorna **503 com `Retry-After`** | circuito aberto: a SEFAZ falhou repetidamente | aguardar o `Retry-After`; conferir `GET /health/circuitos` e `opennotas_circuito_estado` em `/metrics` |
| Emissão retorna **502** com `cStat` | rejeição ou erro do autorizador | ler `cStat`/`xMotivo` no corpo; rejeição fiscal **não** deve ser repetida |
| Webhooks parados | `opennotas_worker_batimento 0` ou `worker.ok: false` em `/health` | subir/reiniciar o worker; conferir Redis |
| Job falhando sempre | item em `dlq` | `POST /v1/admin/dlq/{id}/replay?tenant_id=…` com `X-Admin-Key` (rota **404** se `ADMIN_HABILITADO=false`) |
| Rate limit não bloqueia | Redis indisponível | **fail-open por desenho** (`app/core/ratelimit.py`: storage fora ⇒ permite) |
| Certificado não abre | chave-mestra trocada ou ausente | reenviar o A1 (ver 5.2) |

### Fail-open / fail-closed, declarado

| Componente | Com a dependência fora | Efeito |
|---|---|---|
| Rate limit | **fail-open** | permite a requisição; não protege |
| Health/readiness | **fail-closed** | 503 quando banco ou Redis não respondem (worker só reprova se `READINESS_EXIGE_WORKER=true`) |
| Circuito | **fail-closed** | 503 sem chamar a SEFAZ |
| Métricas | degrada | `/metrics` responde com o que sabe; Redis fora ⇒ `opennotas_worker_batimento 0` |

## 7. Retenção, exportação e exclusão

- **Não há rotina automática de expurgo.** Verificado: nenhum `retencao|retention|expurgar|purgar`
  em `app/`. O dado fica até alguém apagar.
- Exclusão em cascata existe por foreign key (`tenant_id … ondelete="CASCADE"` em documentos e
  eventos): remover o tenant remove o que é dele. **Não** existe rota de exclusão de tenant na API.
- Exportação: há download de XML e de PDF por documento; não há exportação em lote.
- Guarda do documento fiscal e prazo legal: **decisão do operador com o contador**. O sistema não
  afirma prazo — inventar prazo seria pior que não ter.

## 8. O que este documento NÃO cobre

- Alta disponibilidade, réplica de leitura e failover: não implementados.
- Rotação automática de chave-mestra: não implementada (ver 5.2).
- Restauração point-in-time (WAL): depende do PostgreSQL do operador, não do código.
- Runbook de vazamento de credencial: o passo 1 é sempre rotacionar (5.1/5.2) e revogar; o
  procedimento jurídico/LGPD é do operador.

## 9. Armadilha ao rebuildar: o compose tem TRÊS imagens

`api`, `worker` **e `migrate`** saem do mesmo `Dockerfile`. Rebuildar só `api` e `worker` deixa o
`migrate` antigo — e o sintoma não aponta para isso:

```
service "migrate" didn't complete successfully: exit 255
alembic: Can't locate revision identified by '0011'
```

A causa é a imagem velha sem `alembic/versions`, não o banco. Diagnóstico: `alembic current` **dentro
do container da API** (se responde `0011 (head)`, o banco está certo e o problema é imagem).

```bash
docker compose build api worker migrate
docker compose up -d
```

Regra prática: depois de qualquer mudança em `app/`, `alembic/` ou `pyproject.toml`, rebuilde as
**três**.
