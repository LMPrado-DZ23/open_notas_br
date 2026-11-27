# Onboarding e operação do serviço hospedado

**Referência:** `work/auditoria-e-fase-a`, 2026-11-27. Para um cliente que vai usar a **instância
operada pela DZ23**. O modo auto-hospedado usa os mesmos passos, trocando "a DZ23" por "o operador".

> Este documento descreve o que **existe** e o que **falta**. Passo sem rota correspondente está
> marcado como lacuna — não como etapa concluída.

## 1. Criação do tenant

`POST /v1/tenants {"slug", "nome"}` → devolve a **API key uma única vez** (o banco guarda só o hash).

- **Lacuna:** não existe conceito de **usuário** dentro do tenant nem papéis. Um tenant = uma chave,
  acesso total. Para um serviço com várias pessoas por cliente, isso ainda não atende.
- **Lacuna:** não há exclusão de tenant pela API (só cascata por FK no banco).

## 2. Credenciais de API

| Necessidade | Estado |
|---|---|
| Emitir chave | ✅ `POST /v1/tenants` |
| Rotacionar (substitui a anterior) | ✅ `POST /v1/me/rotacionar-chave` |
| **Revogar sem emitir outra** | ✅ `POST /v1/admin/tenants/{id}/revogar-chave` (X-Admin-Key) — §73 |
| **Expiração** | ✅ `rotacionar-chave` aceita `dias_validade`; autenticação recusa expirada (§73) |
| **Escopos por chave** | ✅ `leitura` / `emissao`, definidos na rotação (§75); sem escopo = sem restrição (compatibilidade) |

Recomendação operacional enquanto as lacunas existirem: rotacionar em suspeita de vazamento e tratar
a chave como segredo de nível de tenant (não compartilhar entre sistemas do cliente).

## 3. CNPJ e estabelecimentos

`PUT /v1/me/config-fiscal` grava município, UF, ambiente, série DPS, alíquota e regime.
O CNPJ do emitente vem do **certificado** (extraído do A1 no upload) — não é digitado à mão, o que
evita divergência entre certificado e emitente.

- **Lacuna:** um tenant tem **uma** configuração fiscal. Múltiplos estabelecimentos do mesmo cliente
  exigem hoje múltiplos tenants.

## 4. Certificado e credenciais fiscais

| Necessidade | Estado |
|---|---|
| Enviar A1 (`.pfx` + senha) | ✅ `POST /v1/me/certificados` — selado com AES-GCM, `aad = tenant:<id>` |
| Listar / ver saúde (validade) | ✅ `GET /v1/me/certificados`, `GET /v1/me/certificados/saude` |
| Ativar outro certificado | ✅ `POST /v1/me/certificados/{id}/ativar` |
| Substituir | ✅ enviar novo e ativar |
| Remover | ✅ `DELETE /v1/me/certificados/{id}` |
| **Auditoria de uso** (quem usou qual certificado, quando, para qual operação) | ❌ **não existe** |
| **Exclusão segura** | ✅ sobrescreve o envelope antes do `DELETE` (§74) — reduz a superfície, **não** torna irrecuperável (WAL, réplicas e backups antigos) |
| A3 / token / HSM | ❌ não implementado — **não anunciar** |

O certificado é usado **em memória** no momento da chamada (`abrir_em_memoria`) e nunca gravado em
log, métrica ou resposta. Ver `docs/OPERACAO.md` §5 para rotação da chave-mestra.

## 5. Credenciamento — é do contribuinte

O sistema **não** credencia ninguém e **não** substitui o cadastro do contribuinte junto à SEFAZ/ADN.
Sem credenciamento, a transmissão é recusada pelo autorizador, e o código não tenta contornar isso.

- **Não confirmado:** exigências de cadastro da empresa desenvolvedora, responsável técnico ou CSRT
  por UF/documento. Ver `docs/MODOS-DE-OPERACAO.md` §5 e o próximo passo registrado lá.

## 6. Ambiente (teste × produção)

`ambiente` fica em `TenantFiscalConfig` (`homologacao` | `producao`) e é **por tenant**, não global.
O adaptador real decide o endpoint por esse campo (`sefin_url`).

- **Sandbox local:** `NFSE_ADAPTER=mock` — dublê que deriva a nota do DPS, sem rede. Separado de
  homologação real por definição e por teste (`scripts/demo_e2e.py` recusa rodar fora de mock).
- **Lacuna:** não existe botão "sandbox" por tenant; o sandbox é decisão de implantação.

## 7. Verificação de prontidão antes de emitir

Checklist que o operador deve executar (ordem recomendada):

1. `GET /health` → `database.ok`, `redis.ok` e `worker.ok` (o worker precisa estar vivo para webhooks);
2. `GET /v1/me/config-fiscal` → município/UF/série/ambiente conferem;
3. `GET /v1/me/certificados/saude` → certificado ativo e dentro da validade;
4. `GET /v1/me/webhook` → endpoint e segredo configurados (o segredo **não** é reexibido);
5. `GET /v1/health/circuitos` → nenhum autorizador aberto.

Não existe rota única de "checklist de prontidão" — é composição dos cinco itens acima.

## 8. Consulta de status, eventos, XML, PDF e histórico

| Necessidade | Rota | Isolamento |
|---|---|---|
| Estado da emissão | `GET /v1/emissoes/{id}` | filtro por tenant ✅ |
| XML/PDF | `.../danfse`, `.../representacao` | ✅ provado por teste (§67) |
| Cancelamento e eventos | `POST /v1/emissoes/{id}/cancelamento`, eventos | ✅ |
| Webhooks entregues | `GET /v1/me/webhook/entregas` | ✅ |
| Apuração e guias | `POST /v1/apuracoes`, `.../guia` | ✅ |
| Laudo de cálculo | `GET /v1/auditoria/...` | ✅ |
| **Histórico exportável** (pacote do cliente) | ❌ não existe | — |

## 9. Incidentes, expiração e recuperação

| Situação | Procedimento |
|---|---|
| Certificado vencendo | `GET /v1/me/certificados/saude`; substituir antes do vencimento |
| Autorizador fora do ar | circuito aberto → **503 + `Retry-After`**; alerta em `opennotas_circuito_estado` |
| Worker parado | `worker.ok: false` em `/health` e `opennotas_worker_batimento 0` |
| Segredo de webhook ilegível (chave trocada) | entrega marcada como falha com instrução: rotacionar o segredo em `POST /v1/me/webhook` |
| Falha persistente de job | item em DLQ; replay por `POST /v1/admin/dlq/{id}/replay` com `X-Admin-Key` |
| Vazamento de chave de API | rotacionar (`/me/rotacionar-chave`); **não há revogação sem substituição** |

Detalhe de fail-open × fail-closed e rolagem de chave-mestra: `docs/OPERACAO.md`.

## 10. Backup, portabilidade, exportação e exclusão

| Necessidade | Estado |
|---|---|
| Backup/restore | procedimento em `docs/OPERACAO.md` §2–3 (o dump contém documento fiscal e dado de cliente) |
| Portabilidade | ❌ não há exportação de pacote por tenant |
| Exclusão de dados do cliente | ⚠️ cascata por FK ao remover o tenant; **não há rota** nem procedimento de exclusão física documentado além do `DELETE` no banco |
| Retenção | ❌ não há expurgo automático; prazo é decisão do operador (não inventar prazo legal) |

## Custos e responsabilidades (transparência)

O **software** não cobra nada: licença MIT, sem limite de emissão e sem telemetria
(`docs/MODOS-DE-OPERACAO.md` §1). No modo hospedado, a DZ23 arca e decide preço sobre **infraestrutura,
operação, suporte e conectividade** — custos reais, não hipotéticos. O cliente arca com certificado,
credenciamento e tributos. Nada disso é gratuito por natureza, e o documento não deve sugerir que seja.
