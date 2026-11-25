# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado

- **Catálogo dos 16 tipos de evento** da NFS-e, extraído do XSD oficial, com
  validação parametrizada de cada tipo e exposição em
  `GET /v1/emissoes/eventos/tipos`.
- **Cancelamento de NFS-e** (`POST /v1/emissoes/{id}/cancelamento`) com
  `pedRegEvento` validado contra o XSD oficial, assinatura XMLDSig e trilha de
  evento.
- **Registro genérico de eventos** (`POST /v1/emissoes/{id}/eventos`) para os tipos
  operáveis pelo contribuinte; cancelamento tem rota própria.
- **DAMDFE** (MDF-e) e **DACTE** (CT-e), **cupom NFC-e** com QR local,
  **DANFE A4**, **DANFE simplificado** e **etiquetas de volume**.
- **Validação contra certificado ICP-Brasil real**: mTLS aceito pela SEFIN de
  homologação, `GET /dps/{id}`, `HEAD /dps/{id}`, `GET /nfse/{chave}` e ADN
  confirmados; respostas reais versionadas como fixture de contrato.
- **Schemas XSD oficiais** versionados em `tests/fixtures/schemas/nfse-1.01/` para
  validação offline.
- `exigir_assinatura_valida`, que levanta em vez de devolver booleano ignorável.

### Corrigido

- **`GET /nfse/{chave}/eventos` não existe** (HTTP 405). A implementação usa o ADN,
  que funciona; há teste registrando o achado.
- **Caminho de parametrização de alíquota estava errado** (404 de rota
  inexistente); a orientação passou a ser informar a alíquota na configuração do
  tenant.
- `Id` do pedido de evento é `PRE` com 59 caracteres, não `EVT` com 62.
- `TSDateTimeUTC` não aceita `Z`, apesar do nome: exige offset numérico.
- `xDesc` não é texto livre: cada tipo de evento tem descrição fixa no schema.
- Dublê de SEFIN não honrava a assinatura do `Protocol` (`operacao`).

## [0.2.0]

### Adicionado

- Fases 1 a 6: fundação, cofre A1 com XMLDSig, motor tributário + CNPJ + NFS-e com
  dublê, DANFSe local, worker/lotes/webhooks, conectores DZ23 e Brizu.
- Apuração com provedores plugáveis (MAN/DNA, DAS, municipal).
- Reforma Tributária: alíquotas de referência 2026/2027 e catálogo `cClassTrib`
  versionado.

## [0.1.0]

### Adicionado

- Auditoria offline de XML fiscal e biblioteca `notasbr`.
