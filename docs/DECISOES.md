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
- Instalador: PyInstaller em pasta (não arquivo único, por causa do HD do caixa) + Inno Setup, instalando só para o usuário (sem senha de administrador) e instalando o WebView2 se faltar. Gerado e testado no GitHub Actions a cada tag `v*`, porque o instalador de Windows só pode ser gerado num Windows. O teste abre o programa, confere as páginas e tira um print da janela antes de publicar.
- Janela maximizada por padrão; `--tela-cheia` fica para o modo caixa. Motivo: nos testes o Eric precisa conseguir fechar e alternar janelas.
- Programa empacotado não tem terminal: erros de partida aparecem numa caixa de aviso e vão para `<dados>/logs/moleka.log`.
- Ícone do programa: rosto da mascote da arte 3D (`tools/design/gera_icone.py`).
