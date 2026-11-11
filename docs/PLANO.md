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

## Frente 1 — Operadores e login
Tabela `operador` já existe. Criar o primeiro gerente na primeira execução (tela "Configuração inicial"), hash de senha com `argon2-cffi` ou `hashlib.scrypt`, `POST /api/login`, cookie de sessão local, perfil operador/gerente, tela de login ligada de verdade. Teste: login certo/errado, bloqueio de operador inativo.

## Frente 2 — Produtos, tabelas de preço e clientes (telas)
A API básica existe. Faltam: telas de listagem/cadastro/edição, inativar, faixas de preço por tabela na tela, importação por planilha (CSV/XLSX) para migrar do sistema atual, leitura de EAN. Teste: faixa aplicada corretamente via `app/precos.py`.

## Frente 3 — Controle de caixa
Abertura com fundo de troco, sangria, suprimento, fechamento com conferência por forma de pagamento, histórico. `/api/caixa/...` + tela. Status "Caixa: aberto desde" passa a vir do banco. Teste: não abre dois caixas no mesmo terminal; fechamento calcula diferença.

## Frente 4 — Venda (PDV) sem fiscal
Venda aberta → itens (leitor/nome, quantidade, faixa automática, desconto com rateio) → pagamentos (multi-forma, troco) → finalizar → baixa de estoque (`movimento_estoque`) → lançamento de receita. Atalhos F2–F12. Teste: totais em centavos batem; estoque baixa; cancelamento estorna.

## Frente 5 — Fiscal (NFC-e)
Depende da decisão API × PyNFe (ver ESPECIFICACAO §9). Implementar o provedor escolhido em `app/fiscal/`, homologação primeiro: emissão, contingência offline com fila de reenvio, cancelamento, inutilização, DANFE NFC-e 80 mm com QR Code, grupos IBS/CBS. Configuração de certificado A1 (caminho + senha fora do repositório) e dados da loja. **Nunca** produção sem ordem explícita do Eric.

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
