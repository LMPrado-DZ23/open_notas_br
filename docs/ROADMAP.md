# Roadmap

Ordem por valor entregue, não por facilidade. Cada item diz o que destrava e como
saber que ficou pronto.

## v0.1 — feito

Auditoria offline de NF-e, NFC-e e CT-e com 37 regras, CLI, API opcional,
relatório JSON versionado, 151 testes, documentação de limites.

## v0.2 — confiança no mundo real

Objetivo: parar de supor que o XML real se parece com a fixture.

1. **Validar contra XML real (anonimizado).**
   Rodar a ferramenta em um conjunto de notas reais e anotar, regra por regra,
   onde há falso positivo. Sem isso, o resto é suposição.
   *Pronto quando:* existir `docs/CALIBRAGEM.md` com taxa de falso positivo por
   regra e as regras ruidosas rebaixadas ou corrigidas.

2. **Suporte a XML codificado em ISO-8859-1.**
   Alguns emissores antigos não emitem UTF-8. O parse da stdlib respeita a
   declaração, mas falta teste e mensagem de erro clara para o caso.
   *Pronto quando:* houver fixture em latin-1 passando e teste de erro de
   decodificação.

3. **`--recursivo` e resumo de lote.**
   Auditoria de diretório inteiro com contagem agregada por código de regra.
   *Pronto quando:* `notasbr auditar pasta/ --recursivo --resumo` listar os
   códigos mais frequentes.

4. **Supressão justificada.**
   Arquivo de configuração por projeto (`notasbr.toml`) para silenciar regra
   específica com justificativa registrada no relatório.
   *Pronto quando:* a supressão aparecer em `regras_suprimidas` no JSON com o motivo.

## v0.3 — schema de verdade

5. **Validação XSD opcional.**
   Extra `notasbr[xsd]` com `lxml`, carregando os XSD oficiais de um diretório
   informado pelo usuário. Nunca embutir XSD no pacote (licença e versionamento).
   *Pronto quando:* regra `SCHEMA-001` reprovar documento inválido contra XSD real
   e ficar explicitamente pulada quando o XSD não for fornecido.

6. **Conferência de totais por nota técnica.**
   Com base de casos reais, promover `TOTAL-COMPOSICAO-001` de informação para
   erro, com a fórmula correta por versão de layout e indicador de operação.

## v0.4 — NFS-e

7. **NFS-e municipal por plugin de layout.**
   Um layout por módulo, registrado por `(município, versão)`. Sem tentativa de
   generalizar antes de ter dois ou três layouts reais funcionando.
   *Pronto quando:* dois municípios auditados com fixture real anonimizada.

8. **NFS-e padrão nacional (DPS).**
   Só depois que o layout nacional estabilizar o suficiente para existir um XSD
   que não mude a cada mês.

## v0.5 — emissão e transmissão

Pré-requisito: certificado A1 e credenciamento em homologação. Sem isso, não
começar.

9. **Assinatura de XML** com A1 (PKCS#12), reusando `signxml`.
10. **Envelope SOAP e resolução de endpoint por UF/ambiente**, com tabela de
    endpoints versionada e teste de contrato contra o serviço de homologação.
11. **Consumo de `retConsReciNFe`** e ciclo de autorização (enviar, consultar
    recibo, tratar `cStat`).
12. **Eventos**: cancelamento e carta de correção.

## Fora do roadmap

- Substituir contador ou parecer fiscal. Não é o produto.
- Classificação fiscal automática de produto. Exige base normativa e
  responsabilidade que a ferramenta não deve assumir.
- Emissão em produção sem ambiente de homologação validado antes.

## Como priorizar

Se aparecer conflito entre "mais regras" e "menos falso positivo", ganha menos
falso positivo. Uma ferramenta que reprova documento legítimo é abandonada na
primeira semana; uma que deixa passar caso de borda continua sendo usada e
melhorada.
