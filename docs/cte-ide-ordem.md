# CT-e: ordem obrigatória dos elementos de `ide`

Extraído de `tests/fixtures/schemas/cte-4.00/cteTiposBasico_v4.00.xsd` por
`python -m scripts.extrair_ordem_cte ide` — **não** de memória, e não de tentativa e erro.

O leiaute do CT-e define `xs:sequence`: a ordem importa tanto quanto o conteúdo. Um gerador
que emita os campos certos fora de ordem é recusado pelo schema antes de qualquer validação
de valor.

```
ide: 24 elementos (ordem obrigatória)
  1. cUF
  2. cCT
  3. CFOP
  4. natOp
  5. mod
  6. serie
  7. nCT
  8. dhEmi
  9. tpImp
 10. tpEmis
 11. cDV
 12. tpAmb
 13. tpCTe
 14. verProc
 15. cMunEnv
 16. xMunEnv
 17. UFEnv
 18. modal
 19. tpServ
 20. indIEToma
 21. dhSaidaOrig
 22. dhChegadaDest
 23. escolha(toma/toma/tomaTerceiro/toma/CNPJ/CPF/IE/xNome/xFant/fone/enderToma/email)
 24. ??
```

## Como usar

1. Monte o XML seguindo esta ordem dentro de `ide`.
2. Valide com `app.cte.validar(xml)` — ele aponta o próximo campo faltante com a linha.
3. Repita para `emit`, `dest`, `vPrest`, `imp` e `infCTeNorm` com
   `python -m scripts.extrair_ordem_cte <grupo>`.

## Contexto

O gerador de CT-e foi tentado e **removido** (não commitado): o schema recusou
`CTe@versao` na raiz e depois apontou `cMunEnv` e a cadeia seguinte. Este documento existe
para que a próxima tentativa comece pela ordem certa em vez de descobri-la por erro.
