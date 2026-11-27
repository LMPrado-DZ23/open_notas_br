# Adendo 3 — Evidências oficiais

Este adendo deve ser aplicado antes de qualquer implementação relacionada aos quatro pontos abaixo. O objetivo é transformar cada dependência regulatória em evidência verificável, com origem oficial, versão, data e hash. Sem a evidência correspondente, o código deve permanecer bloqueado.

## Regra geral de bloqueio

- Não inventar XSD, namespace, versão, endpoint, campo, código, regra de roteamento ou interpretação jurídica.
- Não usar blog, repositório de terceiro, exemplo de payload ou resposta de IA como fundamento oficial.
- Toda fonte deve ser preservada com URL oficial, título, órgão, data de acesso, versão/publicação e SHA-256 do arquivo baixado.
- Se a fonte oficial não estiver disponível, registrar `NOT_TESTED` ou `BLOCKED`, explicar a lacuna e não criar schema ou regra aproximada.
- Alterações regulatórias devem ser versionadas; não sobrescrever silenciosamente uma fonte anterior.

## 1. Pacote XSD oficial NT-009

Obter o pacote oficial identificado como **NT-009, publicado ou atualizado em 24/11/2026**, somente de fonte oficial do órgão responsável. Antes de escrever qualquer schema:

1. Registrar URL direta, órgão/publicador, título exato, versão, data de publicação, data de acesso e nome de cada arquivo.
2. Baixar o pacote sem alterar seu conteúdo e gerar manifesto SHA-256 de todos os arquivos.
3. Registrar namespaces, imports/includes, dependências externas, leiautes e códigos de versão encontrados.
4. Confirmar se existem dois leiautes distintos e mapear qual versão é aplicável a cada cenário.
5. Validar exemplos oficiais nos dois leiautes, em `tp_amb=1`, sem usar produção.
6. Derivar `indDest` somente a partir de regra oficial documentada; registrar a decisão em teste e documentação.
7. Criar teste de não regressão que prove que documentos válidos anteriores continuam válidos quando a regra oficial permitir.

### Critério de aceite

`PASS` somente com pacote oficial preservado, manifesto SHA-256, validação dos dois leiautes, regra documentada de `indDest` e teste de não regressão executado. Sem isso: `BLOCKED`.

## 2. Grupos `condominios` e `imovel.unidades`

Localizar o manual e o leiaute oficial que definem:

- grupo `condominios`;
- grupo `imovel.unidades`;
- cardinalidade, obrigatoriedade, tipos e restrições de cada campo;
- versão do manual/leiaute;
- relacionamento entre condomínio, imóvel e unidade;
- regra oficial associada ao código `99.05.01`.

Não implementar esses grupos apenas com base no nome dos campos ou em payload de exemplo. Produzir uma tabela campo a campo com: caminho XML/JSON, tipo, tamanho/formato, cardinalidade, enumeração, condição de preenchimento, fonte e teste correspondente.

### Critério de aceite

`PASS` somente com manual oficial versionado, referência explícita à regra `99.05.01`, schema/contrato atualizado e testes positivos e negativos. Sem manual e versão: `NOT_TESTED` e implementação bloqueada.

## 3. Anexo VIII e códigos de serviço

Encontrar a Resolução, Nota Técnica ou ato oficial que fixe os códigos:

```text
110019000
020201
200046
```

A evidência deve demonstrar:

- órgão emissor, número, versão e vigência do Anexo VIII;
- significado de cada código;
- relação entre código, item de serviço e tributação;
- exceção de rota mencionada na regra;
- condição que faz o sistema usar a rota normal ou a rota excepcional;
- fonte oficial para cada cenário e para cada fallback.

Implementar a identificação do cenário como regra explícita e testável, nunca como busca parcial ou heurística silenciosa. O sistema deve registrar a fonte/regra que justificou a rota escolhida e rejeitar combinações ambíguas quando não houver regra oficial.

### Critério de aceite

`PASS` somente com ato oficial preservado, códigos vinculados a seus significados, exceção de rota documentada e matriz de cenários com testes. Sem a fonte do Anexo VIII: não codificar os códigos nem a exceção.

## 4. Titularidade, certificado de terceiro e procuração RFB

Documentar, com fonte normativa e técnica oficial:

1. Quem é o emitente jurídico e fiscal quando o certificado utilizado pertence a terceiro.
2. Diferença entre titular do certificado, contribuinte emitente, responsável técnico, procurador e operador da API.
3. Quais campos do XML/JSON identificam o emitente, responsável técnico e eventual representante.
4. O que a API ou serviço oficial da RFB expõe sobre procuração eletrônica:
   - endpoint oficial;
   - autenticação exigida;
   - campos retornados;
   - outorgante e outorgado;
   - poderes/serviços abrangidos;
   - data de início e término;
   - situação ativa, revogada, cancelada ou expirada;
   - forma oficial de consulta e evidência da revogação.

Não assumir que posse de certificado, login gov.br ou contrato comercial prova representação. A API deve separar `tenant_id`, contribuinte emitente, certificado usado, procurador/outorgado e operador técnico. Sem procuração válida e compatível com o serviço, bloquear emissão em nome de terceiro.

### Critério de aceite

`PASS` somente com fonte oficial normativa/técnica, contrato de dados documentado, testes de titularidade e casos de procuração ativa, expirada, revogada e inexistente. Sem endpoint ou documentação oficial confirmada: marcar `NOT_TESTED`; não criar integração simulada.

## Entregáveis obrigatórios do próximo ciclo

- `sources/manifest.yaml` ou equivalente, contendo URL, órgão, versão, data de acesso, arquivo e SHA-256;
- matriz `REQ-ID | fonte oficial | evidência | implementação | teste | estado`;
- schemas e contratos somente após os gates dos itens 1–3;
- ADR para titularidade e representação do item 4;
- testes executados com saída registrada;
- lista separada de `PASS`, `PARTIAL`, `NOT_TESTED` e `BLOCKED`;
- nenhum segredo, certificado, senha, token ou dado pessoal em Git, log, fixture ou manifesto.

## Ordem de execução

1. Coletar e validar as quatro fontes oficiais.
2. Gerar manifestos e hashes.
3. Atualizar a matriz de requisitos.
4. Implementar somente os contratos comprovados.
5. Executar validação XML/JSON e testes de não regressão.
6. Fazer revisão independente procurando regra inventada, mistura de titularidade, fallback inseguro e produção liberada sem credencial do cliente.

**Situação:** adendo preparado para revisão e envio ao DeepSeek; não enviado automaticamente.
