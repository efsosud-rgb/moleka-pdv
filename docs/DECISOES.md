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
