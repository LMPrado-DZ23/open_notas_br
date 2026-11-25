# Escopo e limites

Este documento existe para tornar explícito o que o sistema **não** faz. Um motor
fiscal que não declara os próprios limites induz a decisão errada, e aqui a
decisão errada é tratar documento não autorizado como autorizado.

## O que é

Motor e microserviço de documentos fiscais brasileiros, multi-tenant, com:

- **emissão e gestão de NFS-e** (padrão nacional) — Fase 3;
- **geração local de DANFSe** a partir do XML — Fase 4;
- **apuração e guias** plugáveis (MAN/DNA, DAS, municipal) — Fase 4;
- **auditoria de XML** de NF-e, NFC-e e CT-e (biblioteca `notasbr`);
- **API REST + fila + webhook** para integração com ERP, CRM e parceiros.

## Estado por fase

| Fase | Escopo | Estado |
|---|---|---|
| 1 | Fundação: containers, migração, multi-tenant, healthcheck | **concluída e verificada** |
| 2 | Cofre A1 (AES-256-GCM) + assinatura XMLDSig | a fazer |
| 3 | Motor tributário IBS/CBS + CNPJ + emissão NFS-e com mocks | a fazer |
| 4 | DANFSe local + DANFE adapter + apuração/guias | a fazer |
| 5 | Worker de emissão, lotes e webhooks | a fazer |
| 6 | Conectores DZ23/Brizu + OpenAPI | a fazer |
| 7 | NF-e/NFC-e completas + DANFE A4, DANFE Simplificado/Etiqueta, cupom, etiqueta de envio | escopo ampliado |
| 8 | CT-e, CT-e OS e MDF-e (DACTE, DAMDFE, manifesto) | escopo ampliado |
| 9 | NFP-e e logística (rastreio, coleta, impressão em lote) | escopo ampliado |

As fases 7 a 9 foram acrescentadas depois da Fase 1, a partir de pedido do
solicitante com imagens de referência. Campos e decisões de layout em
[DOCUMENTOS-FISCAIS.md](DOCUMENTOS-FISCAIS.md).

Enquanto uma fase não está concluída, **o endpoint correspondente não existe**.
Não há rota que responda "em breve" ou que finja emitir nota.

## Fora do escopo, com motivo

**Autorização real na SEFAZ/SEFIN.** Confirmar `cStat` de verdade exige
certificado A1 válido, credenciamento e ambiente de homologação. Nada disso é
alcançável por código neste ambiente. As integrações são implementadas sobre
adapters com mock e URL base configurável.

**Cadeia de confiança ICP-Brasil.** Verificar assinatura contra o certificado
embutido prova integridade em relação àquele certificado; **não** prova que ele é
ICP-Brasil, que não foi revogado ou que pertence a quem assinou.

**Validação de schema XSD oficial em produção.** A biblioteca de auditoria faz
conferência estrutural curada. Validação XSD depende de obter e versionar os
schemas oficiais vigentes, o que está no roadmap como capacidade explícita.

**Guia nacional única de arrecadação.** Não existe. O que existe é MAN (que gera
DNA) para ISS do regime geral, DAS (regime geral via MAN até 31/12/2032) e guia
municipal. Modelar um "DART nacional" seria inventar documento.

**Classificação fiscal automática de produto.** Exige base normativa e
responsabilidade que o sistema não deve assumir.

**Idoneidade do emitente, fraude, crédito tributário.** Não é inferível de XML.

**Auditoria de NFS-e pela biblioteca `notasbr`.** A biblioteca valida chave de 44
dígitos (NF-e/CT-e). NFS-e nacional usa identificador próprio — o Id da DPS tem 45
posições — e por isso é tratada por módulo de tipo próprio no serviço, não pela
biblioteca. A distinção é intencional: reaproveitar a validação de 44 dígitos para
NFS-e produziria erro silencioso.

## Fatos verificados vs. hipóteses

**Verificado por execução nesta máquina**

- `docker compose up --build` sobe os 4 serviços e todos ficam `healthy`.
- `/health` responde 200 com PostgreSQL e Redis reais; responde 503 quando o banco
  é forçado a falhar (teste dedicado).
- A migração `0001` aplica e `alembic check` confirma que não há drift entre
  modelo ORM e migração.
- Criação de tenant devolve API key uma única vez; o banco guarda só o hash
  (verificado por consulta SQL: `guardou_claro = f`).
- Uma API key de um tenant não alcança dado de outro (teste de isolamento).
- 212 testes passam.

**Hipótese a validar — e que não pode ser tratada como fato**

- **Nenhum documento fiscal real foi emitido ou recebido.** Não há certificado A1
  real, não houve chamada a SEFIN, ADN, prefeitura ou Serpro.
- **URL base da SEFIN/ADN não confirmada.** Vem de `SEFIN_*_BASE_URL`. Os caminhos
  de rota foram lidos de biblioteca de referência (ver `REFERENCIAS.md`), não de
  documentação oficial.
- **Versão do layout DANFSe em disputa:** briefing cita v1.02 (14/07/2026),
  referência local implementa v1.01 (30/06/2026).
- **Lista de municípios com `aderenteEmissorNacional = 1` não verificada.**
- **CNPJ alfanumérico** (julho/2026) ainda não é aceito por
  `notasbr.cadastros` — dívida registrada para a Fase 3.
- **Cota da API Serpro** não exercitada; o desenho de cache e fallback é
  preventivo, não medido.

## Público e uso pretendido

Desenvolvedor de integração, ERP/CRM de terceiros (DZ23, Brizu), analista fiscal e
time de QA fiscal. O sistema é ferramenta de emissão e conferência: não substitui
contador e não decide regime tributário.
