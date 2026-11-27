# Modos de operação — auto-hospedado e serviço hospedado

**Referência:** `work/auditoria-e-fase-a` (base `main` @ `55351cb`), 2026-11-27.
Cada afirmação abaixo foi verificada no código; onde não foi, está escrito **não confirmado**.

## 1. Licença e liberdade de operação

| Item | Estado medido |
|---|---|
| Licença | **MIT** (`LICENSE`: "MIT License", Copyright (c) 2026 Leandro Prado) |
| Chamada obrigatória a servidor do mantenedor | **nenhuma** — varredura por `dz23` em `app/` encontra apenas o **conector de entrada** opcional (§4) |
| Telemetria / analytics | **nenhuma** — varredura por `telemetr|analytics|sentry|posthog|mixpanel` em `app/`, `src/`, `scripts/` retorna zero |
| Paywall, limite de emissão, licença remota | **não existem** no código |
| Domínios externos chamados | SEFAZ/ADN (`sefin.nfse.gov.br`, `adn.nfse.gov.br`, `gateway.apiserpro.serpro.gov.br`), `viacep.com.br`, `brasilapi.com.br`, `minhareceita.org`, `www.melhorenvio.com.br`/`sandbox.melhorenvio.com.br` — todos **serviços fiscais ou de dados públicos**, configuráveis ou opcionais |

Consequência prática: instalar a instância **não** cria vínculo com a DZ23. Não há "chave de ativação",
checagem de licença em runtime, nem envio de dado para o mantenedor.

## 2. Modo A — auto-hospedado

Quem opera instala e administra a própria instância.

**O que o operador fornece:** PostgreSQL 16, Redis, um processo de API e um worker (ARQ), e as
credenciais fiscais dos emissores (certificado A1 + credenciamento do contribuinte).

**O que o sistema faz sozinho:** schema (Alembic), multi-tenancy, emissão NFS-e (padrão nacional),
consultas de status de NF-e/CT-e/MDF-e, geração de XML/PDF, webhooks, apuração, guias, DLQ, métricas.

**O que o operador precisa obter por conta própria:**
- certificado A1 por emitente;
- credenciamento do contribuinte junto à SEFAZ/município para cada documento e UF;
- conectividade com os autorizadores (sem proxy da DZ23);
- decisões de retenção, backup e LGPD da própria operação (ver `docs/OPERACAO.md`).

**Custos:** infraestrutura do operador, certificado, conectividade e eventuais serviços contratados
(Melhor Envio, por exemplo). **Nenhum valor por nota é devido ao mantenedor** — o código não tem
mecanismo para cobrar nem para bloquear.

## 3. Modo B — serviço hospedado pela DZ23

A DZ23 opera a instância e oferece a API para clientes integrarem seus sistemas.

**O que NÃO muda em relação ao Modo A:** o código é o mesmo. Não existe build "enterprise", flag de
licença, nem caminho de código exclusivo do serviço hospedado. Isso é deliberado: se o modo hospedado
dependesse de código privado, o auto-hospedado viraria versão de segunda.

**O que muda é a responsabilidade operacional**, que passa a incluir:
- disponibilidade, backup/restore ensaiado, monitoramento e resposta a incidente;
- guarda das credenciais fiscais dos clientes (cofre com chave-mestra, rotação, auditoria);
- isolamento operacional entre clientes (filas, workers, armazenamento, suporte);
- cumprimento das obrigações de proteção de dados e das exigências fiscais que recaem sobre quem
  **opera** o conector;
- suporte e comunicação de indisponibilidade de autorizador.

**O que continua sendo do cliente emissor:** o CNPJ, o certificado, o credenciamento e a
responsabilidade pelo conteúdo fiscal do documento.

### O que ainda NÃO está pronto para o modo hospedado

Lista honesta, verificada no código (detalhe em `docs/ONBOARDING-HOSPEDADO.md`):

| Lacuna | Estado |
|---|---|
| Escopos por credencial de API | **não implementado** — a chave dá acesso total ao tenant |
| Expiração de chave de API | **não implementada** |
| Revogação de chave sem emitir outra | **não implementada** (rotação substitui; revogar exige rotacionar) |
| Auditoria de uso do certificado | **não implementada** (não há registro de "quem usou qual A1, quando, para quê") |
| Exclusão/exportação de tenant pela API | **não implementada** (só cascata por FK) |
| Múltiplos usuários por tenant, papéis | **não implementado** — o modelo é um tenant, uma chave |
| Alta disponibilidade, réplica, PITR | não implementados (dependem da operação) |

Ou seja: **o software permite operar o modo hospedado hoje** com isolamento por tenant provado em
testes, mas **não oferece** o conjunto de controles que um serviço comercial exige — escopos,
expiração, revogação sem substituição e auditoria de uso de certificado. Afirmar "serviço hospedado
pronto" sem isso seria falso.

## 4. Integrações de parceiro: entrada opcional, não dependência

`POST /v1/integracoes/dz23/vendas` e `POST /v1/integracoes/brizu/atendimentos` são **webhooks de
entrada**: um parceiro envia um evento de venda e o sistema emite com a idempotência derivada do
`evento_id` (`app/integrations/dz23/conector.py`).

Fatos verificados:
- ambas as rotas exigem `X-API-Key` e derivam o tenant da credencial (`tenant_atual`) — **não** aceitam
  `tenant_id` no corpo;
- o `evento_id` é a chave de idempotência entre os sistemas: reenvio devolve **200** com a nota
  existente, não cria segunda;
- **nada no caminho essencial depende delas.** Desativar essas rotas não afeta emissão, consulta,
  webhooks nem PDF.

Elas existem porque o mantenedor também opera o serviço; para um operador auto-hospedado são
**inertes** até alguém enviar evento para elas.

## 5. Fronteira entre desenvolvedor, operador e contribuinte

| Papel | Responsabilidade | Onde está no código |
|---|---|---|
| **Contribuinte (cliente)** | é o emitente fiscal; fornece CNPJ, certificado e dados; obtém o credenciamento dos seus estabelecimentos | `Tenant`, `TenantFiscalConfig`, `TenantCertificate` |
| **Operador (auto-hospedado ou DZ23)** | instala, opera, guarda credenciais, responde por disponibilidade e dados | `docs/OPERACAO.md` |
| **Desenvolvedor (mantenedor)** | software, conectores e correção | este repositório |

**Não confirmado nesta auditoria:** exigência de cadastro da empresa desenvolvedora, identificação de
responsável técnico, CSRT ou homologação específica por UF/documento. Não há fonte oficial verificada
neste repositório sobre isso, e inventá-la seria pior que declarar a lacuna.

**Próximo passo para confirmar:** consultar, por documento e UF, o manual oficial do autorizador e o
Portal Nacional (quando existir), registrando versão, data e hash — o mesmo critério já usado para XSD
em `data/xsd_manifest.json`. Enquanto isso não existir, a resposta correta é "não confirmado".

O que **não** pode ser afirmado: que um cadastro da DZ23 habilitaria automaticamente clientes,
documentos ou estados. O credenciamento é do contribuinte emissor, por estabelecimento.
