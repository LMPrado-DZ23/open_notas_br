# Matriz de requisitos — Adendo 3 (evidências oficiais)

**Data:** 2026-11-27 · **Agente:** dsh · **Base:** branch `work/auditoria-e-fase-a`
**Manifesto:** [`sources/manifest.yaml`](../sources/manifest.yaml)

Estados possíveis: `PASS` · `PARTIAL` · `NOT_TESTED` · `BLOCKED`.
Nenhuma linha abaixo foi marcada `PASS`: todas dependem de fonte oficial que **não foi obtida** nesta
execução. O que existe é código anterior aos requisitos, e ele **não** foi alterado por este adendo.

## Resumo

| REQ | Tema | Estado | Por quê |
|---|---|---|---|
| REQ-1 | XSD NT-009 (2026-11-24) + `indDest` | **PARTIAL** | **fonte obtida** em 2026-11-27: `esquemas-xsd-producao-restrita-20261124.zip` (sha256 `1ca83c1a…`) declara `finNFSe`, `indDest`, `vAjusteBC`. Falta adotar o schema, documentar a regra de `indDest` e validar (implementação não feita) |
| REQ-2 | `condominios` / `imovel.unidades` / 99.05.01 | **PARTIAL** | **fonte obtida**: NT-009 v1.01, Anexo I (DPS 2026-11-24) e Anexo VI v1.04.01; o XSD oficial declara `condominios`, `gCobranca`, `gDetCobranca`, `unidades`. Falta a tabela campo a campo e os testes |
| REQ-3 | Anexo VIII: 110019000 / 020201 / 200046 | **NÃO IMPLEMENTAR (fonte diz que não há regra)** | Anexo VIII v1.02.00, Anexo B (NBS 110019000) e Anexo C (020201) obtidos. A **página oficial** do Anexo VIII avisa: "apenas um trabalho inicial, ainda em desenvolvimento" e "**NÃO HÁ REGRAS DE NEGÓCIO BASEADAS NESTE ANEXO** no Piloto RTC nem em Produção". Codificar roteamento a partir dele contrariaria a fonte |
| REQ-4 | Titularidade, certificado de terceiro, procuração RFB 00233 | **BLOCKED** | documentação técnica oficial do serviço não localizada. Achado secundário (não oficial) indica **indisponibilidade** de procuração eletrônica para as APIs da NFS-e — tratado como pista, não como prova |
| REQ-5 | Contrato multitenant (tenant ≠ emitente ≠ certificado ≠ operador) | **PARTIAL** | campos existem e são usados; falta `procurador` e vínculo certificado↔estabelecimento |

## Detalhe por requisito

### REQ-1 — Pacote XSD NT-009 de 2026-11-24 e `indDest`

| Evidência | Resultado |
|---|---|
| Página oficial "Documentação atual" (acesso 2026-11-27) | oferece `esquemas-xsd-v1.01-20260209.zip` — **2026-02-09** |
| Página oficial "Arquivos dos esquemas XSD" (NFS-e via) | oferece `schemas_v1-01_atualizado.zip` (Via, v1.01) |
| Link para pacote NT-009 / 2026-11-24 | **não existe** nas duas páginas |
| `grep` nos XSD oficiais 1.01 baixados | `finNFSe` 0 · `vAjusteBC` 0 · `indDest` 0 |
| `grep` no manual ADN v1.1 (2026-11-03, 5 páginas) | `NT-009` 0 · `indDest` 0 |
| XSD do repositório × oficial | **diferentes**: `DPS_v1.01.xsd` repo `678 B` / `c7dab363…`; oficial `691 B` / `fe45e525…` |

**Consequência:** o repositório declara `LEIAUTE_NT009` em `app/nfse/constants.py:112` mas valida contra
um XSD que não é o oficial e não conhece os elementos da NT-009. Prova de divergência já existe
(`tests/test_leiaute_nt009_guard.py`, `xfail(strict=True)`).

**Falta exatamente:** URL oficial do pacote NT-009 de 2026-11-24 (ou comunicado que o identifique), com
os arquivos e o hash. Sem isso não se escreve schema, não se deriva `indDest` e não se prova
não-regressão em `tp_amb=1`.

### REQ-2 — `condominios`, `imovel.unidades`, 99.05.01

| Evidência | Resultado |
|---|---|
| `grep` `condomin` em `app/`, `src/`, `tests/`, `docs/` | **0** |
| `grep` `99.05.01`, `gCobranca`, `gDetCobranca`, `CIB` | **0** |
| XSD oficiais baixados | não declaram os grupos |
| Manual/leiaute oficial com cardinalidade e obrigatoriedade | **não obtido** |

**Falta exatamente:** manual oficial versionado que defina o grupo `condominios`, o grupo
`imovel.unidades`, cardinalidade/obrigatoriedade/tipos de cada campo e a regra do código `99.05.01`.
Sem ele, a tabela campo-a-campo exigida pelo adendo não pode ser produzida — e produzi-la por inferência
seria inventar leiaute.

### REQ-3 — Anexo VIII e os três códigos

| Evidência | Resultado |
|---|---|
| `grep` `110019000`, `020201`, `200046`, `Anexo VIII` no código | **0** |
| Validação existente | só formato: `dps.py:38-40` (6/6/9 dígitos), `tribISSQN` como conjunto `{1,2,3,4}` (`dps.py:47`) |
| Página de Resoluções CGNFS-e | índice localizado e preservado; **nenhum documento aberto** |

**Falta exatamente:** ato oficial (Resolução/NT) que fixe os três códigos, seu significado, a relação com
o item de serviço e a **exceção de rota** — inclusive a condição objetiva que faz o sistema escolher a
rota excepcional. Sem isso não se codifica nem a exceção nem o fallback.

**Conflito registrado:** §77 bloqueia emissão nacional em município não aderente fora da obrigação do
Simples. A exceção do Anexo VIII só pode entrar com a fonte que a sustente; implementá-la por hipótese
reintroduziria o defeito que §77 corrigiu.

### REQ-4 — Titularidade, certificado de terceiro e procuração RFB

| Evidência | Resultado |
|---|---|
| Campos de titularidade no código | `Tenant`, `TenantCertificate.cnpj`, `certificado_cnpj` na DPS |
| `procurador` / `outorgado` / `00233` | **0** ocorrências |
| Endpoint oficial de consulta de procuração | **não localizado** |
| Campos de vigência/revogação | inexistentes |

**Falta exatamente:** documentação normativa e técnica oficial que responda os 4 itens do adendo
(emitente jurídico com certificado de terceiro; distinção titular/contribuinte/responsável técnico/
procurador/operador; campos do XML/JSON; e o contrato do serviço oficial de procuração com endpoint,
autenticação, campos, poderes, vigência e situação). Sem isso, **nenhuma integração simulada** será
criada — conforme o adendo.

### REQ-5 — Contrato multitenant (parcial, e é o que já existe)

| Aspecto | Estado |
|---|---|
| Tenant vem da credencial, nunca do corpo | ✅ implementado e testado |
| `tenant_id` ≠ CNPJ emitente (certificado define o emitente) | 🌗 parcial: o CNPJ vem do certificado, sem vínculo formal certificado↔estabelecimento |
| Certificado ambíguo bloqueia em vez de escolher | ✅ §80 (409) |
| `procurador`/`outorgado` separado do operador | ❌ não existe |
| Bloqueio de emissão em nome de terceiro sem procuração | ❌ não existe (não há o conceito) |

## O que este adendo **não** mudou no código

Nada de schema, código fiscal, rota ou integração foi implementado nesta execução. A única alteração de
código relacionada é a de §80 (certificado ambíguo → 409 e guarda `xfail` do gap XSD), que **endurece** o
sistema em vez de supor regra.

## Próximo passo necessário (bloqueio real)

1. Fornecer/indicar a URL oficial do **pacote NT-009 de 2026-11-24** (ou comunicado que o nomeie).
2. Fornecer o **manual/leiaute** de `condominios` e `imovel.unidades`.
3. Fornecer o **ato do Anexo VIII** com os três códigos e a exceção de rota.
4. Fornecer a **documentação oficial do serviço de procuração RFB 00233** com endpoint e campos.

Com qualquer um desses em mão, o ciclo é: baixar → hash → registrar no manifesto → atualizar esta matriz
→ implementar só o contrato comprovado → testar positivo/negativo → revisão independente.

---

## Atualização 2026-11-27 (segunda rodada) — a busca encontrou o que a navegação não achou

**Correção de um erro meu, registrada de propósito.** Na primeira rodada eu afirmei que o pacote XSD da
NT-009 de 24/11/2026 "não existe nas páginas oficiais" e que só havia o de 2026-02-09. **Estava errado**:
eu tinha navegado apenas por `documentacao-atual` e `arquivos-dos-esquemas-xsd`, sem usar busca e sem
abrir as páginas **RTC** e **Documentação Técnica (Homologação/testes)**. O usuário cobrou o uso da busca;
com ela, os quatro itens apareceram em minutos.

### Fontes obtidas agora (hash no manifesto)

| Fonte | Arquivo | Bytes | SHA-256 (16) |
|---|---|---|---|
| **Esquemas XSD Produção Restrita 2026-11-24** | `esquemas-xsd-producao-restrita-20261124.zip` | 39.728 | `1ca83c1a7929f6d5` |
| Anexo I — DPS NFSe v1.01 2026-11-24 | `.xlsx` | 245.045 | `cf4d1d36daae5600` |
| NT-009 v1.01 (01/10/2026) | `.pdf` | 703.145 | `cc86c9402e317e84` |
| Anexo VI — Leiautes/Regras RTC v1.04.01 | `.xlsx` | 296.297 | `103a150dd6f56ec8` |
| Anexo VII — IndOp v1.03.00 | `.xlsx` | 27.475 | `95f30a44ee94adee` |
| **Anexo VIII v1.02.00 (26/10/2026)** | `.xlsx` | 151.656 | `12cc80bc92687856` |
| Anexo B — NBS 2.0 v1.01 | `.xlsx` | 84.980 | `1c07fd27ea447adc` |
| Anexo C — IndOp v1.01 | `.xlsx` | 17.966 | `f13b08dc802e82c3` |

O pacote de 24/11/2026 **declara** `finNFSe` (`TSRTCFinNFSe`), `indDest` (`TSRTCIndDest`), `vAjusteBC`
(`TCInfoAjusteBC`), `condominios` (`TCRTCInfoCondominios`), `gCobranca`, `gDetCobranca` e `unidades` —
exatamente os elementos que eu havia declarado ausentes.

### O que isso muda nos estados

- **REQ-1 e REQ-2 saem de BLOCKED para PARTIAL**: a fonte existe e está preservada com hash; falta
  adotar o schema, documentar a regra de `indDest`, montar a tabela campo a campo e testar. Nada disso
  foi implementado nesta rodada — e não será por inferência.
- **REQ-3 muda de natureza.** O Anexo VIII foi obtido, mas a própria página oficial do gov.br diz, em
  destaque, que ele é "apenas um trabalho inicial, ainda em desenvolvimento" e que "**NÃO HÁ REGRAS DE
  NEGÓCIO BASEADAS NESTE ANEXO** no ambiente do Piloto RTC (Produção Restrita) nem em Produção".
  Implementar o roteamento de Anexo VIII com códigos fixos seria **contrariar a fonte**, não cumpri-la.
  Registro como decisão fundamentada, não como pendência.
- **REQ-4 continua BLOCKED.** A busca trouxe apenas fonte secundária (ofício de entidade pedindo a
  implementação de procuração para as APIs da NFS-e), o que é **pista**, não documentação oficial.

### O que NÃO foi feito nesta rodada

Nenhum schema foi adotado, nenhum campo de condomínio foi implementado, nenhuma regra de `indDest` foi
escrita. A regra do projeto (prompt §9) e o Adendo 3 exigem, antes de codificar: preservar o pacote,
validar os **dois leiautes**, documentar a regra e provar não-regressão. Isso é a próxima fatia, e ela
começa pela adoção do XSD de 24/11/2026 com manifesto próprio.
