# Decisões de arquitetura (ADRs)

Registro do que foi decidido, quando, por quê e o que foi descartado. O objetivo é
que a próxima pessoa não refaça a discussão — e saiba quando a decisão deixou de
valer.

---

## ADR-001 — v0.1 é auditoria offline, não emissão

**Data:** 2026-11-25
**Estado:** aceita

**Contexto.** O repositório começa só com LICENSE. "Notas fiscais" admite dois
produtos muito diferentes: um emissor/transmissor (gera XML, assina, envia à
SEFAZ) ou um conferente (lê XML, aponta inconsistências).

**Decisão.** A v0.1 é conferente: lê NF-e, NFC-e e CT-e e produz relatório de
consistência. Nenhuma chamada de rede.

**Motivo.** Emissão e transmissão não são verificáveis sem certificado digital A1
e credenciamento na SEFAZ. Um emissor escrito sem esses meios seria uma pilha de
código não testável, cuja primeira execução real aconteceria na máquina de outra
pessoa — o pior lugar possível para descobrir erro de assinatura ou de envelope
SOAP. A auditoria offline é 100% testável hoje, resolve dor imediata de quem
recebe XML de terceiro e é o alicerce correto: as mesmas regras servem para
validar o XML que um emissor produzir depois.

**Consequências.**
- Positivo: núcleo sem dependências, testável, publicável de imediato.
- Positivo: a camada de transporte entra depois, ao lado do auditor, sem reescrever regra.
- Negativo: não é possível "emitir uma nota com o notasbr" ainda.
- Negativo: sem documento real, as fixtures são sintéticas — declarado em `ESCOPO.md`.

**Alternativas descartadas.**
- Emissor completo com mocks de SEFAZ: produziria confiança falsa.
- Editor visual de nota fiscal sem integração: escopo muito maior, nenhum ganho de verificação.

---

## ADR-002 — Python com núcleo em stdlib

**Data:** 2026-11-25
**Estado:** aceita

**Contexto.** O pedido deixou a stack a meu critério, com exigência de documentar.

**Decisão.** Python 3.10+, layout `src/`, núcleo **sem dependências externas**.
FastAPI e `signxml` entram como extras opcionais.

**Motivo.** O domínio é dominado por regras sobre árvore XML e aritmética decimal
— nada exige framework. `xml.etree`, `decimal` e `hashlib` da stdlib cobrem o
núcleo. Python é a linguagem em que integrações fiscais acontecem do lado de
quem recebe o XML (ERP, script de conciliação, notebook de conferência), e o
público que mais precisa desta ferramenta é justamente quem não vai montar um
projeto Node para conferir um arquivo.

**Consequências.**
- Positivo: `pip install` leve; roda em qualquer lugar com Python 3.10.
- Positivo: menos superfície de supply chain — argumento relevante para software fiscal.
- Negativo: `ElementTree` é mais lento que `lxml`; irrelevante para arquivos de dezenas de KB.
- Negativo: a verificação criptográfica depende de extra instalado.

**Alternativas descartadas.**
- Node/TypeScript: ecossistema fiscal brasileiro é mais fraco; exigiria dependências para XMLDSig.
- Next.js full-stack: o produto é uma verificação por arquivo, não uma aplicação de tela.

---

## ADR-003 — NFS-e fora da v0.1

**Data:** 2026-11-25
**Estado:** aceita

**Contexto.** O escopo pedido inclui NFS-e.

**Decisão.** NF-e (55), NFC-e (65), CT-e (57) e CT-e OS (67) são auditados. NFS-e
não, e o relatório declara isso em `limitacoes`.

**Motivo.** Não existe um layout de NFS-e: existem centenas de layouts municipais
e um padrão nacional em transição. Uma implementação parcial produziria falso
negativo em escala — exatamente o modo de falha mais perigoso em ferramenta de
conferência. E a chave de 44 dígitos não se aplica: `chave.py` recusa qualquer
outro formato em vez de adivinhar.

**Consequências.**
- Negativo: lacuna explícita no escopo pedido.
- Positivo: nenhuma regra "meia-boca" que aprove documento errado.
- Caminho: ao entrar, será um módulo de tipo próprio (`nfse`), com layout por
  município/versão, não um ajuste nas regras atuais.

---

## ADR-004 — Divergência de composição de `vNF` é informação, não erro

**Data:** 2026-11-25
**Estado:** aceita

**Contexto.** A fórmula de `vNF` (`vProd + frete + seg + outro + II + IPI - desc`
e variantes com ST, FCP, desoneração e IPI na base) muda por nota técnica.

**Decisão.** `TOTAL-COMPOSICAO-001` registra o delta como **informação**, com o
valor calculado e a diferença. Nunca reprova.

**Motivo.** Não tenho certeza suficiente para transformar essa comparação em
veredito para toda operação. Publicar o delta entrega o dado útil para quem
conhece a regra aplicável, sem reprovar documento legítimo. Reprovar legítimo é o
erro que mais rápido destrói confiança em ferramenta de conferência.

**Consequências.**
- Positivo: zero falso positivo nessa dimensão.
- Negativo: exige leitura humana; não protege automaticamente contra erro de total.
- Revisão: quando houver base de casos reais, promover para erro com a fórmula
  correta por versão de layout e por indicador de operação.

---

## ADR-005 — Segurança do parse: recusar `DOCTYPE`

**Data:** 2026-11-25
**Estado:** aceita

**Contexto.** `xml.etree.ElementTree` não resolve entidade externa, mas é exposto
a expansão de entidade interna ("billion laughs"). A alternativa canônica seria
depender de `defusedxml`.

**Decisão.** `parse_seguro` recusa qualquer documento contendo `<!DOCTYPE` ou
`<!ENTITY`, antes do parse. Limite de tamanho de 20 MiB por padrão.

**Motivo.** XML fiscal não usa DTD. Recusar elimina a classe de ataque inteira sem
adicionar dependência ao núcleo, e o comportamento é determinístico e testável —
diferente de confiar em configuração padrão de parser.

**Consequências.**
- Positivo: sem dependência, sem configuração, testado.
- Negativo: um XML legítimo com DTD (improvável no domínio) seria recusado. A
  mensagem de erro explica o motivo e o comando alternativo.

---

## ADR-006 — Relatório expõe CNPJ/CPF sem mascarar

**Data:** 2026-11-25
**Estado:** aceita, com ressalva

**Contexto.** O relatório poderia mascarar documentos para reduzir exposição de PII.

**Decisão.** Emitente e destinatário vêm com CNPJ/CPF completo. O README classifica
o relatório como dado pessoal e o `.gitignore` bloqueia `*.xml`.

**Motivo.** A chave de acesso — que é o identificador central do relatório — **já
contém o CNPJ do emitente** em texto claro. Mascarar o campo `emitente.cnpj`
enquanto `documento.chave` expõe os mesmos 14 dígitos seria teatro de segurança,
não redução de risco. Existe `cadastros.mascarar()` para quem for logar.

**Ressalva.** Isso obriga o consumidor a tratar o JSON como sensível. Se o uso
virar multiusuário ou log centralizado, a decisão precisa ser revista — e aí
mascarar a chave também, não só os campos.

---

## ADR-007 — Falha de regra é erro de auditoria

**Data:** 2026-11-25
**Estado:** aceita

**Decisão.** Exceção dentro de uma regra é capturada e convertida em achado
`MOTOR-001`, severidade **erro**, com o tipo da exceção. A auditoria continua.

**Motivo.** A alternativa (deixar propagar) interrompe o lote; a alternativa
pior (ignorar) produz "aprovado" sem a checagem. Converter em erro mantém o
processo rodando e torna o defeito visível com o nome da regra.
