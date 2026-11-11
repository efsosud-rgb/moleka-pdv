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
- [ ] **Instalação no PC do Eric: bloqueada pelo Windows** (11/11, Windows 11 Pro, versão 10.0.26200). O Controle Inteligente de Aplicativos (Smart App Control) estava ligado e recusou o instalador 0.2.0 por falta de assinatura digital: erro 4551 na tela e evento 3077 da política `VerifiedAndReputableDesktop` no registro do Windows. Caminhos e decisão pendente em DECISOES (11/11).

Ordem aprovada pelo Eric em 11/11: Frente 1 → Frente 2 → Frente 3 → Frente 4. A cada função pronta sai um instalador novo.

## Feito (11/11/2026, versão 0.3.0)

- [x] **Abertura no PC do Eric, pelo código** (`tools/abrir_pelo_codigo.py`): o Eric entrou no sistema com a versão 0.2.0 na janela própria (prints dele, Início e Caixa). O instalador continua bloqueado naquele PC.
- [x] **Frente 2 — Produtos, tabelas de preço e clientes.** Telas de Produtos (preços por tabela e por quantidade), Clientes (CPF ou CNPJ conferido e tabela de preço) e Tabelas de preço e formas de pagamento.
- [x] **Frente 3 — Controle de caixa.** Abertura com fundo de troco, sangria, suprimento, vendas da sessão, fechamento com conferência por forma e fechamentos anteriores.
- [x] **Frente 4 — Venda (PDV), sem fiscal.** Os 9 pedidos de 11/11 estão na tela (ver ESPECIFICACAO §11 e §13).
- Verificado: 232 testes automáticos (preço por quantidade e por tabela, percentual por forma com uma e duas formas, troco, desconto, cancelamento com estorno, caixa, permissões, formato do banco); roteiro no navegador (Chromium, 1366×697) com 128 conferências e valores calculados à mão (`tools/roteiros/vendas_no_navegador.js`); banco criado pela 0.2.0 abrindo na 0.3.0. No Windows, o teste automático do GitHub faz uma venda completa pela API dentro do programa empacotado.
- [ ] **Não verificado**: as telas novas dentro da janela do Windows (só no navegador daqui); leitor de código de barras de verdade (o roteiro simulou a digitação seguida de Enter); impressão; uso por duas pessoas ao mesmo tempo.
- [ ] **Não feito** (estava no plano destas frentes): importação por planilha (CSV/XLSX); lançamento da receita da venda no financeiro (entra com a Frente 8); rateio do desconto por item (entra com a Frente 5).

## Feito (11/11/2026, versão 0.4.0)

- [x] **Frente 7 — Estoque e entrada por XML.** Tela Estoque (saldos, entrada, saída, contagem, histórico, valor do estoque) e tela Entrada de NF (conferir, importar, notas importadas, estorno). Custo médio, de-para do fornecedor e contas a pagar das parcelas.
- [x] **Frente 8 — Financeiro.** Contas a pagar e a receber, fluxo de caixa, DRE, rentabilidade por produto e categorias, no lugar do protótipo.
- Verificado: 284 testes automáticos (os de custo, nota, DRE, fluxo e rentabilidade com valores calculados à mão; cada regra conferida também "ao contrário", trocando uma linha do código para ver se algum teste percebia); roteiro no navegador (Chromium, 1366×697) com 202 conferências (`tools/roteiros/estoque_compras_financeiro_no_navegador.js`), sem erro de JavaScript, de rede ou do servidor; o roteiro de vendas da 0.3.0 repetido (128 conferências); banco criado e usado pelo código da 0.3.0 abrindo na 0.4.0. O que o teste do Windows faz no GitHub está nas notas da versão.
- [ ] **Não verificado**: as telas novas dentro da janela do Windows (só no navegador daqui); a janela de escolher arquivo dentro da janela do programa (no navegador abre com o botão e com F3); XML de uma nota de verdade de um fornecedor da loja (os testes usam notas fictícias no formato da NF-e 4.00); uso no PC do Eric e no do caixa.
- [ ] **Não feito** (estava no plano destas frentes): exportar para Excel e imprimir em A4; fluxo de caixa previsto com prazo e taxa de cartão; comparação de períodos no DRE.

## Frente 1 — Operadores e login — FEITA em 11/11/2026
Ver "Feito (11/11/2026)" acima e ESPECIFICACAO §12. Fica para depois, se o Eric quiser: pedir a senha de novo após um tempo sem uso; obrigar a troca da senha provisória no primeiro login.

## Frente 2 — Produtos, tabelas de preço e clientes — FEITA em 11/11/2026 (versão 0.3.0)
Pedidos de 11/11 atendidos aqui: **1** (faixas de preço por quantidade na ficha do produto), **2** (percentual por forma de pagamento) e **5** (cliente com CPF ou CNPJ e tabela atacado/varejo). Fica para depois: importação por planilha (CSV/XLSX) para migrar do sistema atual; foto do produto.

## Frente 3 — Controle de caixa — FEITA em 11/11/2026 (versão 0.3.0)
Abertura com fundo de troco, sangria, suprimento, fechamento com conferência por forma, fechamentos anteriores. A confirmar com o Eric (padrão adotado): qualquer operador abre, fecha, sangra e supre, com tudo registrado no nome dele; quem fecha vê o valor esperado.

## Frente 4 — Venda (PDV) sem fiscal — FEITA em 11/11/2026 (versão 0.3.0)
Pedidos de 11/11 atendidos aqui: **1**, **2**, **3**, **4**, **6**, **7**, **8** (a escolha fica gravada; a emissão é da Frente 5) e **9**. Baixa de estoque na venda e estorno no cancelamento já são gravados (`movimento_estoque`); a tela de Estoque é da Frente 7. Ficam para depois: lançamento da receita no financeiro (Frente 8), rateio do desconto por item (Frente 5), impressão do cupom (Frente 6), autorização do gerente por senha na hora (desconto e cancelamento sem trocar de operador).

## Frente 5 — Fiscal (NFC-e)
Depende da decisão API × PyNFe (ver ESPECIFICACAO §9). Implementar o provedor escolhido em `app/fiscal/`, homologação primeiro: emissão, contingência offline com fila de reenvio, cancelamento, inutilização, DANFE NFC-e 80 mm com QR Code, grupos IBS/CBS. Configuração de certificado A1 (caminho + senha fora do repositório) e dados da loja. **Nunca** produção sem ordem explícita do Eric.
Pedido **8** de 11/11: emissão conforme a escolha feita na venda; vendas "sem documento fiscal" aparecem nos relatórios. Depende do regime e da UF da loja (ESPECIFICACAO §5 e §9).

## Frente 6 — Impressão
Cupom ESC/POS (`python-escpos`) ou spooler do Windows; A4 em PDF (`reportlab` ou HTML → PDF pelo WebView2). Detecção de impressoras, teste de impressão em Configurações, status real nos chips.

## Frente 7 — Estoque e entrada por XML — FEITA em 11/11/2026 (versão 0.4.0)
Saldos (soma de movimentos), entrada e saída com motivo, contagem; importação de XML de NF-e, de-para fornecedor→produto memorizado, custo (último e médio), contas a pagar das parcelas, estorno. Ver ESPECIFICACAO §14. Ficam para depois: contagem de vários produtos de uma vez; ficha técnica e produção, se a loja fabrica.

## Frente 8 — Financeiro — FEITA em 11/11/2026 (versão 0.4.0)
Lançamentos (receitas e despesas, categorias com grupo do DRE), fluxo de caixa realizado e contas em aberto, DRE por período, rentabilidade por produto. Ver ESPECIFICACAO §14. Ficam para depois: prazo e taxa das maquininhas no fluxo; comparação de períodos; contas que se repetem; exportar Excel (`openpyxl`) e imprimir A4.

## Frente 9 — Instalador e atualização
Feito em 10/11/2026: PyInstaller em pasta + Inno Setup (`MolekaPDV-Instalador-<versão>.exe`), instalador do WebView2 embutido, atalhos, fontes embutidas, build e teste no GitHub Actions. Falta: backup diário (cópia agendada de `moleka.db`), assinatura digital do instalador e verificação de versão nova.
**Assinatura digital subiu de prioridade em 11/11/2026**: sem ela, o instalador é bloqueado no Windows 11 que estiver com o Controle Inteligente de Aplicativos ligado, sem botão de "executar assim mesmo". Depende de o Eric decidir a compra de um certificado de assinatura de código (ver DECISOES de 11/11).

## Fora da v1
NF-e modelo 55, SAT-CF-e (SP), delivery/iFood, fidelidade, multi-loja em nuvem, PostgreSQL (só se houver 2+ caixas).
