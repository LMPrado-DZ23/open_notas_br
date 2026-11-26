# WSDL do NFeStatusServico4 (SVRS, homologação)

Fonte oficial do `soapAction` e do `targetNamespace` usados em `app/nfe/soap.py` e
`app/nfe/transporte.py`.

| Campo | Valor |
|---|---|
| URL | https://nfe-homologacao.svrs.rs.gov.br/ws/NfeStatusServico/NfeStatusServico4.asmx?wsdl |
| Requer mTLS | **sim** — sem certificado de cliente a resposta é HTTP 403 |
| Obtido em | 2026-11-26 |
| Tamanho | ver arquivo ao lado |

## Por que está versionado

Os valores de `action` e `targetNamespace` não podem ser deduzidos do leiaute fiscal: vêm do
WSDL de cada serviço, e cada autorizador publica o seu. Versionar permite que um teste confira
que o código usa exatamente o que a fonte oficial declara — e que uma mudança de WSDL apareça
como diff, não como erro obscuro em produção.

## O que este WSDL NÃO resolve

O `cStat 215` ("Falha no schema XML") que o SVRS devolve ao `consStatServ` ainda não está
explicado por este arquivo: o XML fiscal valida localmente contra `consStatServ_v4.00.xsd`. Falta
o **schema da mensagem** referenciado pelo WSDL para saber o shape exato esperado no
`nfeDadosMsg`.
