# ADR 0002 — Análise de dependências: `pip check` agora, varredura de CVE depois

- **Status**: **aceita e implementada** (opção A); opção B fica decidida para quando houver
  gatilho objetivo, descrito abaixo.
- **Data**: 2026-11-26
- **Contexto**: a missão exige CI com "análise de dependências" e proíbe instalar
  `pip-audit`/`gitleaks`/`schemathesis` sem avaliar e registrar a decisão (regra 11).

## Problema

O CI tinha testes, cobertura, lint, tipagem, migrations, contrato e secret scanning — mas
nenhuma verificação de **dependências**. Duas coisas diferentes cabem nesse nome:

1. **Consistência do ambiente**: o que está instalado satisfaz o que o projeto declara, sem
   conflito de versões. Barato, offline, determinístico.
2. **Vulnerabilidade conhecida (CVE)**: alguma dependência instalada tem advisory publicado.
   Exige **base de advisories atualizada** — logo, rede e uma ferramenta dedicada.

Tratar (1) como se fosse (2) seria teatro: um script caseiro de "procura versão ruim" não tem
base de advisories e envelhece no primeiro dia.

## Opções avaliadas

### A. `pip check` no gate e no CI (implementada)

`python -m pip check` responde "as dependências instaladas satisfazem as declarações, sem
conflito". Offline, já disponível no `pip`, sem dependência nova.

**Prós**: zero custo, zero dependência, pega o erro real de ambiente (extra faltando, pin
incompatível, instalação parcial) e falha de forma determinística.
**Contras**: **não** detecta CVE. É cobertura de consistência, não de segurança de cadeia.

### B. `pip-audit` no CI (decidida, não implementada agora)

Ferramenta oficial da Python Packaging Authority, consulta base de advisories (PyPI/OSV).

**Prós**: cobre CVE de verdade; é a ferramenta que o ecossistema usa; roda em um passo de CI.
**Contras**: (i) exige rede e base externa — resultado pode mudar sem mudança no repositório,
o que reprova CI por fato novo alheio ao commit; (ii) é dependência nova de CI (regra 11);
(iii) advisory sem versão corrigida disponível exige `--ignore-vuln` justificado, que precisa
de disciplina de revisão.

**Gatilho para adotar (B)**: quando existir ambiente publicado (homologação/produção) ou
distribuição do pacote a terceiros. Antes disso, o custo de CI intermitente supera o ganho.

### C. `safety` / `dependabot` / `renovate`

- `safety` é comercial para o modo completo.
- `dependabot`/`renovate` cuidam de **atualizar**, não de barrar merge por CVE, e exigem
  configuração no GitHub (fora do repositório).

Não escolhidas agora; nenhuma resolve (1), que é o problema imediato.

## Decisão

- **A implementada**: `pip check` no gate local (`scripts/check_ci.py`) e no CI.
- **B decidida com gatilho**: adotar `pip-audit` quando houver ambiente publicado; o passo,
  quando entrar, deve falhar (não apenas reportar) e qualquer `--ignore-vuln` precisa de
  justificativa no próprio workflow.
- Sem dependência nova nesta decisão.

## Consequências

- O gate passa a reprovar ambiente inconsistente — o que já aconteceu na prática (extra
  faltando quebra import em runtime, não no import do módulo).
- **Risco residual explícito**: CVE em dependência **não** é detectada hoje. Está registrado
  em `docs/auditoria_inicial.md` §50 como lacuna conhecida, não como cobertura.
