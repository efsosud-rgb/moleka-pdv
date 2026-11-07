# Moleka PDV

Sistema de frente de loja da sorveteria **Moleka Sorvetes**: caixa (PDV) com emissão de NFC-e na SEFAZ, controle de caixa, estoque, entrada de compras por XML, tabelas de preço (varejo, atacado e por quantidade), cadastro de clientes e financeiro (lançamentos, fluxo de caixa, DRE e rentabilidade).

Backend em **Python**; interface em HTML/CSS/JS dentro de uma janela desktop (**pywebview** / WebView2), com visual limpo e relevo 3D nos componentes e na logo animada. Instalação por um único `Moleka-PDV-Setup.exe`.

> Estado atual (07/11/2026): **base executável** — servidor local, banco SQLite com o schema completo, endpoint de status real, cadastros básicos (produtos, clientes, tabelas de preço) e as 4 telas da interface. Venda, fiscal, estoque, XML e financeiro ainda não operam: ver [`docs/PLANO.md`](docs/PLANO.md).

## Como rodar (desenvolvimento)

```powershell
# Windows, PowerShell, na pasta do projeto
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python main.py            # abre a janela em tela cheia (precisa do WebView2, que o Windows 11 já traz)
python main.py --janela   # janela normal 1366×768
python main.py --sem-janela   # só o servidor: abra http://127.0.0.1:8765/ no navegador
```

Testes e lint:

```powershell
pytest
ruff check app tests main.py
ruff format app tests main.py
```

Os dados ficam em `%APPDATA%\MolekaPDV\` (banco `moleka.db`, `backups/`, `logs/`, `xml/`). A variável `MOLEKA_PDV_DADOS` muda a pasta; `MOLEKA_PDV_PORTA` muda a porta (padrão 8765). A API tem documentação automática em `http://127.0.0.1:8765/api/docs`.

## Regras do projeto

As regras para todas as IAs e pessoas que trabalham no repositório estão em [`AGENTS.md`](AGENTS.md) (o `CLAUDE.md` apenas o importa).

A regra que mais importa: **nenhum número inventado**. Dashboards, DRE e relatórios mostram só dados reais; sem dado, exibem `—` e o motivo.

## Estrutura

```
moleka-pdv/
├── AGENTS.md            # regras para IAs e colaboradores
├── CLAUDE.md            # importa AGENTS.md
├── main.py              # entrada: sobe o servidor local e abre a janela pywebview
├── pyproject.toml
├── app/
│   ├── config.py        # nome, versão, pastas (%APPDATA%\MolekaPDV), porta
│   ├── db.py            # engine SQLite (WAL), sessão, criação do schema
│   ├── models.py        # schema completo (cadastros, caixa, vendas, fiscal, estoque, compras, financeiro)
│   ├── dinheiro.py      # centavos: parse, formatação, multiplicação, percentual, rateio
│   ├── precos.py        # tabelas varejo/atacado e faixas por quantidade
│   ├── api/             # FastAPI: /api/status, /api/produtos, /api/clientes, /api/tabelas-preco
│   └── fiscal/          # adaptador fiscal (ProvedorFiscal) + ProvedorNulo
├── ui/                  # interface servida pelo app: index (abertura), inicio, caixa, financeiro, css/, js/
├── assets/brand/        # logo e mascote (recortes com fundo transparente)
├── docs/                # ESPECIFICACAO.md, DECISOES.md, PLANO.md, prototipo/
└── tests/               # pytest (dinheiro, preços, API)
```

## Marca

Cores extraídas da logo enviada pelo cliente (`assets/brand/logo_original_447px.png`):

| Uso | Cor |
|---|---|
| Laranja de fundo | `#FFB759` |
| Amarelo do oval | `#FCF211` |
| Verde (macacão) | `#23A151` |
| Vermelho (letras/camisa) | `#E43238` |
| Vinho (contorno) | `#51222B` |
| Pele | `#FBD1A1` |
