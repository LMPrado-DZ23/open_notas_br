# Schemas de CT-e 4.00 — origem e versão

Pacote oficial de esquemas XML do CT-e, versão **4.00**, obtido do Portal do Conhecimento de
Transporte Eletrônico.

| Campo | Valor |
|---|---|
| Página de origem | https://www.cte.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=0xlG1bdBass%3D |
| Link do pacote | https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=jLXuXo1j17A= |
| Formato | ZIP, `application/zip`, 98.680 bytes |
| Arquivos `.xsd` extraídos | 49 |
| Obtido em | 2026-11-26 |
| Integridade | SHA-256 por arquivo em `data/xsd_manifest.json` |

## Por que estes arquivos existem aqui

O gerador de XML de CT-e precisa validar contra o leiaute oficial antes de assinar e enviar.
Escrever o gerador sem schema produz XML que parece correto e é recusado na primeira
transmissão real, sem indicação clara do motivo.

## O que este pacote NÃO prova

- **Não** foi validado contra um XML autorizado real: nenhum CT-e foi transmitido.
- O pacote cobre CT-e (modelo 57), GTV-e, CT-e OS e CT-e Simplificado. **Não** cobre MDF-e
  (modelo 58), que exige pacote próprio.
- A versão 4.00 é a vigente na data de obtenção; uma NT posterior pode substituir arquivos.

## Armadilha registrada

Os arquivos vieram do ZIP com **CRLF**. O manifesto SHA-256 compara **bytes**: gerar o
manifesto antes de normalizar para LF produziu hashes que não batem no checkout Linux do CI —
foi exatamente o defeito que derrubou o CI no commit `4e2f293`. Por isso a normalização
acontece **antes** de `scripts.gerar_manifesto_xsd`, e `.gitattributes` força `eol=lf` nesta
árvore.
