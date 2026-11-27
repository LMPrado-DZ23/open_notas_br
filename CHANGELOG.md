# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

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
