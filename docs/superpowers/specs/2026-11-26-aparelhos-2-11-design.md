# Aparelhos (2.11) — desenho (aprovado pelo usuário)

## Intenção
Hoje todo celular entra com o mesmo código (`storage.token()`, cookie `sdk` HttpOnly ou `?k=`). O PC não distingue aparelhos, não dá para limitar páginas por aparelho nem tirar o acesso de um só.

## Decidido
- **Chave por aparelho.** Primeiro acesso com o código geral (`/?k=`) → o servidor cria um aparelho `{id, key (secrets.token_hex(16)), name, created, last_seen, last_ip, pages: null|[índices], full: false}` e grava o cookie `sdk=<chave do aparelho>` (HttpOnly, SameSite=Strict, como hoje). Pedidos autenticam pela chave do aparelho.
- **Migração sem reescanear:** cookie antigo igual ao código geral continua aceito; nesse pedido o servidor cria um aparelho e troca o cookie (Set-Cookie) pela chave nova.
- **Armazenamento:** `Documentos\StreamDeck\aparelhos.json` (escrita atômica, lock), nunca exposto aos aparelhos; chaves comparadas com `hmac.compare_digest`.
- **Conectar (só PC):** cartão "Aparelhos": nome (renomear), último acesso, páginas visíveis (todas ou lista), "Controle total", Remover (acesso cai na hora; volta só com o código). "Trocar código" continua invalidando o código geral (aparelhos existentes seguem válidos — dizer isso na tela).
- **Páginas visíveis:** `/api/state`/config entregue ao aparelho só com as páginas permitidas? Não: ações de página (`page`/troca automática) e os índices quebram. Decisão: o servidor entrega o config inteiro e um campo `device: {name, pages, full}`; o celular esconde as páginas não permitidas na navegação; o servidor **recusa** pressionar botão de página não permitida (403). Assim é seguro e não quebra índices.
- **Controle total:** substitui `allow_kill` (migrar: se `allow_kill` era true, todos os aparelhos existentes no momento da migração ganham `full: true`). Ações sensíveis exigem `full` de aparelho remoto: encerrar processo, desligar/reiniciar/suspender o PC, comandos/apps arbitrários se houver ação desse tipo (o implementador lista as ações e decide junto do código de ações; documentar a lista). PC local sempre pode.
- **Grade:** continua por página (2.10.1); nada por aparelho.

## Não objetivos
Contas/senhas por usuário; acesso pela internet; grade por aparelho.

## Anti-objetivos
Aparelho removido continuar entrando; chave aparecendo em logs, URL ou na página; quebrar quem já está conectado.

## Abordagens
1. Chave por aparelho (escolhida). 2. Só apelido por aparelho (recusada: falsificável, remover não bloqueia).

## Restrições
Python 3.8 stdlib; ES5; pt-BR; testes no Linux (unittest, tests/js/flow.test.js, tests/e2e/smoke.js).
