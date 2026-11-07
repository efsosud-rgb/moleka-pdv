# Moleka PDV

Sistema de frente de loja da sorveteria **Moleka Sorvetes**: caixa (PDV) com emissão de NFC-e na SEFAZ, controle de caixa, estoque, entrada de compras por XML, tabelas de preço (varejo, atacado e por quantidade), cadastro de clientes e financeiro (lançamentos, fluxo de caixa, DRE e rentabilidade).

Backend em **Python**; interface em HTML/CSS/JS dentro de uma janela desktop (**pywebview** / WebView2), com visual limpo e relevo 3D nos componentes e na logo animada. Instalação por um único `Moleka-PDV-Setup.exe`.

> Estado atual: **especificação e protótipo visual**. Nenhum módulo foi implementado ainda. Ver [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md).

## Regras do projeto

As regras para todas as IAs e pessoas que trabalham no repositório estão em [`AGENTS.md`](AGENTS.md) (o `CLAUDE.md` apenas o importa).

A regra que mais importa: **nenhum número inventado**. Dashboards, DRE e relatórios mostram só dados reais; sem dado, exibem `—` e o motivo.

## Estrutura (prevista)

```
moleka-pdv/
├── AGENTS.md            # regras para IAs e colaboradores
├── CLAUDE.md            # importa AGENTS.md
├── docs/                # especificação, decisões, protótipo
├── assets/brand/        # logo e mascote (recortes com fundo transparente)
├── app/                 # (futuro) backend Python: FastAPI + SQLite
├── ui/                  # (futuro) interface HTML/CSS/JS servida na janela pywebview
└── installer/           # (futuro) PyInstaller + Inno Setup
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
