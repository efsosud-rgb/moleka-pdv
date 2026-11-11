Quarta versão de teste: agora tem **estoque, entrada de nota de compra por XML e financeiro** (contas a pagar e a receber, fluxo de caixa, DRE e rentabilidade). Ainda **não emite NFC-e** nem imprime o cupom.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado e recusa programa sem assinatura. Nesse caso, use o caminho "Rodar pelo código no Windows, sem instalador", explicado no README.

Não pede senha de administrador. Pode instalar por cima da versão 0.3.0: os dados ficam em `%APPDATA%\MolekaPDV`, e o programa atualiza o banco sozinho, com cópia de segurança antes (`backups\moleka-antes-do-formato-3-….db`). Senhas, produtos, clientes, caixa e vendas continuam como estavam.

## O que há de novo (as três telas são só do gerente)

- **Estoque** (menu Estoque → Saldos, ajustes e contagem):
  - saldo de cada produto, com filtro por nome e por situação (com saldo, abaixo do mínimo, negativo);
  - **entrada** e **saída** à mão, sempre com motivo, e **contagem** da prateleira (o sistema acerta o saldo pela diferença); a tela mostra o saldo de agora e o de depois antes de gravar;
  - **histórico** de cada produto: o que entrou, o que saiu, quando, por quê e quem fez;
  - **valor do estoque a custo** e **custo médio** de cada produto.
- **Entrada de NF por XML** (menu Estoque → Entrada de NF):
  - escolha o arquivo XML da nota do fornecedor; a tela mostra fornecedor, itens, total e parcelas **antes de gravar**;
  - em cada item: dar entrada num produto da loja, criar um produto novo ou não dar entrada; o **fator** converte a caixa da nota em unidades da loja (caixa com 24 → 24);
  - o sistema **lembra** a ligação entre o código do fornecedor e o produto da loja para as próximas notas;
  - ao importar: o estoque sobe, o **custo médio é refeito** e as **parcelas viram contas a pagar**;
  - a mesma nota não entra duas vezes; uma nota importada por engano pode ser **estornada** (com motivo).
- **Financeiro** (menu Financeiro), no lugar da tela em construção:
  - **Contas a pagar e a receber**: lançar, alterar, dar baixa, desfazer a baixa e cancelar; a lista mostra o que está em aberto, vencido e pago;
  - **Fluxo de caixa** por dia: vendas, outros recebimentos, pagamentos, saldo do dia e acumulado;
  - **DRE**: receita bruta, descontos, deduções, receita líquida, custo das vendas, lucro bruto, despesas e resultado, com o percentual sobre a receita líquida;
  - **Rentabilidade por produto** (menu Relatórios): quantidade, receita, custo e margem de cada produto vendido;
  - **Categorias**: o programa já traz 17 categorias (só os nomes, nenhum valor); o gerente muda como quiser.
- A venda passa a **guardar o custo de cada produto** no momento em que é finalizada. É com esse custo que o DRE e a rentabilidade calculam o lucro.
- Datas são digitadas como dia/mês/ano (as barras entram sozinhas).

## Por onde começar

1. **Estoque → Entrada de NF (XML)**, com o XML de uma nota de compra; ou **Estoque → Saldos**, dando uma **Entrada** com a quantidade e o custo de cada produto.
2. Venda normalmente no **Caixa**.
3. **Financeiro → Contas a pagar e a receber**: lance as despesas (aluguel, energia, salários) e dê baixa quando pagar.
4. Veja **Fluxo de caixa**, **DRE** e **Rentabilidade**.

## Importante sobre os números

- **Nenhum número é inventado.** Sem dado, a tela mostra "—" e diz o motivo.
- **Vendas feitas antes desta versão não têm custo gravado.** Elas entram na receita, mas não no custo: o DRE avisa quantos itens estão assim e marca o lucro como parcial; se nenhuma venda do período tem custo, o lucro aparece como "—". O programa não preenche esse custo depois, porque seria uma estimativa.
- O custo de um produto vem da entrada da nota, de uma entrada no Estoque ou do cadastro do produto, e vale para as vendas feitas **depois**.
- **Compra de mercadoria para revenda não é despesa do DRE**: ela entra no fluxo de caixa quando é paga, e o custo aparece no DRE quando o produto é vendido. Se a loja **fabrica** o sorvete, lance a matéria-prima na categoria "Matéria-prima e insumos", que entra como custo.
- No fluxo de caixa, a venda no cartão entra no dia da venda, pelo valor cheio: prazo e taxa da maquininha ainda não são considerados.
- Vender sem saldo não é bloqueado: o saldo fica negativo e aparece em destaque no Estoque.

## O que ainda não funciona

- **NFC-e: nenhum documento fiscal é emitido.** Ao finalizar a venda, a opção "com NFC-e" aparece desligada.
- Impressão do cupom; ficha técnica e produção (para quem fabrica); exportar para Excel e imprimir relatório; contas que se repetem todo mês.
- A entrada de nota foi testada com **notas fictícias**, feitas no formato oficial da NF-e. Ainda não foi testada com o XML de um fornecedor de verdade da loja: se alguma nota for recusada ou vier com valor estranho, guarde o arquivo e avise.
- É uma versão de teste: use produtos, notas e vendas de teste. O que for lançado fica gravado no banco deste computador.

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login. O mesmo teste faz, dentro do programa instalado e sem abrir as telas, um roteiro completo pela API: cadastro, entrada no estoque, caixa, venda com duas formas de pagamento e troco, fechamento, importação de uma nota fictícia, uma despesa paga, fluxo de caixa, DRE e rentabilidade, conferindo cada valor. As telas novas foram conferidas no navegador (188 conferências), não dentro da janela do Windows.
