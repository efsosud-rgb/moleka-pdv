# Moleka PDV

Sistema de frente de loja da sorveteria **Moleka Sorvetes**: caixa (PDV) com emissão de NFC-e na SEFAZ, controle de caixa, estoque, entrada de compras por XML, tabelas de preço (varejo, atacado e por quantidade), cadastro de clientes e financeiro (lançamentos, fluxo de caixa, DRE e rentabilidade).

Backend em **Python**; interface em HTML/CSS/JS dentro de uma janela desktop (**pywebview** / WebView2), com visual limpo e relevo 3D nos componentes e na logo animada. Instalação por um único arquivo, `MolekaPDV-Instalador-<versão>.exe`.

> Estado atual (11/11/2026, versão 0.2.0): o sistema abre no Windows com o visual aprovado e já tem **entrada com usuário e senha** (primeiro acesso, login, perfis operador e gerente, cadastro de operadores). Cadastro de produtos, venda, caixa, estoque, financeiro e NFC-e ainda não operam: as telas levam o selo "Tela em construção". Ver [`docs/PLANO.md`](docs/PLANO.md).

## Como instalar (Windows 10 ou 11)

1. Abra a página de versões do repositório (**Releases**) e baixe `MolekaPDV-Instalador-<versão>.exe`.
2. Dois cliques no arquivo. Se aparecer "O Windows protegeu o computador", clique em **Mais informações** e em **Executar assim mesmo** (o instalador ainda não tem assinatura digital).
   Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado, que recusa programa sem assinatura e não tem botão para liberar. Ver [`docs/DECISOES.md`](docs/DECISOES.md), em 2026-11-11.
3. **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Não pede senha de administrador. Para atualizar, instale a versão nova por cima: os dados ficam em `%APPDATA%\MolekaPDV` e o programa cuida de adaptá-los (com cópia de segurança antes).

O instalador é gerado e testado no GitHub (`.github/workflows/instalador-windows.yml`). Para sair uma versão nova, basta aumentar `VERSAO` em `app/config.py` e enviar para o `main`: o GitHub roda os testes, empacota com PyInstaller, abre o programa num Windows de verdade, tira um print da janela e só então publica em Releases.

## Operadores e senhas

- **Primeiro acesso**: a capa pede a criação do gerente (nome, usuário e senha). Depois, o gerente cadastra os outros operadores em **Cadastros → Operadores**.
- **Trocar de operador** e **Minha senha** ficam no menu **Arquivo**.
- **Esqueci a senha do gerente**: feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

  ```
  "%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
  ```

  Com mais de um gerente, diga de quem é a senha: `... --redefinir-senha usuario`. Cada uso fica registrado em `%APPDATA%\MolekaPDV\logs\moleka.log`.

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
python main.py --redefinir-senha [usuario]  # recuperação de acesso: mostra uma senha provisória
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
│   ├── seguranca.py     # senha dos operadores (hash scrypt)
│   ├── acesso.py        # sessões de login e permissões por perfil
│   ├── operadores.py    # regras do cadastro de operadores e recuperação de acesso
│   ├── web.py           # páginas (Jinja2), lista de módulos e menus; exige login
│   ├── api/             # FastAPI: status, login e operadores, produtos, clientes, tabelas de preço
│   └── fiscal/          # adaptador fiscal (ProvedorFiscal) + ProvedorNulo
├── ui/
│   ├── templates/       # base.html (moldura) e uma página por tela
│   └── static/          # css/moleka.css, js/ (moleka, entrada, operadores), fonts/ (Inter e Nunito)
├── assets/brand/        # logo, mascote, artes da capa e ícone do programa
├── packaging/           # PyInstaller, Inno Setup e teste do instalador no Windows
├── tools/               # design/ (logo em vetor, ícone, exportação do protótipo) e scripts do PC do caixa
├── docs/                # ESPECIFICACAO.md, DECISOES.md, PLANO.md, prototipo/
└── tests/               # pytest (dinheiro, preços, senhas, login e perfis, API, páginas, banco)
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
