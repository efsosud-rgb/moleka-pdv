Sexta versão de teste: agora tem o **relatório de vendas por período** e as **planilhas do Excel** dos relatórios. Ainda **não emite NFC-e**: o comprovante impresso **não é documento fiscal**.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado e recusa programa sem assinatura. Nesse caso, use o caminho "Rodar pelo código no Windows, sem instalador", explicado no README. Por esse caminho, a primeira abertura da versão nova instala uma biblioteca a mais (a das planilhas) e precisa de internet.

Não pede senha de administrador. Pode instalar por cima da versão 0.5.0: os dados ficam em `%APPDATA%\MolekaPDV` e continuam como estavam (o formato do banco não mudou nesta versão).

## O que há de novo

- **Relatórios → Vendas por período** (só o gerente; também pelo bloco **Relatórios** da tela Início). Escolha o período (hoje, ontem, este mês, mês passado, este ano, os últimos 7 ou 30 dias, ou as datas que quiser) e, se quiser, um operador. Cinco abas:
  - **Resumo**: faturamento, ticket médio, descontos dados, vendas canceladas e vendas sem NFC-e; gráfico do faturamento por hora (um dia), por dia ou por mês; formas de pagamento.
  - **Produtos**: o que mais vendeu, com a **curva ABC** (A são os produtos que fazem 80% do faturamento).
  - **Horários**: mapa do movimento por dia da semana e hora (quanto mais escuro, mais movimento).
  - **Operadores**: vendas, faturamento, descontos e cancelamentos de cada um.
  - **Lista de vendas**: cada venda e cada cancelamento do período, com o comprovante.
  - Todo gráfico tem o botão **Tabela**, com os mesmos números. Passando o mouse numa barra ou num quadrado, aparece o valor.
- **Botão Excel** no relatório de vendas, no **Financeiro** (contas a pagar e a receber, fluxo de caixa, DRE e rentabilidade) e no **Estoque**. Abre a janela "Salvar como" do Windows com o nome do arquivo já pronto (por exemplo, `Moleka - Vendas 01-11-2026 a 30-11-2026.xlsx`); depois de salvar, o programa oferece abrir a planilha. Os números são os mesmos da tela, como números de verdade: dá para somar e fazer gráfico no Excel.
- Na tela **Início**, o bloco "DRE e Rentabilidade" agora é **Relatórios**. O DRE e a rentabilidade continuam no Financeiro e no menu do topo.
- O DRE e a rentabilidade de períodos longos (um ano) abrem mais rápido.

## Por onde começar

1. Clique no bloco **Relatórios** da tela Início.
2. Escolha **Mês passado** no período e veja as abas.
3. Clique em **Excel**, escolha a pasta (Documentos, por exemplo) e clique em **Salvar**. Depois, **Abrir a planilha**.

## Importante

- **Nenhum número é inventado.** Sem venda no período, os valores aparecem como "—", com o motivo.
- **Sem NFC-e** mostra todas as vendas, porque o sistema ainda não emite documento fiscal.
- Se a planilha com o mesmo nome estiver aberta no Excel, feche antes de salvar de novo (a tela avisa).
- **Nenhum cupom saiu ainda numa impressora de verdade** (vale o que foi dito na versão 0.5.0).
- É uma versão de teste: use produtos, notas e vendas de teste. O que for lançado fica gravado no banco deste computador.

## O que ainda não funciona

- **NFC-e: nenhum documento fiscal é emitido.** Ao finalizar a venda, a opção "com NFC-e" aparece desligada.
- Comparar com outro período (mês contra mês); relatório por categoria e por cliente; logo e QR Code no cupom; voltar uma cópia de segurança pela tela; ficha técnica e produção (para quem fabrica).

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login. O mesmo teste faz, dentro do programa instalado e sem abrir as telas, um roteiro completo pela API (cadastro, venda, nota fictícia, financeiro, configurações, cópia de segurança e impressão numa impressora de teste). Nesta versão ele também abre o relatório de vendas e **gera uma planilha do Excel dentro do programa empacotado**, conferindo as abas e o faturamento dentro do arquivo. A janela "Salvar como" não entra nesse teste (é uma janela do Windows, que só aparece com alguém clicando). As telas novas foram conferidas no navegador (74 conferências), não dentro da janela do Windows.
