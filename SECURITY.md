# Política de segurança

## Versões suportadas

O projeto está em desenvolvimento ativo. Só a branch `main` recebe correção de
segurança.

## Reportando vulnerabilidade

**Não abra issue pública para falha de segurança.** Use o canal privado do GitHub:
*Security* → *Report a vulnerability* no repositório.

Descreva: o que é possível fazer, o que deveria acontecer, e como reproduzir. Se
envolver dado fiscal real, **não anexe o XML**: descreva a estrutura.

## O que é tratado como segurança aqui

| Área | Compromisso |
|---|---|
| Certificado A1 | Cifrado em repouso com AES-256-GCM; descriptografado só em memória; nunca logado |
| Chave-mestra | Fora do repositório; em produção a ausência é erro, não aviso |
| API Key | Guardada apenas como hash SHA-256; nunca recuperável |
| Multi-tenant | Toda consulta filtra por `tenant_id`, inclusive as de escrita |
| Webhook | HMAC-SHA256 com janela de 300 s e comparação em tempo constante |
| Idempotência | Chave única por tenant; repetição não gera nota duplicada |

## O que **não** é tratado como segurança (e é limitação declarada)

- **O XML autorizado vale mais que o PDF.** O PDF é representação; não é assinado.
- **A assinatura não valida cadeia ICP-Brasil nem revogação.** Ela prova integridade
  em relação ao certificado informado, nada além.
- **Não há rate limiting por tenant** implementado; deve ser feito no proxy.
- **Não há auditoria de acesso administrativo** além do log estruturado.

## Segredos

Nunca grave no repositório. `.gitignore` cobre `*.pfx`, `*.p12`, `.env` e
certificados. Há teste (`tests/test_configuracao_documentada.py`) que falha se
aparecer segredo ou variável não documentada.
