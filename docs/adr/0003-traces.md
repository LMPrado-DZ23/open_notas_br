# ADR 0003 — Traces distribuídos: não agora, com gatilho

- **Status**: **aceita** (decisão de *não* implementar neste ciclo). Nada instalado.
- **Data**: 2026-11-27
- **Contexto**: a Fase F pede "instrumentar chamadas externas, worker e filas com traces" e pede
  para distinguir biblioteca/configuração de instrumentação efetiva.

## Problema

Hoje a correlação entre uma requisição e o que ela causou é feita por **log JSON com
`request_id`** (`app/main.py`, middleware) e pela série de requisições em `/metrics`
(`app/core/metrics.py`, ADR-irmão da seção 51 da auditoria). O que **não** existe:

- trace distribuído entre API → worker (ARQ) → SEFAZ;
- span por chamada externa, com latência e resultado por autorizador;
- propagação de contexto entre a requisição HTTP e o job que ela enfileirou.

## Por que não implementar agora

1. **Peso real de dependência** (regra 11): `opentelemetry-sdk` + `opentelemetry-exporter-otlp` +
   `opentelemetry-instrumentation-fastapi` + `-sqlalchemy` + `-httpx` são cinco pacotes com
   versionamento próprio e acoplamento a instrumentação de terceiros.
2. **Exige coletor.** Trace sem backend (Tempo/Jaeger/OTLP) não entrega valor; configurar coletor é
   decisão de infraestrutura, não de código, e não há ambiente publicado para consumi-lo.
3. **Instrumentação efetiva ≠ biblioteca instalada.** Adicionar o SDK e marcar "temos OTel" seria
   exatamente o falso positivo que o prompt manda evitar. Sem backend e sem validação de trace real,
   o ganho é zero e o risco (overhead, ruído, versões) é imediato.
4. **O que existe resolve o caso atual.** `request_id` no header e no log correlaciona a requisição;
   `/metrics` dá latência por rota. O que falta é a **costura** API→worker, não o número.

## Decisão

Não instalar OpenTelemetry neste ciclo. Registrar a lacuna como **lacuna**, não como cobertura.

**Gatilho para adotar** (qualquer um):

- ambiente publicado (homologação/produção) com incidente em que `request_id` não bastou para
  localizar a causa;
- mais de um worker/instância, quando a correlação entre processos deixa de ser inferível;
- exigência contratual de SLA com relatório de trace.

**Quando entrar**, o mínimo aceitável: spans em `TransporteHTTP` (autorizador), no job do worker e
na entrega de webhook; propagação de `traceparent` do header HTTP para o payload do job; amostragem
< 100% configurável; e **teste que prove span exportado**, não apenas instrumentação registrada.

## Alternativa intermediária (não escolhida agora, registrada)

Propagar o `request_id` para o payload do job do ARQ — barato, sem dependência, e resolve metade do
problema real (saber qual requisição gerou qual job). Fica como candidato para o próximo ciclo; não
foi feito aqui para não misturar com as correções de defeito deste período.

## Consequências

- `docs/auditoria_inicial.md` §51 e `docs/MATRIZ-COBERTURA.md` seguem dizendo "sem traces":
  continua verdade e não é contradição.
- Um leitor do repositório encontra a decisão com data e gatilho, em vez de inferir abandono.
