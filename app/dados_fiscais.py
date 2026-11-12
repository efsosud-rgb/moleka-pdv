"""Dados fiscais da NFC-e que o dono da loja preenche em Configurações → Fiscal (NFC-e).

Esta versão NÃO emite NFC-e: aqui os dados ficam prontos, conferidos e gravados neste computador.
- Empresa: regime tributário (CRT), código do município (IBGE), inscrição municipal, CNAE e as
  respostas sobre a SEFAZ (a empresa já é credenciada para NFC-e? já emite por outro sistema?).
  Razão social, CNPJ, IE e endereço continuam na aba Dados da loja (app/configuracoes.py).
- CSC (Código de Segurança do Contribuinte), de homologação e de produção: o ID fica na tabela
  `configuracao`; o código é segredo e vai para app/segredos.py (a tela só vê os 4 últimos
  caracteres, para conferir).
- Numeração: série e próximo número da NFC-e de cada caixa (tabela `caixa`).
- Contador: nome, contato e o que ele orientou.
- Produtos: NCM, CEST, CFOP, CST/CSOSN e origem ficam no cadastro de cada produto; aqui há o
  resumo por categoria e o preenchimento de uma categoria inteira de uma vez.

`pendencias` monta a lista "o que falta para emitir" só com o que está gravado: não consulta a
SEFAZ nem o contador. O ambiente é sempre o de homologação (testes): produção só com a ordem
explícita do Eric (AGENTS.md, regra 3).

Fontes das listas: CFOP aceitos na NFC-e (MOC 7.0, Anexo I, regra 725); CSOSN do MEI na NFC-e,
102 e 300 (NT 2024.001, regras que valem desde 01/04/2025); códigos de UF da tabela do IBGE.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import certificado, configuracoes, documentos, segredos
from app.models import Caixa, DocumentoFiscal, Produto
from app.operadores import RegraError

log = logging.getLogger("moleka.fiscal")

AMBIENTE = "homologacao"
AMBIENTE_ROTULO = "Homologação (testes, a nota não vale)"
AVISO = (
    "Esta versão ainda não emite NFC-e. Aqui você deixa os dados prontos; a emissão de teste "
    "(homologação) entra numa próxima versão."
)
CRTS: dict[str, str] = {
    "1": "Simples Nacional (microempresa ou EPP)",
    "4": "MEI (microempreendedor individual)",
    "2": "Simples Nacional, acima do sublimite de receita",
    "3": "Regime normal (Lucro Presumido ou Lucro Real)",
}
RESPOSTAS: dict[str, str] = {"sim": "Sim", "nao": "Não", "nao-sei": "Não sei"}
ORIGENS: dict[str, str] = {
    "0": "0 – Nacional",
    "1": "1 – Estrangeira, importação direta",
    "2": "2 – Estrangeira, comprada no Brasil",
    "3": "3 – Nacional, de 40% a 70% importado",
    "4": "4 – Nacional, processo produtivo básico",
    "5": "5 – Nacional, até 40% importado",
    "6": "6 – Estrangeira, importação direta, sem similar",
    "7": "7 – Estrangeira, comprada no Brasil, sem similar",
    "8": "8 – Nacional, mais de 70% importado",
}
CFOPS_DA_NFCE: dict[str, str] = {
    "5101": "5101 – Venda de produção própria",
    "5102": "5102 – Venda de mercadoria comprada de terceiros",
    "5103": "5103 – Venda de produção própria, fora da loja",
    "5104": "5104 – Venda de mercadoria de terceiros, fora da loja",
    "5115": "5115 – Venda de mercadoria recebida em consignação",
    "5405": "5405 – Venda de mercadoria com substituição tributária (ST)",
    "5656": "5656 – Venda de combustível a consumidor final",
    "5667": "5667 – Venda de combustível a consumidor de outro estado",
    "5933": "5933 – Serviço tributado pelo ISSQN",
}
CSOSN = frozenset({"101", "102", "103", "201", "202", "203", "300", "400", "500", "900"})
CST_ICMS = frozenset(
    {"00", "02", "10", "15", "20", "30", "40", "41", "50", "51", "53", "60", "61", "70", "90"}
)
CSOSN_DO_MEI_NA_NFCE = ("102", "300")
CODIGO_DA_UF: dict[str, str] = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35", "PR": "41",
    "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}  # fmt: skip
SERIE_MAXIMA = 999
NUMERO_MAXIMO = 999_999_999
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _texto(valor: str | None, maximo: int, nome: str) -> str:
    limpo = " ".join((valor or "").split())
    if len(limpo) > maximo:
        raise RegraError(f"{nome}: no máximo {maximo} caracteres.")
    return limpo


def _digitos(valor: str | None) -> str:
    return re.sub(r"[\s.\-/]", "", valor or "")


def _so_numeros(valor: str | None, tamanho: int, nome: str, exemplo: str = "") -> str:
    limpo = _digitos(valor)
    if limpo and (not limpo.isdigit() or len(limpo) != tamanho):
        dica = f" Por exemplo: {exemplo}." if exemplo else ""
        raise RegraError(f"{nome}: são {tamanho} números.{dica}")
    return limpo


# ---------------------------------------------------------------- campos fiscais do produto


def conferir_ncm(valor: str | None) -> str | None:
    return _so_numeros(valor, 8, "NCM", "2105.00.10") or None


def conferir_cest(valor: str | None) -> str | None:
    return _so_numeros(valor, 7, "CEST", "23.001.00") or None


def conferir_cfop(valor: str | None) -> str | None:
    cfop = _so_numeros(valor, 4, "CFOP", "5102")
    if cfop and cfop[0] != "5":
        raise RegraError(
            "CFOP: na NFC-e ele começa com 5 (venda dentro do estado, para o consumidor). "
            "Por exemplo: 5102 ou 5405."
        )
    return cfop or None


def conferir_cst_csosn(valor: str | None) -> str | None:
    limpo = _digitos(valor)
    if limpo and (not limpo.isdigit() or len(limpo) not in (2, 3, 4)):
        raise RegraError("CST/CSOSN: só números (CST tem 2, CSOSN tem 3).")
    return limpo or None


def conferir_origem(valor: str | None) -> str:
    origem = (valor or "").strip() or "0"
    if origem not in ORIGENS:
        raise RegraError("Origem: um número de 0 a 8 (0 = nacional).")
    return origem


def do_simples(crt: str) -> bool:
    return crt in ("1", "4")


def combina_com_o_regime(crt: str, cst_csosn: str | None) -> bool:
    """O código combina com o regime? Sem regime escolhido, não há o que conferir."""
    if not crt or not cst_csosn:
        return True
    if do_simples(crt):
        return cst_csosn in CSOSN and (crt != "4" or cst_csosn in CSOSN_DO_MEI_NA_NFCE)
    return cst_csosn in CST_ICMS


# ---------------------------------------------------------------- empresa


@dataclass(frozen=True)
class Empresa:
    crt: str = ""
    codigo_municipio: str = ""  # IBGE, 7 números
    inscricao_municipal: str = ""
    cnae: str = ""  # 7 números
    credenciada: str = ""  # já é credenciada para NFC-e na SEFAZ? (RESPOSTAS ou vazio)
    emite_hoje: str = ""  # já emite NFC-e hoje, por outro sistema? (RESPOSTAS ou vazio)
    emite_hoje_detalhe: str = ""  # qual sistema, série e último número


_CAMPOS_DA_EMPRESA = (
    "crt codigo_municipio inscricao_municipal cnae credenciada emite_hoje emite_hoje_detalhe"
).split()


def ler_empresa(sessao: Session) -> Empresa:
    return Empresa(
        **{c: configuracoes.ler_valor(sessao, f"fiscal.{c}") for c in _CAMPOS_DA_EMPRESA}
    )


def uf_do_codigo(codigo: str) -> str:
    return next((uf for uf, prefixo in CODIGO_DA_UF.items() if codigo.startswith(prefixo)), "")


def gravar_empresa(sessao: Session, dados: Empresa, quem: str) -> Empresa:
    if dados.crt and dados.crt not in CRTS:
        raise RegraError("Regime tributário: escolha uma das opções da lista.")
    municipio = _so_numeros(dados.codigo_municipio, 7, "Código do município (IBGE)", "3550308")
    if municipio:
        uf_codigo = uf_do_codigo(municipio)
        if not uf_codigo:
            raise RegraError(
                f"Código do município: {municipio} não começa com o código de nenhum estado. "
                "Confira os números."
            )
        uf_loja = configuracoes.ler_loja(sessao).uf
        if uf_loja and uf_loja != uf_codigo:
            raise RegraError(
                f"O código {municipio} é de uma cidade de {uf_codigo}, mas o estado da loja "
                f"(aba Dados da loja) é {uf_loja}. Confira o código ou o estado."
            )
    inscricao = _texto(dados.inscricao_municipal, 20, "Inscrição municipal").upper()
    if inscricao and not all(c.isalnum() or c in ".-/" for c in inscricao):
        raise RegraError("Inscrição municipal: só letras, números, ponto, traço e barra.")
    cnae = _so_numeros(dados.cnae, 7, "CNAE", "1053-8/00")
    for resposta, nome in ((dados.credenciada, "credenciada"), (dados.emite_hoje, "emite hoje")):
        if resposta and resposta not in RESPOSTAS:
            raise RegraError(f"Resposta inválida ({nome}): escolha Sim, Não ou Não sei.")
    empresa = Empresa(
        crt=dados.crt,
        codigo_municipio=municipio,
        inscricao_municipal=inscricao,
        cnae=cnae,
        credenciada=dados.credenciada,
        emite_hoje=dados.emite_hoje,
        emite_hoje_detalhe=_texto(dados.emite_hoje_detalhe, 160, "Sistema, série e número"),
    )
    for campo in _CAMPOS_DA_EMPRESA:
        configuracoes.gravar_valor(sessao, f"fiscal.{campo}", getattr(empresa, campo))
    log.info("dados fiscais da empresa gravados por %s (regime %s)", quem, empresa.crt or "—")
    return empresa


# ---------------------------------------------------------------- contador


@dataclass(frozen=True)
class Contador:
    nome: str = ""
    crc: str = ""
    telefone: str = ""
    email: str = ""
    documento: str = ""  # CPF ou CNPJ do contador ou do escritório
    observacoes: str = ""  # o que ele orientou


_CAMPOS_DO_CONTADOR = "nome crc telefone email documento observacoes".split()


def ler_contador(sessao: Session) -> Contador:
    return Contador(
        **{c: configuracoes.ler_valor(sessao, f"fiscal.contador_{c}") for c in _CAMPOS_DO_CONTADOR}
    )


def gravar_contador(sessao: Session, dados: Contador) -> Contador:
    email = _texto(dados.email, 80, "E-mail").lower()
    if email and not _EMAIL.fullmatch(email):
        raise RegraError("E-mail do contador inválido. Confira: nome@provedor.com.br")
    documento = documentos.limpar(dados.documento)
    if documento and documentos.tipo(documento) is None:
        raise RegraError("CPF ou CNPJ do contador inválido. Confira os números.")
    linhas = [" ".join(linha.split()) for linha in (dados.observacoes or "").splitlines()]
    observacoes = "\n".join(linhas).strip()
    if len(observacoes) > 600:
        raise RegraError("Observações: no máximo 600 caracteres.")
    contador = Contador(
        nome=_texto(dados.nome, 80, "Nome do contador"),
        crc=_texto(dados.crc, 20, "CRC").upper(),
        telefone=_texto(dados.telefone, 20, "Telefone"),
        email=email,
        documento=documento,
        observacoes=observacoes,
    )
    for campo in _CAMPOS_DO_CONTADOR:
        configuracoes.gravar_valor(sessao, f"fiscal.contador_{campo}", getattr(contador, campo))
    return contador


# ---------------------------------------------------------------- CSC


AMBIENTES = ("homologacao", "producao")


@dataclass(frozen=True)
class Csc:
    ambiente: str
    id: str  # identificador do CSC na SEFAZ (até 6 números)
    salvo: bool  # o código está guardado
    final: str  # os 4 últimos caracteres do código, para conferir (vazio se não há)


def _nome_do_segredo(ambiente: str) -> str:
    return f"csc-{ambiente}"


def ler_csc(sessao: Session, ambiente: str) -> Csc:
    try:
        codigo = segredos.ler(_nome_do_segredo(ambiente)) or ""
    except segredos.SegredoError:
        codigo = ""
    return Csc(
        ambiente=ambiente,
        id=configuracoes.ler_valor(sessao, f"fiscal.csc_{ambiente}_id"),
        salvo=bool(codigo),
        final=codigo[-4:] if len(codigo) >= 8 else "",
    )


def _nome_do_ambiente(ambiente: str) -> str:
    return "de homologação" if ambiente == "homologacao" else "de produção"


def conferir_csc(ambiente: str, id_csc: str, codigo: str) -> tuple[str, str]:
    """Confere o ID e o código digitados e devolve os dois limpos. Não grava nada."""
    if ambiente not in AMBIENTES:
        raise RegraError("Ambiente inválido.")
    nome = _nome_do_ambiente(ambiente)
    identificador = "".join((id_csc or "").split())
    if identificador and (not identificador.isdigit() or len(identificador) > 6):
        raise RegraError(f"ID do CSC {nome}: só números, até 6 (por exemplo: 000001).")
    novo = (codigo or "").strip()
    if any(c.isspace() for c in novo):
        raise RegraError(f"Código CSC {nome}: sem espaços no meio. Copie e cole de novo.")
    if len(novo) > 36 or not all(c.isascii() and (c.isalnum() or c == "-") for c in novo):
        raise RegraError(f"Código CSC {nome}: só letras e números, até 36 caracteres.")
    if novo and not identificador:
        raise RegraError(
            f"Digite também o ID do CSC {nome} (o número que a SEFAZ mostra junto com o código)."
        )
    return identificador, novo


def gravar_csc(
    sessao: Session, ambiente: str, id_csc: str, codigo: str, apagar: bool, quem: str
) -> Csc:
    """Grava o ID e, se veio, o código. Código vazio mantém o que já está guardado."""
    identificador, novo = conferir_csc(ambiente, id_csc, codigo)
    nome = _nome_do_ambiente(ambiente)
    configuracoes.gravar_valor(sessao, f"fiscal.csc_{ambiente}_id", identificador)
    try:
        if apagar:
            segredos.apagar(_nome_do_segredo(ambiente))
            log.warning("CSC %s apagado por %s", nome, quem)
        elif novo:
            segredos.gravar(_nome_do_segredo(ambiente), novo)
            log.info("CSC %s gravado por %s (ID %s)", nome, quem, identificador)
    except segredos.SegredoError as erro:
        raise RegraError(f"Não consegui guardar o código CSC {nome}. {erro}") from erro
    return ler_csc(sessao, ambiente)


# ---------------------------------------------------------------- numeração


@dataclass(frozen=True)
class Numeracao:
    caixa_id: int
    caixa: str
    serie: int
    proximo_numero: int
    ultima_registrada: int | None  # maior número desta série que o sistema já registrou


def _ultima_da_serie(sessao: Session, serie: int) -> int | None:
    return sessao.scalar(
        select(func.max(DocumentoFiscal.numero)).where(
            DocumentoFiscal.modelo == "65", DocumentoFiscal.serie == serie
        )
    )


def ler_numeracao(sessao: Session) -> list[Numeracao]:
    caixas = list(sessao.scalars(select(Caixa).where(Caixa.ativo.is_(True)).order_by(Caixa.id)))
    return [
        Numeracao(
            caixa_id=c.id,
            caixa=c.nome,
            serie=c.serie_nfce,
            proximo_numero=c.proximo_numero_nfce,
            ultima_registrada=_ultima_da_serie(sessao, c.serie_nfce),
        )
        for c in caixas
    ]


def numeracao_conferida(sessao: Session) -> bool:
    return configuracoes.ler_valor(sessao, "fiscal.numeracao_conferida") == "1"


def gravar_numeracao(
    sessao: Session, caixa_id: int, serie: int, proximo_numero: int, quem: str
) -> Numeracao:
    caixa = sessao.get(Caixa, caixa_id)
    if caixa is None or not caixa.ativo:
        raise RegraError("Caixa não encontrado.", status=404)
    if not 0 <= serie <= SERIE_MAXIMA:
        raise RegraError(f"Série: um número de 0 a {SERIE_MAXIMA}.")
    if not 1 <= proximo_numero <= NUMERO_MAXIMO:
        raise RegraError("Próximo número: de 1 a 999.999.999.")
    outro = sessao.scalar(
        select(Caixa).where(Caixa.id != caixa.id, Caixa.ativo.is_(True), Caixa.serie_nfce == serie)
    )
    if outro is not None:
        raise RegraError(f"A série {serie} já é do {outro.nome}: cada caixa usa uma série.")
    ultima = _ultima_da_serie(sessao, serie)
    if ultima is not None and proximo_numero <= ultima:
        raise RegraError(
            f"A NFC-e nº {ultima} da série {serie} já foi registrada por este sistema: "
            f"o próximo número tem de ser maior que {ultima}."
        )
    antes = (caixa.serie_nfce, caixa.proximo_numero_nfce)
    caixa.serie_nfce = serie
    caixa.proximo_numero_nfce = proximo_numero
    configuracoes.gravar_valor(sessao, "fiscal.numeracao_conferida", "1")
    log.info(
        "numeração da NFC-e do %s: série %s, próximo nº %s (antes: série %s, nº %s), por %s",
        caixa.nome,
        serie,
        proximo_numero,
        antes[0],
        antes[1],
        quem,
    )
    return Numeracao(caixa.id, caixa.nome, serie, proximo_numero, ultima)


# ---------------------------------------------------------------- produtos


@dataclass(frozen=True)
class Categoria:
    nome: str | None  # None = produtos sem categoria
    produtos: int
    sem_ncm: int
    sem_cfop: int
    sem_cst_csosn: int
    fora_do_regime: int  # CST/CSOSN que não combina com o regime escolhido
    cfop_fora_da_lista: int  # CFOP que a NFC-e não costuma aceitar

    @property
    def completa(self) -> bool:
        return not (self.sem_ncm or self.sem_cfop or self.sem_cst_csosn)


def _ativos(sessao: Session) -> list[Produto]:
    return list(sessao.scalars(select(Produto).where(Produto.ativo.is_(True))))


def _nome_da_categoria(produto: Produto) -> str | None:
    return (produto.categoria or "").strip() or None


def resumo_por_categoria(sessao: Session, crt: str) -> list[Categoria]:
    grupos: dict[str | None, list[Produto]] = {}
    for produto in _ativos(sessao):
        grupos.setdefault(_nome_da_categoria(produto), []).append(produto)
    resumo = [
        Categoria(
            nome=nome,
            produtos=len(lista),
            sem_ncm=sum(1 for p in lista if not p.ncm),
            sem_cfop=sum(1 for p in lista if not p.cfop),
            sem_cst_csosn=sum(1 for p in lista if not p.cst_csosn),
            fora_do_regime=sum(1 for p in lista if not combina_com_o_regime(crt, p.cst_csosn)),
            cfop_fora_da_lista=sum(1 for p in lista if p.cfop and p.cfop not in CFOPS_DA_NFCE),
        )
        for nome, lista in grupos.items()
    ]
    # As categorias em ordem alfabética; "sem categoria" no fim.
    return sorted(resumo, key=lambda c: (c.nome is None, (c.nome or "").lower()))


@dataclass(frozen=True)
class Preenchimento:
    """O que preencher numa categoria inteira. None = não mexer neste campo."""

    ncm: str | None = None
    cest: str | None = None
    cfop: str | None = None
    cst_csosn: str | None = None
    origem: str | None = None


def conferir_preenchimento(dados: Preenchimento) -> Preenchimento:
    conferido = Preenchimento(
        ncm=conferir_ncm(dados.ncm),
        cest=conferir_cest(dados.cest),
        cfop=conferir_cfop(dados.cfop),
        cst_csosn=conferir_cst_csosn(dados.cst_csosn),
        origem=conferir_origem(dados.origem) if (dados.origem or "").strip() else None,
    )
    if all(getattr(conferido, c) is None for c in ("ncm", "cest", "cfop", "cst_csosn", "origem")):
        raise RegraError("Preencha pelo menos um dos campos.")
    return conferido


def preencher_categoria(
    sessao: Session, categoria: str | None, dados: Preenchimento, sobrescrever: bool, quem: str
) -> int:
    """Preenche os campos dados em todos os produtos ativos da categoria. Devolve quantos mudaram.

    Sem `sobrescrever`, só os campos vazios de cada produto são preenchidos (e a origem, que todo
    produto já tem, não muda). Com `sobrescrever`, os campos dados trocam em todos.
    """
    conferido = conferir_preenchimento(dados)
    alvo = (categoria or "").strip() or None
    produtos = [p for p in _ativos(sessao) if _nome_da_categoria(p) == alvo]
    if not produtos:
        raise RegraError("Nenhum produto ativo nesta categoria.", status=404)
    mudaram = 0
    for produto in produtos:
        mudou = False
        for campo in ("ncm", "cest", "cfop", "cst_csosn", "origem"):
            novo = getattr(conferido, campo)
            if novo is None:
                continue
            atual = getattr(produto, campo)
            if (sobrescrever or not atual) and atual != novo:
                setattr(produto, campo, novo)
                mudou = True
        mudaram += mudou
    campos = ", ".join(
        f"{c}={getattr(conferido, c)}"
        for c in ("ncm", "cest", "cfop", "cst_csosn", "origem")
        if getattr(conferido, c) is not None
    )
    log.info(
        "dados fiscais preenchidos na categoria %s por %s: %s de %s produtos (%s; %s)",
        alvo or "(sem categoria)",
        quem,
        mudaram,
        len(produtos),
        campos,
        "trocando o que já havia" if sobrescrever else "só os campos vazios",
    )
    return mudaram


# ---------------------------------------------------------------- o que falta para emitir


@dataclass(frozen=True)
class Pendencia:
    chave: str
    situacao: str  # "ok", "falta" ou "atencao"
    titulo: str
    detalhe: str
    onde: str  # a aba "loja" ou a parte da aba Fiscal onde se resolve


_CAMPOS_DA_LOJA_NA_NOTA = (
    ("razao_social", "razão social"),
    ("cnpj", "CNPJ"),
    ("ie", "inscrição estadual"),
    ("logradouro", "endereço"),
    ("numero", "número"),
    ("bairro", "bairro"),
    ("cidade", "cidade"),
    ("uf", "estado"),
    ("cep", "CEP"),
)


def _lista(partes: list[str]) -> str:
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1]


def _pendencia_da_loja(loja: configuracoes.Loja) -> Pendencia:
    titulo = "Dados da empresa (aba Dados da loja)"
    faltam = [nome for campo, nome in _CAMPOS_DA_LOJA_NA_NOTA if not getattr(loja, campo)]
    if faltam:
        return Pendencia("loja", "falta", titulo, f"Falta: {_lista(faltam)}.", "loja")
    if loja.ie == "ISENTO":
        return Pendencia(
            "loja",
            "atencao",
            titulo,
            "A inscrição estadual está como ISENTO. Quem emite NFC-e tem inscrição estadual: "
            "confira com o contador.",
            "loja",
        )
    return Pendencia(
        "loja", "ok", titulo, "Razão social, CNPJ, inscrição estadual e endereço.", "loja"
    )


def _pendencia_do_certificado(
    situacao: certificado.Situacao | None, cnpj_da_loja: str, agora: datetime
) -> Pendencia:
    titulo = "Certificado digital A1"
    if situacao is None:
        return Pendencia(
            "certificado", "falta", titulo, "Instale o certificado A1 da empresa.", "certificado"
        )
    if not situacao.tem_arquivo or not situacao.tem_senha:
        falta = "o arquivo" if not situacao.tem_arquivo else "a senha"
        return Pendencia(
            "certificado",
            "falta",
            titulo,
            f"Sumiu {falta} do certificado deste computador: instale de novo.",
            "certificado",
        )
    if situacao.vencido(agora):
        return Pendencia(
            "certificado",
            "falta",
            titulo,
            f"Venceu em {certificado.data_br(situacao.fim)}: instale o certificado novo.",
            "certificado",
        )
    if cnpj_da_loja and cnpj_da_loja[:8] != situacao.cnpj[:8]:
        return Pendencia(
            "certificado",
            "falta",
            titulo,
            f"É do CNPJ {documentos.formatar(situacao.cnpj)}, diferente do CNPJ da loja.",
            "certificado",
        )
    dias = situacao.dias_restantes(agora)
    if dias <= certificado.AVISO_DE_VENCIMENTO_DIAS:
        quando = "hoje" if dias <= 0 else ("amanhã" if dias == 1 else f"em {dias} dias")
        return Pendencia(
            "certificado",
            "atencao",
            titulo,
            f"Vence {quando} ({certificado.data_br(situacao.fim)}): providencie a renovação.",
            "certificado",
        )
    return Pendencia(
        "certificado",
        "ok",
        titulo,
        f"Válido até {certificado.data_br(situacao.fim)}.",
        "certificado",
    )


def _pendencia_dos_produtos(categorias: list[Categoria], crt: str) -> Pendencia:
    titulo = "Dados fiscais dos produtos"
    total = sum(c.produtos for c in categorias)
    if not total:
        return Pendencia(
            "produtos", "atencao", titulo, "Nenhum produto ativo cadastrado.", "produtos"
        )
    contas = (
        (sum(c.sem_ncm for c in categorias), "sem NCM"),
        (sum(c.sem_cfop for c in categorias), "sem CFOP"),
        (sum(c.sem_cst_csosn for c in categorias), "sem CST/CSOSN"),
    )
    faltando = [f"{n} {nome}" for n, nome in contas if n]
    de = "Do produto ativo" if total == 1 else f"Dos {total} produtos ativos"
    if faltando:
        return Pendencia("produtos", "falta", titulo, f"{de}: {_lista(faltando)}.", "produtos")
    avisos: list[str] = []
    fora = sum(c.fora_do_regime for c in categorias)
    if fora:
        if crt == "4":
            regra = "o MEI usa CSOSN 102 ou 300 na NFC-e"
        elif do_simples(crt):
            regra = "o Simples usa CSOSN, de 3 números, como 102 ou 500"
        else:
            regra = "o regime normal usa CST, de 2 números, como 00 ou 60"
        avisos.append(f"{fora} com CST/CSOSN que não combina com o regime ({regra})")
    cfop = sum(c.cfop_fora_da_lista for c in categorias)
    if cfop:
        avisos.append(f"{cfop} com CFOP fora da lista que a NFC-e aceita (confira com o contador)")
    if avisos:
        return Pendencia("produtos", "atencao", titulo, f"{de}: {'; '.join(avisos)}.", "produtos")
    todos = "O produto ativo tem" if total == 1 else f"Os {total} produtos ativos têm"
    return Pendencia("produtos", "ok", titulo, f"{todos} NCM, CFOP e CST/CSOSN.", "produtos")


def pendencias(sessao: Session, agora: datetime | None = None) -> list[Pendencia]:
    """A lista "o que falta para emitir", na ordem em que o dono resolve."""
    momento = agora or datetime.now(UTC)
    loja = configuracoes.ler_loja(sessao)
    empresa = ler_empresa(sessao)
    itens = [_pendencia_da_loja(loja)]

    if empresa.crt:
        itens.append(Pendencia("regime", "ok", "Regime tributário", CRTS[empresa.crt], "empresa"))
    else:
        itens.append(
            Pendencia(
                "regime",
                "falta",
                "Regime tributário",
                "Escolha o regime (o contador sabe qual é).",
                "empresa",
            )
        )

    titulo = "Código do município (IBGE)"
    uf_codigo = uf_do_codigo(empresa.codigo_municipio)
    if not empresa.codigo_municipio:
        itens.append(
            Pendencia("municipio", "falta", titulo, "Digite o código, de 7 números.", "empresa")
        )
    elif loja.uf and uf_codigo != loja.uf:
        itens.append(
            Pendencia(
                "municipio",
                "falta",
                titulo,
                f"O código {empresa.codigo_municipio} é de {uf_codigo or 'outro estado'}, mas o "
                f"estado da loja é {loja.uf}.",
                "empresa",
            )
        )
    else:
        itens.append(Pendencia("municipio", "ok", titulo, empresa.codigo_municipio, "empresa"))

    titulo = "Credenciamento na SEFAZ"
    if empresa.credenciada == "sim":
        itens.append(
            Pendencia(
                "credenciamento", "ok", titulo, "A empresa é credenciada para NFC-e.", "empresa"
            )
        )
    elif empresa.credenciada == "nao":
        itens.append(
            Pendencia(
                "credenciamento",
                "falta",
                titulo,
                "A empresa precisa se credenciar para emitir NFC-e na SEFAZ do estado "
                "(o contador faz o pedido).",
                "empresa",
            )
        )
    else:
        itens.append(
            Pendencia(
                "credenciamento",
                "atencao",
                titulo,
                "Pergunte ao contador se a empresa já é credenciada para emitir NFC-e.",
                "empresa",
            )
        )

    itens.append(
        _pendencia_do_certificado(certificado.situacao_gravada(sessao), loja.cnpj, momento)
    )

    for ambiente, situacao_sem in (("homologacao", "falta"), ("producao", "atencao")):
        csc = ler_csc(sessao, ambiente)
        titulo = "CSC de homologação (testes)" if ambiente == "homologacao" else "CSC de produção"
        faltam = [nome for ok, nome in ((csc.id, "o ID"), (csc.salvo, "o código")) if not ok]
        if faltam:
            detalhe = f"Falta {_lista(faltam)}."
            if ambiente == "producao":
                detalhe += " Ele só é usado quando a nota passar a valer de verdade."
            itens.append(Pendencia(f"csc_{ambiente}", situacao_sem, titulo, detalhe, "csc"))
        else:
            itens.append(
                Pendencia(f"csc_{ambiente}", "ok", titulo, f"ID {csc.id}, código guardado.", "csc")
            )

    titulo = "Numeração da NFC-e"
    numeracao = ler_numeracao(sessao)
    resumo = "; ".join(
        f"{n.caixa}: série {n.serie}, próxima nota nº {n.proximo_numero}" for n in numeracao
    )
    if numeracao_conferida(sessao):
        itens.append(Pendencia("numeracao", "ok", titulo, resumo + ".", "numeracao"))
    elif empresa.emite_hoje == "sim":
        itens.append(
            Pendencia(
                "numeracao",
                "atencao",
                titulo,
                "A loja já emite NFC-e por outro sistema: acerte a série e o próximo número para "
                f"não repetir nota ({resumo}).",
                "numeracao",
            )
        )
    else:
        itens.append(
            Pendencia(
                "numeracao",
                "atencao",
                titulo,
                f"Confira e salve a série e o próximo número ({resumo}).",
                "numeracao",
            )
        )

    itens.append(_pendencia_dos_produtos(resumo_por_categoria(sessao, empresa.crt), empresa.crt))

    contador = ler_contador(sessao)
    titulo = "Contato do contador"
    if contador.nome and (contador.telefone or contador.email):
        itens.append(Pendencia("contador", "ok", titulo, contador.nome, "contador"))
    else:
        itens.append(
            Pendencia(
                "contador",
                "atencao",
                titulo,
                "Anote o nome e o telefone ou e-mail: ele confere o regime, o CSC e os dados "
                "dos produtos.",
                "contador",
            )
        )
    return itens
