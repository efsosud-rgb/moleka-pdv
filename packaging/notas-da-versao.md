Segunda versão de teste: o sistema agora pede **usuário e senha** para entrar.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Não pede senha de administrador. Pode instalar por cima da versão 0.1.0: os dados ficam guardados em `%APPDATA%\MolekaPDV`.

## O que há de novo

- **Primeiro acesso**: na primeira vez, a capa pede o nome, o usuário e a senha do gerente.
- **Login**: nas vezes seguintes, escolha o operador na lista e digite a senha. Cinco senhas erradas seguidas travam aquele usuário por 30 segundos.
- **Operadores** (menu Cadastros, só o gerente): cadastrar, alterar, trocar a senha e inativar operadores, com dois perfis: operador e gerente.
- **Arquivo → Minha senha** e **Arquivo → Trocar de operador**.
- O operador comum vê trancadas as telas que são só do gerente (Produtos, Financeiro, Operadores).
- As telas foram reajustadas para caber na janela maximizada de um monitor de 1366×768. Na versão 0.1.0, Início, Produtos e Financeiro precisavam de rolagem.

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

## O que ainda não funciona

- Cadastro de produtos, venda, controle de caixa, estoque, financeiro e NFC-e. Essas telas levam o selo "Tela em construção" ou a etiqueta "em breve" e não mostram nenhum número de exemplo.

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login.
