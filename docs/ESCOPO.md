# Escopo e limites

Este documento existe para tornar explícito o que a ferramenta **não** faz. Um
auditor fiscal que não declara os próprios limites induz a decisão errada, e a
decisão errada aqui é tratar documento inconsistente como autorizado.

## Problema que resolve

XML de nota fiscal chega de terceiros — fornecedor, transportadora, sistema
legado, integração malfeita. Antes de lançar no ERP, no financeiro ou na
contabilidade, alguém precisa responder:

1. Este XML está internamente coerente?
2. A chave de acesso corresponde ao que está escrito dentro do documento?
3. Os valores fecham?
4. A assinatura está lá e é plausível?
5. O regime tributário declarado bate com o CST/CSOSN usado?

O `notasbr` responde isso de forma reprodutível, com o caminho exato do nó no XML
e sem depender de certificado digital, credenciamento ou rede.

## Dentro do escopo (v0.1)

| Capacidade | Como é verificada |
|---|---|
| Chave de acesso de 44 dígitos | Decomposição por layout fixo + DV módulo 11 |
| Coerência chave × documento | Campo a campo: UF, modelo, série, número, `tpEmis`, `cNF`, CNPJ do emitente |
| Coerência com o protocolo | `chNFe`/`chCTe` do `infProt` e `tpAmb` |
| Fechamento de totais | Soma dos itens × `vProd`, `vNF` × pagamentos (com `vTroco`) |
| Formato tributário | CFOP (4 dígitos e grupo), sentido × `tpNF`, NCM (8 dígitos), CST/CSOSN em tabela fechada |
| Coerência de regime | `CRT` do emitente × uso de CST ou CSOSN |
| Estrutura mínima | Raiz, namespace, versão do layout, campos escalares obrigatórios, `nItem` |
| Assinatura | Presença, `Reference/@URI`, `DigestValue`/`SignatureValue`, e verificação criptográfica opcional |
| CNPJ / CPF | Dígito verificador (módulo 11) |

## Fora do escopo (e por quê)

**Validação de schema XSD.** Exigiria carregar e versionar os XSD oficiais de
cada layout e de cada UF. Sem isso, uma "validação de schema" seria um subconjunto
disfarçado. A v0.1 faz conferência estrutural curada e declara isso. O caminho
para incluir XSD está no roadmap, como capacidade explícita e opcional.

**Cadeia de confiança do certificado.** Verificar o XMLDSig contra o certificado
embutido prova integridade em relação àquele certificado; **não** prova que ele é
ICP-Brasil, que não foi revogado ou que pertence a quem assinou. Fazer essa
distinção é obrigatório, senão o relatório promete mais do que entrega.

**Autorização na SEFAZ.** Confirmar `cStat=100` de verdade requer consulta ao
webservice com certificado e credenciamento. A ferramenta confia no `protNFe`
presente no arquivo e diz isso.

**NFS-e.** O cenário municipal é heterogêneo (centenas de layouts) e o padrão
nacional está em transição. Implementar pela metade produziria falso negativo em
escala. Está fora da v0.1 por decisão consciente, não por esquecimento.

**NCM e enquadramento fiscal.** A tabela NCM muda por ato normativo e a
classificação correta depende da operação. A ferramenta confere a **forma**
(8 dígitos), não o mérito.

**Idoneidade do emitente.** Situação cadastral, sonegação, fraude e crédito
tributário não são inferíveis de um XML.

## Fatos verificados vs. hipóteses neste repositório

**Verificado por teste automatizado** (151 testes):

- O algoritmo do DV reproduz um vetor conferido por três formulações independentes.
- CNPJ 11.222.333/0001-81 e CPF 111.444.777-35 são aceitos; variantes com DV
  trocado são rejeitadas.
- Cada regra tem ao menos um caso que a faz disparar e um caso que não a dispara.
- Documento com `DOCTYPE` é recusado; XML malformado vira erro de leitura.
- A API responde 422 para XML inválido e 413 acima do limite.

**Hipótese a validar com documento real** — a v0.1 foi construída e testada com
XML **sintético**. Nenhum XML real de contribuinte foi usado. Consequências:

- Fixtures podem não cobrir idiossincrasias de emissores reais (prefixos de
  namespace, campos opcionais ausentes por regime, `indPres`, `vTroco`).
- As tabelas de CST/CSOSN são fechadas e estáveis, mas a **coerência** exigida
  pela regra `TRIB-CRT-001` é um aviso, não um erro, justamente porque há
  exceções legítimas.
- A fórmula de composição de `vNF` está implementada como **informação**, não
  como erro, porque ela muda por nota técnica (ST, FCP, desoneração, IPI na base).

O próximo passo de validação é rodar a ferramenta contra um conjunto real e
anotar, regra por regra, onde há falso positivo. Isso está no roadmap como
primeira tarefa da v0.2.

## Público e uso pretendido

Desenvolvedor de integração, analista fiscal, time de QA de ERP, contador que
precisa de segunda opinião mecânica. Não é ferramenta de decisão fiscal: o
relatório é insumo para uma pessoa decidir.
