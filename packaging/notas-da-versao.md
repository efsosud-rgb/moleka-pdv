Sétima versão de teste: agora tem a tela onde o dono da loja preenche os **dados fiscais da NFC-e** e instala o **certificado digital A1** da empresa. Ainda **não emite NFC-e**: os dados ficam prontos para quando a emissão chegar. O comprovante impresso continua **não sendo documento fiscal**.

## Como instalar

1. Baixe o arquivo `MolekaPDV-Instalador-….exe`, logo abaixo, em **Assets**.
2. Se a versão anterior estiver aberta, feche. Dê dois cliques no instalador. Se aparecer a tela azul "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. Isso acontece porque o instalador ainda não tem assinatura digital.
3. Clique em **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado e recusa programa sem assinatura. Nesse caso, use o caminho "Rodar pelo código no Windows, sem instalador", explicado no README. Por esse caminho, a primeira abertura da versão nova instala uma biblioteca a mais (a que lê o certificado digital) e precisa de internet.

Não pede senha de administrador. Pode instalar por cima da versão 0.6.0: os dados ficam em `%APPDATA%\MolekaPDV` e continuam como estavam. O formato do banco muda nesta versão (o produto ganha o CFOP): ao abrir pela primeira vez, o programa guarda antes uma cópia do banco em `%APPDATA%\MolekaPDV\backups` (`moleka-antes-do-formato-4-….db`).

## O que há de novo

- **Fiscal → Dados fiscais e certificado A1** (só o gerente; também pelo bloco **Fiscal / NFC-e** da tela Início, ou em **Arquivo → Configurações → Fiscal (NFC-e)**). Seis partes:
  - **Empresa**: regime tributário, código do município (IBGE), inscrição municipal, CNAE e duas perguntas sobre a SEFAZ (a empresa já é credenciada para NFC-e? a loja já emite por outro sistema?). Razão social, CNPJ, inscrição estadual e endereço continuam na aba **Dados da loja**.
  - **Certificado A1**: clique em **Escolher o arquivo…**, escolha o arquivo do certificado (termina em `.pfx` ou `.p12`), digite a senha e clique em **Instalar o certificado**. A tela mostra o titular, o CNPJ (e se é o da loja) e a validade. **Testar o certificado** confere se ele ainda abre. O programa recusa certificado vencido, de outra empresa, de pessoa física ou sem a chave privada.
  - **CSC da SEFAZ**: o ID e o código de homologação (testes) e de produção.
  - **Numeração**: a série e o número da próxima NFC-e. Se a loja já emite por outro sistema, não pode repetir número.
  - **Produtos**: quantos produtos de cada categoria estão sem NCM, CFOP ou CST/CSOSN, e o botão **Preencher…**, que preenche a categoria inteira de uma vez.
  - **Contador**: nome, telefone, e-mail e o que ele orientou.
- À direita, a lista **O que falta para emitir**: em vermelho o que falta, em amarelo o que pede atenção. Clique num item para ir à parte certa.
- No cadastro do produto (Cadastros → Produtos, parte "Dados fiscais"): campo **CFOP** novo e a **origem** numa lista de 0 a 8.

## Onde ficam o certificado e as senhas

- Só neste computador. A senha do certificado e o código do CSC ficam **cifrados pelo Windows**, numa pasta separada; não vão para a internet, para a cópia de segurança, para o registro do sistema nem para o desenvolvedor.
- A cópia de segurança do sistema **não leva** o certificado: guarde o arquivo original num lugar seguro.
- Só serve o certificado **A1** (arquivo). O A3 (cartão ou token USB) não funciona aqui.

## Importante

- **Nenhuma NFC-e é emitida nesta versão.** O ambiente fica em homologação (testes); a nota que vale de verdade só será ligada depois dos testes, com a autorização do desenvolvedor.
- Os dados de cada produto (NCM, CFOP, CST ou CSOSN) e o regime são do **contador**: confira com ele.
- **Nenhum número é inventado.** Sem dado, a tela mostra "—" e o motivo.
- **Nenhum cupom saiu ainda numa impressora de verdade** (vale o que foi dito na versão 0.5.0).

## O que ainda não funciona

- **Emitir a NFC-e** (enviar à SEFAZ, contingência, cancelamento, DANFE com QR Code).
- Alíquotas de ICMS, PIS e COFINS por produto (o regime normal vai precisar); campos da reforma tributária (IBS/CBS); certificado A3.
- Comparar com outro período; relatório por categoria e por cliente; logo e QR Code no cupom; voltar uma cópia de segurança pela tela.

## Esqueci a senha do gerente

Feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

```
"%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
```

Os prints abaixo (`janela-pasta.png` e `janela-instalado.png`) foram tirados pelo teste automático num Windows de verdade: o primeiro mostra o primeiro acesso; o segundo, a tela de login. O mesmo teste faz, dentro do programa instalado e sem abrir as telas, um roteiro completo pela API. Nesta versão ele também **instala um certificado A1 fictício** (gerado para o teste, não vale para nada), confere que a senha ficou cifrada pelo Windows e que a cópia de segurança não a levou, e remove o certificado. A aba Fiscal foi conferida no navegador (110 conferências), não dentro da janela do Windows; nenhum certificado de verdade foi usado.
