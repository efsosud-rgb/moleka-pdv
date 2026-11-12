# Especificação — Moleka PDV (rascunho v0.3, 07/11/2026; atualizado em 11/11/2026)

Documento vivo. Itens marcados **[A DEFINIR]** dependem de resposta do cliente ou do Eric; ver seção 9. Os pedidos de 11/11/2026 estão na seção 11; operadores e permissões, na seção 12; as regras de cadastros, caixa e venda (versão 0.3.0), na seção 13; as de estoque, entrada de nota por XML e financeiro (versão 0.4.0), na seção 14.

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
| Impressão de cupom | térmica 80 mm, ESC/POS pela fila de impressão do Windows em modo RAW (funções do próprio Windows, sem biblioteca extra) | não existe mais ECF para NFC-e; o cupom fiscal será o DANFE NFC-e. Feito na 0.5.0 o comprovante não fiscal (seção 15) |
| Impressão A4 | impressão do Windows a partir de uma folha montada só para o papel | para guardar em PDF, a impressora "Microsoft Print to PDF" do Windows. Feito na 0.5.0 (seção 15) |
| Instalador | PyInstaller (one-dir) + Inno Setup → `Moleka-PDV-Setup.exe` | instala WebView2 se faltar e cria o atalho. A cópia de segurança diária é feita pelo próprio programa (seção 15), sem tarefa agendada do Windows |
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
- **Como ficou (versão 0.5.0): ver a seção 15.** O que está acima era o plano de 07/11/2026.

## 7. Instalação e atualização

- `Moleka-PDV-Setup.exe` (Inno Setup) com o app empacotado pelo PyInstaller; instala o WebView2 Runtime se faltar; cria atalho na Área de Trabalho. A cópia de segurança diária ficou a cargo do próprio programa, sem tarefa agendada (seção 15).
- Sem certificado de assinatura de código, o Windows mostra o aviso do SmartScreen na primeira execução ("Mais informações → Executar assim mesmo").
- No Windows 11 com o Controle Inteligente de Aplicativos (Smart App Control) ligado, o instalador sem assinatura é bloqueado de vez (erro 4551), sem botão para liberar. Visto em 11/11/2026 no PC do Eric. Para esses computadores, a assinatura digital é obrigatória; a compra do certificado é decisão pendente (ver DECISOES de 11/11).
- Atualização: o app verifica uma versão nova em um endereço configurável e baixa o novo instalador (v2).

## 8. Fora de escopo da v1

NF-e modelo 55 (venda para empresa), SAT-CF-e (só SP), delivery/iFood, fidelidade, multi-loja em nuvem. Entram depois se o cliente pedir.

## 9. Perguntas em aberto [A DEFINIR]

1. UF da sorveteria e regime tributário (Simples Nacional?). NCM/CST/ST do sorvete: confirmar com o contador.
2. Rota fiscal: API intermediária (qual) ou PyNFe direto.
3. PC do caixa: versão do Windows; quantos caixas; internet estável.
4. ~~Impressora térmica: marca/modelo e conexão; impressora A4 existente.~~ **Respondida pelo diagnóstico de 10/11/2026** (seção 10): ELGIN i9 por USB, padrão do Windows; nenhuma impressora A4 física.
5. Logo em vetor ou alta resolução, de preferência com a menina separada do oval.
6. Sistema atual (produtos/clientes para importar) e certificado digital A1 (tem?).
7. ~~Preço por forma de pagamento~~ **Respondida pelo Eric em 11/11/2026**: percentual por forma (desconto ou acréscimo); com duas formas na venda, o percentual vale só sobre a parte paga em cada uma. Ver seção 13.
8. **Emitir ou não a NFC-e** (pedido 8): a loja é MEI ou ME/EPP do Simples? Em qual estado? O contador confirma em quais vendas a emissão pode ser dispensada?
9. Tempo sem uso: o sistema deve pedir a senha de novo depois de algum tempo parado? (Hoje a sessão vale até trocar de operador ou fechar o programa.)
10. **Controle de caixa**: o operador comum pode abrir, fechar, sangrar e suprir sozinho (como está) ou alguma dessas ações deve pedir o gerente? No fechamento, quem fecha deve ver o valor esperado (como está) ou contar "às cegas"?
11. **Desconto e cancelamento no caixa**: hoje o gerente precisa entrar com o usuário dele (a venda continua aberta). Vale construir a autorização por senha do gerente na hora, sem trocar de operador?
12. Quais percentuais a loja usa em cada forma de pagamento (dinheiro, Pix, débito, crédito)? O sistema começa com 0% em todas.
13. **A loja fabrica o sorvete, revende, ou os dois?** Quem revende dá entrada pela nota e o custo do produto sai dela. Quem fabrica compra leite, açúcar e embalagem: o custo de cada sorvete depende de uma ficha técnica (receita), que ainda não existe. Enquanto isso, quem fabrica pode lançar a matéria-prima como custo (grupo "Custo das vendas"). Ver seção 14.
14. **Custo na entrada da nota**: hoje o custo do item soma frete, seguro, outras despesas, IPI e ICMS-ST, e não desconta imposto nenhum (conta de quem não recupera imposto na compra). O contador confirma que é assim para a loja?
15. **Vender sem saldo no estoque**: hoje a venda passa e o saldo fica negativo, em destaque na tela Estoque. Deve continuar assim, avisar no caixa ou bloquear?
16. **Cartão no fluxo de caixa**: hoje a venda no cartão entra no dia da venda, pelo valor cheio. A loja quer ver o dinheiro no dia em que cai na conta, já sem a taxa da maquininha? Quais são os prazos e as taxas?
17. **Plano de contas**: as 17 categorias iniciais do Financeiro (seção 14) servem para a loja? Quais faltam e quais sobram?
18. **Comprovante de venda**: oferecer o botão de imprimir depois de cada venda (como está), imprimir sozinho em toda venda ou não imprimir? Uma via ou duas?
19. **Gaveta de dinheiro**: a loja tem gaveta ligada na impressora de cupom? Ela deve abrir sozinha na venda em dinheiro?
20. **Cópia de segurança**: qual vai ser a pasta extra (pendrive que fica na loja, HD externo ou pasta sincronizada com a nuvem)? Quantos dias guardar (hoje, 30)?
21. **Dados da loja** para o cabeçalho do cupom e dos relatórios: nome, razão social, CNPJ, inscrição estadual, endereço, telefone e a mensagem do fim do cupom.

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
| 1 | Tabela de preço por quantidade | Frente 2 (cadastro das faixas) e Frente 4 (o caixa aplica a faixa sozinho) | **Feito na 0.3.0.** Na ficha do produto, cada tabela tem faixas "a partir de"; no caixa, a linha do item mostra a faixa aplicada. |
| 2 | Tabela de preço por forma de pagamento | Frente 2 (cadastro da regra) e Frente 4 (aplicação na venda) | **Feito na 0.3.0**, pela regra escolhida pelo Eric: percentual por forma (Cadastros → Tabelas de preço e pagamento). Os botões de pagamento mostram quanto fica em cada forma. |
| 3 | Mais de uma forma de pagamento na mesma venda (ex.: parte no débito, parte no crédito) | Frente 4 | **Feito na 0.3.0.** Ao receber, digita-se só a parte paga naquela forma; o resto fica para outra. A venda só finaliza quando tudo está quitado. |
| 4 | Saldo de vendas do dia na tela | Frente 4 | **Feito na 0.3.0.** No topo do Caixa (total e número de vendas; clicando, o detalhe por forma) e no "Resumo de hoje" do Início. Sem venda, mostra "—" e o motivo. |
| 5 | Cliente com CPF ou CNPJ e tabela atacadista ou varejista no cadastro | Frente 2 | **Feito na 0.3.0.** Tela Clientes, com CPF e CNPJ conferidos pelos dígitos; a tabela de preço do cliente, só o gerente define. |
| 6 | Alterar (editar) a quantidade dos itens na tela do PDV | Frente 4 | **Feito na 0.3.0.** A quantidade é um campo em cada linha; ao mudar, a faixa de preço é recalculada. O botão × tira o item. |
| 7 | Trocar a forma de pagamento mesmo depois de escolhida | Frente 4 | **Feito na 0.3.0.** Cada pagamento lançado tem uma lista para trocar a forma (o percentual é refeito) e um × para tirar, até a venda ser finalizada. |
| 8 | Ao finalizar a venda, escolher se emite ou não a NFC-e | Frente 4 (a escolha fica gravada na venda) e Frente 5 (emissão) | **A escolha está na tela (0.3.0)**; "com NFC-e" fica desligado até o módulo fiscal existir. **Nenhuma NFC-e é emitida ainda.** A emissão depende do regime tributário e da UF (seção 5 e seção 9, pergunta 8). |
| 9 | No PDV, escolher o cliente pelo cadastro e trocar o cliente da venda | Frente 4 | **Feito na 0.3.0.** Busca por nome, CPF ou CNPJ (F4); trocar ou tirar o cliente recalcula os preços pela tabela dele, com aviso na tela. |

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
| Abrir e fechar o caixa, sangria e suprimento | sim | sim |
| Cancelar a venda que está aberta | sim | sim |
| Dar desconto no total da venda | não | sim |
| Cancelar venda já finalizada (com motivo) | não | sim |
| Definir a tabela de preço do cliente e inativar cliente | não | sim |
| Ver os fechamentos de caixa anteriores | não | sim |
| Cadastrar ou alterar produtos, preços, tabelas de preço e percentuais das formas de pagamento | não | sim |
| Ver o financeiro (DRE, fluxo de caixa, rentabilidade) | não | sim |
| Estoque, entrada de NF, fiscal e configurações | não | sim |
| Cadastrar, alterar e inativar operadores | não | sim |

"Desconto só do gerente" foi decisão do Eric (11/11/2026). As linhas do caixa são o padrão adotado na versão 0.3.0, a confirmar com ele (seção 9, perguntas 10 e 11).

## 13. Cadastros, controle de caixa e venda (Frentes 2 a 4, feitas em 11/11/2026, versão 0.3.0)

### Preço

- **Tabelas de preço**: VAREJO (padrão da loja) e ATACADO nascem com o banco; o gerente cria outras. A venda usa a tabela do cliente; sem cliente, ou com cliente sem tabela própria, a padrão.
- **Por quantidade**: em cada tabela o produto tem faixas "a partir de" (ex.: 1 → R$ 5,00; 10 → R$ 4,50). Vale a maior faixa que a quantidade alcança. Toda tabela usada precisa da faixa a partir de 1.
- Produto sem preço na tabela do cliente usa o preço da tabela padrão. Sem preço nenhum, não entra na venda.
- **Por forma de pagamento**: percentual por forma, de -50% a +50% (negativo é desconto). Vale só sobre a parte paga naquela forma.

### Venda (tela do Caixa)

- O caixa precisa estar aberto. Há uma venda aberta por vez, guardada no banco.
- **Produto**: leitor de código de barras, código ou nome (lista de sugestões; sem acento também acha). `3*codigo` lança três de uma vez. O mesmo produto repetido soma na mesma linha.
- **Quantidade**: editável na linha. Casas decimais só para KG, G, L, ML e M.
- **Cliente**: busca no cadastro; pode ser trocado ou retirado, e os preços são recalculados.
- **Desconto** no total: só o gerente, em reais ou em %.
- **Pagamento**: uma ou mais formas. Cada pagamento guarda o valor que entrou e o desconto ou acréscimo da forma. Só o dinheiro dá troco (até R$ 1.000,00; acima disso o sistema pede para conferir o valor). A forma de um pagamento lançado pode ser trocada.
- Contas: base = subtotal - desconto; total = base + ajustes das formas. Mexer em itens, cliente ou desconto desfaz os pagamentos.
- **Finalizar**: só com tudo pago; pergunta "com NFC-e" ou "sem NFC-e" (a escolha fica gravada; a emissão é da Frente 5). Dá baixa no estoque.
- **Cancelar**: a venda aberta, qualquer operador; a finalizada, só o gerente, com motivo, enquanto o caixa dela estiver aberto (o estoque volta).
- **Saldo do dia**: vendas finalizadas hoje, no horário de Brasília; canceladas ficam de fora.

### Controle de caixa

- Um caixa (Caixa 01) e uma sessão aberta por vez. Abertura com fundo de troco.
- **Sangria** (sai dinheiro) e **suprimento** (entra dinheiro): com valor e motivo, gravados com o nome de quem fez; a sangria não passa do dinheiro esperado.
- Dinheiro esperado = fundo + vendas em dinheiro + suprimentos - sangrias. Nas outras formas, o esperado é o recebido nas vendas.
- **Fechamento**: digita-se o contado em cada forma; o sistema guarda esperado, contado e diferença. Não fecha com venda aberta. Depois de fechado, só uma nova abertura volta a vender.

### O que ainda não existe nestas telas

NFC-e; CPF na nota; importação de produtos por planilha; autorização do gerente por senha na hora. A impressão do comprovante chegou na versão 0.5.0 (seção 15). A tela de estoque e o financeiro chegaram na versão 0.4.0 (seção 14); a venda não vira um lançamento no financeiro: o fluxo de caixa, o DRE e a rentabilidade leem as vendas direto.

## 14. Estoque, entrada de nota por XML e financeiro (Frentes 7 e 8, feitas em 11/11/2026, versão 0.4.0)

As três telas são só do gerente. Nenhuma das regras abaixo foi combinada antes com o Eric: são o padrão adotado para as telas funcionarem (ver DECISOES de 11/11/2026 e as perguntas 13 a 17 da seção 9).

### Estoque (menu Estoque → Saldos, ajustes e contagem)

- O saldo de cada produto é a soma dos movimentos: venda (sai), cancelamento de venda (volta), entrada de nota, estorno de nota, entrada e saída feitas à mão e contagem. Ninguém digita o saldo direto.
- No alto: quantos produtos têm saldo, quantos estão abaixo do mínimo do cadastro, quantos estão com saldo negativo e o **valor do estoque a custo** (saldo × custo médio; produto sem custo fica fora da soma, e a tela diz quantos são).
- A lista filtra por nome, código, código de barras ou categoria (sem acento também acha) e por situação: todos, com saldo, abaixo do mínimo, saldo negativo.
- **Entrada** e **saída** à mão: quantidade e motivo obrigatório (por exemplo: quebra, produção do dia). Na entrada, o custo de cada unidade é opcional; informado, entra na média.
- **Contagem**: digita-se quanto há na prateleira; o sistema grava a diferença como movimento e o saldo passa a ser o contado. A contagem não mexe no custo.
- Antes de gravar, a tela mostra o saldo de agora e o saldo depois. O **histórico** do produto mostra cada movimento com data, quantidade, saldo depois, custo, motivo e quem fez.
- Casas decimais só para KG, G, L, ML e M. "1.000" com ponto é recusado (mil ou um?): digita-se 1000 ou 1,000.
- Vender sem saldo é permitido: o saldo fica negativo e aparece em destaque (pergunta 15).

### Custo

- O custo do produto é o **custo médio ponderado**, em centavos: `(saldo × custo de agora + quantidade que entrou × custo da entrada) ÷ (saldo + quantidade)`, arredondado para o centavo. Com saldo zero ou negativo, ou sem custo anterior, o custo da entrada passa a ser o custo. Guardam-se o custo médio e o da última entrada.
- Saída, contagem, venda e cancelamento de venda não mudam o custo.
- A venda **guarda o custo de cada item no momento em que é finalizada**; é esse o custo usado no DRE e na rentabilidade. Venda feita antes da 0.4.0 não tem custo gravado.

### Entrada de NF por XML (menu Estoque → Entrada de NF)

- Aceita o arquivo XML da **NF-e modelo 55** (a nota de compra), autorizada ou não. Recusa, dizendo o motivo: arquivo que não é XML, cortado, maior que 2 MB, NFC-e (modelo 65), evento (cancelamento, carta de correção) e chave de acesso com dígito errado. Chave com CNPJ de letras (alfanumérico) é aceita.
- **Passo 1 — conferir** (não grava nada): a tela mostra fornecedor, número, data, total, itens e parcelas, e os **avisos**: nota sem protocolo de autorização, nota não autorizada pela SEFAZ, nota de entrada emitida pelo próprio fornecedor, total diferente da soma dos itens, item de brinde ou bonificação (entra com custo zero), parcelas que não somam o total, nota já importada. O sistema ainda não confere se a nota foi emitida para a loja (o CNPJ da loja ainda não está cadastrado).
- Em cada item o gerente escolhe: **dar entrada num produto nosso** (busca por nome ou código), **criar um produto novo** (com a descrição, o código de barras e o NCM da nota; nasce **sem preço de venda**) ou **não dar entrada**. O sistema sugere o produto pela memória daquele fornecedor e, se não houver, pelo código de barras.
- **Fator**: quantas unidades nossas há em cada unidade da nota (caixa com 24 → 24). Entra no estoque `quantidade da nota × fator`. A tela mostra, antes de gravar, quanto entra e o custo de cada unidade.
- **Custo do item** = valor dos produtos − desconto + frete + seguro + outras despesas + IPI + ICMS-ST (com FCP-ST). O ICMS próprio não é somado (já está no valor dos produtos). Custo de cada unidade = custo do item ÷ quantidade que entra, arredondado para o centavo.
- **Passo 2 — importar**: grava a nota, os movimentos de estoque, o custo novo, a memória "código do fornecedor → nosso produto" e as contas a pagar. O que entra é sempre a nota que estava na tela: se o arquivo for trocado depois da conferência, a importação é recusada. O arquivo fica guardado em `%APPDATA%\MolekaPDV\xml\entrada\<chave>.xml`. A mesma nota não entra duas vezes.
- **Contas a pagar**: uma por parcela (duplicata) da nota, na categoria "Compra de mercadorias para revenda" ou na que o gerente escolher. Nota sem parcelas só gera conta se o gerente digitar um vencimento (uma conta com o total). Dá para importar sem gerar conta.
- **Notas importadas**: lista com fornecedor, número, total, itens e contas; "Ver" mostra os itens como entraram. **Estornar** (com motivo) tira do estoque o que entrou, volta o custo e cancela as contas a pagar em aberto daquela nota. Não estorna se alguma parcela já foi paga: primeiro se desfaz a baixa. Se o custo não puder ser refeito com exatidão, a tela lista os produtos para o gerente conferir. A nota estornada pode ser importada de novo.

### Financeiro: categorias e lançamentos (menu Financeiro)

- **Categorias**: cada uma pertence a um grupo do DRE: receita de vendas, deduções da receita, custo das vendas (CMV), despesas operacionais, outras receitas, outras despesas, fora do resultado (saídas) e fora do resultado (entradas). O banco nasce com 17 categorias, só nomes, sem valor. O gerente cria, renomeia e inativa; o grupo de uma categoria com lançamento não muda.
- **Lançamento**: despesa (conta a pagar) ou receita (conta a receber), com descrição, categoria, valor, vencimento e competência (o dia a que o gasto ou a receita pertence; em branco, vale o vencimento). Pode nascer já pago, com o dia e a forma do pagamento. Não há campo de fornecedor, cliente, documento nem observação: o que precisar vai na descrição.
- **Baixa**: dia e forma do pagamento ou do recebimento. Dá para desfazer.
- **Situação**: em aberto, vencido (venceu antes de hoje e não foi pago), pago ou recebido, cancelado.
- Lançamento **não é apagado**: é cancelado (fica na lista de cancelados, com data e autor). Pago não se altera nem cancela sem antes desfazer a baixa. Conta que veio de nota de compra só sai estornando a nota.
- A lista filtra por período (do vencimento), tipo e situação. "Vencidas (qualquer data)" e "Em aberto (qualquer data)" não olham o período. Se há conta em aberto vencendo fora do período escolhido, a tela avisa quantas são e oferece "Ver todas em aberto" (a nota importada hoje costuma vencer no mês que vem).
- No alto: a pagar, a receber, pago e recebido das contas com vencimento no período, mesmo com a lista filtrada. Com o filtro "Em aberto (qualquer data)", "A pagar" e "A receber" somam tudo o que está em aberto.
- A lista nunca vem cortada: se passar de 2.000 lançamentos, a tela pede um período menor (uma lista cortada daria totais errados).
- Períodos prontos: este mês, mês passado, hoje, últimos 7 e 30 dias, próximos 30 dias, mês que vem, este ano, ou as datas digitadas (dia/mês/ano), até 366 dias.

### Fluxo de caixa

- Por dia: **vendas** (no dia da venda, todas as formas, pelo valor que o cliente pagou), **outros recebimentos** (receitas baixadas no dia), **pagamentos** (despesas baixadas no dia), saldo do dia e acumulado do período.
- No alto: quanto entrou, quanto saiu, o saldo do período e o que está em aberto com vencimento no período (a receber e a pagar); à parte, o que está vencido, de qualquer data.
- Sangria e suprimento não entram (são da gaveta: ver Controle de caixa). Prazo e taxa de cartão não são considerados (pergunta 16). O saldo é o do período, não o da conta bancária: o sistema não conhece o saldo inicial.

### DRE (resultado do período)

- Por **competência**: as vendas contam no dia em que foram feitas; os lançamentos, no dia de competência, pagos ou não. Cancelados ficam de fora.

| Linha | De onde vem |
|---|---|
| Receita bruta | itens vendidos + acréscimos das formas de pagamento + receitas lançadas no grupo "receita de vendas" |
| (−) Descontos | desconto do gerente + descontos das formas de pagamento |
| (−) Deduções | lançamentos do grupo "deduções" (impostos sobre a venda, taxas de cartão e Pix) |
| = Receita líquida | |
| (−) CMV | custo gravado nos itens vendidos + lançamentos do grupo "custo das vendas" |
| = Lucro bruto | |
| (−) Despesas operacionais | lançamentos do grupo, abertos por categoria |
| (+) Outras receitas, (−) outras despesas | lançamentos dos grupos |
| = Resultado | |

- As deduções, o CMV, o lucro bruto, as despesas e o resultado mostram também o percentual sobre a receita líquida. As linhas abrem em detalhes (por exemplo, cada categoria de despesa).
- **Compra de mercadoria, retirada dos sócios, empréstimo e aporte ficam fora do resultado**: aparecem só no fluxo de caixa.
- **Sem custo, sem lucro inventado**: se nenhuma venda do período tem custo gravado e não há custo lançado, o CMV, o lucro bruto e o resultado aparecem como "—", com o motivo. Se só parte dos itens tem custo, as três linhas vêm marcadas como parciais e um aviso diz quantos itens e quanto em vendas ficaram sem custo.
- Sem vendas nem lançamentos no período, a tela mostra "—" e o motivo, em todas as linhas.

### Rentabilidade por produto

- Por produto vendido no período: quantidade, receita, custo, margem em reais e em %. A receita do produto é o que o cliente pagou por ele: o desconto do gerente e o desconto ou acréscimo das formas de pagamento são divididos entre os itens pela proporção do valor, sem perder centavos.
- O custo é o gravado em cada venda. Produto com alguma venda sem custo aparece com "—" no custo e na margem e fica fora do total da margem; a tela mostra separadas a receita dos produtos com custo e a dos sem custo.

### O que ainda não existe nestas telas

Ficha técnica e produção (para quem fabrica); contagem de vários produtos de uma vez (inventário); prazo e taxa das maquininhas no fluxo de caixa; saldo inicial e conta bancária; contas que se repetem todo mês; centro de custo e anexos; comparação de períodos; margem por categoria de produto; lançamento automático de impostos e taxas (hoje são digitados como lançamento).

## 15. Configurações, impressão e cópia de segurança (Frente 6 e parte da 9, feitas em 11/11/2026, versão 0.5.0)

A tela **Configurações** (menu Arquivo → Configurações, ou o menu lateral) é só do gerente e tem três abas. Nenhuma das regras abaixo foi combinada antes com o Eric: são o padrão adotado para as telas funcionarem (ver DECISOES de 11/11/2026 e as perguntas 18 a 21 da seção 9).

### Dados da loja

- Nome da loja, razão social, CNPJ, inscrição estadual, endereço, telefone e uma mensagem para o fim do cupom. Nenhum campo é obrigatório; o cupom e os relatórios mostram só o que estiver preenchido. O programa não traz nenhum dado de exemplo.
- O CNPJ é conferido pelos dígitos; o CEP tem de ter 8 números; a inscrição estadual aceita números ou "ISENTO".
- Quando a NFC-e for ligada, serão estes mesmos dados. Senha de certificado e outros segredos não ficam aqui.

### Impressora de cupom

- A lista mostra as impressoras instaladas no Windows, com a padrão marcada. O gerente escolhe a impressora, a **largura do papel** (48, 42 ou 32 colunas), a página de **letras com acento** (CP850, CP860, Windows-1252 ou sem acento), se a impressora **corta o papel** e se há **gaveta de dinheiro** ligada nela.
- **Imprimir teste** manda uma página com o nome da impressora, uma régua de números do tamanho da largura escolhida, uma linha de letras acentuadas e exemplos de negrito e de letra grande. A tela mostra o que foi mandado e pergunta se saiu certo.
- A impressora só aparece como testada (indicador verde) depois que o gerente responde **"Sim, saiu certo"**. Mudar a impressora, a largura ou os acentos desfaz a confirmação. Se o teste sair errado: acentos trocados → mudar "Letras com acento"; régua quebrada em duas linhas → diminuir a largura.
- O programa manda o cupom para a fila de impressão do Windows. Quando o Windows aceita, o programa diz "enviado"; se saiu papel, só quem olha a impressora sabe.

### Comprovante de venda (tela do Caixa)

- É um **comprovante não fiscal**, e isso sai escrito nele. Traz os dados da loja, número, data e hora da venda, operador, cliente (se houver), itens, subtotal, descontos e acréscimos, total, formas de pagamento, troco e a mensagem do fim.
- Em Configurações o gerente escolhe o que acontece depois de cada venda: **oferecer o botão** (padrão), **imprimir sozinho** ou **não imprimir**; e uma ou duas vias.
- **Ctrl+P** ou o botão **Comprovante** imprime o comprovante da última venda encerrada naquela tela, quantas vezes for preciso. Se a impressora não puder imprimir (ou não houver impressora escolhida), o comprovante aparece na tela, com o motivo.
- A impressora **nunca** desfaz nem trava a venda: se falhar, a venda fica finalizada e a tela do caixa avisa.
- Com a gaveta ligada em Configurações, a venda que tem dinheiro manda o pulso de abertura. Reimprimir não abre a gaveta.

### Controle de caixa: comprovante, resumo e fechamento

- Na aba **Vendas**, cada venda tem um botão de impressora que mostra o comprovante na tela, com o botão Imprimir. Vale também para venda cancelada (o papel sai marcado como cancelada).
- **Imprimir o resumo** mostra o caixa aberto até aquele momento: vendas, recebido por forma, dinheiro esperado na gaveta, sangrias e suprimentos.
- Depois de **fechar o caixa**, o papel do fechamento (com esperado, contado e diferença de cada forma e uma linha para assinatura) aparece na tela pronto para imprimir, se houver impressora de cupom escolhida. O gerente imprime qualquer fechamento anterior na aba **Fechamentos**; o operador comum, só o caixa aberto e o que ele mesmo fechou.

### Relatórios em folha comum

- Botão **Imprimir** (ou Ctrl+P) em **Financeiro** (contas a pagar e a receber, fluxo de caixa, DRE e rentabilidade) e em **Estoque**. Abre a impressão do Windows, em qualquer impressora instalada; para guardar em PDF, escolha "Microsoft Print to PDF".
- A folha traz o nome e o CNPJ da loja, o título, o período, os filtros usados, os números e as tabelas que estão na tela e, no pé, a data, quem imprimiu e a versão do programa. Os valores são os da tela; onde a tela mostra "—" e o motivo, a folha mostra o mesmo.

### Cópia de segurança

- O programa copia o banco de dados **uma vez por dia**, para `%APPDATA%\MolekaPDV\backups\moleka-AAAA-MM-DD.db`: ao abrir (se a cópia do dia ainda não existir), a cada fechamento de caixa (a cópia do dia é refeita) e quando o gerente clica em **Fazer a cópia agora**. De hora em hora ele confere de novo.
- Cada cópia é aberta e conferida antes de valer. Ficam guardadas as últimas **30** (o gerente escolhe de 7 a 365); as mais antigas são apagadas.
- **Pasta extra**: um pendrive que fica na loja, outro disco ou uma pasta sincronizada com a nuvem. Recebe a mesma cópia. Sem ela, a cópia fica no mesmo disco do sistema e não protege se o disco estragar ou o computador for roubado; a tela diz isso.
- O indicador **Backup** do rodapé fica verde com a cópia de hoje feita e, havendo pasta extra, com ela já tendo recebido a de hoje. Se o pendrive estiver fora, o indicador avisa, e o programa tenta de novo sozinho.
- **Voltar uma cópia** ainda é feito à mão. Os passos abaixo foram conferidos em 11/11/2026 com um banco de teste, fora do Windows (são só trocas de nome e cópia de arquivos); no Windows ainda não foram feitos:
  1. Feche o Moleka PDV.
  2. Abra a pasta de dados: aperte `Win + R`, cole `%APPDATA%\MolekaPDV` e dê Enter.
  3. **Não apague nada.** Mude o nome de `moleka.db` para `moleka-com-problema.db`. Se existirem os arquivos `moleka.db-wal` e `moleka.db-shm`, mude o nome deles também.
  4. Abra a pasta `backups` (ou a pasta extra), copie o arquivo do dia desejado (`moleka-AAAA-MM-DD.db`), cole na pasta de dados e mude o nome da cópia para `moleka.db`.
  5. Abra o programa. Tudo o que foi lançado depois daquela cópia não estará lá.

### O que ainda não existe nestas telas

Logo e QR Code no cupom; via do estabelecimento; voltar uma cópia pela tela; DANFE NFC-e (Frente 5). O relatório de vendas por período e a exportação para o Excel chegaram na versão 0.6.0 (seção 16).

### O que não foi verificado

Ver "Verificado" e "Não verificado" da versão 0.5.0 em PLANO.md. Em resumo: **nenhum cupom saiu ainda numa impressora de verdade**, e as telas novas não foram vistas dentro da janela do programa no Windows.

## 16. Relatório de vendas e planilhas do Excel (versão 0.6.0, feita em 12/11/2026)

Menu **Relatórios → Vendas por período**, ou o bloco **Relatórios** da tela Início. Só o gerente. Nenhuma das regras abaixo foi combinada antes com o Eric: são o padrão adotado (ver DECISOES de 12/11/2026).

### Regras dos números

- **Venda do período** = venda **finalizada** com a hora da finalização dentro do período. Venda cancelada não soma em nada, nem quando foi cancelada depois, em outro dia.
- **Faturamento** = soma dos totais das vendas: o que o cliente pagou, já com o desconto do gerente e o desconto ou acréscimo da forma de pagamento. É o mesmo total de vendas da Rentabilidade e do Fluxo de caixa no mesmo período. No DRE, as mesmas vendas entram como receita bruta (itens e acréscimos) menos os descontos concedidos: sem outros lançamentos de receita ou de dedução, a receita líquida do DRE é igual ao faturamento. (Os três casos são conferidos por testes.)
- **Ticket médio** = faturamento ÷ número de vendas, arredondado no centavo (meio centavo para cima).
- **Descontos dados** = desconto do gerente + descontos das formas de pagamento. Os acréscimos das formas aparecem separados.
- **Cancelamentos** contam no dia em que foram feitos (hora do cancelamento), separados em **antes de finalizar** (a venda nem chegou a ser paga) e **depois de finalizada** (estorno; só o gerente faz).
- **Dia, dia da semana e hora são os da loja** (horário de Brasília), não os do banco (que guarda em UTC): uma venda das 23:30 conta no dia dela, às 23 h.
- **Por produto**, o valor de cada venda é dividido entre os itens na proporção do preço de cada um (descontos e acréscimos incluídos), sem perder nem criar centavos: a mesma divisão da rentabilidade. A soma dos produtos dá o faturamento.
- **Curva ABC**: do produto que mais faturou para o que menos. **A** são os que, somados, chegam a 80% do faturamento (o produto que passa dos 80% ainda é A); **B**, os seguintes até 95%; **C**, o resto. Empate no faturamento: ordem alfabética.
- **Por operador**: cada venda conta para quem a fez. Nas vendas feitas antes da versão 0.3, que não guardavam o operador, vale quem abriu o caixa.
- **Horários**: cada linha soma todos os dias daquela semana no período, e a tela diz quantos são (um mês pode ter 4 segundas e 5 sábados).
- **Sem NFC-e**: como o sistema ainda não emite, todas as vendas aparecem sem documento fiscal, com o motivo. O relatório também conta em quantas o caixa pediu NFC-e ao finalizar.
- Sem venda no período, os valores em dinheiro aparecem como "—", com o motivo ("sem vendas no período"); contagens aparecem como 0.

### A tela

- Uma linha de filtros vale para todas as abas: **período** (Este mês, Hoje, Ontem, Últimos 7 dias, Últimos 30 dias, Mês passado, Este ano ou datas escolhidas, até um ano) e **operador**. Os períodos prontos param em hoje. Ao lado, **Imprimir** (a aba que está na tela, em folha comum, como na seção 15) e **Excel**.
- **Resumo**: faturamento, ticket médio, descontos, canceladas e vendas sem NFC-e; gráfico de barras do faturamento **por hora** (período de um dia), **por dia** (até 62 dias) ou **por mês** (mais que isso), com o botão **Tabela** que mostra os mesmos números; formas de pagamento com o recebido, o desconto ou acréscimo e a parte de cada uma no faturamento.
- **Produtos**: a curva ABC, com a quantidade, em quantas vendas o produto apareceu, o faturamento, a porcentagem e a porcentagem acumulada.
- **Horários**: mapa de dia da semana × hora, em tons de vermelho (mais escuro, mais movimento), por faturamento ou por número de vendas; o maior movimento escrito no alto; botão **Tabela** com os números.
- **Operadores**: vendas, faturamento, ticket, parte do total, desconto do gerente e cancelamentos de cada um.
- **Lista de vendas**: cada venda e cada cancelamento do período, com o botão que mostra o comprovante (a venda cancelada sai marcada como cancelada). A lista nunca vem cortada: acima de 2.000 vendas, pede um período menor (os números das outras abas não mudam).
- Passando o mouse numa barra ou num quadrado (ou usando as setas do teclado no gráfico), aparece o valor daquele dia ou daquela hora.

### Planilhas do Excel

- Botão **Excel** no relatório de vendas (todas as abas, com o período e o operador escolhidos), no **Financeiro** (a aba que está na tela: contas a pagar e a receber com os filtros, fluxo de caixa, DRE ou rentabilidade) e no **Estoque** (a lista da tela, com a pesquisa e o filtro).
- Os números são os mesmos da tela, vindos da mesma função: a planilha não refaz conta nenhuma. Entram como números de verdade (dá para somar e fazer gráfico no Excel): dinheiro em reais com duas casas, quantidades, porcentagens e datas. Onde a tela mostra "—", a planilha também mostra, e o motivo vai nas notas do pé da aba.
- Cada aba traz no alto o nome e o CNPJ da loja, o título, o período e os filtros, e a data, quem gerou e a versão do programa. Texto que começa com "=" (o nome de um produto, por exemplo) entra como texto, nunca como fórmula.
- O nome do arquivo já vem pronto, por exemplo `Moleka - Vendas 01-11-2026 a 12-11-2026.xlsx` (com o nome do operador quando o relatório é de um só).
- Na janela do programa, o botão abre a janela **Salvar como** do Windows, com o nome sugerido; depois de salvar, o programa oferece abrir a planilha. Se a planilha antiga com o mesmo nome estiver aberta no Excel, a tela pede para fechá-la e tentar de novo (a antiga fica como estava).

### O que ainda não existe

Comparação com outro período (mês contra mês, ano contra ano); relatório por categoria de produto e por cliente; margem (lucro) no relatório de vendas (está na Rentabilidade, no Financeiro); envio da planilha por e-mail; agendamento de relatórios.

### O que não foi verificado

Ver "Verificado" e "Não verificado" da versão 0.6.0 em PLANO.md. Em resumo: a janela **Salvar como** e o **abrir a planilha** só existem dentro da janela do programa no Windows e não foram vistos funcionando; a planilha não foi aberta no Excel (foi lida por duas bibliotecas e aberta no LibreOffice); as telas foram vistas no navegador, não na janela do Windows.

## 17. Dados fiscais da NFC-e e certificado A1 (versão 0.7.0, feita em 12/11/2026)

Menu **Fiscal → Dados fiscais e certificado A1**, o bloco **Fiscal / NFC-e** da tela Início, ou **Arquivo → Configurações → Fiscal (NFC-e)**. Só o gerente. Pedido do Eric (12/11): "Crie de forma que o dono da loja preencha todos esses dados fiscais e tributários e onde possa adicionar o certificado digital da empresa e dados da empresa". **Esta versão não emite NFC-e**: a tela diz isso no alto e na lista do que falta.

### O que o dono preenche (seis partes, à esquerda da tela)

- **Empresa**: regime tributário (CRT 1 Simples Nacional, 4 MEI, 2 Simples acima do sublimite, 3 regime normal), código do município do IBGE (7 números; os 2 primeiros têm de ser os do estado da aba Dados da loja), inscrição municipal e CNAE (se tiver), e duas perguntas: a empresa já é **credenciada para NFC-e na SEFAZ**? a loja **já emite NFC-e por outro sistema**? (se sim: qual sistema, série e último número). Razão social, CNPJ, inscrição estadual e endereço continuam na aba **Dados da loja**; a parte Empresa mostra um resumo deles, com o botão **Mudar**.
- **Certificado A1**: escolher o arquivo `.pfx`/`.p12` e digitar a senha. O sistema abre o arquivo e mostra titular, CNPJ (e se é o da loja), quem emitiu, validade e quando foi instalado. **Testar o certificado** abre de novo a cópia guardada com a senha guardada. **Trocar** (renovação) pergunta antes; **Remover deste computador** pede confirmação e fica no registro do sistema. Recusa: senha errada, arquivo sem a chave privada, certificado vencido ou que ainda não vale, de pessoa física (e-CPF), sem CNPJ, ou de outra empresa (os 8 primeiros caracteres do CNPJ diferentes dos da loja: o da matriz vale para a filial). Certificado A3 (cartão ou token) não é aceito.
- **CSC da SEFAZ** (Código de Segurança do Contribuinte): ID (até 6 números) e código (letras e números, até 36) de **homologação** e de **produção**. Código vazio mantém o guardado; a tela só mostra os 4 últimos caracteres.
- **Numeração**: série (0 a 999) e próximo número (1 a 999.999.999) de cada caixa. Duas regras: cada caixa usa uma série; o próximo número tem de ser maior que o maior número da série já registrado por este sistema. Se a loja já emite por outro sistema, a tela lembra de não repetir número.
- **Produtos**: resumo por categoria (produtos ativos, quantos sem NCM, sem CFOP e sem CST/CSOSN) e o botão **Preencher…** de cada categoria: NCM, CEST, CFOP, CST/CSOSN e origem para todos os produtos ativos dela. Sem marcar "trocar também", só os campos **vazios** de cada produto são preenchidos (e a origem, que todo produto já tem, não muda); marcando, os campos digitados trocam em todos, depois de uma confirmação. Fica no registro do sistema. No cadastro de cada produto, o grupo "Dados fiscais" ganhou o **CFOP** e a origem virou uma lista de 0 a 8.
- **Contador**: nome, CRC, telefone, e-mail, CPF ou CNPJ e o que ele orientou.

### Regras de conferência

- NCM com 8 números, CEST com 7, CST/CSOSN com 2 a 4 (CST tem 2, CSOSN tem 3), origem de 0 a 8. **CFOP com 4 números começando com 5** (a NFC-e é venda dentro do estado). O CFOP que começa com 5 mas não está na lista que a NFC-e aceita (5101, 5102, 5103, 5104, 5115, 5405, 5656, 5667 e 5933: MOC 7.0, Anexo I, regra 725) é gravado, mas a lista do que falta pede atenção.
- CST/CSOSN que não combina com o regime pede atenção: Simples (CRT 1 e 4) usa CSOSN; regime normal (CRT 2 e 3) usa CST; o MEI, na NFC-e, só usa CSOSN 102 ou 300 (NT 2024.001, regras em vigor desde 01/04/2025).
- Inscrição estadual "ISENTO" pede atenção (quem emite NFC-e tem inscrição estadual; confirmar com o contador).

### O que falta para emitir (à direita da tela)

Lista feita só com o que está gravado (não consulta a SEFAZ nem o contador), em vermelho o que falta e em amarelo o que pede atenção: dados da empresa (razão social, CNPJ, IE e endereço), regime, código do município, credenciamento, certificado (falta, vencido, de outro CNPJ, arquivo ou senha sumidos; atenção a 30 dias do vencimento), CSC de homologação (falta) e de produção (atenção), numeração (atenção até ser conferida e salva), dados fiscais dos produtos ativos e contato do contador. Cada item leva à parte onde se resolve; as partes têm uma bolinha verde, amarela ou vermelha. O indicador do certificado (`/api/status`) usa o certificado instalado.

### Onde ficam os dados

- Regime, município, CSC (só o ID), contador, e os dados do certificado que não são segredo (titular, CNPJ, validade): tabela `configuracao` do banco deste computador (vão na cópia de segurança).
- **Arquivo do certificado**: cópia em `%APPDATA%\MolekaPDV\certificado\certificado-a1.pfx`. **Senha do certificado e códigos CSC**: `%APPDATA%\MolekaPDV\segredos\`, um arquivo por segredo, cifrado pela DPAPI do Windows (só o mesmo usuário do Windows, neste computador, abre). Nenhum dos dois vai para o banco, para a cópia de segurança, para o registro do sistema, para as respostas da API ou para o repositório.
- CFOP do produto: coluna nova `produto.cfop` (formato 4 do banco, com cópia de segurança automática antes de atualizar).
- Ambiente: sempre **homologação** (testes). Produção só com a ordem explícita do Eric (AGENTS.md, regra 3).

### O que ainda não existe

A **emissão** da NFC-e (envio à SEFAZ, contingência, cancelamento, inutilização, DANFE com QR Code) e a decisão do provedor (API intermediária ou PyNFe, §9); alíquotas de ICMS, PIS e COFINS por produto (o regime normal vai precisar); os campos da reforma tributária (IBS/CBS); os dados do **responsável técnico** do sistema, que a nota leva (são do desenvolvedor, não do dono da loja); certificado A3; conferência automática do credenciamento ou do CSC na SEFAZ.

### O que não foi verificado

Ver "Verificado" e "Não verificado" da versão 0.7.0 em PLANO.md. Em resumo: nenhum certificado de verdade foi usado (só certificados fictícios, autoassinados, gerados nos testes); a escolha do arquivo e a tela dentro da janela do programa no Windows não foram vistas; a DPAPI foi testada só na máquina de teste do GitHub; os valores de cada produto e do regime são do contador.
