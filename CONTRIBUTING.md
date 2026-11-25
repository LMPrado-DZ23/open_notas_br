# Como contribuir

Obrigado pelo interesse. Este projeto lida com **documento fiscal**, então a regra
que vale acima das outras é: **não inventar**. Se algo não está confirmado contra a
documentação oficial, tem que estar marcado como tal.

## Antes de abrir PR

```bash
python -m pip install -e ".[app,dev]"
ruff check . && ruff format --check .
pytest
```

O CI roda exatamente isso, mais a validação contra os XSD oficiais.

## Regras de contribuição

1. **Transparência obrigatória.** Toda referência a endpoint, código de erro, layout
   ou regra fiscal precisa de etiqueta:
   - `[CONFIRMADO]` — verificado contra fonte oficial (cite qual).
   - `[INFERIDO]` — inferência razoável (explique de onde veio).
   - `[A VALIDAR]` — depende de acesso ou validação que ainda não existe.

2. **`[A VALIDAR]` fica isolado.** Vai em adapter, dublê ou tabela substituível —
   nunca espalhado na lógica principal.

3. **Sem código incompleto.** Nada de `TODO`, `...` ou `raise NotImplementedError`
   como marcador de trabalho futuro na lógica principal. Se falta informação,
   documente o que falta e por quê.

4. **Sem segredo no repositório.** Nenhum `.pfx`, `.p12`, `.env`, token ou senha.
   Há teste que falha se aparecer.

5. **Teste o comportamento, não o inventário.** Um teste que afirma que uma lista
   tem 7 itens quebra a cada item novo sem indicar defeito. Prefira verificar o que
   o código garante.

6. **Controle negativo quando validar contrato.** Se você escreve um teste que diz
   "meu XML valida contra o XSD", inclua um caso que o schema *recusa* — senão o
   teste pode estar passando sem validar nada.

## Onde é mais fácil ajudar

- **Novos tipos de evento**: o catálogo fica em `app/nfse/eventos_tipos.py` e já
  cobre os 16 do leiaute 1.01.
- **Municípios que não aderiram ao padrão nacional**: a integração municipal está
  como `[A VALIDAR]` e precisa de um adapter por padrão de prefeitura.
- **Guias de arrecadação (MAN/DNA, DAS)**: os provedores são determinísticos; falta
  a chamada real.
- **DANFE/DACTE/DAMDFE**: o leiaute visual está `[A VALIDAR]` contra os MOC oficiais.

## Reportando problema fiscal

Se um documento foi gerado com dado errado, abra issue com:
- o XML gerado (pode anonimizar nome e documento do tomador),
- a etiqueta de confiança daquela parte do código,
- e o que a SEFIN respondeu, se houver.

Não cole certificado, senha ou dado pessoal de terceiro.

## Licença

Ao contribuir você concorda em licenciar sua contribuição sob a licença MIT deste
repositório.
