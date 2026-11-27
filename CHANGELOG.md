# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado — exportação dos dados do tenant (portabilidade)

- `GET /v1/me/exportacao`: identificação, configuração fiscal, **metadados** de certificado, URL de
  webhook e contagem de emissões por status. `?incluir_xml=true&limite=N` acrescenta até N documentos.
- **Sem XML por padrão** (exportar tudo transformaria conferência em resposta de gigabytes) e **nunca**
  PFX, senha, hash de chave, segredo de webhook ou token — portabilidade é sobre os dados do cliente,
  não sobre as credenciais dele. Teste inclui a própria API key literal.
- 6 testes, com isolamento entre tenants e prova de que a chave não aparece.
- **Limites:** não é backup (isso é o dump); sem paginação de documentos (corta nos N mais recentes);
  **exclusão de tenant por API ainda não existe** — e não vou implementar apagamento de documento
  fiscal sem decisão sobre guarda legal.

### Adicionado — escopos por chave de API (migração 0014)

- A chave era **tudo-ou-nada no tenant**: não havia como dar só leitura ao ERP e só emissão ao PDV —
  o caso real de integração.
- Coluna `api_key_escopos` (JSONB), aplicada em `tenant_atual` por **método HTTP**:
  `GET`/`HEAD`/`OPTIONS` exigem `leitura`; o resto exige `emissao`.
- Por método e não por rota de propósito: anotar 60 handlers deixaria rota nova **sem exigência**
  silenciosamente; a regra por método fecha por padrão.
- **Compatibilidade:** `None` = sem restrição — é o que mantém chave antiga funcionando; tratar
  ausência como "nenhum escopo" seria negar acesso geral na migração.
- `POST /v1/me/rotacionar-chave` aceita `escopos` e devolve prazo + escopos na resposta.
- 6 testes, incluindo o caso espelhado (`emissao` barra leitura) e recusa de escopo inválido (422).
- **Limites:** escopo é por método, não por recurso (permite qualquer escrita); rotação **substitui**
  escopos — reduzir privilégio exige rotacionar e redistribuir a chave.

### Corrigido — exclusão de certificado agora sobrescreve o envelope

- `remover()` só apagava a linha: o ciphertext continuava em **páginas antigas** e no **WAL**,
  recuperável com ferramenta trivial. "Removido" no banco ≠ "fora do banco".
- `_sobrescrever_envelope()` troca `pfx_selado`/`senha_selada` por bytes **aleatórios do mesmo
  tamanho** e dá `flush` **antes** do `DELETE`; aplicado em `remover()` e `remover_todos()`.
- **O que não garante** (declarado): WAL, réplicas e backups antigos ainda têm a versão anterior; a
  proteção efetiva continua sendo a selagem AES-256-GCM com `aad` por tenant + guarda da chave-mestra.
  A sobrescrita é camada adicional, não substituta.
- 3 testes (bytes mudam/tamanho preservado, sem senha, remoção apaga a linha).

### Adicionado — expiração e revogação de API key (migração 0013)

- A chave vivia **para sempre** e não havia como matá-la sem emitir outra — insuficiente para operar
  credencial de terceiro.
- Migração **0013**: `api_key_expira_em` e `api_key_revogada_em` (upgrade, downgrade, `alembic check`
  sem drift).
- Autenticação recusa **expirada** (`401 credencial expirada; rotacione...`) e **revogada**.
- `rotacionar-chave` aceita `dias_validade` e **limpa** o carimbo de revogação — chave nova não nasce
  morta.
- `POST /v1/admin/tenants/{id}/revogar-chave` (X-Admin-Key). **Revogar substitui o hash por valor
  aleatório**: a chave não volta a valer por flip de flag, e o carimbo fica como auditoria. Efeito
  aceito: chave revogada responde igual a desconhecida — troquei mensagem específica por
  irreversibilidade.
- 6 testes, incluindo revogação sem afetar vizinho e rotação com prazo.
- **Achado:** a rota nasceu como `/v1/admin/admin/...` (o router já tem `prefix="/admin"`); o teste
  pegou como 404.
- **Limite:** revogar deixa o tenant sem acesso até alguém emitir outra chave (banco no auto-hospedado,
  suporte no modo hospedado).

### Adicionado — auditoria de uso do certificado (migração 0012)

- Era impossível responder "este A1 foi usado para quê, e quando?" — pergunta obrigatória ao operar
  credencial fiscal de terceiros.
- Tabela `certificado_usos` (migração **0012**, upgrade/downgrade testados, `alembic check` sem
  drift), registrada em **todos** os pontos de uso: emissão, cancelamento, evento, consulta e status
  de transporte.
- `abrir_para_uso()` grava **também a falha** (com tipo da exceção): chave-mestra trocada ou envelope
  corrompido só aparecem no uso, e sem isso o operador descobre por reclamação do cliente.
- **Nunca** guarda PFX, senha, XML, payload nem mensagem de erro — só operação, ambiente, sucesso e
  tipo do erro. Teste proíbe `pfx`/`senha`/`signature`/`xml` no registro.
- `GET /v1/me/certificados/{id}/usos` (404 para certificado de outro tenant). 5 testes.
- Mesma transação da operação fiscal: rollback remove o uso, porque nada foi assinado.

### Corrigido — teste que chamou a borda real da SEFIN (guarda na suíte)

- Um teste meu esqueceu o override de `nfse_adapter="mock"`; como o padrão do projeto é `sefin`, a
  emissão saiu para a **borda real**: **403** (certificado autoassinado recusado), **nenhum documento
  emitido**. Mesma classe do incidente de §48.
- Correção estrutural: `tests/conftest.py` define `NFSE_ADAPTER=mock` para **toda** a suíte — o
  esquecimento passou a ser explícito em vez de padrão.

### Documentado — dois modos de operação, com as lacunas do modo hospedado

- `docs/MODOS-DE-OPERACAO.md`: auto-hospedado × serviço hospedado. Verificado antes de escrever:
  licença **MIT**, **nenhuma** chamada obrigatória ao servidor do mantenedor, **nenhuma** telemetria,
  sem paywall nem limite de emissão no código. O `ConectorDz23` é webhook de **entrada** opcional
  (autenticado por `tenant_atual`); desativá-lo não afeta emissão.
- `docs/ONBOARDING-HOSPEDADO.md`: os 10 passos de onboarding mapeados às rotas reais, com **lacuna**
  explícita onde não há rota.
- **Lacunas medidas do modo hospedado:** sem escopos por chave, sem expiração, sem revogação sem
  substituição, sem auditoria de uso do certificado, sem usuário/papel por tenant, sem
  exportação/exclusão por API, e exclusão de certificado sem sobrescrita do ciphertext.
- **Não confirmado (registrado, não inventado):** cadastro da empresa desenvolvedora, responsável
  técnico, CSRT ou homologação por UF/documento — próximo passo escrito.

### Corrigido — 422 era o único erro fora do padrão RFC 7807

- Medido em container: 401, 404 e 405 saíam `application/problem+json`; o **422 saía
  `application/json`** (handler padrão do FastAPI para `RequestValidationError`), obrigando o cliente
  a tratar dois formatos de erro — e o que fugia era o mais comum em integração nova.
- Agora 422 responde problem+json com `type`/`title`/`status`/`origem`/`retryable` **e mantém o
  `detail` como a lista de erros do Pydantic**, exatamente como antes: contrato existente preservado,
  campos novos ao lado (`errors` espelha `detail`).
- `jsonable_encoder` no caminho: sem ele, `exc.errors()` com `ctx` não serializável estouraria 500
  dentro do tratamento de erro.
- 5 testes, incluindo contraprova de que o 401 continua problem+json.
- **Limite:** o corpo do 422 cresceu (lista duplicada em `detail` e `errors` — duplicação deliberada).
  Os `HTTPException(422)` levantados de propósito por algumas rotas continuam com `detail` em texto;
  são dois formatos por origem, agora documentados.

### Adicionado — testes de isolamento em downloads e travas de `tenant_id` no contrato

- **Downloads de documento não tinham teste de isolamento:** `GET /v1/emissoes/{id}/danfse` e
  `.../representacao` filtram por tenant no `where` (verificado), mas nenhum teste provava. Agora dois
  emissores reais: B recebe **404** nos arquivos de A, **A baixa o próprio (200, `%PDF`)** como
  contraprova, e sem chave é **401**. O arquivo aqui é o documento fiscal do cliente.
- **Trava da regra 7:** medido no contrato, nenhum schema de entrada expõe `tenant_id` (só duas
  saídas). Isso estava certo e indefeso — agora um teste reprova se qualquer `requestBody` ou query
  passar a aceitar `tenant_id`, com a exceção `/v1/admin` declarada por prefixo e verificada (o teste
  falha se a exceção ficar sem objeto).
- Nenhuma mudança de código: o defeito era de cobertura de teste, não de implementação.

### Documentado (correção de precisão) — o motor ABRASF não tem transporte real

- §59 e o painel diziam "contrato, roteamento e motor ABRASF existem e são testados", o que sugere
  que faltava só ligar. O código mostra outra coisa: `TransporteProvedor` é apenas um **`Protocol`**,
  há **zero implementações em `app/`**, e os testes usam `TransporteFalso`.
- Ou seja: **não existe cliente SOAP municipal**, e nenhum provedor tem URL/leiaute com fonte oficial
  no repositório — a condição que o próprio `criar_driver` impõe. Ligar a fábrica hoje não habilitaria
  município nenhum.
- Corrigido em `docs/MATRIZ-COBERTURA.md` (linha nova), no gerador do painel (estado vira
  🔒 **bloqueado**) e no `docs/ROADMAP.md` (pendência passa a ser "implementar transporte real e
  evidência oficial por provedor", não "ligar").
- Nenhuma mudança de código: o `Protocol` é a decisão correta; o erro era de descrição. Inclusive esta
  seção começou atribuindo a frase à matriz, onde ela não estava — corrigido.

### Verificado — demo ponta a ponta em container, com 20/20 verificações

- A demo estava registrada como "não reexecutada" desde a Fase 7. Executada agora em container, com
  PostgreSQL e Redis reais e `NFSE_ADAPTER=mock`: tenant → A1 → webhook → emissão (chave de 50) →
  DANFSe (PDF válido) → webhook assinado com HMAC válida → apuração (ISS 7,50) → guia DNA.
- **A demo pegou uma expectativa desatualizada:** o passo de idempotência reenviava corpo **parcial**
  com a mesma chave e esperava 200. Depois de §57 isso é **409** — corretamente. Corrigido para provar
  os dois casos: reenvio idêntico → 200 com a mesma fatura; corpo divergente → 409.
- **Armadilha operacional documentada** (e vivida): o compose tem **três** imagens (`api`, `worker`,
  `migrate`). Rebuildar só duas deixa `migrate` velho e o erro aparece como
  `alembic: Can't locate revision identified by '0011'` — que parece problema de banco, não de imagem.
  Registrado em `docs/OPERACAO.md` §9 com o diagnóstico (`alembic current` dentro do container).
- Provado no container: `/health` traz `nfse_adapter` e `worker.ok`, `/metrics` rotula por **template**
  (sem UUID), circuitos respondem, flag de rate limit no-op quando desligada.
- Adaptador real restaurado ao final (`nfse_adapter: sefin`).

### Adicionado — coleção Postman gerada do contrato, com guarda anti-drift

- Medido: 67 operações no OpenAPI e **nenhuma coleção**. Agora `scripts/gerar_postman.py` gera
  `docs/postman_collection.json` a partir do contrato: 18 pastas, 67 requisições, 14 com corpo.
- `--check` reprova quando a coleção diverge do contrato — coleção manual envelhece em silêncio.
- Corpo é **esqueleto derivado do schema**, não exemplo de negócio: CNPJ/valor inventado em gateway
  fiscal vira dado errado na mão de quem integra. Teste proíbe `00000000000`, CNPJ fictício e `R$ `.
- `X-API-Key: {{api_key}}` — a chave deriva o tenant, a coleção não sugere `tenant_id` no corpo.
- 8 testes, incluindo "toda requisição existe no contrato" e "toda rota está na coleção".
- **Limite:** exemplos de *response* continuam ausentes; corpo esqueleto não passa na validação de
  negócio (é ponto de partida); sem Newman (dependência nova exigiria ADR).

### Corrigido — worker herdava o teto de 60 s e podia abortar lote no meio

- Risco introduzido pelo próprio `statement_timeout` de §60: o worker usa o mesmo engine, e um lote
  de emissões dura minutos. O Postgres cancelaria a consulta **no meio do lote**, deixando documentos
  processados pela metade.
- Agora o worker tem engine e pool próprios, com `DB_STATEMENT_TIMEOUT_WORKER_MS` (600 000 ms).
  `criar_engine()` ganhou o parâmetro; `dispose_engine()`/`reset_engine()` cuidam dos dois engines;
  `entregar_webhooks` e `processar_lote` usam a fábrica do worker. Nenhuma rota da API mudou.
- 3 testes, provando no servidor: worker **600 000 ms**, API **60 000 ms**.
- Achado de teste: comparar a string de `SHOW statement_timeout` é frágil — o Postgres devolve
  `1min`/`10min`, não `60s`/`600s`. Normalização por unidade (`_em_ms`) no lugar da comparação textual.

### Corrigido — painel contradizia a auditoria (correção no gerador, não no arquivo)

- `docs/PAINEL.md` tinha tabelas narrativas fixas em `scripts/gerar_painel.py` que nunca acompanharam
  o projeto: dizia **"CT-e/MDF-e geração ❌ / assinatura ❌"** e **"consulta ❌"** para documentos
  cuja geração, XSD, assinatura e consulta de status (real, `cStat 107`) existem e são testados.
  Também listava como pendentes o admin auth (ADR 0001 implementado) e o `pip-audit` (ADR 0002
  decidido).
- Corrigido **na fonte geradora**, como manda a regra do projeto. As tabelas agora distinguem
  `🔒 módulo, sem rota` de `❌ ausente` e apontam para `docs/MATRIZ-COBERTURA.md`.
- **Incidente registrado:** rodei `pytest --cov` e o gerador ao mesmo tempo, no mesmo banco de teste —
  erro que a própria auditoria já documentava. Um teste falhou com `NoResultFound` e a cobertura saiu
  86,77%. Não era regressão: isolado, a suíte passa (`exit=0`) e o gate dá 9/9. **A cobertura de
  86,77% está contaminada e não deve ser citada.**

### Corrigido — banco sem `statement_timeout` podia derrubar a API

- O engine não definia `statement_timeout`, `idle_in_transaction_session_timeout` nem
  `pool_recycle`. Uma consulta travada segurava a conexão indefinidamente; com `pool_size=10`, dez
  consultas assim esgotavam o pool e a API parava de atender emissão, consulta e health.
- Agora os tempos vão como `server_settings` do asyncpg (valem **no servidor**, para todo o pool) e
  há reciclagem de conexão: `DB_STATEMENT_TIMEOUT_MS` (60 s), `DB_IDLE_TX_TIMEOUT_MS` (120 s),
  `DB_POOL_RECYCLE_S` (1800 s) — documentados em `.env.example`.
- 4 testes, sendo o principal `SHOW statement_timeout` após `criar_engine(...)`: prova que o valor
  chega ao Postgres. A primeira versão inspecionava o `_creator` do pool por introspecção e passava
  sem provar nada — foi substituída.
- **Limite declarado:** o teto é global para a API; relatório longo passa a falhar em vez de demorar.
  O caminho correto é o worker com teto próprio, que **ainda não existe** (o worker usa o mesmo
  engine).

### Documentado — inventário de implementações isoladas (código testado, fluxo não)

- Levantamento sistemático em `app/`: 8 módulos só são importados por testes e **não** estão no
  caminho de execução da API/worker.
- Os mais relevantes: **NFS-e multi-prefeitura não está no fluxo** (`drivers_factory`, `drivers`
  e motor ABRASF existem e são testados, mas `nfse/servico.py` sempre usa o padrão nacional);
  **consulta de situação do CT-e não tem rota** (a chamada real de §31 foi por script); transmissão
  de CT-e/MDF-e **sem endpoint**; helper de retry→DLQ do worker **não usado pelo worker**.
- `docs/MATRIZ-COBERTURA.md` corrigida: onde dizia "falta credenciamento" agora diz **"módulo existe,
  testado, sem rota"** — bloqueio diferente e mais honesto.
- `docs/ROADMAP.md` ganhou a lista de pendências com o motivo de cada adiamento.

### Corrigido — rate limit existia e nunca era instalado

- `MiddlewareRateLimit` estava escrito e testado, mas **`criar_app()` não o registrava**: ligar
  `RATE_LIMIT_HABILITADO=true` não fazia nada. Os testes antigos montavam uma `FastAPI()` própria e
  adicionavam o middleware à mão — provavam a peça, nunca a instalação.
- Agora é registrado sempre (o middleware no-opa quando desligado), **por dentro** do middleware de
  requisição, para o 429 ainda carregar `X-Request-ID`, log e métrica.
- Storage trocado de memória para **Redis** (`ArmazenamentoRedis`): com N instâncias a cota em memória
  seria `N x limite`. `INCR` atômico e `EXPIRE` só na primeira escrita (senão a janela desliza e a
  cota nunca fecha). Falha do Redis segue **fail-open**, como antes.
- 5 testes novos no app real; dois achados registrados: chave de cota fixa vazava entre execuções
  (Redis não expira entre testes) e a ordem dos middlewares no Starlette é o inverso do que eu supus.

### Alterado (correção com mudança de comportamento) — mesma `Idempotency-Key` com corpo diferente agora é 409

- Antes: reusar a chave com **outro corpo** devolvia `200` com a fatura anterior e `ja_existia: true`.
  Quem pedia R$ 100 recebia a nota de R$ 50 e concluía que emitiu o que pediu — divergência entre o
  pedido e o que foi escriturado.
- Agora: corpo diferente → **409** com orientação ("reenvio idêntico devolve a emissão original; para
  documento novo, use outra chave"). Corpo idêntico continua **200** com `ja_existia`, e chave nova
  continua **201**.
- Sem coluna nova e sem migração: compara com o `payload` que a fatura já guardava.
- **Aviso:** muda o comportamento de `/v1` neste caso. Não houve versionamento porque o
  comportamento anterior não era contrato — era resultado errado.
- Limites declarados: comparação é de corpo normalizado (campo opcional explícito como `null` vs
  ausente precisa gerar o mesmo dump) e a chave não expira — reusar chave antiga nunca emite documento
  novo.

### Documentado — ADR 0003 decide não instalar OpenTelemetry agora

- Traces distribuídos nunca existiram, mas a lacuna não tinha **decisão registrada** — lacuna sem
  decisão vira esquecimento.
- Motivos no ADR: cinco pacotes com versionamento próprio, necessidade de coletor (decisão de
  infraestrutura) e, o principal, instalar SDK e chamar de "temos OTel" seria o falso positivo que o
  objetivo manda evitar. Sem backend consumindo span, ganho zero e custo imediato.
- Gatilho registrado (incidente em ambiente publicado em que `request_id` não bastou; mais de um
  worker; exigência contratual) e mínimo aceitável quando entrar, incluindo **teste que prove span
  exportado**.
- Alternativa intermediária registrada e não escolhida: propagar `request_id` no payload do job.
- Cobertura medida nesta rodada: **87,72%** — o valor anterior (87,98%) era baseline antigo e foi
  corrigido no documento.

### Corrigido (crítico) — emissão concorrente com a mesma `Idempotency-Key` devolvia 500

- Duas requisições **simultâneas** com a mesma chave passavam as duas pela checagem, as duas
  inseriam, e a segunda batia na constraint. Havia tratamento de `IntegrityError`, mas a
  recuperação estourava com `MissingGreenlet` → **500** num caminho que deve devolver 200 com a
  fatura existente.
- A hipótese antiga ("problema do harness no `pool_pre_ping`") foi **testada e descartada**: pool,
  `sessionmaker` e middleware funcionam sob concorrência; só a emissão falhava.
- Correção: `pg_advisory_xact_lock` derivado de `sha256(tenant_id:chave)` **antes** da checagem —
  evita a corrida em vez de remendar o estrago. Escopo por chave, liberado no commit; tenants e
  chaves distintas seguem em paralelo.
- Teste `TestSimultaneidade` com `asyncio.gather`: antes `[201, MissingGreenlet]`, agora
  `[200, 201]` e **uma** fatura.
- Limite declarado: a trava é PostgreSQL (o projeto é Postgres-only) e a serialização por chave
  pode esperar a latência do autorizador quando a emissão síncrona está dentro da transação.

### Corrigido — webhook que esgotava tentativas não entrava na DLQ

- Ao esgotar as 5 tentativas, a entrega só virava `FALHOU` na tabela: ninguém era avisado e não
  havia caminho de replay. Agora entra na fila morta com `fila="webhook"` e
  `payload={entrega_id, tipo_evento, url_destino}` — **sem** copiar o payload do cliente, que já
  vive em `webhook_deliveries`.
- Idempotente: item `PENDENTE` existente para a mesma entrega impede duplicata, então reprocessar
  `entregar` à mão não enche a fila morta.
- Replay usa o caminho já existente e autenticado (`POST /v1/admin/dlq/{id}/replay`, ADR 0001), com
  a mesma recusa de replay duplo.
- 3 testes novos. Um registro honesto: a primeira versão do teste falhou por falta de segredo no
  cenário (a entrega já nascia `FALHOU` antes de tentar) — armadilha que produz teste verde sem
  prova; corrigida no fixture.

### Adicionado — rotação da chave-mestra com re-selagem verificada

- Trocar `MASTER_ENCRYPTION_KEY` tornava ilegível **tudo** que estava selado (A1, segredo de
  webhook, credenciais municipais, tokens de frete). Não existia re-selagem.
- `scripts/rotacionar_chave_mestra.py`: abre cada envelope com a chave antiga usando o **mesmo
  `aad`** e re-sela com a nova, em **uma transação**, **verificando antes do commit**.
- Garantias: falha limpa (nada gravado) se a chave antiga não for a que selou o dado; recusa chave
  ausente/malformada/igual; chaves só por variável de ambiente (nunca em argumento, que aparece em
  `ps`); relatório com contagens, sem conteúdo nem chave.
- 11 testes, incluindo "nova abre, antiga não" (prova de re-selagem) e "`aad` amarra ao tenant".
- `docs/OPERACAO.md` §5.2 atualizado: o texto que dizia "não existe re-selagem" agora traz o
  procedimento; o caminho manual (reenviar A1) fica como último recurso.

### Adicionado — matriz de cobertura fiscal e runbook de operação

- `docs/MATRIZ-COBERTURA.md`: por documento e operação, com **nível de prova** explícito
  (`✅ teste` × `✅ real` × `🔒 bloqueado` × `❌ ausente`) e a legenda dizendo que teste não é
  homologação.
- Achado ao montar: o banco de dev tem 1 fatura `authorized` e 2 documentos com `xml_autorizado`,
  mas **0 com `protocolo`**, misturando mock e real — registrado como **não sendo prova** de
  autorização, em vez de virar "emissão homologada".
- `docs/OPERACAO.md`: backup/restore (o dump contém documento fiscal e dado de cliente), migrations
  e rollback (11/11 com `downgrade()`, mas downgrade de tabela criada **dropa dado**), rotação de
  chave, incidentes e a tabela fail-open × fail-closed de cada componente.
- **Descoberta:** não existe re-selagem ao trocar `MASTER_ENCRYPTION_KEY` — trocar a chave exige
  reenviar A1 e regravar segredos. Está no runbook com o procedimento, não escondido.
- Ambos linkados no README.

### Adicionado — `/metrics` em formato Prometheus (sem dependência)

- Não havia métrica nenhuma: só `GET /health/circuitos` em JSON, inútil para scraping. Agora
  `/metrics` expõe contador e histograma de requisições, batimento do worker e estado dos
  circuitos.
- **Cardinalidade controlada por construção**: rótulo de rota é o *template*, nunca o caminho com
  UUID (teste afirma que dois ids da mesma rota não geram duas séries), e **nenhum rótulo de
  tenant** (teste proíbe `tenant`, `cnpj`, `cpf`, `api_key`, `chave` no payload).
- `/metrics` não conta a si mesmo e fica **fora do OpenAPI**: é superfície de scraping, não
  contrato de cliente.
- Feito à mão em vez de `prometheus-client`: quatro métricas não pagam uma dependência nova
  (regra 11 / ADR 0002). 11 testes.
- **Continua ausente**: traces OpenTelemetry — dependência nova com peso real, exige ADR próprio.

### Adicionado — `pip check` no gate/CI e ADR 0002 decidindo a varredura de CVE

- O CI não tinha **nada** sobre dependências. Agora tem consistência: `python -m pip check` no
  gate local (7/7 rápido, 9/9 completo) e no CI.
- `docs/adr/0002-dependencias.md` separa as duas coisas que "análise de dependências" costuma
  misturar: **consistência** (implementada, offline) e **CVE** (decidida com gatilho objetivo).
- `pip-audit` **não** foi adicionada agora: dependência nova (regra 11), base externa que reprova
  CI por fato alheio ao commit, e `--ignore-vuln` exigindo disciplina de revisão. Gatilho para
  adotar: existir ambiente publicado ou distribuição a terceiros.
- **Risco residual declarado**: CVE em dependência não é detectada hoje — registrado como lacuna,
  não como cobertura.

### Adicionado — `/health` reporta o worker; teste de contrato passou a comparar schemas

- O worker já tinha batimento em Redis (TTL 120 s) e healthcheck para o Docker, mas a **API** não
  reportava nada: `/health` respondia `ok` com o worker morto. Agora a resposta traz
  `worker: {ok, ultimo_batimento, detalhe}`, lendo a mesma chave do worker.
- Política explícita: `READINESS_EXIGE_WORKER` (padrão `false`) decide se o worker **reprova** a
  readiness. Reportar ≠ reprovar — API e worker escalam separado.
- `saude()` passou a receber `settings` por `Depends`, senão `dependency_overrides` não tinha
  efeito (o próprio teste da flag revelou).
- **Defeito de teste corrigido**: `test_openapi_sincronizado` comparava só `paths` e aprovava um
  `openapi.json` sem o schema novo. Com a comparação de `components`, o teste ficou vermelho, o
  arquivo foi regenerado (+40 linhas) e voltou ao verde.

### Adicionado — performance do caminho síncrono medida (alvo de produto: p95 < 300 ms em mock)

- `scripts/benchmark_mock.py`: emissão de NFS-e pelo HTTP completo, em processo (`ASGITransport`,
  sem rede), `NFSE_ADAPTER=mock`, PostgreSQL de teste, assinatura XMLDSig **real**.
- Medido: **p95 285,5 ms** (n=60) e **289,9 ms** (n=30); p50 172,7/211,1 ms. Alvo atingido, mas
  **sem folga** — p99 já passa de 300 ms e o máximo chegou a 429 ms.
- O custo dominante é a assinatura RSA-2048, não o banco.
- **Incidente registrado**: a primeira execução foi para a borda real da SEFIN (script não definia
  `NFSE_ADAPTER`; o padrão do projeto é `sefin`). Recusada com 403 por certificado autoassinado,
  **nenhum documento emitido**. Corrigido com env explícito + guarda `recusa_por_adaptador`,
  testada em `tests/test_benchmark_mock.py`.
- `docs/auditoria_inicial.md` §48 traz condições, números e o limite ("não é tempo de autorização
  fiscal").

### Adicionado — circuito em cancelamento e evento (não só na emissão)

- Cancelamento e evento falam com a **mesma** SEFIN Nacional e não passavam pelo circuit breaker:
  com o autorizador fora, cada requisição queimava timeout próprio. Agora passam.
- `executar_com_circuito(registro, uf=, operacao=, acao=)` substitui o wrapper específico de
  emissão; `emitir_com_circuito` delega nele (API pública preservada).
- Chaves separadas por operação (`:autorizacao`, `:cancelamento`, `:evento`): rejeição de
  cancelamento não abre o circuito de emissão. O handler global de `CircuitoAberto` já respondia
  503 com `Retry-After` e `problem+json`.
- 4 testes novos, incluindo um que **documenta o limite**: o registro de circuitos é em memória,
  por processo — com N processos o limite efetivo é N × `limite_falhas`. Mover para Redis fica
  registrado como decisão pendente, não como implementado.

### Adicionado — secret scanning no gate e no CI (sem dependência nova)

- A regra "nunca versionar chave/senha/PEM" não tinha **nenhuma** verificação automática. Agora
  `scripts/verificar_segredos.py` varre o índice do git (biblioteca padrão) e procura bloco PEM,
  token GitHub/OpenAI/AWS, PKCS#12 em literal e senha literal.
- O relatório traz **caminho, linha e tipo** — nunca o valor encontrado: log de CI não pode virar
  segundo vazamento. Há teste afirmando isso.
- `tests/` e `docs/` são dispensados **apenas** da regra de senha literal (fixtures usam
  `"senha-de-teste"` de propósito); chave privada e token continuam proibidos em qualquer caminho.
- Gate local agora 8/8 com `--tudo` (6/6 rápido) e CI com passo `Secret scanning`.
- Medido: `nenhum segredo em 479 arquivo(s)`; 11 testes novos.

### Adicionado — `mypy` no gate e no CI; 93 → 0 erros

- `mypy` estava configurado no `pyproject.toml` desde o início e **nunca** rodava: 93 erros
  acumularam em 43 arquivos. Agora são **0 em 173**, e a checagem entrou no gate local
  (`scripts/check_ci.py`, 7/7) e no CI (`Tipagem (mypy)`).
- Dois **defeitos de execução** apareceram na triagem: `enviar_evento` (CT-e) chamava
  `montar_evento` sem `cnpj` → `TypeError` em todo envio de evento; e o `Protocol` de
  `registrar_evento` não declarava `operacao`, que as duas implementações já aceitavam.
- `reset_ephemeral_key()` removido: prometia descartar uma chave efêmera que não existe (a chave
  de desenvolvimento é constante derivada, de propósito).
- Guarda nova: certificado A1 sem CNPJ no titular falha **antes** da chamada, em cancelamento e
  em evento, em vez de seguir com autor indefinido.
- `app/nfse/documento_autorizado.py`: a chave de acesso de documento autorizado passou a carregar
  o invariante no tipo, em vez de só em `if` de tempo de execução.

### Corrigido — emissão por lote e por integração podia ir para a SEFIN de homologação

- `app/api/v1/lotes.py`, `app/api/v1/integracoes.py` e `app/worker/main.py` montavam
  `SefinNacionalClient(settings)`, passando `Settings` no parâmetro `ambiente`, que espera
  `AmbienteFiscal`. Como `sefin_url()` decide por `is AmbienteFiscal.PRODUCAO`, qualquer outro
  objeto cai em **homologação** — sem exceção e sem log. O cliente também ia sem certificado, e o
  mTLS falhava. Achado por `mypy`; confirmado por leitura.
- Correção: `app/nfse/factory.py::montar_adapter` decide o dublê em um só lugar e devolve `None` no
  caminho real, para que o serviço de emissão monte o cliente com o ambiente do tenant e o A1 dele.
- Testes: `tests/test_nfse_factory_ambiente.py` (7), incluindo guarda estrutural contra reintrodução.
- Auditoria reconciliada em `docs/auditoria_inicial.md` §44, com baseline medido: **1405 testes**,
  cobertura **87,98%**, 58 rotas, 2 jobs de CI, `mypy` com 93 erros (não verde, não está no CI).

### Adicionado — caminho feliz de `POST /v1/transportes/{cte,mdfe}` medido

- As rotas de geração tinham teste só de auth e OpenAPI; a pendência estava declarada em §25 e
  nunca executada. Agora 10 testes montam tenant + A1 no cofre e provam, por HTTP, que o XML sai
  assinado, no namespace certo e com o **DER do certificado do tenant** embutido (não um literal).
- Nenhum defeito encontrado: as rotas estavam corretas — o que faltava era evidência.
- Medido: **1396 testes**, 58 rotas, gate 6/6. Nada é transmitido: a rota devolve XML assinado.

### Corrigido — `GET /v1/transportes/status` respondia 500 com certificado ativo

- A rota lia `certificado.cert_pem` / `certificado.key_pem`, atributos que o cofre **não** expõe
  (`CertificadoA1` os mantém privados de propósito). Resultado: `AttributeError` → 500 em toda
  chamada em que houvesse A1 ativo **e** endpoint no catálogo, isto é, exatamente no caminho
  para o qual a rota existe.
- Correção: `TransporteHTTP` passou a aceitar `ssl_context`, repassado ao `httpx` como
  `verify=<contexto>`; a rota usa `CertificadoA1.ssl_context()`. O caminho antigo (PEM por
  caminho de arquivo) continua válido — nada foi removido.
- Causa de ter passado: a rota nunca foi exercitada com certificado. Agora há 6 testes de rota
  (200 CT-e, 200 MDF-e, 503, 422, 504 ×2) e 1 teste de regressão do repasse ao `httpx`.
- Medido: **1386 testes**, 58 rotas, gate 6/6, `alembic check` sem drift.

### Adicionado — catálogo nacional, CT-e/MDF-e e primeira chamada real à SEFAZ

Medido nesta sessão: **~1356 testes**, 57 rotas, 15 tabelas, 11 migrations, gate 6/6, CI verde.

- **Catálogo SEFAZ completo**: NF-e, NFC-e, CT-e e MDF-e em **27/27 UFs** (648 endpoints), cada
  um com `fonte_url` e SHA-256 no manifesto. Importação idempotente por
  `(uf, modelo, ambiente, servico)`.
- **Municípios**: 5571/5571 com provedor identificado a partir do `ACBrNFSeXServicos.ini`.
- **Schemas versionados**: 112 XSD (NFS-e 1.01, NF-e 4.00, CT-e 4.00, MDF-e 3.00) com hash no
  manifesto e verificação no boot.
- **Geradores de CT-e e MDF-e**: geram, assinam e **validam contra o XSD oficial**. Rotas
  `POST /v1/transportes/cte` e `/mdfe`, com tenant derivado da API key e isolamento entre
  tenants provado por teste.
- **`desenvelopar` corrigido**: devolvia o embrulho `nfeResultMsg` do WSDL e `ler()` recusava —
  quebraria a autorização real. Descoberto com resposta real da SEFAZ-GO.
- **TLS multi-autorizador**: `ssl.create_default_context()` não usava a loja do Windows, e
  SVRS/SP falhavam com `CERTIFICATE_VERIFY_FAILED`. Agora carrega as raízes do sistema.
- **SOAP por serviço**: `envelopar(ns_servico=)` e `TransporteHTTP(soap_action=)`, com valores
  derivados do WSDL oficial (versionado em `tests/fixtures/wsdl/`).
- **Migration 0011**: alinha banco aos modelos e zera o drift; `alembic check` passou a rodar no
  gate local e no CI (a causa de o drift ter sobrevivido).
- **Primeira chamada real a autorizador**: `NFeStatusServico4` de GO em homologação respondeu
  `cStat 107 — Serviço em operação`, com certificado A1 real. **Nenhuma nota foi emitida.**

#### Contato real com autorizador (com certificado A1 da empresa)

| Documento | Serviço | Autorizador | Resposta |
|---|---|---|---|
| NF-e | `NFeStatusServico4` | SEFAZ-GO (SOAP 1.2) | `107` |
| NF-e | `NFeStatusServico4` | SVRS — ES, SC, TO (SOAP **1.1**) | `107` |
| CT-e | `CTeStatusServicoV4` | SVRS — ES (SOAP 1.2) | `107` |
| MDF-e | `MDFeStatusServico` | SVRS — ES (SOAP 1.2) | `107` |

**Nenhuma nota foi emitida.** Status é leitura; autorização exige credenciamento.

Sete defeitos de produção só apareceram nesse contato — e nenhum dos 1300+ testes locais os
pegava, porque os fixtures vinham do leiaute e esses detalhes vivem no **WSDL**:

1. `desenvelopar` devolvia o embrulho `nfeResultMsg` (autorização quebraria)
2. TLS sem raízes ICP-Brasil (18+ UFs inacessíveis no Windows)
3. SOAP sem `action` (HTTP 500)
4. Wrapper no namespace fiscal em vez do namespace do serviço (242)
5. SOAP 1.2 onde o serviço exige 1.1 (215)
6. `nfeDadosMsg` no serviço de CT-e (243)
7. Embrulho `*Result` não desembrulhado e `cStat` lido no namespace fixo de NF-e

Cada um foi corrigido com teste que fixa o valor do WSDL.

#### Limitações conhecidas

- `cStat 215` do SVRS não resolvido: envelope correto pelo WSDL e XML fiscal correto pelo XSD;
  as hipóteses testáveis foram eliminadas com evidência (`docs/auditoria_inicial.md` §28).
- NFC-e sem geração: depende de CSC por UF.
- Autorização de NF-e/CT-e/MDF-e depende de credenciamento do contribuinte.


### Adicionado — evolução para gateway fiscal (v10.0)

Idempotência, contrato de erro, resiliência, auditoria de cálculo e a base de
multi-prefeitura. Medido: **1156 testes**, 55 rotas, 15 tabelas, 7 migrations.

- **`Idempotency-Key` por header**, com o campo do body mantido como fallback. O header
  vence quando os dois divergem: header é contrato explícito, e escolher o body permitiria
  que um proxy injetado mudasse a chave sem o cliente perceber. Nenhum dos dois → 422.
- **Contrato de erro RFC 7807** ativo em todas as rotas (`application/problem+json`),
  preservando `detail` e o status original — cliente que lia `detail` continua funcionando.
- **Rate limit por tenant** no middleware, **desligado por padrão**: ligar mudaria o
  comportamento de todas as rotas de uma vez. `/health` e `/ready` isentos.
- **Circuit breaker por serviço/UF**, injetado em `POST /v1/emissoes`. Circuito aberto
  responde **503 com `Retry-After`**, não 500 — 500 faria o cliente retentar na hora e
  piorar a fila. Rejeição fiscal **não** abre o circuito: o serviço está no ar.
- **DLQ** com replay autenticado (`X-Admin-Key`, 404 quando desabilitado) e
  `executar_com_dlq`: só falha transitória é retentada; sucesso não deixa rastro.
- **`CalculoAudit`**: hash determinístico de entrada/saída/laudo, vigência de tabela como
  erro quando há sobreposição, persistência na **mesma transação** da fatura e endpoints de
  consulta com integridade recalculável.
- **Base multi-prefeitura**: `municipios_nfse`, `credenciais_municipais` (segredos selados
  com AAD por tenant+município) e `webservices_sefaz`; seed idempotente com **5571
  municípios reais** do IBGE em 27 UFs.
- **Integridade de XSD** por manifesto SHA-256 (21 schemas), em modo `WARN` por padrão.
- **NF-e até o fio**: envelope `enviNFe`, SOAP 1.2, cliente com classificação de erro,
  transporte HTTP mTLS, leitura de retorno e ciclo de autorização — todos verificados com
  transporte falso, **nenhuma chamada real**.

### Corrigido

- **HTML de gateway classificado como recusa fiscal**: `403` em HTML (borda/mTLS) virava
  `AUTENTICACAO` com o HTML inteiro na mensagem. Agora classifica como borda, nomeia as
  hipóteses e não embute HTML.
- **`TABELAS` do truncate de teste** listava 9 das 14 tabelas: dado vazava entre testes e
  um teste passava pela sobra do anterior. Derivado do metadata.
- **Mock em produção recusado no boot** (`ENVIRONMENT=production` + `NFSE_ADAPTER=mock`).

### Notas

- **A emissão NFS-e real não foi re-testada** depois destas mudanças: o certificado está
  selado no banco e `MASTER_ENCRYPTION_KEY` não estava disponível. As 1156 verificações são
  locais. Re-testar é o primeiro passo antes de qualquer outra evolução.
- NF-e, NFC-e, CT-e e MDF-e **não transmitem**. Bloqueio: credenciamento na SEFAZ.


### Validado em produção restrita

- **Emissão de NFS-e autorizada pela SEFIN** (Produção Restrita) com certificado
  ICP-Brasil A1 real, seguida de consulta, DANFSe e **cancelamento** aceito.
  Ciclo completo verificado contra o serviço real.
- Contrato da SEFIN travado com respostas reais: `GET /dps/{id}`, `HEAD /dps/{id}`,
  `GET /nfse/{chave}`, envelopes do ADN e códigos `E2401`, `E2404`, `E2240`.
- DPS, pedido de evento e os 16 tipos de evento validados contra os XSD oficiais.

### Corrigido

- `pAliq` ia como fração (0,05) em vez de percentual (5,00) — imposto 100x menor.
- Alíquota não pode ser informada por prestador não optante do Simples (`E0617`).
- `KeyInfo` levava a cadeia inteira; a SEFIN aceita só o certificado folha
  (`E0714`).
- Declaração XML com aspas simples (`E1229`) e declaração descartada ao assinar.
- C14N trocada para `xml-exc-c14n#WithComments`, como na referência oficial.
- Configuração fiscal ambígua escolhia o município mais antigo em silêncio;
  agora exige `municipio_ibge` na emissão.
- `EmissaoIn` ignorava campos desconhecidos e descartava o tomador em silêncio.

### Adicionado

- **Catálogo dos 16 tipos de evento** da NFS-e, extraído do XSD oficial, com
  validação parametrizada de cada tipo e exposição em
  `GET /v1/emissoes/eventos/tipos`.
- **Cancelamento de NFS-e** (`POST /v1/emissoes/{id}/cancelamento`) com
  `pedRegEvento` validado contra o XSD oficial, assinatura XMLDSig e trilha de
  evento.
- **Registro genérico de eventos** (`POST /v1/emissoes/{id}/eventos`) para os tipos
  operáveis pelo contribuinte; cancelamento tem rota própria.
- **DAMDFE** (MDF-e) e **DACTE** (CT-e), **cupom NFC-e** com QR local,
  **DANFE A4**, **DANFE simplificado** e **etiquetas de volume**.
- **Validação contra certificado ICP-Brasil real**: mTLS aceito pela SEFIN de
  homologação, `GET /dps/{id}`, `HEAD /dps/{id}`, `GET /nfse/{chave}` e ADN
  confirmados; respostas reais versionadas como fixture de contrato.
- **Schemas XSD oficiais** versionados em `tests/fixtures/schemas/nfse-1.01/` para
  validação offline.
- `exigir_assinatura_valida`, que levanta em vez de devolver booleano ignorável.

### Corrigido

- **`GET /nfse/{chave}/eventos` não existe** (HTTP 405). A implementação usa o ADN,
  que funciona; há teste registrando o achado.
- **Caminho de parametrização de alíquota estava errado** (404 de rota
  inexistente); a orientação passou a ser informar a alíquota na configuração do
  tenant.
- `Id` do pedido de evento é `PRE` com 59 caracteres, não `EVT` com 62.
- `TSDateTimeUTC` não aceita `Z`, apesar do nome: exige offset numérico.
- `xDesc` não é texto livre: cada tipo de evento tem descrição fixa no schema.
- Dublê de SEFIN não honrava a assinatura do `Protocol` (`operacao`).

## [0.2.0]

### Adicionado

- Fases 1 a 6: fundação, cofre A1 com XMLDSig, motor tributário + CNPJ + NFS-e com
  dublê, DANFSe local, worker/lotes/webhooks, conectores DZ23 e Brizu.
- Apuração com provedores plugáveis (MAN/DNA, DAS, municipal).
- Reforma Tributária: alíquotas de referência 2026/2027 e catálogo `cClassTrib`
  versionado.

## [0.1.0]

### Adicionado

- Auditoria offline de XML fiscal e biblioteca `notasbr`.

### Corrigido — `codigo_status` da NFS-e não era persistido

- Medido em 2026-11-27: `fiscal_documents.codigo_status` era **NULL em todos os registros**, inclusive na
  NFS-e real autorizada cujo XML traz `cStat=100`. O código de autorização existia apenas dentro do blob,
  então "esta nota está autorizada?" exigia abrir o XML.
- `extrair_cstat()` lê `cStat` com namespace e **nunca levanta**; `RespostaEmissao.codigo_status` é
  preenchido pelo adapter real **e** pelo dublê (que imita o contrato: `cStat=100`), e o valor é
  persistido no documento. 6 testes.
- `protocolo` permanece **nulo de propósito**: a NFS-e Nacional não emite número de protocolo como a
  NF-e — a evidência é `cStat` + `dhProc` + `nDFSe`. Teste fixa isso para ninguém "corrigir" depois
  inventando o campo.

### Documentado — ciclo NFS-e reconciliado (README contradizia a si mesmo)

- O cabeçalho do README afirmava NFS-e **autorizada** em Produção Restrita; o quadro "Produção restrita"
  dizia "falta validar o payload de emissão". As duas afirmações estavam no mesmo arquivo.
- Evidência reconciliada: `docs/REFERENCIAS.md` §15 (25/11/2026, chave + ciclo completo) e, no banco,
  3 `authorized` (todas homologação) e o XML autorizado com `cStat=100`/`ambGer=2`.
- **Correção da minha própria fala:** onde eu disse "zero notas autorizadas", o correto é **zero em
  produção**; em homologação há autorização real documentada.
- Nenhum arquivo passou a chamar Produção Restrita de produção: o README agora diz explicitamente que
  são níveis diferentes.

### Corrigido — CI vermelho por infraestrutura (`lxml` sem headers)

- A CI falhou em "Instalar dependências" nos dois jobs: `Please make sure the libxml2 and libxslt
  development packages are installed`. Não era regressão de código — o commit anterior passou no mesmo
  workflow. Reexecutei: persistente.
- Passo `apt-get install libxml2-dev libxslt1-dev` adicionado aos dois jobs, antes do `pip`. Resolve o
  build em vez de mascarar o erro; não adiciona dependência de runtime.
- **Erro meu registrado:** a primeira edição juntou `run: |` na linha do `name:` e quebrou o YAML. O
  `yaml.safe_load` pegou antes do commit. Workflow inválido não roda e produziria vermelho sem log.
