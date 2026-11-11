# Especificação — Moleka PDV (rascunho v0.2, 07/11/2026; atualizado em 11/11/2026)

Documento vivo. Itens marcados **[A DEFINIR]** dependem de resposta do cliente ou do Eric; ver seção 9. Os pedidos de 11/11/2026 estão na seção 11; operadores e permissões, na seção 12.

## 1. Objetivo

Sistema de frente de loja para a sorveteria Moleka Sorvetes, instalado no PC do caixa, que:

- registra vendas e emite **NFC-e (modelo 65)** autorizada na SEFAZ, imprimindo o DANFE NFC-e em impressora térmica;
- controla o caixa (abertura, sangria, suprimento, fechamento) e o estoque;
- importa compras por XML de NF-e, atualizando estoque e custo;
- mantém tabelas de preço varejo, atacado e por quantidade;
- cadastra clientes e produtos;
- registra despesas e receitas e produz fluxo de caixa, DRE e rentabilidade.

Tudo com visual limpo, relevo 3D nos componentes e a logo animada, e instalação por um clique.

## 2. Arquitetura

| Camada | Escolha | Motivo |
|---|---|---|
| Janela desktop | `pywebview` (WebView2 no Windows) | permite interface HTML/CSS/JS com 3D e animação, mantendo o backend em Python |
| Backend | Python 3.12 + FastAPI (servidor local, só `127.0.0.1`) | API interna consumida pela interface; fácil de testar |
| Banco | SQLite (arquivo local, WAL) — PostgreSQL se houver 2+ caixas **[A DEFINIR]** | funciona sem internet; backup é copiar um arquivo |
| Fiscal | adaptador `app/fiscal/` com dois provedores: API intermediária (Focus NFe ou similar) **ou** PyNFe direto na SEFAZ **[A DEFINIR]** | troca de provedor sem mexer no resto |
| Impressão de cupom | térmica 80 mm via ESC/POS (`python-escpos`) ou spooler do Windows | não existe mais ECF para NFC-e; o cupom é o DANFE NFC-e |
| Impressão A4 | PDF (relatórios, DRE) enviado à impressora padrão | |
| Instalador | PyInstaller (one-dir) + Inno Setup → `Moleka-PDV-Setup.exe` | instala WebView2 se faltar, cria atalho e tarefa de backup |
| Logs e backup | `%APPDATA%\MolekaPDV\` | fora da pasta do programa |

Dinheiro: inteiros em centavos. Datas: ISO 8601, fuso America/Sao_Paulo.

## 3. Módulos e funções (lista do cliente → como entra no sistema)

| Pedido | Módulo | Observações |
|---|---|---|
| Atendimento de caixa | **Caixa (PDV)** | leitor de código de barras, busca por nome, quantidade, desconto, cliente/CPF na nota, formas de pagamento (dinheiro, Pix, débito, crédito; multi-pagamento), atalhos F2–F12 |
| Emissão NFC-e | **Fiscal** | emissão, contingência offline (reenvio automático), cancelamento (prazo legal), inutilização, consulta de status, DANFE NFC-e com QR Code, grupos IBS/CBS |
| Controle de caixa | **Controle de Caixa** | abertura com fundo de troco, sangria, suprimento, fechamento com conferência por forma de pagamento, histórico por operador |
| Cadastro de produtos | **Produtos** | código interno, EAN, descrição, unidade, NCM, CEST, CST/CSOSN, origem, custo, preços, estoque mínimo, foto opcional |
| Ajuste de estoque | **Estoque** | saldo por produto, ajustes com motivo, inventário, baixa automática na venda |
| Entrada em NF por XML | **Compras** | importa XML de NF-e, vincula itens do fornecedor aos produtos (de-para memorizado), atualiza estoque e custo médio |
| Tabela por quantidade | **Tabelas de preço** | faixas (ex.: 1–9, 10–49, 50+) por produto; o PDV aplica a faixa sozinho |
| Tabela varejo e atacado | **Tabelas de preço** | tabela por cliente ou escolhida na venda |
| Cadastro de clientes | **Clientes** | nome, CPF/CNPJ, telefone, endereço, tabela de preço padrão, histórico de compras |
| Lançamento de despesas e receitas | **Financeiro** | contas a pagar/receber, categorias, centro de custo opcional, anexos |
| Fluxo de caixa | **Financeiro** | realizado + previsto (cartões/Pix a receber, contas a pagar) |
| DRE | **Financeiro** | receita bruta → deduções → receita líquida → CMV → lucro bruto → despesas → resultado; por período, com comparação |
| Rentabilidade | **Financeiro** | margem por produto/categoria com base no custo do último XML ou custo médio |

## 4. Visual

- Cores da logomarca (identidade aprovada em 10/11/2026): vermelho `#E43030`, amarelo `#FCF00C`, vinho `#542424`, verde `#249C48`, sobre fundo creme `#FFF9E3`. O laranja da primeira versão saiu (era o fundo do arquivo da logo).
- Componentes com relevo 3D (bisel, extrusão, afundam ao clicar); campos com profundidade interna.
- Logo: oval com extrusão e inclinação 3D que "endireita" ao passar o mouse; mascote animada (balança, inclina na direção do nome, manda beijos). Para braço/mão/olhos se moverem de verdade é preciso a arte em camadas ou vetor **[A DEFINIR — pedir ao cliente]**.
- Resolução alvo: tela de 1366×768. Com a janela maximizada, a área útil é de cerca de **1366×697** (descontados a barra de título e a barra de tarefas): é nesse tamanho que as telas precisam caber sem rolagem. Precisa funcionar em 1920×1080.
- A moldura (menus, faixa do topo, barra de status) fica sempre visível; se a janela for menor, só o miolo da tela rola.
- Protótipo das 5 telas (Capa, Início, Caixa, Financeiro/DRE, Produtos) em canvas de design, com cópia estática em `docs/prototipo/`.

## 5. Fiscal — pontos verificados em 07/11/2026

- NFC-e não usa mais ECF/impressora fiscal; o cupom é o DANFE NFC-e numa térmica comum.
- Campos IBS/CBS existem nos documentos fiscais desde 01/01/2026; preenchimento obrigatório para o regime normal desde 03/08/2026; a rejeição 1115 (nota sem o grupo) foi suspensa pela NT 2025.002 v1.51 e, até 28/09/2026, não tinha data nova; a data de 04/01/2027 para o Simples Nacional foi retirada do calendário; a NFC-e está entre os documentos que precisam carregar o grupo; alíquotas de teste em 2026: CBS 0,9% e IBS 0,1%. Fonte: https://taxcel.com.br/ibs-cbs-nota-fiscal-2026-obrigatorio-rejeicao
- PyNFe (LGPL): suporta NFC-e modelo 65, emissão normal e em contingência, Python 3.8–3.13; o README não cita QR Code nem IBS/CBS e não lista UFs. Fonte: https://github.com/TadaSoftware/PyNFe
- Focus NFe, plano Retail: R$ 62,90/mês, 1 CNPJ, 500 NFC-e + 100 NF-e incluídas, R$ 0,055 por NFC-e extra, 30 dias de teste; a página de preços não fala de contingência offline nem de IBS/CBS. Fonte: https://focusnfe.com.br/precos/

Conclusão: o sistema nasce com os grupos IBS/CBS no XML. Recomendação para a v1: API intermediária (absorve notas técnicas e diferenças por UF); PyNFe fica como segundo provedor do adaptador.

### Emitir ou não a NFC-e em cada venda (pedido 8 da seção 11) — lido em 11/11/2026

O que as fontes lidas dizem (são sites de contabilidade, não o texto oficial das normas):

- **MEI**: dispensado de emitir nota fiscal na venda para consumidor pessoa física; obrigado quando o destinatário tem CNPJ, salvo se o destinatário emitir nota de entrada. Base citada: art. 106 da Resolução CGSN 140/2018 e art. 26 da LC 123/2006. Fontes: https://www.portaltributario.com.br/tributario/O_MEI_e_obrigado_a_emitir_nota_fiscal.htm (texto de 08/07/2025) e https://fiscalia.app/blog/mei-2026-limite-nfe-obrigatoria-cpf-cnpj (17/03/2026).
- **ME ou EPP do Simples Nacional**: a emissão de documento fiscal se aplica, conforme a legislação do estado; a fonte lida não cita dispensa para venda a consumidor. Fonte: https://www.jettax.com.br/blog/quais-sao-as-obrigacoes-do-simples-nacional/ (atualizado em 02/09/2026).
- **Divergência entre fontes**: https://razonet.com.br/contabilidade-digital/nota-fiscal-mei-em-2026-quando-e-obrigatoria-e-como-emitir (24/08/2026) diz que, se o consumidor pedir, o MEI é obrigado a emitir, e que a partir de 2027 a emissão passaria a ser obrigatória em todas as operações. As outras fontes lidas não confirmam esse prazo.
- **Não lido**: o texto oficial das normas; a Resolução CGSN 195, de 21/10/2026, que alterou a 140/2018 (as páginas não abriram); as regras do estado da loja (UF ainda não informada).

Consequência para o sistema: a opção "emitir ou não" será construída, mas **quem diz se a loja pode vender sem emitir é o contador**, conforme o regime tributário e a UF. A venda sem NFC-e fica gravada como "sem documento fiscal", aparece nos relatórios e a emissão posterior respeita os prazos da SEFAZ (a detalhar na Frente 5).

## 6. Impressão

- Térmica 80 mm (Epson, Elgin, Bematech, Daruma…): ESC/POS por USB ou rede. Detectar impressoras instaladas no Windows e permitir escolher.
- Impressora comum (A4): relatórios e DRE em PDF.
- Teste de impressão na tela de Configurações, com status visível no rodapé.

## 7. Instalação e atualização

- `Moleka-PDV-Setup.exe` (Inno Setup) com o app empacotado pelo PyInstaller; instala o WebView2 Runtime se faltar; cria atalho na Área de Trabalho e tarefa de backup diário.
- Sem certificado de assinatura de código, o Windows mostra o aviso do SmartScreen na primeira execução ("Mais informações → Executar assim mesmo").
- No Windows 11 com o Controle Inteligente de Aplicativos (Smart App Control) ligado, o instalador sem assinatura é bloqueado de vez (erro 4551), sem botão para liberar. Visto em 11/11/2026 no PC do Eric. Para esses computadores, a assinatura digital é obrigatória; a compra do certificado é decisão pendente (ver DECISOES de 11/11).
- Atualização: o app verifica uma versão nova em um endereço configurável e baixa o novo instalador (v2).

## 8. Fora de escopo da v1

NF-e modelo 55 (venda para empresa), SAT-CF-e (só SP), delivery/iFood, fidelidade, multi-loja em nuvem. Entram depois se o cliente pedir.

## 9. Perguntas em aberto [A DEFINIR]

1. UF da sorveteria e regime tributário (Simples Nacional?). NCM/CST/ST do sorvete: confirmar com o contador.
2. Rota fiscal: API intermediária (qual) ou PyNFe direto.
3. PC do caixa: versão do Windows; quantos caixas; internet estável.
4. Impressora térmica: marca/modelo e conexão; impressora A4 existente.
5. Logo em vetor ou alta resolução, de preferência com a menina separada do oval.
6. Sistema atual (produtos/clientes para importar) e certificado digital A1 (tem?).
7. **Preço por forma de pagamento** (pedido 2 da seção 11): a regra é um ajuste em % por forma (ex.: desconto no Pix e no dinheiro, acréscimo no crédito) ou um preço próprio por forma em cada produto? E quando a venda é paga em duas formas (pedido 3), o ajuste vale só sobre a parte paga em cada forma?
8. **Emitir ou não a NFC-e** (pedido 8): a loja é MEI ou ME/EPP do Simples? Em qual estado? O contador confirma em quais vendas a emissão pode ser dispensada?
9. Tempo sem uso: o sistema deve pedir a senha de novo depois de algum tempo parado? (Hoje a sessão vale até trocar de operador ou fechar o programa.)

## 10. PC do caixa — diagnóstico de 10/11/2026 (dados medidos com `tools/diagnostico-pc.ps1`)

| Item | Medido |
|---|---|
| Equipamento | Notebook ASUS VivoBook 15 X540UAR |
| Sistema | Windows 10 Home 22H2 (build 19045); última atualização instalada em 09/09/2026 |
| Processador | Intel Core i3-6100U, 2 núcleos / 4 threads, 2,3 GHz |
| Memória | 3,9 GB em 1 módulo — 0,5 GB livres no momento da medição, com compressão de memória ativa |
| Disco | HD mecânico WDC WD10SPZX 1 TB (SATA), saúde "Healthy", 874 GB livres |
| Tela | 1366×768 |
| Rede | Wi-Fi 150 Mbps, ping 13 ms |
| Impressora de cupom | ELGIN i9 (USB), fila "ELGIN i9(USB)", porta USB001, padrão do Windows, pronta, fila vazia |
| Impressora A4 | nenhuma física instalada (só PDF, XPS, OneNote e Fax virtuais) |
| Leitor de código de barras | não identificado no diagnóstico (1 teclado presente) — testar com o leitor conectado |
| Já instalado | WebView2 157.0.4341.42; SQL Server 2014 (instância SQL2014) rodando — provável banco do sistema atual da loja; AnyDesk como serviço |
| Não instalado | Python (só o atalho da Microsoft Store), Git |
| Eventos | 7 erros Kernel-Power + 7 EventLog em 7 dias (indício de desligamentos sem fechar o Windows — a confirmar) |

Consequências para o projeto (recomendações, não decisões fechadas):

1. **Interface leve.** Animações só em CSS, como estão; nada de WebGL/3D pesado no PDV — este hardware não aguenta sem travar o caixa.
2. **Meta de memória** do Moleka PDV aberto (Python + WebView2): até ~400 MB. Medir quando houver build.
3. **Instalador autocontido**: o PyInstaller precisa levar o Python junto; o PC não tem Python.
4. **Impressão** pela fila do Windows "ELGIN i9(USB)" em modo RAW (ESC/POS) — confirmar no teste de impressão.
5. **Banco resistente a queda de energia**: SQLite em WAL + backup diário; recomendar nobreak ao cliente.
6. **Migração**: o SQL Server 2014 pode ser a fonte de produtos e clientes do sistema atual.
7. **Hardware**: a lentidão vem principalmente de 4 GB de RAM + HD mecânico; a troca por SSD e a ampliação para 8 GB são as melhorias de maior efeito.

## 11. Pedidos de 11/11/2026 (Eric) — onde cada um entra

Ordem de construção aprovada: (1) login e operadores, (2) cadastro de produtos e preços, (3) abrir e fechar o caixa, (4) venda. A cada função pronta sai um instalador novo para teste.

| # | Pedido | Onde entra | Situação e o que falta decidir |
|---|---|---|---|
| 1 | Tabela de preço por quantidade | Frente 2 (cadastro das faixas) e Frente 4 (o caixa aplica a faixa sozinho) | O modelo e o cálculo já existem (`preco_produto.qtd_min`, `app/precos.py`, com testes). Faltam as telas. |
| 2 | Tabela de preço por forma de pagamento | Frente 2 (cadastro da regra) e Frente 4 (aplicação na venda) | **Falta decidir a regra** (seção 9, pergunta 7). Não há nada no modelo ainda. |
| 3 | Mais de uma forma de pagamento na mesma venda (ex.: parte no débito, parte no crédito) | Frente 4 | O modelo já aceita vários pagamentos por venda (`pagamento`). Falta a tela e a conferência "soma dos pagamentos = total". |
| 4 | Saldo de vendas do dia na tela | Frente 4 | Total do dia vindo do banco, na tela do Caixa e no "Resumo de hoje" do Início. Sem venda, mostra "—" e o motivo. |
| 5 | Cliente com CPF ou CNPJ e tabela atacadista ou varejista no cadastro | Frente 2 | O cadastro já tem `cpf_cnpj` e `tabela_id`. Faltam a validação dos dígitos do CPF/CNPJ e a tela. |
| 6 | Alterar (editar) a quantidade dos itens na tela do PDV | Frente 4 | Ao mudar a quantidade, a faixa de preço do item é recalculada. |
| 7 | Trocar a forma de pagamento mesmo depois de escolhida | Frente 4 | Os pagamentos ficam editáveis até a venda ser finalizada. |
| 8 | Ao finalizar a venda, escolher se emite ou não a NFC-e | Frente 4 (a escolha fica gravada na venda) e Frente 5 (emissão) | Depende do regime tributário e da UF (seção 5 e seção 9, pergunta 8). |
| 9 | No PDV, escolher o cliente pelo cadastro e trocar o cliente da venda | Frente 4 | Ao trocar o cliente, passa a valer a tabela de preço dele e os preços dos itens são recalculados, com aviso na tela. |

## 12. Operadores, login e permissões (Frente 1, feita em 11/11/2026)

- **Primeiro acesso**: sem nenhum operador cadastrado, a capa pede a criação do gerente (nome, usuário e senha) e já entra com ele.
- **Login**: na capa, o operador escolhe o nome na lista e digita a senha. A lista já abre no último operador usado. Cinco senhas erradas seguidas travam aquele usuário por 30 segundos.
- **Senha**: mínimo de 4 caracteres. O banco guarda só o hash (scrypt); a senha não aparece em resposta da API nem no log.
- **Sessão**: vale até "Trocar de operador" (menu Arquivo) ou até fechar o programa. Cada operador troca a própria senha em Arquivo → Minha senha.
- **Operadores** (menu Cadastros, só o gerente): cadastrar, alterar nome, usuário, perfil e senha, e inativar. Operador não é apagado: fica inativo, e o histórico dele continua guardado. Ninguém inativa nem rebaixa o próprio usuário; assim sempre existe um gerente ativo.
- **Recuperação de acesso** (senha esquecida): com o sistema fechado, rodar `MolekaPDV.exe --redefinir-senha` (ou `--redefinir-senha usuario`). O programa sorteia uma senha provisória, mostra na tela uma única vez e registra o uso no log.

Perfis (padrão proposto; o Eric pode mudar):

| O que faz | Operador | Gerente |
|---|---|---|
| Vender no caixa e consultar produtos | sim | sim |
| Cadastrar cliente | sim | sim |
| Trocar a própria senha | sim | sim |
| Cadastrar ou alterar produtos, preços e tabelas de preço | não | sim |
| Ver o financeiro (DRE, fluxo de caixa, rentabilidade) | não | sim |
| Estoque, entrada de NF, fiscal e configurações | não | sim |
| Cadastrar, alterar e inativar operadores | não | sim |

A definir na Frente 3: se abertura, sangria, suprimento e fechamento do caixa ficam com o operador ou pedem a senha do gerente.
