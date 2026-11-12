"""Cadastros: tabelas de preço, formas de pagamento, produtos e clientes.

Permissões (todas as rotas exigem login; ver `criar_app`):
- tabelas de preço, formas de pagamento e produtos: só o gerente cria e altera; qualquer
  operador consulta (o caixa precisa dos produtos e das formas para vender);
- clientes: qualquer operador cadastra e corrige; a tabela de preço do cliente (atacado ou
  varejo) e a situação (ativo/inativo), só o gerente.

Nada é apagado: produto, cliente e tabela ficam inativos. Preços entram em centavos.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import acesso, catalogo, dados_fiscais, db, documentos, vendas
from app.caixa import ROTULOS
from app.models import (
    Cliente,
    FormaPagamento,
    Operador,
    PrecoProduto,
    Produto,
    RegraFormaPagamento,
    TabelaPreco,
)
from app.operadores import RegraError
from app.pesquisa import sem_acento

router = APIRouter(tags=["cadastros"])
log = logging.getLogger("moleka.cadastros")


def _texto(valor: str | None, maximo: int, campo: str) -> str | None:
    """Tira espaços sobrando; vazio vira None; texto longo demais é recusado."""
    limpo = " ".join((valor or "").split())
    if len(limpo) > maximo:
        raise RegraError(f"{campo}: no máximo {maximo} caracteres.")
    return limpo or None


# ---------------------------------------------------------------- tabelas de preço


class TabelaPrecoOut(BaseModel):
    id: int
    nome: str
    padrao: bool
    ativo: bool


class TabelaPrecoIn(BaseModel):
    nome: str
    padrao: bool = False


class TabelaPrecoAlteracao(BaseModel):
    nome: str
    padrao: bool
    ativo: bool


def _nome_de_tabela(sessao: Session, nome: str, menos: int | None = None) -> str:
    nome = (_texto(nome, 40, "Nome da tabela") or "").upper()
    if not nome:
        raise RegraError("Digite o nome da tabela.")
    outra = sessao.scalar(select(TabelaPreco).where(TabelaPreco.nome == nome))
    if outra is not None and outra.id != menos:
        raise RegraError(f"Já existe a tabela {nome}.", status=409)
    return nome


def _tornar_padrao(sessao: Session, tabela: TabelaPreco) -> None:
    for outra in sessao.scalars(select(TabelaPreco).where(TabelaPreco.padrao.is_(True))):
        outra.padrao = False
    tabela.padrao = True


@router.get("/tabelas-preco", response_model=list[TabelaPrecoOut])
def listar_tabelas(todas: bool = False, sessao: Session = Depends(db.sessao)) -> list[TabelaPreco]:
    consulta = select(TabelaPreco).order_by(TabelaPreco.padrao.desc(), TabelaPreco.nome)
    if not todas:
        consulta = consulta.where(TabelaPreco.ativo.is_(True))
    return list(sessao.scalars(consulta))


@router.post("/tabelas-preco", response_model=TabelaPrecoOut, status_code=201)
def criar_tabela(
    dados: TabelaPrecoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> TabelaPreco:
    nome = _nome_de_tabela(sessao, dados.nome)
    primeira = (sessao.scalar(select(func.count()).select_from(TabelaPreco)) or 0) == 0
    tabela = TabelaPreco(nome=nome, padrao=False)
    sessao.add(tabela)
    if dados.padrao or primeira:
        _tornar_padrao(sessao, tabela)
    sessao.commit()
    log.info("tabela de preço %s criada por %s", tabela.nome, gerente.login)
    return tabela


@router.put("/tabelas-preco/{tabela_id}", response_model=TabelaPrecoOut)
def alterar_tabela(
    tabela_id: int,
    dados: TabelaPrecoAlteracao,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> TabelaPreco:
    tabela = sessao.get(TabelaPreco, tabela_id)
    if tabela is None:
        raise HTTPException(404, "Tabela de preço não encontrada.")
    tabela.nome = _nome_de_tabela(sessao, dados.nome, menos=tabela.id)
    if tabela.padrao and not dados.padrao:
        raise RegraError(
            "A loja precisa de uma tabela padrão. Marque outra tabela como padrão.", status=409
        )
    if not dados.ativo and (tabela.padrao or dados.padrao):
        raise RegraError("A tabela padrão não pode ficar inativa.", status=409)
    tabela.ativo = dados.ativo
    if dados.padrao and not tabela.padrao:
        _tornar_padrao(sessao, tabela)
    sessao.commit()
    log.info("tabela de preço %s alterada por %s", tabela.nome, gerente.login)
    return tabela


# ---------------------------------------------------------------- formas de pagamento


class FormaPagamentoOut(BaseModel):
    forma: FormaPagamento
    rotulo: str
    ajuste_bp: int  # centésimos de por cento: -500 = 5% de desconto; 300 = 3% de acréscimo
    ativo: bool


class FormaPagamentoIn(BaseModel):
    ajuste_bp: int
    ativo: bool


def _formas(sessao: Session) -> list[FormaPagamentoOut]:
    regras = vendas.regras_de_pagamento(sessao)
    return [
        FormaPagamentoOut(
            forma=forma, rotulo=ROTULOS[forma], ajuste_bp=regra.ajuste_bp, ativo=regra.ativo
        )
        for forma, regra in regras.items()
    ]


@router.get("/formas-pagamento", response_model=list[FormaPagamentoOut])
def listar_formas(sessao: Session = Depends(db.sessao)) -> list[FormaPagamentoOut]:
    return _formas(sessao)


@router.put("/formas-pagamento/{forma}", response_model=FormaPagamentoOut)
def alterar_forma(
    forma: FormaPagamento,
    dados: FormaPagamentoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FormaPagamentoOut:
    if abs(dados.ajuste_bp) > vendas.AJUSTE_MAXIMO_BP:
        raise RegraError("O desconto ou acréscimo da forma de pagamento vai de -50% a +50%.")
    regras = vendas.regras_de_pagamento(sessao)
    if not dados.ativo and not any(r.ativo for f, r in regras.items() if f != forma):
        raise RegraError("Pelo menos uma forma de pagamento precisa ficar ativa.", status=409)
    regra = sessao.get(RegraFormaPagamento, forma)
    if regra is None:
        regra = RegraFormaPagamento(forma=forma)
        sessao.add(regra)
    regra.ajuste_bp = dados.ajuste_bp
    regra.ativo = dados.ativo
    sessao.commit()
    log.info(
        "forma de pagamento %s alterada por %s: ajuste %s bp, ativa=%s",
        forma.value,
        gerente.login,
        dados.ajuste_bp,
        dados.ativo,
    )
    return next(f for f in _formas(sessao) if f.forma == forma)


# ---------------------------------------------------------------- produtos


class FaixaIn(BaseModel):
    tabela_id: int
    qtd_min: Decimal = Decimal("1")
    preco_centavos: int


class FaixaOut(BaseModel):
    tabela_id: int
    qtd_min: Decimal
    preco_centavos: int


class ProdutoIn(BaseModel):
    codigo: str | None = None  # vazio = o sistema numera
    descricao: str
    categoria: str | None = None
    ean: str | None = None
    unidade: str = "UN"
    ncm: str | None = None
    cest: str | None = None
    cst_csosn: str | None = None
    cfop: str | None = None
    origem: str = "0"
    custo_centavos: int | None = None
    estoque_minimo: Decimal = Decimal("0")
    ativo: bool = True
    precos: list[FaixaIn] = Field(default_factory=list)


class ProdutoOut(BaseModel):
    id: int
    codigo: str
    descricao: str
    categoria: str | None
    ean: str | None
    unidade: str
    ncm: str | None
    cest: str | None
    cst_csosn: str | None
    cfop: str | None
    origem: str
    custo_centavos: int | None
    estoque_minimo: Decimal
    ativo: bool
    precos: list[FaixaOut]


def _so_digitos(valor: str | None, tamanhos: tuple[int, ...], campo: str) -> str | None:
    limpo = "".join((valor or "").split())
    if not limpo:
        return None
    if not limpo.isdigit() or len(limpo) not in tamanhos:
        esperado = " ou ".join(str(t) for t in tamanhos)
        raise RegraError(f"{campo}: só números, com {esperado} dígitos.")
    return limpo


def _conferir_precos(sessao: Session, precos: list[FaixaIn]) -> None:
    vistos: set[tuple[int, Decimal]] = set()
    menor_por_tabela: dict[int, Decimal] = {}
    nomes: dict[int, str] = {}
    for faixa in precos:
        tabela = sessao.get(TabelaPreco, faixa.tabela_id)
        if tabela is None:
            raise RegraError(f"A tabela de preço {faixa.tabela_id} não existe.")
        nomes[tabela.id] = tabela.nome
        if faixa.qtd_min <= 0:
            raise RegraError("A quantidade mínima de uma faixa precisa ser maior que zero.")
        if faixa.preco_centavos < 0:
            raise RegraError("O preço não pode ser negativo.")
        chave = (faixa.tabela_id, faixa.qtd_min.normalize())
        if chave in vistos:
            raise RegraError(
                f"A tabela {tabela.nome} tem duas faixas com a mesma quantidade mínima."
            )
        vistos.add(chave)
        atual = menor_por_tabela.get(tabela.id)
        menor_por_tabela[tabela.id] = faixa.qtd_min if atual is None else min(atual, faixa.qtd_min)
    for tabela_id, menor in menor_por_tabela.items():
        if menor > 1:
            raise RegraError(
                f"Na tabela {nomes[tabela_id]} falta o preço a partir de 1 "
                "(a primeira faixa de quantidade)."
            )


def _gravar_produto(sessao: Session, produto: Produto, dados: ProdutoIn) -> None:
    descricao = _texto(dados.descricao, 120, "Descrição")
    if not descricao:
        raise RegraError("Digite a descrição do produto.")
    codigo = _texto(dados.codigo, 30, "Código") or produto.codigo or catalogo.proximo_codigo(sessao)
    repetido = sessao.scalar(select(Produto).where(Produto.codigo == codigo))
    if repetido is not None and repetido.id != produto.id:
        raise RegraError(f"Já existe um produto com o código {codigo}.", status=409)
    ean = _so_digitos(dados.ean, (8, 12, 13, 14), "Código de barras")
    if ean and dados.ativo:
        com_ean = sessao.scalar(select(Produto).where(Produto.ean == ean, Produto.ativo.is_(True)))
        if com_ean is not None and com_ean.id != produto.id:
            raise RegraError(
                f"O código de barras {ean} já é do produto “{com_ean.descricao}”.", status=409
            )
    unidade = (_texto(dados.unidade, 6, "Unidade") or "UN").upper()
    if dados.custo_centavos is not None and dados.custo_centavos < 0:
        raise RegraError("O custo não pode ser negativo.")
    if dados.estoque_minimo < 0:
        raise RegraError("O estoque mínimo não pode ser negativo.")
    _conferir_precos(sessao, dados.precos)

    produto.codigo = codigo
    produto.descricao = descricao
    produto.categoria = _texto(dados.categoria, 40, "Categoria")
    produto.ean = ean
    produto.unidade = unidade
    produto.ncm = _so_digitos(dados.ncm, (8,), "NCM")
    produto.cest = _so_digitos(dados.cest, (7,), "CEST")
    produto.cst_csosn = _so_digitos(dados.cst_csosn, (2, 3, 4), "CST/CSOSN")
    produto.cfop = dados_fiscais.conferir_cfop(dados.cfop)
    produto.origem = dados_fiscais.conferir_origem(dados.origem)
    produto.custo_centavos = dados.custo_centavos
    produto.estoque_minimo = dados.estoque_minimo
    produto.ativo = dados.ativo
    # Apaga as faixas antigas antes de gravar as novas: o banco não aceita, nem por um
    # instante, duas faixas com a mesma tabela e a mesma quantidade mínima.
    if produto.precos:
        produto.precos.clear()
        sessao.flush()
    produto.precos.extend(
        PrecoProduto(tabela_id=f.tabela_id, qtd_min=f.qtd_min, preco_centavos=f.preco_centavos)
        for f in dados.precos
    )


@router.get("/produtos", response_model=list[ProdutoOut])
def listar_produtos(
    busca: str | None = None,
    inativos: bool = False,
    limite: int = 200,
    sessao: Session = Depends(db.sessao),
) -> list[Produto]:
    # Ordem alfabética e busca sem acento: "agua" acha "Água" (ver app/pesquisa.py).
    consulta = select(Produto).order_by(func.sem_acento(Produto.descricao))
    if not inativos:
        consulta = consulta.where(Produto.ativo.is_(True))
    if busca and busca.strip():
        termo = f"%{sem_acento(busca.strip())}%"
        consulta = consulta.where(
            func.sem_acento(Produto.descricao).like(termo)
            | func.sem_acento(Produto.codigo).like(termo)
            | Produto.ean.like(termo)
            | func.sem_acento(Produto.categoria).like(termo)
        )
    return list(sessao.scalars(consulta.limit(max(1, min(limite, 500)))))


@router.get("/produtos/categorias", response_model=list[str])
def listar_categorias(sessao: Session = Depends(db.sessao)) -> list[str]:
    consulta = select(Produto.categoria).where(Produto.categoria.is_not(None)).distinct()
    return sorted({c for (c,) in sessao.execute(consulta) if c}, key=str.lower)


@router.get("/produtos/{produto_id}", response_model=ProdutoOut)
def ver_produto(produto_id: int, sessao: Session = Depends(db.sessao)) -> Produto:
    produto = sessao.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(404, "Produto não encontrado.")
    return produto


@router.post("/produtos", response_model=ProdutoOut, status_code=201)
def criar_produto(
    dados: ProdutoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Produto:
    produto = Produto()
    with sessao.no_autoflush:
        _gravar_produto(sessao, produto, dados)
    sessao.add(produto)
    sessao.commit()
    sessao.refresh(produto)
    log.info("produto %s (%s) criado por %s", produto.codigo, produto.descricao, gerente.login)
    return produto


@router.put("/produtos/{produto_id}", response_model=ProdutoOut)
def alterar_produto(
    produto_id: int,
    dados: ProdutoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> Produto:
    produto = sessao.get(Produto, produto_id)
    if produto is None:
        raise HTTPException(404, "Produto não encontrado.")
    with sessao.no_autoflush:
        _gravar_produto(sessao, produto, dados)
    sessao.commit()
    sessao.refresh(produto)
    log.info("produto %s alterado por %s (ativo=%s)", produto.codigo, gerente.login, produto.ativo)
    return produto


# ---------------------------------------------------------------- clientes


class ClienteIn(BaseModel):
    nome: str
    cpf_cnpj: str | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None
    tabela_id: int | None = None  # None = tabela padrão da loja
    observacao: str | None = None
    ativo: bool = True


class ClienteOut(BaseModel):
    id: int
    nome: str
    cpf_cnpj: str | None
    documento: str  # CPF ou CNPJ com pontuação, para mostrar
    tipo_pessoa: str | None  # "cpf", "cnpj" ou None (sem documento)
    telefone: str | None
    email: str | None
    endereco: str | None
    tabela_id: int | None
    tabela_nome: str | None
    observacao: str | None
    ativo: bool


def cliente_out(cliente: Cliente) -> ClienteOut:
    return ClienteOut(
        id=cliente.id,
        nome=cliente.nome,
        cpf_cnpj=cliente.cpf_cnpj,
        documento=documentos.formatar(cliente.cpf_cnpj),
        tipo_pessoa=documentos.tipo(cliente.cpf_cnpj or ""),
        telefone=cliente.telefone,
        email=cliente.email,
        endereco=cliente.endereco,
        tabela_id=cliente.tabela_id,
        tabela_nome=cliente.tabela.nome if cliente.tabela else None,
        observacao=cliente.observacao,
        ativo=cliente.ativo,
    )


def _gravar_cliente(sessao: Session, cliente: Cliente, dados: ClienteIn, autor: Operador) -> None:
    novo = cliente.id is None
    nome = _texto(dados.nome, 120, "Nome")
    if not nome:
        raise RegraError("Digite o nome do cliente.")
    ativo = True if novo else dados.ativo
    documento = documentos.limpar(dados.cpf_cnpj) or None
    if documento:
        if documentos.tipo(documento) is None:
            raise RegraError(
                "CPF ou CNPJ inválido: confira os números (o CPF tem 11 dígitos; o CNPJ, 14)."
            )
        outro = sessao.scalar(
            select(Cliente).where(Cliente.cpf_cnpj == documento, Cliente.ativo.is_(True))
        )
        if outro is not None and outro.id != cliente.id and ativo:
            raise RegraError(
                f"Já existe um cliente com esse documento: “{outro.nome}”.", status=409
            )
    if dados.tabela_id is not None and sessao.get(TabelaPreco, dados.tabela_id) is None:
        raise RegraError(f"A tabela de preço {dados.tabela_id} não existe.")
    if not acesso.e_gerente(autor):
        # Atacado ou varejo muda o preço de tudo o que o cliente compra: só o gerente decide.
        if dados.tabela_id != (None if novo else cliente.tabela_id):
            raise RegraError("Só o gerente define a tabela de preço do cliente.", status=403)
        if not novo and dados.ativo != cliente.ativo:
            raise RegraError("Só o gerente inativa ou reativa um cliente.", status=403)
    cliente.nome = nome
    cliente.cpf_cnpj = documento
    cliente.telefone = _texto(dados.telefone, 20, "Telefone")
    cliente.email = _texto(dados.email, 120, "E-mail")
    cliente.endereco = _texto(dados.endereco, 200, "Endereço")
    cliente.tabela_id = dados.tabela_id
    cliente.observacao = (dados.observacao or "").strip() or None
    cliente.ativo = ativo


@router.get("/clientes", response_model=list[ClienteOut])
def listar_clientes(
    busca: str | None = None,
    inativos: bool = False,
    limite: int = 200,
    sessao: Session = Depends(db.sessao),
) -> list[ClienteOut]:
    consulta = select(Cliente).order_by(func.sem_acento(Cliente.nome))
    if not inativos:
        consulta = consulta.where(Cliente.ativo.is_(True))
    if busca and busca.strip():
        termo = f"%{sem_acento(busca.strip())}%"
        filtro = func.sem_acento(Cliente.nome).like(termo) | Cliente.telefone.like(termo)
        documento = documentos.limpar(busca)
        if len(documento) >= 3 and any(c.isdigit() for c in documento):
            filtro = filtro | Cliente.cpf_cnpj.ilike(f"%{documento}%")
        consulta = consulta.where(filtro)
    return [cliente_out(c) for c in sessao.scalars(consulta.limit(max(1, min(limite, 500))))]


@router.post("/clientes", response_model=ClienteOut, status_code=201)
def criar_cliente(
    dados: ClienteIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> ClienteOut:
    cliente = Cliente()
    _gravar_cliente(sessao, cliente, dados, operador)
    sessao.add(cliente)
    sessao.commit()
    log.info("cliente %s criado por %s", cliente.id, operador.login)
    return cliente_out(cliente)


@router.put("/clientes/{cliente_id}", response_model=ClienteOut)
def alterar_cliente(
    cliente_id: int,
    dados: ClienteIn,
    sessao: Session = Depends(db.sessao),
    operador: Operador = Depends(acesso.exigir_operador),
) -> ClienteOut:
    cliente = sessao.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(404, "Cliente não encontrado.")
    _gravar_cliente(sessao, cliente, dados, operador)
    sessao.commit()
    log.info("cliente %s alterado por %s", cliente.id, operador.login)
    return cliente_out(cliente)
