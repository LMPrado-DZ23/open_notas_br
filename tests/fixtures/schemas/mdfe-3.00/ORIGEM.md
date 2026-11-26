# Schemas de MDF-e 3.00 — origem e versão

Pacote oficial de esquemas XML do MDF-e, versão **3.00**, obtido do Portal do Conhecimento
de Transporte Eletrônico (mesma página dos schemas de CT-e).

| Campo | Valor |
|---|---|
| Página de origem | https://www.cte.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=0xlG1bdBass%3D |
| Link do pacote | https://www.cte.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=KnJNEIBHgBg= |
| Formato | ZIP, `application/zip` |
| Arquivos `.xsd` extraídos | 41 |
| Obtido em | 2026-11-26 |
| Integridade | SHA-256 por arquivo em `data/xsd_manifest.json` |

## Como este pacote foi localizado

A página lista 69 anexos. Testar cada um por `Content-Type` e depois **abrir o ZIP** foi o que
identificou o pacote certo: os candidatos incluem BP-e, CT-e, MDF-e e outros documentos, e o
nome do arquivo não é revelado pela página. O critério de identificação foi a presença de
`mdfe`/`MDFe` nos nomes dos `.xsd`.

## O que este pacote NÃO prova

- **Não** foi validado contra um MDF-e autorizado real: nenhum foi transmitido.
- Cobre o leiaute 3.00, vigente na data de obtenção; uma NT posterior pode substituir arquivos.
- Não cobre CT-e, que tem pacote próprio em `cte-4.00`.

## Armadilha

Os arquivos vêm do ZIP com **CRLF**. Os 41 foram normalizados para LF **antes** de gerar o
manifesto SHA-256, porque o manifesto compara bytes e o CI faz checkout em LF.
