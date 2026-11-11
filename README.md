# Moleka PDV

Sistema de frente de loja da sorveteria **Moleka Sorvetes**: caixa (PDV) com emissão de NFC-e na SEFAZ, controle de caixa, estoque, entrada de compras por XML, tabelas de preço (varejo, atacado e por quantidade), cadastro de clientes e financeiro (lançamentos, fluxo de caixa, DRE e rentabilidade).

Backend em **Python**; interface em HTML/CSS/JS dentro de uma janela desktop (**pywebview** / WebView2), com visual limpo e relevo 3D nos componentes e na logo animada. Instalação por um único arquivo, `MolekaPDV-Instalador-<versão>.exe`.

> Estado atual (10/11/2026, versão 0.1.0): o sistema **abre no Windows com o visual aprovado** (capa com as artes novas, cores da logomarca, 5 telas) e mostra indicadores reais. Login, cadastro de produtos, venda, caixa, estoque, financeiro e NFC-e ainda não operam: as telas levam o selo "Tela em construção". Ver [`docs/PLANO.md`](docs/PLANO.md).

## Como instalar (Windows 10 ou 11)

1. Abra a página de versões do repositório (**Releases**) e baixe `MolekaPDV-Instalador-<versão>.exe`.
2. Dois cliques no arquivo. Se aparecer "O Windows protegeu o computador", clique em **Mais informações** e em **Executar assim mesmo** (o instalador ainda não tem assinatura digital).
3. **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Não pede senha de administrador. Para atualizar, instale a versão nova por cima: os dados ficam em `%APPDATA%\MolekaPDV` e o programa cuida de adaptá-los (com cópia de segurança antes).

O instalador é gerado e testado no GitHub (`.github/workflows/instalador-windows.yml`) a cada tag `v*`: roda os testes, empacota com PyInstaller, abre o programa num Windows de verdade, tira um print da janela e só então publica.

## Como rodar (desenvolvimento)

```powershell
# Windows, PowerShell, na pasta do projeto
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python main.py               # abre a janela maximizada (precisa do WebView2, que o Windows 11 já traz)
python main.py --tela-cheia  # tela cheia, sem barra de título (modo caixa)
python main.py --janela      # janela normal 1366×768
python main.py --sem-janela  # só o servidor: abra http://127.0.0.1:8765/ no navegador
```

Testes e lint:

```powershell
pytest
ruff check .
ruff format .
```

Os dados ficam em `%APPDATA%\MolekaPDV\` (banco `moleka.db`, `backups/`, `logs/moleka.log`, `xml/`). A variável `MOLEKA_PDV_DADOS` muda a pasta; `MOLEKA_PDV_PORTA` muda a porta (padrão 8765). A API tem documentação automática em `http://127.0.0.1:8765/api/docs`.

## Regras do projeto

As regras para todas as IAs e pessoas que trabalham no repositório estão em [`AGENTS.md`](AGENTS.md) (o `CLAUDE.md` apenas o importa).

A regra que mais importa: **nenhum número inventado**. Dashboards, DRE e relatórios mostram só dados reais; sem dado, exibem `—` e o motivo.

## Estrutura

```
moleka-pdv/
├── AGENTS.md            # regras para IAs e colaboradores
├── CLAUDE.md            # importa AGENTS.md
├── main.py              # entrada: log, servidor local e janela pywebview
├── pyproject.toml
├── app/
│   ├── config.py        # nome, versão, pastas (%APPDATA%\MolekaPDV), porta
│   ├── db.py            # engine SQLite (WAL), sessão, criação do schema
│   ├── migracoes.py     # formato do banco entre versões, com cópia de segurança
│   ├── models.py        # schema completo (cadastros, caixa, vendas, fiscal, estoque, compras, financeiro)
│   ├── dinheiro.py      # centavos: parse, formatação, multiplicação, percentual, rateio
│   ├── precos.py        # tabelas varejo/atacado e faixas por quantidade
│   ├── web.py           # páginas (Jinja2), lista de módulos e menus
│   ├── api/             # FastAPI: /api/status, /api/produtos, /api/clientes, /api/tabelas-preco
│   └── fiscal/          # adaptador fiscal (ProvedorFiscal) + ProvedorNulo
├── ui/
│   ├── templates/       # base.html (moldura) e uma página por tela
│   └── static/          # css/moleka.css, js/moleka.js, fonts/ (Inter e Nunito embutidas)
├── assets/brand/        # logo, mascote, artes da capa e ícone do programa
├── packaging/           # PyInstaller, Inno Setup e teste do instalador no Windows
├── tools/               # design/ (logo em vetor, ícone, exportação do protótipo) e scripts do PC do caixa
├── docs/                # ESPECIFICACAO.md, DECISOES.md, PLANO.md, prototipo/
└── tests/               # pytest (dinheiro, preços, API, páginas, banco)
```

## Marca

Cores da logomarca (`assets/brand/`):

| Uso | Cor |
|---|---|
| Vermelho das letras | `#E43030` |
| Amarelo do oval | `#FCF00C` |
| Vinho do contorno | `#542424` |
| Verde do macacão | `#249C48` |

As artes da capa (`capa_logo_3d.jpg`, `capa_loja.jpg`, `capa_animacao.gif`) foram enviadas pelo cliente em 10/11/2026. `logo_oval_vetor.svg` é um redesenho provisório da logo, até chegar o vetor oficial.
