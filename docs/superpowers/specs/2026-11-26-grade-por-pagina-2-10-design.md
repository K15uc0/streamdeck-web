# Grade por página (2.10) — desenho

## Intenção
O usuário monta páginas no editor do PC e quer que o celular mostre exatamente o mesmo arranjo. Hoje a grade (colunas × linhas, e a variante vertical `portrait`) é global: a página "Monitor" (9 blocos, pensada para 5×4) aparece apertada num deck 4×3, e mudar a grade para uma página altera todas.

## Objetivos
- Cada página pode ter grade própria: `page.grid = {"columns": 1..10, "rows": 1..8, "portrait": {"columns", "rows"}?}` (opcional).
- Sem `page.grid`, a página usa a grade global (configs antigos não mudam).
- Celular (deck.js) usa a grade da página atual; trocar de página refaz a grade.
- Editor: na barra da página, "Grade: Geral | Própria"; com "Própria", seletores Colunas/Linhas (e vertical) só daquela página. A prévia usa a grade da página. Mudar a grade geral não altera páginas com grade própria.
- Modelo "Monitor do PC" cria a página com `grid` 5×4.
- Limite de botões por página segue `MAX_BUTTONS`; capacidade validada pela grade da página.

## Não objetivos
- Não mudar o desenho dos blocos (2.9.1 já cobre telas pequenas).
- Não criar grades por aparelho (fica para "aparelhos").

## Anti-objetivos
- Editar uma página nunca pode mexer na grade ou nos botões de outra.
- Config salvo pela 2.10 tem de continuar abrindo na 2.9 (campo extra ignorado ou removido? — a 2.9 rejeita chaves desconhecidas? ver builder: se rejeitar, aceitar: atualização é só para frente).

## Abordagens
1. **Grade opcional por página (escolhida)**: compatível, mudança local em schema/deck/editor.
2. Grade obrigatória por página com migração: mais simples na leitura, mas muda todos os configs e o JSON.
3. Escalar a página para caber (sem grade própria): não resolve "cada página com sua quantidade de botões".

## Restrições
Python 3.8 stdlib, ES5, textos pt-BR, comentários sem acento, testes no Linux (unittest, tests/js/flow.test.js, tests/e2e/smoke.js).

## Fica para o implementador
Nome exato dos controles, posição na barra do editor, como `SD.flow` recebe a grade (já recebe cols/rows).
