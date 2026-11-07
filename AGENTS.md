# AGENTS.md — regras para todas as IAs e colaboradores

Vale para Claude Code (Opus, Sonnet, Fable), Codex, Jules e qualquer pessoa. O `CLAUDE.md` importa este arquivo.

## O projeto

Moleka PDV: frente de loja (PDV + NFC-e + estoque + financeiro) para a sorveteria Moleka Sorvetes. Backend Python; interface HTML/CSS/JS numa janela `pywebview`; instalador único para Windows. Especificação em `docs/ESPECIFICACAO.md`; decisões em `docs/DECISOES.md`.

## Regras que não se negociam

1. **Nunca inventar dados.** Telas, relatórios, DRE e painéis mostram apenas números vindos do banco. Sem dado, mostrar `—` e o motivo (ex.: "sem vendas no período"). Nada de mock, estimativa ou valor de exemplo apresentado como real. Dados fictícios só em `tests/` e em fixtures claramente nomeadas.
2. **Nunca afirmar que algo funciona sem evidência.** "Disponível" ≠ "testado". Ao relatar uma tarefa, dizer o que foi executado, o que foi observado (saída, status, caminho) e o que ficou **não verificado**.
3. **Fiscal é sério.** Nenhum envio real para a SEFAZ de produção sem ordem explícita do Eric. Desenvolvimento e testes usam o ambiente de homologação. Certificado A1, senhas e tokens de API nunca entram no repositório (ficam em `%APPDATA%\MolekaPDV\` ou variáveis de ambiente; ver `.gitignore`).
4. **Dinheiro em centavos.** Valores monetários são inteiros em centavos no banco e no backend; só a interface formata `R$ 0,00`. Nada de `float` para dinheiro.
5. **Uma fonte da verdade fiscal.** O módulo fiscal é um adaptador (`app/fiscal/`): a interface pública não muda quando o provedor muda (API intermediária ⇄ PyNFe direto).
6. **Sem aviso, sem susto.** Qualquer operação destrutiva (apagar banco, zerar estoque, cancelar NFC-e em lote) exige confirmação explícita e fica registrada em log.

## Como trabalhar

- Linguagem do código, comentários, commits e docs: **português do Brasil** (nomes de variáveis/funções em inglês são aceitos quando forem mais claros).
- Python 3.12+. Formatação com `ruff format`; lint com `ruff check`; tipos com `mypy` nos módulos de dinheiro e fiscal.
- Testes com `pytest`. Todo cálculo de preço, imposto, caixa e DRE nasce com teste.
- Commits pequenos, mensagem no imperativo em português ("Adiciona cadastro de produtos"). Branches `feat/...`, `fix/...`, `docs/...`.
- Antes de começar uma frente nova, ler `docs/ESPECIFICACAO.md` e `docs/DECISOES.md`; se faltar decisão, perguntar em vez de supor.
- Não adicionar dependências pesadas sem registrar o motivo em `docs/DECISOES.md`.

## Divisão de trabalho entre sessões do Claude Code

- **Opus 5.5**: construção (código novo, arquitetura, módulos fiscal/financeiro).
- **Sonnet**: tarefas mecânicas (git, testes, lint, build do instalador, status).
- **Fable 5.1**: só o que o Opus não resolver.

Só uma sessão escreve código numa mesma pasta por vez.
