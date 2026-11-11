# Moleka PDV

Sistema de frente de loja da sorveteria **Moleka Sorvetes**: caixa (PDV) com emissão de NFC-e na SEFAZ, controle de caixa, estoque, entrada de compras por XML, tabelas de preço (varejo, atacado e por quantidade), cadastro de clientes e financeiro (lançamentos, fluxo de caixa, DRE e rentabilidade).

Backend em **Python**; interface em HTML/CSS/JS dentro de uma janela desktop (**pywebview** / WebView2), com visual limpo e relevo 3D nos componentes e na logo animada. Instalação por um único arquivo, `MolekaPDV-Instalador-<versão>.exe`.

> Estado atual (11/11/2026, versão 0.4.0): já funcionam a **entrada com usuário e senha**, os **cadastros** (produtos com preço por tabela e por quantidade, clientes com CPF ou CNPJ, tabelas de preço, percentual por forma de pagamento, operadores), o **controle de caixa** (abertura, sangria, suprimento, fechamento), a **venda** (várias formas de pagamento, troco, desconto do gerente, saldo do dia), o **estoque** (saldos, entrada, saída, contagem, custo médio), a **entrada de nota de compra por XML** e o **financeiro** (contas a pagar e a receber, fluxo de caixa, DRE e rentabilidade por produto). **Ainda não**: NFC-e (nenhum documento fiscal é emitido) e impressão do cupom. As telas foram testadas no navegador e por testes automáticos; o que falta conferir na janela do Windows está em [`docs/PLANO.md`](docs/PLANO.md).

## Como instalar (Windows 10 ou 11)

1. Abra a página de versões do repositório (**Releases**) e baixe `MolekaPDV-Instalador-<versão>.exe`.
2. Dois cliques no arquivo. Se aparecer "O Windows protegeu o computador", clique em **Mais informações** e em **Executar assim mesmo** (o instalador ainda não tem assinatura digital).
   Se aparecer **"Erro 4551: uma política de Controle de Aplicativo bloqueou este arquivo"**, o Windows 11 está com o Controle Inteligente de Aplicativos ligado, que recusa programa sem assinatura e não tem botão para liberar. Ver [`docs/DECISOES.md`](docs/DECISOES.md), em 2026-11-11.
3. **Avançar** até **Concluir**. O atalho **Moleka PDV** fica na Área de Trabalho e no menu Iniciar.

Não pede senha de administrador. Para atualizar, instale a versão nova por cima: os dados ficam em `%APPDATA%\MolekaPDV` e o programa cuida de adaptá-los (com cópia de segurança antes).

O instalador é gerado e testado no GitHub (`.github/workflows/instalador-windows.yml`). Para sair uma versão nova, basta aumentar `VERSAO` em `app/config.py` e enviar para o `main`: o GitHub roda os testes, empacota com PyInstaller, abre o programa num Windows de verdade, tira um print da janela e só então publica em Releases.

## Por onde começar (gerente)

1. **Cadastros → Tabelas de preço e pagamento**: confira as tabelas (VAREJO e ATACADO já vêm criadas) e digite o percentual de cada forma de pagamento (negativo é desconto, positivo é acréscimo).
2. **Cadastros → Produtos** (F5): descrição, código de barras e os preços de cada tabela; "Adicionar faixa" cria o preço por quantidade.
3. **Cadastros → Clientes**: nome, CPF ou CNPJ e a tabela de preço do cliente.
4. **Caixa → Controle de caixa** (F11): digite o fundo de troco e abra o caixa.
5. **Caixa → Venda** (F2): passe o leitor ou digite o produto; F6 a F9 recebem; F10 finaliza.
6. **Estoque → Entrada de NF (XML)**: escolha o arquivo XML da nota do fornecedor, diga em cada item qual é o produto da loja (ou crie um novo) e importe. O estoque sobe, o custo é refeito e as parcelas viram contas a pagar.
7. **Estoque → Saldos, ajustes e contagem**: entrada e saída à mão (com motivo) e contagem da prateleira.
8. **Financeiro**: lance as despesas (aluguel, energia, salários) e dê baixa quando pagar; o fluxo de caixa, o DRE e a rentabilidade saem das vendas e desses lançamentos.

O lucro só aparece para o que tem custo: o custo vem da entrada da nota, de uma entrada no Estoque ou do cadastro do produto, e vale para as vendas feitas **depois**. Sem custo, o DRE e a rentabilidade mostram "—" e dizem o motivo.

## Operadores e senhas

- **Primeiro acesso**: a capa pede a criação do gerente (nome, usuário e senha). Depois, o gerente cadastra os outros operadores em **Cadastros → Operadores**.
- **Trocar de operador** e **Minha senha** ficam no menu **Arquivo**.
- **Esqueci a senha do gerente**: feche o sistema, aperte `Win + R`, cole o comando abaixo e dê Enter. Aparece uma senha provisória; entre com ela e troque em Arquivo → Minha senha.

  ```
  "%LOCALAPPDATA%\Programs\MolekaPDV\MolekaPDV.exe" --redefinir-senha
  ```

  Com mais de um gerente, diga de quem é a senha: `... --redefinir-senha usuario`. Cada uso fica registrado em `%APPDATA%\MolekaPDV\logs\moleka.log`.

## Rodar pelo código no Windows, sem instalador

Para testar num Windows 11 que recusa o instalador (erro 4551, acima). Precisa do Python 3.12 ou mais novo. Com o código numa pasta (zip extraído ou `git clone`), no PowerShell:

```powershell
py tools\abrir_pelo_codigo.py
```

O roteiro cria um ambiente do Python só do Moleka, instala as bibliotecas, confere se o Windows deixa carregá-las e abre o sistema na janela própria; se a janela não puder abrir, abre no navegador (`--navegador` força esse modo). Não altera nenhuma configuração do Windows, e os dados ficam em `%APPDATA%\MolekaPDV`, como no programa instalado.

Para abrir uma versão recebida em `.zip` (`MolekaPDV-codigo-<versão>.zip`) sem digitar caminhos: cole no PowerShell o texto de [`tools/abrir_versao_baixada.ps1`](tools/abrir_versao_baixada.ps1). Ele acha o zip mais novo em Downloads, na Área de Trabalho ou em Documentos, confere o Python, extrai em `%USERPROFILE%\MolekaPDV-dev` e chama o roteiro acima, mostrando o andamento. Esse texto é testado no Windows PowerShell 5.1 do GitHub (`.github/workflows/teste-comando-windows.yml`).

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
mypy
```

Além dos testes do `pytest`, há dois roteiros que usam o sistema pelo navegador, como uma pessoa faria, com os valores esperados calculados à mão: `tools/roteiros/vendas_no_navegador.js` (cadastros, caixa e venda) e `tools/roteiros/estoque_compras_financeiro_no_navegador.js` (estoque, entrada de nota e financeiro). Precisam do Node.js com o pacote `playwright`; o começo de cada arquivo explica como rodar. As notas usadas neles são fictícias, geradas por `tools/roteiros/notas_ficticias.py`.

Os dados ficam em `%APPDATA%\MolekaPDV\` (banco `moleka.db`, `backups/`, `logs/moleka.log`, `xml/entrada/` com as notas de compra importadas). A variável `MOLEKA_PDV_DADOS` muda a pasta; `MOLEKA_PDV_PORTA` muda a porta (padrão 8765). A API tem documentação automática em `http://127.0.0.1:8765/api/docs`.

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
│   ├── vendas.py        # a venda: itens, cliente, desconto, formas de pagamento, finalizar, cancelar
│   ├── caixa.py         # controle de caixa: abertura, sangria, suprimento, fechamento
│   ├── estoque.py       # saldos (soma dos movimentos), custo médio, entrada, saída e contagem
│   ├── nfe_xml.py       # leitura do XML da NF-e de compra (modelo 55) e conferência da chave
│   ├── compras.py       # entrada da nota: de-para do fornecedor, custo, contas a pagar e estorno
│   ├── financeiro.py    # categorias, lançamentos, fluxo de caixa, DRE e rentabilidade
│   ├── catalogo.py      # próximo código de produto
│   ├── documentos.py    # CPF e CNPJ (dígitos verificadores)
│   ├── pesquisa.py      # busca sem acento
│   ├── tempo.py         # horário da loja (Brasília) e o "dia" das vendas
│   ├── seguranca.py     # senha dos operadores (hash scrypt)
│   ├── acesso.py        # sessões de login e permissões por perfil
│   ├── operadores.py    # regras do cadastro de operadores e recuperação de acesso
│   ├── web.py           # páginas (Jinja2), lista de módulos e menus; exige login
│   ├── api/             # FastAPI: status, login e operadores, cadastros, caixa, vendas, estoque, compras e financeiro
│   └── fiscal/          # adaptador fiscal (ProvedorFiscal) + ProvedorNulo
├── ui/
│   ├── templates/       # base.html (moldura) e uma página por tela
│   └── static/          # css/moleka.css, js/ (um arquivo comum e um por tela), fonts/ (Inter e Nunito)
├── assets/brand/        # logo, mascote, artes da capa e ícone do programa
├── packaging/           # PyInstaller, Inno Setup e teste do instalador no Windows
├── tools/               # abrir_pelo_codigo.py (roda sem instalador), roteiros/ (testes pelo navegador), design/ e scripts do PC do caixa
├── docs/                # ESPECIFICACAO.md, DECISOES.md, PLANO.md, prototipo/
└── tests/               # pytest (dinheiro, preços, vendas, caixa, cadastros, estoque, compras, financeiro, login e perfis, páginas, banco)
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
