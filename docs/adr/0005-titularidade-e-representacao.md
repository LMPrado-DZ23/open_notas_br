# ADR 0005 — Titularidade da emissão e representação por procuração

- **Status:** aceito (decisão de **bloqueio**), 2026-11-27
- **Contexto:** Adendo 3 exige fonte oficial antes de implementar titularidade, certificado de terceiro e
  procuração RFB (serviço 00233)
- **Decisão:** separar os papéis no modelo e **não** implementar representação até haver contrato oficial

## Contexto

O produto emite em nome do cliente. Hoje o tenant é resolvido pela API key, e o CNPJ do emitente vem do
certificado A1 (`certificado.cnpj`). Isso funciona quando **titular do certificado = contribuinte**, que
é o caso do modo auto-hospedado.

No modo hospedado, três papéis podem divergir:

| Papel | Quem é | Existe no código? |
|---|---|---|
| Operador da plataforma | DZ23, dona da infraestrutura | não modelado |
| Contribuinte emitente | o cliente, sujeito passivo | `Tenant` + CNPJ do certificado |
| Titular do certificado | pode ser terceiro (procurador, contabilidade) | não distinguido |
| Procurador/outorgado | quem tem poderes na RFB para o serviço | **não existe** |

Sem separação, "posse do certificado" vira "autorização para emitir" — e isso não é verdade jurídica.

## Decisão

1. **`tenant_id` continua sendo a fronteira de isolamento**, derivada da credencial, nunca do corpo.
2. **Emitente é o CNPJ do certificado ativo** — comportamento atual, agora documentado como
   *pré-condição*: só vale quando titular = contribuinte.
3. **Representação por procuração fica BLOQUEADA.** Não haverá coluna `procurador`, nem integração
   simulada, nem fallback "confia no certificado", enquanto não existir documentação oficial do serviço
   00233 com endpoint, autenticação, campos, poderes, vigência e revogação.
4. **Certificado de terceiro sem procuração comprovada não pode emitir.** Como o sistema não sabe
   verificar procuração, o modo hospedado **não** aceita certificado de terceiro para emissão. O que ele
   aceita é o certificado do próprio contribuinte — e isso é declarado ao cliente no onboarding.
5. **Ambiguidade de certificado é erro, não escolha** (§80): 409 com os certificados listados.

## Consequências

- O modo hospedado **não atende** escritório de contabilidade que queira emitir por procuração. É uma
  limitação declarada, não um bug: atender exige o item 4 do Adendo 3.
- O modo auto-hospedado não é afetado: o cliente usa o próprio certificado.
- Quando a fonte oficial aparecer, a evolução é aditiva: colunas de representação, validação de vigência
  e revogação, e bloqueio por serviço/documento — **sem** mudar `/v1`.

## Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| Tratar posse de certificado como prova de representação | é exatamente o erro que o adendo proíbe; gera nota em nome de terceiro sem autorização |
| Integração "simulada" de procuração com dados de exemplo | contrato falso com aparência de pronto; pior que ausência |
| Estender a regra de procuração da NFS-e a NF-e/CT-e/MDF-e | cada serviço tem regra própria; o adendo veda a extensão automática |

## Evidência desta decisão

- `docs/REQUISITOS-FONTES.md` — REQ-4 `BLOCKED`, com o que falta exatamente;
- `sources/manifest.yaml` — nenhuma fonte oficial de procuração coletada;
- `app/certificates/service.py` — CNPJ vem do certificado; sem campo de procurador.

## Atualização 27/11/2026 — fonte oficial encontrada; decisão mantida, fundamento trocado

O FAQ oficial v1.5 (23/11/2026, Tema 28) e o comunicado do Release 2 (25/11/2026, atualizado 27/11/2026)
confirmam o **fluxo** e mudam o motivo do bloqueio:

**Confirmado pela fonte:**

1. a procuração eletrônica é concedida pelo **outorgante** (CPF/CNPJ) no **Portal de Serviços da Receita
   Federal**, para os **serviços da NFS-e**;
2. o procurador pode autenticar por certificado (e-CNPJ/e-CPF, inclusive de procurador), usuário/senha ou
   gov.br Prata/Ouro, e **alterna o perfil** para o outorgante;
3. a plataforma **valida o vínculo** no momento da troca de perfil;
4. **o emitente continua sendo o outorgante** — a representação não transfere titularidade;
5. a funcionalidade está **em produção desde 31/10/2026** e foi estendida à Produção Restrita no
   Release 2 (24/11/2026).

**Não confirmado pela fonte:**

- o código de serviço **`00233`** não aparece no FAQ consultado;
- **não há API documentada** para consultar vigência, revogação ou procuradores;
- o grupo de XML para registrar nota emitida por representante só entra na **Release 3** (prevista para
  07/12/2026, "nova versão da NT009 a ser publicada").

**Consequência para esta decisão:** o bloqueio de representação por procuração **permanece**, mas por
motivo diferente do registrado antes. Não é "não existe representação": ela existe, funciona e está em
produção. O que falta ao sistema é **como verificar** o vínculo sem uma API oficial, e **onde registrar**
o representante no XML, que ainda não foi publicado. Autorizar emissão confiando apenas na posse do
certificado continuaria sendo o erro que este ADR proíbe.

**O que faria esta decisão mudar:** publicação de endpoint oficial de consulta de procuração (vigência e
revogação) **e** da versão da NT-009 com o grupo de representante. Com os dois, a implementação é aditiva:
colunas de representação, validação de vigência e bloqueio por serviço/documento, sem mudar `/v1`.

**Evidência atualizada:**

- `sources/manifest.yaml` — 15 fontes com hash, incluindo FAQ v1.5 e o comunicado do Release 2;
- `docs/REQUISITOS-FONTES.md` — REQ-4 `PARTIAL` (fluxo) / `BLOCKED` (API), com a citação do que a fonte
  diz e do que ela não diz.
