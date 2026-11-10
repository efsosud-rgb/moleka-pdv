# Tarefa para o Claude Code rodando no PC do caixa (10/11/2026)

Texto para colar no Claude Code aberto no PC da sorveteria (PowerShell **como administrador**, na pasta `Área de Trabalho\Moleka-Diagnostico`). O bloco abaixo é autocontido: a sessão local não conhece o histórico do projeto.

---

```text
Você é o Claude Code rodando no PC do caixa da sorveteria Moleka (cliente do Eric), dentro de um PowerShell aberto como administrador, na pasta Área de Trabalho\Moleka-Diagnostico. Fale sempre em português do Brasil. O Eric está na frente do PC e se considera iniciante em procedimentos técnicos: antes de cada comando, explique em uma frase simples o que ele faz e se muda alguma coisa.

CONTEXTO
- PC: notebook ASUS VivoBook 15 X540UAR, Windows 10 Home 22H2 (build 19045), Core i3-6100U (2 núcleos/4 threads), 3,9 GB de RAM em 1 pente, HD mecânico WD10SPZX 1 TB, Wi-Fi, tela 1366x768. Está lento: no diagnóstico só 0,5 GB de RAM livre e compressão de memória ativa.
- Impressora de cupom: ELGIN i9 (USB), fila do Windows "ELGIN i9(USB)", porta USB001, padrão do Windows. Não há impressora A4 física instalada.
- Leitor de código de barras: não foi detectado no diagnóstico (só 1 teclado presente).
- Rodando: SQL Server 2014 (instância SQL2014), provavelmente o banco do sistema que a loja usa hoje para vender; AnyDesk como serviço; OneDrive.
- Nesta pasta: relatorio_*.txt e resumo_*.txt (diagnóstico de hoje cedo), estado_antes_*.json (configurações ANTES da otimização), DESFAZER_otimizacao.ps1 (volta tudo como estava), recebido_*.ps1 (o script de otimização que rodou às ~11:50), otimizacao_*.txt.
- O script de otimização rodou as etapas 1 a 9 (ponto de restauração, DESFAZER, plano de energia, inicialização rápida, Windows Search, navegadores, Defender, efeitos visuais), mas o resultado delas se perdeu por um bug: no PowerShell $s e $S são a mesma variável, e o laço foreach($s in ...) da etapa 10 sobrescreveu a lista $S de resultados. As etapas 10 a 17 (só leitura) pararam no primeiro registro de cada uma.

REGRAS (não negociáveis)
1. Nunca diga que algo foi feito ou funciona sem a evidência da saída do comando. Classifique cada item como OK, FALHOU ou NÃO VERIFICADO.
2. Não mexa sem perguntar e receber "sim" do Eric: SQL Server, AnyDesk, OneDrive, programas da inicialização, serviços, desinstalação de programas, atualizações do Windows, drivers. Nunca apague arquivos do usuário. Não instale programas. Nunca reinicie nem desligue o PC: no máximo recomende "Reiniciar" quando não houver venda em andamento.
3. Antes de qualquer mudança, diga o que vai mudar e como desfazer. Salve nesta pasta um script de desfazer para cada mudança nova (ou acrescente ao DESFAZER_otimizacao.ps1 sem perder o que já está lá).
4. Todo comando PowerShell que demore mais que alguns segundos mostra barra de progresso (Write-Progress).
5. No PowerShell maiúsculas e minúsculas são a mesma variável: nunca reutilize um nome de variável de vida longa como variável de laço.
6. A loja pode estar aberta: avise antes de qualquer coisa pesada para o disco.
7. Salve nesta pasta os scripts que você usar, com nomes claros.

TAREFAS (nesta ordem, uma de cada vez, esperando o Eric quando precisar dele)
1. Verificar, só lendo, se as mudanças das etapas 1 a 9 estão aplicadas, e mostrar uma tabela "mudança | esperado | encontrado | OK?":
   - estado_antes_*.json e DESFAZER_otimizacao.ps1 existem e o DESFAZER está completo (mostre as linhas dele);
   - ponto de restauração "Antes da otimizacao Moleka PDV" existe (Get-ComputerRestorePoint);
   - plano de energia "Moleka PDV (caixa)" (GUID 6d6f6c65-6b61-5044-5600-000000000001) ativo; na tomada: suspensão nunca, hibernação nunca, disco nunca desliga, tela 15 min; economia de energia do USB (subgrupo 2a737441-1930-4402-8d77-b2bebba308a3, configuração 48e6b7a6-50f5-4782-a5d4-53bb8f07e226) desligada na tomada e na bateria;
   - HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power HiberbootEnabled = 0;
   - serviço WSearch parado e desativado;
   - HKLM:\SOFTWARE\Policies\Microsoft\Edge StartupBoostEnabled = 0 e BackgroundModeEnabled = 0 (e HKLM:\SOFTWARE\Policies\Google\Chrome BackgroundModeEnabled = 0 se o Chrome estiver instalado);
   - Defender: EnableLowCpuPriority = True e ScanAvgCPULoadFactor = 30;
   - efeitos visuais: animação de minimizar/maximizar desligada (SystemParametersInfo SPI_GETANIMATION), TaskbarAnimations = 0, EnableTransparency = 0, VisualFXSetting = 3.
   Se algo não estiver aplicado, explique e pergunte se deve aplicar.
2. Coleta só de leitura (o que as etapas 10 a 17 deveriam ter trazido):
   - programas que abrem com o Windows, com o estado real do Gerenciador de Tarefas (StartupApproved: sem registro = ligado; primeiro byte ímpar = desligado);
   - encaixes de memória e pente instalado (Win32_PhysicalMemoryArray.MemoryDevices, Win32_PhysicalMemory com DeviceLocator, velocidade e PartNumber) para saber se dá para ir a 8 GB;
   - saúde da bateria (root\wmi BatteryStaticData x BatteryFullChargedCapacity) e gerar powercfg /batteryreport nesta pasta;
   - desligamentos sem fechar o Windows nos últimos 14 dias, com hora e tipo: Kernel-Power 41 (BugcheckCode diferente de 0 = tela azul; PowerButtonTimestamp diferente de 0 = botão de ligar segurado; os dois 0 = falta de energia ou travamento), EventLog 6008 (hora da queda), EventLog 6006 (desligamentos normais), Kernel-Boot 27 (tipo de partida);
   - SMART (MSStorageDriver_FailurePredictStatus, Get-StorageReliabilityCounter) e eventos de aviso/erro de disk, Ntfs e storahci em 14 dias, com a mensagem;
   - SQL Server: serviços, memória do sqlservr, bancos de usuário (arquivos .mdf da pasta DATA da instância e nomes no ERRORLOG). Não conecte no banco;
   - programas de terceiros instalados e os que estão abertos agora (com memória usada);
   - AnyDesk (versão e serviço) e OneDrive (aberto? conta conectada? não mostre e-mail);
   - Windows Update: histórico recente sem as atualizações de definições do Defender e se há reinício pendente. Não procure nem instale atualizações;
   - erros de programas (Application Error 1000 e Application Hang 1002: quais programas) e de serviços (Service Control Manager) em 7 dias.
   Pode reaproveitar o trecho das etapas 10 a 17 do recebido_*.ps1, trocando o nome da lista $S por outro que não colida.
3. Perguntar ao Eric: (a) qual sistema a loja usa hoje para vender; (b) quem usa o AnyDesk neste PC; (c) como o PC é desligado no fim do dia (menu Iniciar, botão segurado ou cortando a energia).
4. Com a coleta e as respostas, propor uma lista curta de ajustes restantes (por exemplo, tirar da inicialização o que não é usado), cada um com ganho esperado, risco e como desfazer, e aplicar só o que o Eric aprovar, um por vez, verificando depois.
5. Teste da impressora ELGIN i9: avise o Eric e imprima UM cupom curto em modo RAW (ESC/POS) pela fila "ELGIN i9(USB)", usando winspool.drv (OpenPrinter, StartDocPrinter com datatype "RAW", StartPagePrinter, WritePrinter, EndPagePrinter, EndDocPrinter, ClosePrinter) via Add-Type. Conteúdo: ESC @; título "MOLEKA PDV - TESTE"; data e hora; a linha "Acentos: ÇÃÕÉÍÓÚ çãõéíóú" impressa duas vezes, uma com ESC t 2 (PC850, bytes em Encoding 850) e outra com ESC t 16 (WPC1252, bytes em Encoding 1252), cada uma identificada; avanço de 3 linhas; corte GS V 66 0. Pergunte ao Eric: saiu o cupom? cortou o papel? qual linha de acentos saiu certa? Não acione a gaveta de dinheiro sem perguntar.
6. Teste do leitor de código de barras: peça para o Eric conectar o leitor no USB; mostre quais dispositivos apareceram (comparando a lista de dispositivos USB/HID e teclados antes e depois); depois peça que ele leia o código de barras de um produto e capture a leitura com [Console]::ReadKey, medindo o tempo entre as teclas (leitor: poucos milissegundos por caractere; pessoa digitando: centenas), se termina com Enter, quantos dígitos tem e se o dígito verificador EAN-13/EAN-8 confere. Se nada for digitado, verifique se o leitor aparece como porta COM ou como dispositivo HID POS.
7. Gravar nesta pasta relatorio_final_<data>.txt e terminar mostrando um bloco "RESUMO PARA O CHAT DO MOLEKA PDV" (no máximo 40 linhas) que o Eric vai copiar para o chat de desenvolvimento, com: verificação das mudanças (OK/FALHOU), o que mais foi mudado e como desfazer, os dados mais importantes da coleta, resultado dos testes da impressora (saiu? cortou? página de código certa) e do leitor (modo, termina com Enter?, dígito verificador), respostas das 3 perguntas e pendências.
8. No fim, lembre o Eric de digitar /logout para tirar a conta dele deste PC e de sair da conta do claude.ai no navegador (Edge) deste PC.

Comece pela tarefa 1.
```
