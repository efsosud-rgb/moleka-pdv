Quinta versão de teste: agora tem **Configurações**, **impressão do comprovante de venda e do fechamento de caixa** na impressora de cupom, **impressão dos relatórios** em impressora comum e **cópia de segurança diária**. Ainda **não emite NFC-e**: o comprovante impresso **não é documento fiscal**.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado e recusa programa sem assinatura. Nesse caso, use o caminho "Rodar pelo código no Windows, sem instalador", explicado no README.

Não pede senha de administrador. Pode instalar por cima da versão 0.4.0: os dados ficam em `%APPDATA%\MolekaPDV` e continuam como estavam (o formato do banco não mudou nesta versão).

## O que há de novo

- **Configurações** (menu Arquivo → Configurações; só o gerente), com três abas:
  - **Dados da loja**: nome, CNPJ, endereço, telefone e a mensagem do fim do cupom. Saem no cabeçalho do cupom e dos relatórios. Nenhum campo é obrigatório.
  - **Impressão**: escolha a impressora de cupom na lista do Windows, a largura do papel e as letras com acento; **Imprimir teste** manda uma página de teste, e a impressora só aparece como testada depois que você confirma que saiu certo.
  - **Cópia de segurança**: veja as cópias guardadas, escolha uma **pasta extra** (pendrive que fica na loja ou pasta da nuvem) e faça uma cópia na hora.
- **Comprovante de venda** na impressora de cupom (térmica, de 80 mm ou de 58 mm):
  - depois de cada venda, conforme a opção escolhida em Configurações: o sistema oferece o botão, imprime sozinho ou não imprime;
  - **Ctrl+P** ou o botão **Comprovante**, na tela do Caixa, imprime o comprovante da última venda;
  - no **Controle de caixa**, o botão com o desenho da impressora mostra o comprovante de qualquer venda na tela, com o botão Imprimir;
  - se a impressora falhar, **a venda fica gravada do mesmo jeito** e a tela avisa;
  - opção de abrir a **gaveta de dinheiro** ligada na impressora, na venda em dinheiro.
- **Resumo e fechamento de caixa** impressos: vendas, recebido por forma, dinheiro na gaveta, esperado, contado e diferença, com linha para assinatura. Depois de fechar o caixa, o papel aparece na tela pronto para imprimir.
- **Relatórios em impressora comum**: botão **Imprimir** (ou Ctrl+P) em Financeiro (contas a pagar e a receber, fluxo de caixa, DRE e rentabilidade) e em Estoque. Abre a impressão do Windows; para guardar em PDF, escolha a impressora "Microsoft Print to PDF". A folha sai com o nome da loja, o período e os filtros escritos no alto.
- **Cópia de segurança diária**, feita sozinha: quando o programa abre, quando o caixa fecha e quando você pede. Ficam guardadas as últimas 30. O indicador **Backup**, no rodapé, mostra a situação.

## Por onde começar

1. **Arquivo → Configurações → Dados da loja**: preencha e salve.
2. Aba **Impressão**: escolha a impressora de cupom, clique em **Imprimir teste**, olhe o papel e responda se saiu certo. Se os acentos saírem trocados, mude "Letras com acento" e teste de novo.
3. Aba **Cópia de segurança**: escolha a pasta extra e clique em **Fazer a cópia agora**.
4. Faça uma venda no **Caixa** e aperte **Ctrl+P**.

## Importante

- **O comprovante não é documento fiscal** (isso sai escrito nele). A NFC-e ainda não é emitida.
- **Nenhum cupom saiu ainda numa impressora de verdade.** A impressão foi testada com impressoras de teste, que gravam num arquivo o que receberiam; a impressora da loja (ELGIN i9) só pode ser testada aí. O primeiro teste é o da tela Configurações.
- "Enviado para a impressora" quer dizer que o Windows aceitou o trabalho. Se a impressora estiver desligada, sem papel ou com o cabo solto, o trabalho fica parado na fila do Windows.
- **Sem pasta extra, a cópia de segurança fica no mesmo disco do sistema**: protege de um erro de uso, mas não se o disco estragar ou o computador for roubado.
- Voltar uma cópia de segurança ainda é feito à mão, com o programa fechado (o passo a passo está em `docs/ESPECIFICACAO.md`, seção 15). Se precisar, peça ajuda antes de mexer.
- **Nenhum número é inventado.** Sem dado, a tela e a folha impressa mostram "—" e dizem o motivo.

## O que ainda não funciona

- **NFC-e: nenhum documento fiscal é emitido.** Ao finalizar a venda, a opção "com NFC-e" aparece desligada.
- Logo e QR Code no cupom; voltar uma cópia de segurança pela tela; exportar para Excel; ficha técnica e produção (para quem fabrica).
- É uma versão de teste: use produtos, notas e vendas de teste. O que for lançado fica gravado no banco deste computador.

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login. O mesmo teste faz, dentro do programa instalado e sem abrir as telas, um roteiro completo pela API (cadastro, venda, nota fictícia, financeiro). Nesta versão ele também grava os dados da loja, faz a cópia de segurança (a do dia e a da pasta extra), compara a lista de impressoras do sistema com a do Windows e **imprime pela fila de impressão do Windows** numa impressora de teste que grava em arquivo: a página de teste, o comprovante de uma venda e uma venda em dinheiro com o pulso da gaveta, conferindo os bytes. Isso mostra que o cupom chega certo à fila do Windows; **não mostra a impressora da loja** (papel, acentos, corte e gaveta). As telas novas foram conferidas no navegador (152 conferências), não dentro da janela do Windows.
