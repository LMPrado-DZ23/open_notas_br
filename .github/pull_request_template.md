## O que muda

<!-- Uma frase. Se precisar de duas, o PR está grande. -->

## Por que

## Etiqueta de confiança

- [ ] `[CONFIRMADO]` contra fonte oficial (cite no código)
- [ ] `[INFERIDO]` (explique de onde veio)
- [ ] `[A VALIDAR]` — isolado em adapter/dublê, não na lógica principal

## Verificação

```
ruff check . && pytest
```

<!-- Cole a saída real. "Deve funcionar" não é verificação. -->

## Checklist

- [ ] Sem segredo no diff (certificado, token, senha, `.env`)
- [ ] Teste novo falha sem a mudança e passa com ela
- [ ] Se valida contrato, há **controle negativo** (o schema recusa o caso errado)
- [ ] Docstring explica o *porquê*, não o *o quê*
