# Plano de construção — frentes de trabalho

Cada frente é um bloco que uma sessão do Claude Code (Opus 5.5) constrói de ponta a ponta: modelo → API → tela → testes. Ordem pensada para o caixa funcionar o quanto antes e o fiscal entrar sem retrabalho. Marque `[x]` ao concluir e anote a data.

## Feito (07/11/2026, sessão Fable)

- [x] Especificação v0.1, regras (AGENTS.md), marca, protótipo estático (`docs/prototipo/`).
- [x] Base executável: `main.py` (pywebview + uvicorn), `app/config.py`, `app/db.py`, schema completo em `app/models.py`, `app/dinheiro.py` e `app/precos.py` com testes, `/api/status` honesto, cadastros básicos (`/api/produtos`, `/api/clientes`, `/api/tabelas-preco`), adaptador fiscal com `ProvedorNulo`, 4 telas em `ui/` lendo o status real. 41 testes passando; lint limpo.
- [x] Abertura da janela pywebview no Windows: verificada em 10/11/2026 no Windows do GitHub Actions (print da janela guardado no build). Falta o PC do Eric e o do caixa.

## Feito (10/11/2026)

- [x] Prévia do layout refeita com as cores da logomarca e as artes novas na capa (5 telas, `docs/prototipo/`). Conferida em 1366×768 por exportação local e no canvas publicado.
- [x] Prévia aprovada pelo Eric; identidade levada para o frontend real (`ui/templates/`, `ui/static/`), com fontes e artes da capa embutidas. Conferido em 1366×768: as 5 telas cabem sem rolagem, sem erros, sem pedir nada à internet.
- [x] Empacotamento para Windows (parte da Frente 9, adiantada para o Eric poder testar): PyInstaller + Inno Setup + GitHub Actions, com teste do executável e do instalador num Windows de verdade.
- [x] Controle do formato do banco entre versões (`app/migracoes.py`).
- [ ] **Não verificado**: abertura no PC do Eric e no PC do caixa (i3, 4 GB, HD), impressão e leitor.

## Feito (11/11/2026)

- [x] **Frente 1 — Operadores e login** (versão 0.2.0). Primeiro acesso cria o gerente; login na capa; perfis operador e gerente; tela Operadores; Minha senha; Trocar de operador; recuperação de acesso (`--redefinir-senha`). Verificado: testes automáticos (login certo e errado, bloqueio por senhas erradas, operador inativo, permissões, telas protegidas) e roteiro no navegador em 1366×697. Ver ESPECIFICACAO §12.
- [x] Telas reajustadas para a área útil real da janela maximizada (1366×697). Na versão 0.1.0, Início, Produtos e Financeiro rolavam um pouco: a conferência de 10/11 tinha usado 1366×768.
- [x] Os 9 pedidos do Eric de 11/11 registrados (ESPECIFICACAO §11) e distribuídos nas frentes abaixo.
- [ ] **Não verificado**: login e telas internas dentro da janela do Windows (o teste automático no Windows confere a API, as páginas e o print da capa; as telas internas foram vistas só no navegador daqui).

Ordem aprovada pelo Eric em 11/11: Frente 1 → Frente 2 → Frente 3 → Frente 4. A cada função pronta sai um instalador novo.

## Frente 1 — Operadores e login — FEITA em 11/11/2026
Ver "Feito (11/11/2026)" acima e ESPECIFICACAO §12. Fica para depois, se o Eric quiser: pedir a senha de novo após um tempo sem uso; obrigar a troca da senha provisória no primeiro login.

## Frente 2 — Produtos, tabelas de preço e clientes (telas)
A API básica existe. Faltam: telas de listagem/cadastro/edição, inativar, faixas de preço por tabela na tela, importação por planilha (CSV/XLSX) para migrar do sistema atual, leitura de EAN. Teste: faixa aplicada corretamente via `app/precos.py`.
Pedidos de 11/11 que entram aqui: **1** (tabela de preço por quantidade: tela das faixas), **2** (preço por forma de pagamento: cadastro da regra, depois de decidida), **5** (cliente com CPF ou CNPJ validado e tabela atacado/varejo). O campo "Categoria" que aparece na tela de Produtos ainda não existe no banco: entra com um passo em `app/migracoes.py`.

## Frente 3 — Controle de caixa
Abertura com fundo de troco, sangria, suprimento, fechamento com conferência por forma de pagamento, histórico. `/api/caixa/...` + tela. Status "Caixa: aberto desde" passa a vir do banco. Teste: não abre dois caixas no mesmo terminal; fechamento calcula diferença.
A decidir antes: o operador comum faz sangria, suprimento e fechamento sozinho ou precisa da senha do gerente?

## Frente 4 — Venda (PDV) sem fiscal
Venda aberta → itens (leitor/nome, quantidade, faixa automática, desconto com rateio) → pagamentos (multi-forma, troco) → finalizar → baixa de estoque (`movimento_estoque`) → lançamento de receita. Atalhos F2–F12. Teste: totais em centavos batem; estoque baixa; cancelamento estorna.
Pedidos de 11/11 que entram aqui: **1** (o caixa aplica a faixa por quantidade sozinho), **2** (preço conforme a forma de pagamento), **3** (mais de uma forma de pagamento na mesma venda), **4** (saldo de vendas do dia na tela, vindo do banco), **6** (editar a quantidade dos itens), **7** (trocar a forma de pagamento depois de escolhida), **8** (escolher se emite ou não a NFC-e ao finalizar; a escolha fica gravada na venda) e **9** (escolher e trocar o cliente da venda pelo cadastro, recalculando os preços pela tabela dele).

## Frente 5 — Fiscal (NFC-e)
Depende da decisão API × PyNFe (ver ESPECIFICACAO §9). Implementar o provedor escolhido em `app/fiscal/`, homologação primeiro: emissão, contingência offline com fila de reenvio, cancelamento, inutilização, DANFE NFC-e 80 mm com QR Code, grupos IBS/CBS. Configuração de certificado A1 (caminho + senha fora do repositório) e dados da loja. **Nunca** produção sem ordem explícita do Eric.
Pedido **8** de 11/11: emissão conforme a escolha feita na venda; vendas "sem documento fiscal" aparecem nos relatórios. Depende do regime e da UF da loja (ESPECIFICACAO §5 e §9).

## Frente 6 — Impressão
Cupom ESC/POS (`python-escpos`) ou spooler do Windows; A4 em PDF (`reportlab` ou HTML → PDF pelo WebView2). Detecção de impressoras, teste de impressão em Configurações, status real nos chips.

## Frente 7 — Estoque e entrada por XML
Saldos (soma de movimentos), ajuste com motivo, inventário; importação de XML de NF-e (`lxml`), de-para fornecedor→produto memorizado, atualização de custo (último e médio), geração de conta a pagar.

## Frente 8 — Financeiro
Lançamentos (receitas/despesas, categorias com grupo DRE), fluxo de caixa realizado + previsto, DRE por período com comparação, rentabilidade por produto (preço − custo). Exportar Excel (`openpyxl`) e imprimir A4.

## Frente 9 — Instalador e atualização
Feito em 10/11/2026: PyInstaller em pasta + Inno Setup (`MolekaPDV-Instalador-<versão>.exe`), instalador do WebView2 embutido, atalhos, fontes embutidas, build e teste no GitHub Actions. Falta: backup diário (cópia agendada de `moleka.db`), assinatura digital do instalador (tira o aviso do Windows) e verificação de versão nova.

## Fora da v1
NF-e modelo 55, SAT-CF-e (SP), delivery/iFood, fidelidade, multi-loja em nuvem, PostgreSQL (só se houver 2+ caixas).
