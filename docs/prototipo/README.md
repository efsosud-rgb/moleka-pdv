# Protótipo visual (estático)

Quatro telas em HTML puro, sem backend, para avaliar o visual e mostrar ao cliente. Abra `index.html` no navegador (duplo clique) — funciona sem internet, exceto as fontes Nunito/Inter, que vêm do Google Fonts (sem internet o navegador usa a fonte do sistema).

| Arquivo | Tela | Navegação |
|---|---|---|
| `index.html` | Abertura / Login com a logo animada | botão **Entrar** → Início |
| `inicio.html` | Início com os módulos | tiles **Caixa (PDV)**, **Financeiro** e **DRE** levam às outras telas; **F2** → Caixa |
| `caixa.html` | Caixa (PDV) — venda | **Esc** → Início |
| `financeiro.html` | Financeiro — DRE / Fluxo | **Esc** → Início |

A pílula numerada na borda direita troca de tela. Resolução alvo: 1366×768.

**Os itens da venda em `caixa.html` são fictícios** (marcados na própria tela). Os números de DRE e indicadores aparecem como `—` de propósito: só entram quando houver dado real.

Fonte dos arquivos: canvas de design "Moleka PDV — Prévia do Layout" (exportado em 07/11/2026). Ao mudar o design, exportar de novo em vez de editar estes arquivos à mão.
