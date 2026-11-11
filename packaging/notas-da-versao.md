Terceira versão de teste: agora dá para **cadastrar produtos e clientes, abrir o caixa e vender**. Ainda **não emite NFC-e** nem imprime o cupom.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado e recusa programa sem assinatura. Nesse caso, use o caminho "Rodar pelo código no Windows, sem instalador", explicado no README.

Não pede senha de administrador. Pode instalar por cima da versão 0.2.0: os dados ficam em `%APPDATA%\MolekaPDV`, e o programa atualiza o banco sozinho, com cópia de segurança antes.

## O que há de novo

- **Produtos** (menu Cadastros, só o gerente): descrição, código de barras, unidade, categoria, custo e **preços por tabela e por quantidade** (por exemplo: varejo R$ 5,00; a partir de 10, R$ 4,50; atacado R$ 4,00).
- **Clientes**: nome, **CPF ou CNPJ** (conferido pelos dígitos) e a **tabela de preço** do cliente (atacado ou varejo; só o gerente muda).
- **Tabelas de preço e formas de pagamento** (só o gerente): as tabelas VAREJO e ATACADO já vêm criadas; cada forma de pagamento tem um **percentual de desconto ou acréscimo**.
- **Controle de caixa** (F11): abrir com fundo de troco, sangria, suprimento, vendas do caixa, **fechamento com conferência por forma de pagamento** e, para o gerente, os fechamentos anteriores.
- **Venda** (F2):
  - produto pelo leitor, pelo código ou pelo nome; `3*codigo` lança três de uma vez;
  - **quantidade editável** em cada item, com o preço por quantidade entrando sozinho;
  - **cliente escolhido no cadastro**, que pode ser trocado ou retirado (os preços são recalculados);
  - **mais de uma forma de pagamento** na mesma venda, com o percentual de cada uma; a **forma de um pagamento já lançado pode ser trocada**; troco no dinheiro;
  - desconto no total, só o gerente;
  - ao finalizar, a escolha **com NFC-e ou sem NFC-e** (por enquanto só "sem": veja abaixo);
  - **saldo de vendas do dia** no topo da tela.
- **Início**: o "Resumo de hoje" mostra as vendas de verdade.
- A pesquisa ignora acentos: "agua" acha "Água".
- F2 (venda), F5 (produtos) e F11 (controle de caixa) funcionam em todas as telas com menu.

## Por onde começar

1. **Cadastros → Tabelas de preço e pagamento**: digite o percentual de cada forma (negativo é desconto).
2. **Cadastros → Produtos**: cadastre os produtos e os preços.
3. **Cadastros → Clientes**: cadastre quem compra no atacado.
4. **Caixa → Controle de caixa**: digite o fundo de troco e abra o caixa.
5. **Caixa → Venda**.

## O que ainda não funciona

- **NFC-e: nenhum documento fiscal é emitido.** Ao finalizar a venda, a opção "com NFC-e" aparece desligada.
- Impressão do cupom, tela de estoque, entrada de NF por XML e financeiro. A tela Financeiro continua com o selo "Tela em construção", sem número de exemplo.
- É uma versão de teste: use produtos e vendas de teste. O que for lançado fica gravado no banco deste computador.

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login. O mesmo teste faz, dentro do programa instalado, uma venda de teste completa (cadastro, caixa, duas formas de pagamento, troco e fechamento).
