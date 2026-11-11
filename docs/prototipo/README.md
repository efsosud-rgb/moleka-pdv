# Protótipo visual (estático)

Cinco telas em HTML puro, sem backend, para avaliar o visual e mostrar ao cliente. Abra `index.html` no navegador (duplo clique). Funciona sem internet, exceto as fontes Nunito/Inter, que vêm do Google Fonts (sem internet o navegador usa a fonte do sistema).

| Arquivo | Tela | Navegação |
|---|---|---|
| `index.html` | Capa / Login: artes novas na vitrine (logo 3D e loja, alternando) e a animação da mascote no telão | botão **Entrar** ou **Enter** → Início |
| `inicio.html` | Início com os módulos | menu lateral e tiles levam às outras telas; **F2** → Caixa; **F5** → Produtos |
| `caixa.html` | Caixa (PDV): venda | **Esc** → Início |
| `financeiro.html` | Financeiro: DRE / Fluxo | **Esc** → Início |
| `produtos.html` | Produtos: cadastro e preços | **Esc** → Início |

A pílula numerada na borda direita troca de tela. Resolução alvo: 1366×768 (monitor do caixa).

## O que é exemplo e o que é dado

- **Os itens da venda em `caixa.html` são fictícios** e estão marcados na própria tela ("Exemplo · valores fictícios").
- DRE, indicadores, resumos e status aparecem como `—` de propósito: só entram quando houver dado real.

## Cores e artes

- Cores da logomarca: vermelho `#E43030` (letras), amarelo `#FCF00C` (oval), vinho `#542424` (contorno), verde `#249C48` (macacão). O laranja da primeira versão era o fundo do arquivo da logo, não uma cor da marca.
- Artes da capa, enviadas pelo Eric em 10/11/2026 (em `assets/brand/`): `capa_logo_3d.jpg`, `capa_loja.jpg` e `capa_animacao.gif` (9 quadros de 507×336 px). O telão usa `capa_animacao_tira.jpg`, que são os mesmos 9 quadros lado a lado, um por segundo.
- `logo_oval_vetor.svg` e `logo_oval_1016px.png` são um **redesenho provisório** da logo a partir do arquivo de 447 px, feito por `tools/design/vetoriza_logo.py`. Trocar pelo arquivo vetorial oficial quando o cliente enviar.

## De onde vêm estes arquivos

Do canvas de design "Moleka PDV — Prévia do Layout", exportado em 10/11/2026 com `tools/design/exporta_prototipo.py`. Ao mudar o design, exportar de novo em vez de editar estes arquivos à mão.

O frontend real (`ui/`) ainda está com as cores antigas; ele recebe esta identidade depois que o Eric aprovar a prévia.
