# Decisões do projeto

Registro curto, em ordem cronológica. Uma linha por decisão; o motivo quando não for óbvio.

## 2026-11-07

- Repositório privado `efsosud-rgb/moleka-pdv` criado; regras em `AGENTS.md`, importado pelo `CLAUDE.md`.
- Backend em Python; interface HTML/CSS/JS numa janela `pywebview` (WebView2). Motivo: visual 3D e logo animada sem abrir mão do Python.
- Banco local SQLite para a v1 (PostgreSQL só se houver mais de um caixa — pendente).
- Módulo fiscal como adaptador com dois provedores possíveis (API intermediária ou PyNFe); escolha pendente. O XML nasce com os grupos IBS/CBS.
- Dinheiro em centavos (inteiro); nunca `float`.
- Cores do sistema extraídas da logo do cliente (ver README). Fontes: Nunito (títulos) e Inter (texto).
- Valores de dashboards, DRE e indicadores exibem `—` enquanto não houver dado real; nada de mock.
- Protótipo visual (4 telas) feito em canvas de design; cópia estática a ser exportada para `docs/prototipo/`.
- Base executável construída na sessão Fable (claude.ai/code): FastAPI + SQLAlchemy 2 + SQLite (WAL) + pywebview; sem Alembic até o schema estabilizar. Motivo de não esperar a sessão Opus: o design (CSS/animações) já estava nas mãos desta sessão.
- `/api/status` é a única fonte dos indicadores da interface; cada item traz `ok` e `motivo`, e a interface mostra `—` quando `ok` é falso.
- Autenticação de operador ainda não existe: o botão Entrar leva ao Início (Frente 1 do PLANO.md).
- Fontes Nunito/Inter vêm do Google Fonts por enquanto; serão embutidas no instalador (Frente 9).
- Janela pywebview em tela cheia (1366×768 alvo), com `--janela` e `--sem-janela` para desenvolvimento. Abertura da janela no Windows ainda não verificada.

## 2026-11-10

- Identidade visual: o sistema usa as cores da logomarca (vermelho `#E43030`, amarelo `#FCF00C`, vinho `#542424`, verde `#249C48`) sobre fundo creme claro. O laranja da primeira versão sai: era o fundo do arquivo da logo, não uma cor da marca. Pedido do Eric.
- Capa do sistema: usa as artes novas enviadas pelo Eric (logo 3D com a mascote e a loja, alternando na vitrine) e a animação da mascote num telão. A animação chegou como GIF de 9 quadros (507×336 px); no telão ela passa um quadro por segundo, a partir de uma tira com os 9 quadros. Se existir o vídeo original, ele substitui a tira.
- Logo das telas internas: redesenho provisório em vetor a partir do arquivo de 447 px (`tools/design/vetoriza_logo.py`), porque a logo ampliada ficava borrada. "SORVETES" foi recolocado com a fonte Inter ExtraBold. Trocar pelo vetor oficial quando o cliente enviar.
- Animações e 3D só com CSS (relevo, perspectiva, camadas, tira de quadros), sem WebGL. Motivo: o PC do caixa tem i3, 4 GB e HD (ver ESPECIFICACAO §10).
- Protótipo passa a ter 5 telas (entra Produtos) e é exportado do canvas por `tools/design/exporta_prototipo.py`.
- O frontend real (`ui/`) só recebe a nova identidade depois que o Eric aprovar a prévia.
- Eric aprovou a prévia ("está muito bom o design do frontend"). A identidade foi para o frontend real.
- Telas montadas no servidor com Jinja2 (`ui/templates/`, moldura única em `base.html`); os dados continuam chegando pela API. Motivo: a moldura estava copiada em cada página e ia se multiplicar a cada módulo. Dependência leve (`jinja2`).
- O que ainda não existe aparece como "em breve" (menus, menu lateral, tela inicial) ou com o selo "Tela em construção" (Caixa, Produtos, Financeiro), e avisa ao ser clicado. Nenhuma tela do sistema mostra valor de exemplo; há teste automático para isso.
- Fontes Inter e Nunito embutidas em `ui/static/fonts/` (licença OFL junto): o sistema não busca nada na internet para abrir.
- `tzdata` entra nas dependências: o Windows não traz a base de fusos horários, e sem ela o programa não abria. Achado pelo primeiro build no GitHub Actions.
- Formato do banco controlado por `PRAGMA user_version` (`app/migracoes.py`), com cópia de segurança em `<dados>/backups` antes de cada mudança, em vez de Alembic. Motivo: um único arquivo SQLite por loja, e o Eric vai instalar versões novas por cima dos dados de teste.
- Instalador: PyInstaller em pasta (não arquivo único, por causa do HD do caixa) + Inno Setup, instalando só para o usuário (sem senha de administrador) e instalando o WebView2 se faltar. Gerado e testado no GitHub Actions, porque o instalador de Windows só pode ser gerado num Windows. Sai uma versão nova quando `VERSAO` (em `app/config.py`) aumenta no `main`; a própria publicação cria a tag `v<VERSAO>`. O teste abre o programa, confere as páginas e tira um print da janela antes de publicar.
- Janela maximizada por padrão; `--tela-cheia` fica para o modo caixa. Motivo: nos testes o Eric precisa conseguir fechar e alternar janelas.
- Programa empacotado não tem terminal: erros de partida aparecem numa caixa de aviso e vão para `<dados>/logs/moleka.log`.
- Ícone do programa: rosto da mascote da arte 3D (`tools/design/gera_icone.py`).

## 2026-11-11

- Ordem de construção aprovada pelo Eric: login e operadores → produtos e preços → abrir e fechar o caixa → venda. A cada função pronta sai um instalador novo para ele testar.
- Nove pedidos novos do Eric registrados em ESPECIFICACAO §11 e distribuídos nas Frentes 2, 4 e 5. Dois dependem de resposta dele: a regra do preço por forma de pagamento e o regime tributário/UF da loja (para a opção de emitir ou não a NFC-e).
- A Frente 1 foi construída nesta sessão (Fable 5.2), por escolha do Eric, que trocou o modelo em 10/11. O `AGENTS.md` ainda descreve a divisão antiga (construção com o Opus); o texto só muda se ele pedir.
- Senha dos operadores: hash `scrypt` do próprio Python (`hashlib`), com sal por senha e os parâmetros gravados junto (`app/seguranca.py`). Motivo de não usar `argon2-cffi`: seria mais uma dependência compilada no instalador, e o `scrypt` atende a este uso. Mínimo de 4 caracteres, para permitir senha numérica no caixa; recomendar senha maior para o gerente.
- Sessão de login só na memória do programa, com cookie `HttpOnly` e `SameSite=Strict` (`app/acesso.py`). Fechar o programa encerra todas as sessões. Não há prazo por tempo sem uso (pergunta aberta em ESPECIFICACAO §9).
- Freio contra adivinhação: 5 senhas erradas seguidas travam o usuário por 30 segundos. Usuário inexistente e senha errada recebem a mesma resposta.
- Primeiro acesso: enquanto não há operador, a capa cria o gerente. Depois disso, só um gerente cria operadores.
- Perfis operador e gerente conforme a tabela de ESPECIFICACAO §12 (padrão proposto, a confirmar com o Eric). A permissão é conferida no servidor em cada pedido; a tela só esconde ou tranca o que o perfil não pode.
- Operador nunca é apagado (fica inativo). Ninguém inativa nem rebaixa o próprio usuário: como só gerente ativo altera operadores, sempre sobra um gerente ativo.
- Recuperação de acesso por linha de comando (`MolekaPDV.exe --redefinir-senha [usuario]`), sem atalho no menu Iniciar, de propósito: um atalho visível deixaria qualquer pessoa no caixa virar gerente. Cada uso vai para o log. Limite conhecido: quem usa a conta do Windows do caixa alcança o arquivo do banco; essa proteção é da conta do Windows, não do sistema.
- O servidor local recusa pedidos com endereço (`Host`) que não seja `127.0.0.1`/`localhost` e pedidos que alteram dados vindos de outra origem (`Origin`). Motivo: um site aberto no navegador do mesmo PC consegue mandar pedidos para `127.0.0.1`.
- Telas HTML saem com `Cache-Control: no-store`: depois de trocar de operador, "voltar" não mostra a tela do anterior.
- Moldura fixa: a página não rola mais; menus, faixa do topo e barra de status ficam sempre visíveis e, se faltar altura, só o miolo rola. As telas foram reajustadas para 1366×697, que é a área útil da janela maximizada numa tela de 1366×768. Motivo: as medidas de 10/11 usaram 1366×768 por engano, e na versão 0.1.0 as telas Início, Produtos e Financeiro rolavam.
- O teste do instalador no Windows passou a fazer o primeiro acesso, sair, recusar senha errada e entrar de novo dentro do programa empacotado; o print da pasta mostra o primeiro acesso e o do instalado mostra o login.
- Achado do primeiro teste fora do GitHub (PC do Eric, Windows 11 Pro): com o Controle Inteligente de Aplicativos (Smart App Control) ligado, o instalador sem assinatura é bloqueado e não há opção de liberar (erro 4551; evento 3077, política `VerifiedAndReputableDesktop`). O que a Microsoft diz, lido em 11/11/2026: não existe exceção por aplicativo; o programa passa se for assinado com certificado de uma autoridade do programa de raízes confiáveis ou se a nuvem da Microsoft já o conhecer; nas atualizações recentes o recurso pode ser religado depois de desligado; o serviço de assinatura da própria Microsoft (Artifact Signing) atende organizações de alguns países e pessoas só dos EUA e do Canadá, e o Brasil não está na lista. Fontes: https://support.microsoft.com/windows/smart-app-control-faq-285ea03d-fa88-4d56-882e-6698afdb7003 , https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/overview , https://learn.microsoft.com/azure/trusted-signing/quickstart .
- Consequência: para instalar em qualquer Windows 11 com esse recurso ligado, o instalador e o programa precisam de assinatura digital com certificado comprado de uma certificadora (custo anual; opções e preços ainda não levantados). **Decisão pendente do Eric.** O PC do caixa é Windows 10, e a Microsoft lista o recurso só para o Windows 11; lá o bloqueio não deve ocorrer (não verificado na prática).
- Caminho escolhido pelo Eric para testar no PC dele sem mexer na proteção do Windows: **rodar pelo código** (`tools/abrir_pelo_codigo.py`), com o Python no lugar do instalador. O roteiro instala as bibliotecas sem os extras opcionais (menos arquivos compilados para o Windows conferir) e abre no navegador se a janela própria não puder ser usada. Não verificado: se o Controle Inteligente deixa carregar as bibliotecas compiladas do Python (`pydantic_core` e as da janela); o roteiro avisa quando há bloqueio.
