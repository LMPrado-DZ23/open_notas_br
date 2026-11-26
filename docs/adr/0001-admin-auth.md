# ADR 0001 — Admin auth mínima para operações de plataforma

- **Status**: proposta (não implementada)
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

## Critério de aceite (para quando A for aprovada)

- [ ] `admin_habilitado=True` + `admin_api_key` configurada → rota existe
- [ ] `admin_habilitado=False` (padrão) → rota **não** registrada (404, não 403)
- [ ] chave errada → 401, sem revelar se a rota existe
- [ ] replay duplo → 409 (já garantido no serviço)
- [ ] teste de que tenant comum **não** acessa
- [ ] chave nunca aparece em log nem em resposta
