# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

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
