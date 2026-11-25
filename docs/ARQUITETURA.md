# Arquitetura

## Princípio condutor

O núcleo não deve exigir instalação pesada para ser útil. Um contador que quer
conferir um XML precisa rodar um comando, não montar um ambiente com FastAPI,
lxml, criptografia e driver de banco. Por isso: **stdlib para o núcleo, extras
opcionais para o resto**. Hoje o núcleo instala com zero dependências.

## Camadas

```
                    ┌──────────────────────────────┐
   XML em disco ──▶ │ xml_util.parse_seguro        │  recusa DTD/ENTITY, limita tamanho
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │ auditor._detectar            │  raiz → nfe | cte, ou erro claro
                    │ auditor._preparar_contexto   │  extrai chave, versão, emitente
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │ regras.Contexto + REGRAS      │  cada regra lê e registra achados
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │ modelos.Relatorio.to_dict()   │  contrato notasbr.relatorio/1
                    └──────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
          cli.main()           api:app            uso como biblioteca
```

## Módulos

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `versao.py` | versão da ferramenta e do contrato JSON | — |
| `erros.py` | hierarquia de exceções de domínio | — |
| `cadastros.py` | CNPJ/CPF: DV módulo 11, formatação, mascaramento | — |
| `chave.py` | chave de 44 dígitos: layout, DV, decomposição | `cadastros`, `erros` |
| `xml_util.py` | parse seguro, navegação por nome local, `Decimal`, caminhos | `erros` |
| `modelos.py` | `Achado`, `Pulada`, `Resumo`, `Relatorio` | `versao` |
| `regras/base.py` | `Contexto`, registro `@regra`, tolerância monetária | `modelos`, `xml_util` |
| `regras/*.py` | as 37 regras, agrupadas por família | `regras/base` |
| `auditor.py` | orquestra detecção, regras e montagem do relatório | tudo acima |
| `cli.py` | argparse, saída texto/JSON, códigos de saída | `auditor` |
| `api.py` | FastAPI (extra `api`) | `auditor` + FastAPI |

## Decisões estruturais que sustentam o resto

**Navegação por nome local, não por nome qualificado.** NF-e e CT-e usam default
namespace, e há emissor que troca prefixo. `xml_util.navegar` compara o nome local
da tag, então `<ns0:infNFe>` e `<infNFe>` são o mesmo caminho. O namespace do
documento é conferido **uma vez**, pela regra `DOC-NS-001`, em vez de espalhar
verificação de URI por 37 regras.

**`Contexto` separa corpo de raiz.** Quase toda regra lê dentro de `infNFe`/
`infCte`, então `ctx.txt("ide/nNF")` já é relativo ao corpo e o caminho do achado
sai prefixado automaticamente. Mas `Signature` e `protNFe` são **irmãos** do
corpo; para esses existe `ctx.elem_raiz` / `erro_em`, que reportam o caminho real.
Essa distinção nasceu de um bug real: achados de assinatura apareciam como
`infNFe/Signature` antes dessa correção.

**Falha de regra é achado, nunca silêncio.** Cada regra roda dentro de
`try/except`. Uma exceção vira `MOTOR-001` com severidade **erro**. O pior
resultado possível de um bug é um relatório reprovado com explicação — nunca um
"aprovado" por omissão. Há teste cobrindo exatamente isso.

**Regra pulada é registrada.** Quando falta pré-requisito (a assinatura não tem
certificado, a chave é inválida), a regra chama `ctx.pular(...)` em vez de
retornar em silêncio. O consumidor vê `regras_puladas` e sabe o que não foi
avaliado. Regra pulada não conta como satisfeita.

**Severidade calibrada por certeza, não por gravidade percebida.** Onde a regra
oficial varia por nota técnica ou por UF, o achado é `aviso` ou `informacao`, não
`erro`. Reprovar documento legítimo destrói a confiança mais rápido do que deixar
passar um caso de borda. Exemplos deliberados: `CHAVE-AMM-002` (fuso e
contingência), `TOTAL-COMPOSICAO-001` (composição de `vNF`),
`TRIB-CRT-001` (exceções de regime).

## O registro de regras e sua armadilha

`@regra` adiciona a função a `REGRAS` no import do módulo. Um módulo de regra que
não é importado em `regras/__init__.py` **nunca executa** — e o relatório sai
"aprovado" sem aquela checagem. É a falha silenciosa clássica dessa arquitetura.

Mitigação atual: o import explícito em `regras/__init__.py` e o teste
`test_lista_catalogo`, que verifica a presença de regras específicas no catálogo.
Se você adicionar um módulo, adicione o import.

## Fluxo de dados do relatório

1. `parse_seguro` valida tamanho, ausência de DTD e boa formação.
2. `_detectar` mapeia a raiz para `nfe` ou `cte`; raízes conhecidas mas não
   auditáveis (`enviNFe`, `procEventoNFe`) geram mensagem específica.
3. `_preparar_contexto` localiza o corpo, extrai a chave do `Id` (com fallback
   para o protocolo), tenta `ChaveAcesso.parse` e coleta emitente, destinatário,
   valor total e ambiente.
4. As regras do tipo rodam em ordem de registro.
5. `Relatorio.to_dict()` ordena achados por severidade e código e serializa.

## Testes

151 testes, organizados por camada: unidade (chave, cadastros, xml_util), regra a
regra (uma mutação por caso, a partir de fixture autoconsistente), CLI (códigos de
saída e JSON) e API (só roda com o extra instalado).

As fixtures são **sintéticas e geradas por código** (`tests/construir.py`), não
XML gravado em disco. Gerar por código garante que a chave, o `cDV` e os totais
sejam sempre coerentes, e deixa a mutação de um caso explícita.

## O que mudaria com transmissão

A camada de transporte entraria ao lado de `auditor`, não dentro das regras:
`transport/` com envelope SOAP, resolução de endpoint por UF e ambiente, e um
cliente de certificado A1. As regras continuariam lendo XML — inclusive o XML da
resposta da SEFAZ. Essa separação é o motivo de o núcleo não conhecer rede.
