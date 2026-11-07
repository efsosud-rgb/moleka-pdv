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
