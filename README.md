# open_notas_br

Auditoria **offline** de documentos fiscais brasileiros — NF-e, NFC-e e CT-e.

O programa lê o XML que você já tem e responde, regra por regra e com o caminho
exato no arquivo, o que está inconsistente: chave de acesso que não fecha, total
que não soma, CFOP de entrada em nota de saída, assinatura ausente, protocolo de
outra nota.

```
$ notasbr auditar nota.xml

nota.xml
  NF-e | layout 4.00 | 3525 0111 2223 3300 0181 5500 1000 0001 2311 2345 6782
  ambiente: Produção
  emitente: Empresa Exemplo LTDA | 11.222.333/0001-81 | SP
  valor total: 1000.00
  situação: REPROVADO (1 erro(s), 1 aviso(s), 1 info, 35 regra(s), 1 pulada(s))
  ERRO  TOTAL-VPROD-001: vProd total (999.00) difere da soma dos itens (1000.00)  [nfeProc/NFe/infNFe/total/ICMSTot/vProd]
  AVISO ASSIN-005: Signature sem X509Certificate: não é possível conferir a autoria  [nfeProc/NFe/Signature]
```

## O que ele é e o que ele não é

**É** um conferente de consistência: valida a aritmética da chave de acesso,
o fechamento dos totais, a coerência entre regime tributário e CST/CSOSN, a
estrutura do XMLDSig e a integridade do que está escrito no documento.

**Não é** emissor, não é transmissor, não é homologação junto à SEFAZ e não é
parecer fiscal. Em particular, ele **não**:

- valida contra o XSD oficial (a conferência de estrutura é curada, não schema validation);
- valida cadeia ICP-Brasil, revogação ou autenticidade do certificado;
- acessa a SEFAZ — não confirma autorização, cancelamento ou denegação;
- audita NFS-e (municipal ou padrão nacional);
- confere NCM ou enquadramento fiscal contra a legislação vigente;
- avalia idoneidade do emitente, fraude ou crédito tributário.

Essas limitações viajam **dentro do relatório**, no campo `limitacoes`. Quem
consome o JSON recebe junto o que a ferramenta não prova.

## Instalação

Requer Python 3.10+. O núcleo **não tem dependências externas**.

```bash
pip install -e .              # núcleo + CLI
pip install -e ".[api]"       # + API HTTP (FastAPI)
pip install -e ".[assinatura]" # + verificação criptográfica do XMLDSig
pip install -e ".[dev]"       # + pytest, ruff
```

## Uso

### Linha de comando

```bash
notasbr auditar nota.xml                    # relatório legível
notasbr auditar lote/*.xml --json           # JSON, um ou vários arquivos
notasbr auditar nota.xml --estrito          # aviso também reprova (saída 1)
notasbr auditar nota.xml --verboso          # mostra info, regras puladas e limitações

notasbr chave 35250111222333000181550010000001231123456782
notasbr cnpj 11.222.333/0001-81
notasbr cpf 111.444.777-35
notasbr regras                              # catálogo completo
```

Códigos de saída (úteis em CI e em script de lote):

| Código | Significado |
|---|---|
| `0` | aprovado, ou aprovado com avisos (sem `--estrito`) |
| `1` | reprovado: ao menos um erro (ou aviso com `--estrito`) |
| `2` | falha de leitura: XML inválido, arquivo não UTF-8, documento não suportado |
| `3` | erro de uso: arquivo inexistente, argumento inválido |

### Biblioteca

```python
from notasbr import auditar_arquivo, auditar_bytes, Severidade

relatorio = auditar_arquivo("nota.xml")

relatorio.aprovado  # False se houver erro
relatorio.resumo.situacao  # "aprovado" | "aprovado_com_avisos" | "reprovado"
relatorio.chave  # 44 dígitos, ou None
relatorio.valor_total  # "1000.00"

for achado in relatorio.por_severidade(Severidade.ERRO):
    print(achado.codigo, achado.caminho, achado.mensagem)

relatorio.to_dict()  # contrato JSON notasbr.relatorio/1
```

Erros de leitura são exceções, problemas de documento são achados:

```python
from notasbr import XmlInvalido, DocumentoNaoSuportado, ArquivoGrandeDemais

try:
    relatorio = auditar_bytes(dados)
except (XmlInvalido, DocumentoNaoSuportado, ArquivoGrandeDemais) as exc:
    print("não auditado:", exc)
```

### API HTTP

```bash
uvicorn notasbr.api:app --reload
```

| Método | Rota | Função |
|---|---|---|
| `GET` | `/v1/saude` | versão, quantidade de regras |
| `GET` | `/v1/regras` | catálogo de regras |
| `GET` | `/v1/limitacoes` | o que a auditoria não prova |
| `POST` | `/v1/auditar` | multipart `arquivo=<xml>` → relatório |
| `GET` | `/v1/chave/{chave}` | decompõe a chave |
| `GET` | `/v1/cnpj/{valor}` | valida CNPJ |
| `GET` | `/v1/cpf/{valor}` | valida CPF |

Documentação interativa em `/docs`.

```bash
curl -F "arquivo=@nota.xml" http://127.0.0.1:8000/v1/auditar
```

## Catálogo de regras

37 regras em seis famílias. Os códigos são estáveis: use-os em supressão,
dashboards e testes.

**Estrutura** — raiz, namespace, versão do layout, campos obrigatórios, itens.

**Chave de acesso** — 44 dígitos, DV módulo 11, UF, modelo, AAMM, `Id`,
`cDV`, e a coerência entre cada campo da chave e o conteúdo do XML (UF, modelo,
série, número, `tpEmis`, `cNF`, CNPJ do emitente) mais o protocolo de autorização.

**Totais** — soma dos itens × `vProd` total, `vNF` positivo, pagamentos (com
`vTroco`), arredondamento por item e composição indicativa do valor total.

**Tributos** — formato do CFOP e seu grupo, sentido do CFOP × `tpNF`, NCM com
8 dígitos, CST/CSOSN nas tabelas fechadas, CRT × CSOSN, presença de PIS/COFINS.

**Assinatura** — presença da `Signature`, `Reference/@URI`, `DigestValue`,
`SignatureValue` e, com o extra `notasbr[assinatura]`, a verificação
criptográfica contra o certificado embutido.

**CT-e** — tomador identificado, `vTPrest`, `vRec` e soma dos componentes.

<details>
<summary>Tabela completa (37 regras)</summary>

| Código | Descrição | Tipos |
|---|---|---|
| `AMB-001` | Ambiente de emissão válido e coerente | NFE, CTE |
| `ASSIN-001` | Documento assinado (elemento Signature presente) | NFE, CTE |
| `ASSIN-002` | Reference aponta para o Id do documento | NFE, CTE |
| `ASSIN-003` | DigestValue e SignatureValue preenchidos | NFE, CTE |
| `ASSIN-004` | Assinatura confere criptograficamente | NFE, CTE |
| `ASSIN-005` | Certificado do assinante presente | NFE, CTE |
| `CHAVE-AMM-001` | Ano/mês da chave é possível | NFE, CTE |
| `CHAVE-AMM-002` | AAMM da chave coerente com a data de emissão | NFE, CTE |
| `CHAVE-CDV-001` | cDV do ide bate com o DV da chave | NFE, CTE |
| `CHAVE-CONSIST-001` | Campos do ide conferem com a chave | NFE, CTE |
| `CHAVE-DV-001` | Dígito verificador da chave confere | NFE, CTE |
| `CHAVE-EMIT-001` | CNPJ/CPF do emitente confere com a chave | NFE, CTE |
| `CHAVE-FMT-001` | Chave com 44 dígitos numéricos | NFE, CTE |
| `CHAVE-ID-001` | Id do documento bate com a chave | NFE, CTE |
| `CHAVE-MOD-001` | Modelo da chave corresponde ao documento | NFE, CTE |
| `CHAVE-UF-001` | Código de UF da chave existe | NFE, CTE |
| `CTE-PREST-001` | Prestação do serviço coerente | CTE |
| `CTE-TOMADOR-001` | Tomador do serviço identificado | CTE |
| `DOC-ID-001` | Identificador do documento presente | NFE, CTE |
| `DOC-ITENS-001` | Documento tem ao menos um item | NFE, CTE |
| `DOC-NS-001` | Namespace do documento corresponde ao tipo | NFE, CTE |
| `DOC-OBRIG-001` | Campos escalares obrigatórios preenchidos | NFE, CTE |
| `DOC-VER-001` | Versão do layout presente e reconhecida | NFE, CTE |
| `NFE-DEST-001` | Destinatário presente quando exigido | NFE |
| `NFE-DET-001` | nItem sequencial começando em 1 | NFE |
| `PROT-001` | Protocolo de autorização corresponde ao documento | NFE, CTE |
| `TOTAL-COMPOSICAO-001` | Composição indicativa do valor total | NFE |
| `TOTAL-ITEM-001` | Quantidade x valor unitário confere com o item | NFE |
| `TOTAL-PAG-001` | Pagamentos somam o valor total | NFE |
| `TOTAL-VNF-001` | Valor total da nota é positivo | NFE |
| `TOTAL-VPROD-001` | Total de produtos é a soma dos itens | NFE |
| `TRIB-CFOP-001` | CFOP com 4 dígitos e primeiro dígito válido | NFE, CTE |
| `TRIB-CFOP-002` | CFOP coerente com o sentido da operação | NFE |
| `TRIB-CRT-001` | Regime do emitente coerente com CST/CSOSN | NFE |
| `TRIB-ICMS-001` | ICMS presente com CST ou CSOSN conhecido | NFE |
| `TRIB-NCM-001` | NCM com 8 dígitos | NFE |
| `TRIB-PIS-COFINS-001` | Grupos de PIS e COFINS presentes | NFE |

Além destes, `MOTOR-001` sinaliza uma regra que quebrou durante a execução. Ele
é sempre severidade **erro**: falha de software nunca vira aprovação.

</details>

## Contrato do relatório

`schema: "notasbr.relatorio/1"`. Mudanças incompatíveis alteram essa string.

```json
{
  "schema": "notasbr.relatorio/1",
  "versao_ferramenta": "0.1.0",
  "arquivo": "nota.xml",
  "sha256": "…",
  "documento": {
    "tipo": "nfe",
    "raiz": "nfeProc",
    "versao_layout": "4.00",
    "chave": "35250111222333000181550010000001231123456782",
    "modelo": "NF-e",
    "ambiente": "Produção",
    "emitente": {"cnpj": "11.222.333/0001-81", "nome": "…", "uf": "SP"},
    "destinatario": {"cnpj": "…", "nome": "…", "uf": "SP"},
    "valor_total": "1000.00"
  },
  "resumo": {
    "situacao": "reprovado",
    "erros": 1,
    "avisos": 1,
    "informacoes": 1,
    "regras_avaliadas": 35,
    "regras_puladas": 1
  },
  "achados": [
    {
      "codigo": "TOTAL-VPROD-001",
      "severidade": "erro",
      "mensagem": "vProd total (999.00) difere da soma dos itens (1000.00)",
      "caminho": "nfeProc/NFe/infNFe/total/ICMSTot/vProd",
      "detalhe": {"total": "999.00", "soma_itens": "1000.00"}
    }
  ],
  "regras_puladas": [{"codigo": "ASSIN-004", "motivo": "…"}],
  "limitacoes": ["…"],
  "duracao_ms": 1.4
}
```

`regras_puladas` é transparência, não aprovação: uma regra que não pôde ser
avaliada nunca conta como satisfeita.

## Segurança e privacidade

- XML de nota fiscal contém CNPJ, CPF, endereço e valores. O `.gitignore` do
  projeto bloqueia `*.xml` justamente por isso; só as fixtures sintéticas de
  `tests/fixtures` são versionadas.
- `parse_seguro` recusa documentos com `DOCTYPE` ou `ENTITY`. XML fiscal não
  precisa de DTD, e recusar elimina a classe de ataque por expansão de entidade.
- Tamanho de entrada é limitado (20 MiB por padrão, configurável).
- O relatório expõe CNPJ/CPF do emitente e destinatário porque a chave de acesso
  já contém o CNPJ do emitente — mascarar só o campo daria falsa sensação de
  proteção. Trate o relatório como dado pessoal.

## Documentação

- [Escopo e limites](docs/ESCOPO.md)
- [Arquitetura](docs/ARQUITETURA.md)
- [Decisões (ADRs)](docs/DECISOES.md)
- [Roadmap](docs/ROADMAP.md)

## Desenvolvimento

```bash
pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Sem instalar nada, os testes também rodam apontando o `PYTHONPATH`:

```bash
python -m pytest            # pyproject já define pythonpath = ["src", "."]
```

Para criar uma regra nova: escreva a função em `src/notasbr/regras/`, decore com
`@regra("FAMILIA-999", "descrição", tipos=("nfe",))` e **importe o módulo em
`regras/__init__.py`** — sem esse import a regra nunca executa.

## Licença

MIT. Veja [LICENSE](LICENSE).
