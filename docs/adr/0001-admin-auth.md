# ADR 0001 — Admin auth mínima para operações de plataforma

- **Status**: **aceita e implementada** (opção A)
- **Data**: 2026-11-26
- **Contexto**: item 5 do documento v10.0 pede `POST /v1/admin/dlq/{id}/replay`.
- **Decisão pendente de**: proprietário do projeto.

## Problema

O v10.0 exige um endpoint de replay de DLQ **com autenticação de admin**. O projeto só
tem autenticação de **tenant** (`X-API-Key` → `Tenant`). Não existe conceito de admin.

Criar uma rota `/v1/admin/...` validando apenas a API key de tenant seria **falso
positivo de segurança**: qualquer lojista poderia reprocessar a fila morta de si mesmo —
e, pior, o prefixo `admin` sugeriria um controle que não existe.

## Opções avaliadas

### A. Chave estática de admin em configuração (recomendada)

- `Settings.admin_api_key` (obrigatória apenas se `admin_habilitado=True`)
- Header `X-Admin-Key`, comparação com `secrets.compare_digest`
- `admin_habilitado` nasce **falso**: sem chave configurada, as rotas não existem

**Prós**: mínimo, sem tabela nova, sem migração, sem dependência. Reversível.
**Contras**: uma chave compartilhada, sem identidade por operador — não serve para
auditar *quem* reprocessou.

### B. Tabela `admins` com chave por operador e audit log

**Prós**: identidade, rastreabilidade, rotação individual.
**Contras**: tabela + migração + CRUD + audit log. É a solução certa para produção com
mais de uma pessoa operando, e é maior que o restante do item 5.

### C. Replay apenas por CLI (`python -m scripts.replay_dlq`)

**Prós**: zero superfície HTTP, zero risco de exposição.
**Contras**: não atende ao texto do v10.0, que pede endpoint.

## Recomendação

**Opção A agora, B quando houver mais de um operador.** O replay já existe como serviço
(`app/worker/dlq.py:preparar_replay`) com as garantias testadas — recusa replay duplo e
devolve o item para pendente se o replay falhar. O que falta é só a porta de entrada.

A opção C permanece disponível como escape operacional e pode ser escrita junto com A.

## Consequência se não decidir

O item 5 fica **fechado exceto o replay**. Não é dívida técnica: é escopo que exige uma
decisão de quem opera o sistema. Registrar isso é mais honesto que inventar uma rota
"admin" que não autentica admin.

## Critério de aceite — **todos verificados**

- [x] `admin_habilitado=True` + `admin_api_key` configurada → rota existe
- [x] `admin_habilitado=False` (padrão) → rota **não** registrada (404, não 403)
- [x] chave errada → 401, sem revelar se a rota existe
- [x] replay duplo → 409 (já garantido no serviço)
- [x] teste de que tenant comum **não** acessa
- [x] chave nunca aparece em log nem em resposta

## Registro de implementação

- `app/api/v1/admin.py`: `exigir_admin` + `POST /v1/admin/dlq/{item_id}/replay`.
- `admin_habilitado=False` e `admin_api_key=None` por padrão; documentados no `.env.example`.
- `secrets.compare_digest` na comparação (evita vazar prefixo por tempo de resposta).
- **404 quando desabilitado, não 403** — não revela existência da rota.
- `tenant_id` explícito na query: operação de admin atravessa tenants por natureza;
  deixar implícito esconderia qual tenant está sendo afetado.
- 9 testes em `tests/test_admin_dlq.py`, incluindo: desabilitado → 404, sem chave → 401,
  `X-API-Key` de tenant **não** serve, replay duplo → 409, tenant errado → 409, e a chave
  nunca aparece na resposta.

**Quando migrar para a opção B**: mais de um operador humano. Aí a chave compartilhada
deixa de bastar porque não há como auditar *quem* reprocessou.
