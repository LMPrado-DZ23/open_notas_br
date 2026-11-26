# Escopo negativo — o que o v10.0 §3.3 exclui

Documento complementar ao `docs/ROADMAP.md` (que descreve as 6 fases entregues). Aqui está
o que **não** entra, com o motivo e a dependência técnica. Registrar o que não se faz evita
que a ausência seja lida como esquecimento.

## Fora de escopo por decisão (v10.0 §3.3)

| Documento | Motivo | Dependência para entrar |
|---|---|---|
| **NF3e** (energia, modelo 66) | leiaute e mercado próprios; nenhuma base no repositório | XSD oficial, webservice por UF, domínio de faturamento de energia |
| **NFCom** (telecom, modelo 62) | leiaute específico de serviços de comunicação | XSD oficial e o MOC correspondente |
| **BP-e** (bilhete de passagem, modelo 63) | leiaute próprio de transporte de passageiros | XSD oficial e regras do setor |
| **NFAg** (agronegócio) | padrão em implantação, sem estabilidade suficiente | definição do padrão pela SEFAZ |

Nenhum deles foi "quase implementado": não existe geração, assinatura, transmissão nem
representação para eles. O transporte SOAP (item 3 da auditoria) é pré-requisito comum e
ele próprio está bloqueado por credenciamento.

## Autorização em produção real — fora de escopo nesta execução

O mesmo §3.3 exclui autorização em SEFAZ real de produção: exige certificado de produção,
contrato e homologação prévia aprovada. Emitir em produção sem essa cadeia seria violação
legal, não atalho técnico.

## Pendências reais — bloqueios, não escopo

| Item | Bloqueio | Como destrava |
|---|---|---|
| F9.1 cotação Melhor Envio | OAuth do proprietário | abrir a URL de autorização no navegador |
| F9.3–F9.6 / item 3 (SOAP) | credenciamento NF-e em GO | credenciar a empresa no portal da SEFAZ-GO |
| Item 1 drivers multi-prefeitura | URL/leiaute oficial por provedor | obter a documentação de cada prefeitura |
| `pip-audit` no CI | dependência nova | ADR justificando (R9) |

## Ordem sugerida quando o bloqueio cair

1. `NFeStatusServico` — a chamada mais barata; confirma certificado, URL e envelope juntos
2. Autorização síncrona com uma nota de teste em homologação
3. Consulta e recibo do lote assíncrono
4. Cancelamento; depois CC-e
5. Contingência (SVC/EPEC) — só depois que o caminho normal funciona
6. Inutilização de numeração

Contingência sobre caminho normal quebrado esconde o problema em vez de resolvê-lo.
