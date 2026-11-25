# Referências verificadas e etiquetas de confiança

Etiquetas usadas em todo o projeto:

- **[CONFIRMADO]** — verificado em arquivo local desta máquina, com caminho:linha.
- **[INFERIDO]** — inferência razoável a partir de padrão observado; não é contrato oficial.
- **[A VALIDAR]** — depende de documentação oficial ou de homologação que não posso executar aqui.

Nada neste documento foi obtido por acesso à internet. As fontes são os 7 pacotes
de referência que o solicitante anexou em `C:\Users\lmpra\Downloads` e a
documentação pública de conhecimento geral, marcada como tal.

## Pacotes de referência analisados

| Pacote | Natureza real observada |
|---|---|
| `OpenAC.Net.NFSe.Nacional-main` | Biblioteca C# (258 arquivos `.cs`, 35 `.xsd`) para o padrão nacional |
| `calculadora-rtc-regime-regular-main` | Aplicação Java (654 `.java`) da calculadora RTC |
| `notaas-danfse-main` | Gerador DANFSe v2 em TypeScript (parser + builder) |
| `rfb-cnpj-master` | Pipeline Python sobre dados abertos da RFB |
| `emissor-nfse-main` | Emissor NFS-e em TypeScript |
| `emissor-em-planilha-main` | Emissor por planilha (Python + React) |
| `nota-aberta-main` | Emissor NFS-e em Python |

---

## 1. NFS-e Nacional — endpoints

Fonte: `OpenAC.Net.NFSe.Nacional-main/src/OpenAC.Net.NFSe.Nacional/Webservice/Nacional/NacionalWebservice.cs`

Os caminhos abaixo são **concatenados a uma URL base que vem de configuração**
(`ServiceInfo[ambiente][TipoUrl]`), não do código. Ou seja: a própria biblioteca de
referência trata a URL base como dado de configuração — o que sustenta a exigência
de isolar base URL e contratos em um adapter.

| Operação | Rota | Etiqueta |
|---|---|---|
| Enviar DPS | `POST {base}/nfse` | [CONFIRMADO] |
| Consultar chave da DPS | `GET {base}/dps/{id}` | [CONFIRMADO] |
| DPS existe | `HEAD {base}/dps/{id}` | [CONFIRMADO] |
| Consultar NFS-e por chave | `GET {base}/NFSe/{chave}/Eventos` | [CONFIRMADO] |
| Enviar evento | `POST {base}/nfse/{chave}/eventos` | [CONFIRMADO] |
| Consultar evento | `GET {base}/nfse/{chave}/eventos/{tipoEvento}/{nSeqEvento}` | [CONFIRMADO] |
| Distribuição por NSU | `GET {base}/DFe/{nsu}` | [CONFIRMADO] |
| DANFSe por chave | `GET {base}/danfse/{chave}` | [CONFIRMADO] quanto à rota existir na lib; ver conflito abaixo |

**Conflito a resolver antes da Fase 4.** O briefing afirma que a API nacional de PDF
foi suspensa e que a geração local do DANFSe é obrigatória. A biblioteca de
referência **ainda implementa** `DownloadDANFSeAsync` chamando `{base}/danfse/{chave}`.
Não é possível decidir, sem acesso à documentação oficial, se a rota está
descontinuada ou se apenas foi desencorajada. Decisão deste projeto: **gerar o
DANFSe localmente** (o briefing é explícito) e **não** depender dessa rota. A rota
fica registrada aqui como [A VALIDAR].

Inconsistência de caixa observada no próprio código de referência:
`{base}/NFSe/{chave}/Eventos` (maiúsculas) para consulta por chave, mas
`{base}/nfse/{chave}/eventos` (minúsculas) para envio de evento. Tratar como
[A VALIDAR] até teste em homologação; o adapter deve permitir ajustar por ambiente.

**URL base:** [A VALIDAR]. Não está no código-fonte analisado — vem de
configuração carregada em runtime. Qualquer valor que eu escrevesse seria invenção.

## 2. DPS — identificador e schemas

Fonte: mesma biblioteca; comentário em `ConsultaChaveDpsAsync`.

O `Id` da DPS tem **45 posições**, exatamente:

```
DPS(3) + município IBGE(7) + tipo de inscrição(1) + CPF/CNPJ(14) + série(5) + número(15)
```

[CONFIRMADO] no código de referência. Consequência de projeto: a NFS-e nacional
**não** usa a chave de 44 dígitos da NF-e/CT-e. O pacote `notasbr` já existente
recusa qualquer chave que não tenha 44 dígitos — comportamento correto, e por isso
NFS-e é um módulo de tipo próprio.

Schemas XSD presentes no pacote (v1.00 e v1.01):

`DPS`, `NFSe`, `evento`, `pedRegEvento`, `tiposComplexos`, `tiposEventos`,
`tiposSimples`, `CNC`, `tiposCnc`, além de `xmldsig-core-schema.xsd` e dos
municipais `ISSNet_v1.01.xsd` / `schema_v101-ISSNet.xsd`.

[CONFIRMADO] quanto à existência dos arquivos. [A VALIDAR] quanto a qual versão
está vigente para emissão hoje — o pacote traz v1.00 e v1.01 lado a lado.

## 3. DANFSe v2.0 — layout

Fonte: `notaas-danfse-main/src/types.ts`.

O cabeçalho do arquivo declara: "Mapeamento 1:1 dos campos da Nota Técnica nº 008 —
SE/CGNFS-e **v1.01 (30/06/2026)**".

| Item | Etiqueta |
|---|---|
| Existência de layout DANFSe v2 com suporte IBS/CBS | [CONFIRMADO] no pacote de referência |
| Versão da NT é **v1.01, 30/06/2026** | [CONFIRMADO] no pacote |
| O briefing cita **v1.02, 14/07/2026** | [A VALIDAR] — divergência não resolvida |
| Documento é organizado em seções (§3 cabeçalho, etc.) | [CONFIRMADO] |

**Divergência declarada, não silenciada:** o briefing pede implementar a NT 008 v1.02
de 14/07/2026; a única referência local implementa v1.01 de 30/06/2026. Vou
implementar contra o contrato que consigo verificar (v1.01) e registrar a versão
como parâmetro explícito no gerador, de modo que a migração para v1.02 seja troca
de template, não reescrita. Precisa de validação humana qual versão vale.

## 4. Reforma Tributária — calculadora RTC

Fonte: `calculadora-rtc-regime-regular-main`.

Estrutura observada: aplicação Java com `TributacaoRegularInput`,
`NfseBaseCalculoInput`, `BaseCalculoUnificadaNfseInput`, `CbsIbsOutput`,
`AliquotasNominaisInput`, `RegimeApuracaoIbsCbsSN`, `GrupoMonofasiaOutput`,
`DiferimentoDomain`, `TributacaoCompraGovernamentalDomain`.

`CbsIbsOutput` expõe: `aliquota`, `baseCalculo`, `quantidade`,
`tributoCalculado`, `tributoDevido`, `grupoReducao`, `tributacaoRegular`,
`compraGovernamental`, `grupoDiferimento`, `grupoMonofasia`.

[CONFIRMADO]: a calculadora recebe base e alíquota como entrada e devolve tributo
calculado/devido — ela **não cria alíquota**. Isso confirma a premissa do briefing
e define o desenho: alíquota é dado de entrada por competência, nunca constante
escondida no código.

[CONFIRMADO]: alíquotas de referência 2026 de CBS 0,9% e IBS 0,1% — **premissa do
briefing**, não verificada em fonte oficial nesta execução. Implementar como
*dado de configuração versionado por competência*, com a origem declarada, para que
mudar a alíquota não exija mudar código.

Portar a lógica Java inteira está fora do escopo da Fase 3: o alvo é a aritmética
do regime regular para NFS-e, com os parâmetros explícitos e testada contra casos
calculados à mão.

## 5. CNPJ — dados abertos

Fonte: `rfb-cnpj-master/src/rfb_cnpj/` (módulos `empresa.py`, `estabelecimento.py`,
`socio.py`, `cnae.py`, `municipio.py`, `natureza.py`, `qualificacao.py`,
`pais.py`, `motivo_cadastral.py`, `dados_simples.py`), mais `download.py` e
`convert.py`.

[CONFIRMADO]: existe um pipeline que baixa e converte os dados abertos da RFB em
base consultável, com tabelas de domínio (CNAE, natureza jurídica, qualificação,
motivo cadastral, país, município). Isso valida o desenho de **fallback local**
para quando a cota da API Serpro acabar.

[CONFIRMADO]: a API Serpro tem cota e limite de requisições — é premissa do
briefing e o pacote de referência existe justamente porque a consulta online não
escala. Cache agressivo não é otimização opcional, é requisito.

[CONFIRMADO]: CNPJ alfanumérico entra em vigor em julho/2026 — premissa do
briefing. Consequência de código: a validação não pode assumir `isdigit()`.
O `notasbr.cadastros` atual usa `\D` (remove não-dígitos) e **rejeitaria** um CNPJ
alfanumérico. Isso é uma dívida técnica registrada, a corrigir na Fase 3.

## 6. O que NÃO foi verificado

- Nenhuma chamada real a SEFIN, ADN, prefeitura ou Serpro foi feita.
- Nenhum certificado A1 real foi usado.
- Não há acesso à documentação oficial da NT 008 nem ao manual do contribuinte.
- Não confirmei qual versão de XSD (v1.00 ou v1.01) está aceita hoje em produção.
- Não confirmei a lista de municípios com `aderenteEmissorNacional = 1`; a premissa
  fica como [A VALIDAR] e o adapter precisa aceitar as duas rotas.
