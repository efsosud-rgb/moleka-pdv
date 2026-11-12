"""Dados fiscais da NFC-e pela API (Configurações → Fiscal). Só o gerente.

Esta versão não emite NFC-e: aqui o dono deixa prontos o regime, o município, o certificado
digital A1, o CSC, a numeração, o contador e os dados fiscais dos produtos.

Cuidados com os segredos (senha do certificado e código do CSC):
- nunca voltam nas respostas (o CSC volta só com os 4 últimos caracteres);
- os campos que os trazem são lidos sem a validação automática do Pydantic, que repetiria o
  valor recusado na mensagem de erro; a conferência é feita aqui, com mensagem própria.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import acesso, certificado, configuracoes, dados_fiscais, db
from app.models import Operador
from app.operadores import RegraError
from app.tempo import FUSO

router = APIRouter(tags=["fiscal"], dependencies=[Depends(acesso.exigir_gerente)])


class Opcao(BaseModel):
    valor: str
    rotulo: str


class LojaResumoOut(BaseModel):
    nome_fantasia: str
    razao_social: str
    cnpj: str
    ie: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    uf: str
    cep: str


class EmpresaIO(BaseModel):
    crt: str = ""
    codigo_municipio: str = ""
    inscricao_municipal: str = ""
    cnae: str = ""
    credenciada: str = ""
    emite_hoje: str = ""
    emite_hoje_detalhe: str = ""


class ContadorIO(BaseModel):
    nome: str = ""
    crc: str = ""
    telefone: str = ""
    email: str = ""
    documento: str = ""
    observacoes: str = ""


class CertificadoOut(BaseModel):
    titular: str
    cnpj: str
    emissor: str
    inicio: str  # ISO, no horário da loja
    fim: str
    instalado_em: str
    arquivo: str  # nome do arquivo que o gerente escolheu
    dias_restantes: int
    vencido: bool
    tem_arquivo: bool
    tem_senha: bool
    cnpj_confere: bool | None  # com o CNPJ da aba Loja (None = a loja ainda não tem CNPJ)


class CscOut(BaseModel):
    ambiente: str
    id: str
    salvo: bool
    final: str


class NumeracaoOut(BaseModel):
    caixa_id: int
    caixa: str
    serie: int
    proximo_numero: int
    ultima_registrada: int | None


class CategoriaOut(BaseModel):
    nome: str | None  # None = produtos sem categoria
    produtos: int
    sem_ncm: int
    sem_cfop: int
    sem_cst_csosn: int
    fora_do_regime: int
    cfop_fora_da_lista: int
    completa: bool


class PendenciaOut(BaseModel):
    chave: str
    situacao: str  # ok, falta, atencao
    titulo: str
    detalhe: str
    onde: str


class FiscalOut(BaseModel):
    aviso: str  # "esta versão ainda não emite NFC-e"
    ambiente: str
    ambiente_rotulo: str
    loja: LojaResumoOut
    empresa: EmpresaIO
    certificado: CertificadoOut | None
    csc: list[CscOut]
    numeracao: list[NumeracaoOut]
    numeracao_conferida: bool
    contador: ContadorIO
    categorias: list[CategoriaOut]
    pendencias: list[PendenciaOut]
    faltam: int  # quantos itens estão como "falta"
    crts: list[Opcao]
    respostas: list[Opcao]
    origens: list[Opcao]
    cfops: list[Opcao]


def _opcoes(itens: dict[str, str]) -> list[Opcao]:
    return [Opcao(valor=v, rotulo=r) for v, r in itens.items()]


def _certificado_out(sessao: Session) -> CertificadoOut | None:
    situacao = certificado.situacao_gravada(sessao)
    if situacao is None:
        return None
    loja = configuracoes.ler_loja(sessao).cnpj
    return CertificadoOut(
        titular=situacao.titular,
        cnpj=situacao.cnpj,
        emissor=situacao.emissor,
        inicio=situacao.inicio.astimezone(FUSO).isoformat(timespec="seconds"),
        fim=situacao.fim.astimezone(FUSO).isoformat(timespec="seconds"),
        instalado_em=situacao.instalado_em.astimezone(FUSO).isoformat(timespec="seconds"),
        arquivo=situacao.arquivo,
        dias_restantes=situacao.dias_restantes(),
        vencido=situacao.vencido(),
        tem_arquivo=situacao.tem_arquivo,
        tem_senha=situacao.tem_senha,
        cnpj_confere=None if not loja else loja[:8] == situacao.cnpj[:8],
    )


def montar(sessao: Session) -> FiscalOut:
    loja = configuracoes.ler_loja(sessao)
    empresa = dados_fiscais.ler_empresa(sessao)
    pendencias = dados_fiscais.pendencias(sessao)
    return FiscalOut(
        aviso=dados_fiscais.AVISO,
        ambiente=dados_fiscais.AMBIENTE,
        ambiente_rotulo=dados_fiscais.AMBIENTE_ROTULO,
        loja=LojaResumoOut(
            nome_fantasia=loja.nome_fantasia,
            razao_social=loja.razao_social,
            cnpj=loja.cnpj,
            ie=loja.ie,
            logradouro=loja.logradouro,
            numero=loja.numero,
            bairro=loja.bairro,
            cidade=loja.cidade,
            uf=loja.uf,
            cep=loja.cep,
        ),
        empresa=EmpresaIO(**asdict(empresa)),
        certificado=_certificado_out(sessao),
        csc=[CscOut(**asdict(dados_fiscais.ler_csc(sessao, a))) for a in dados_fiscais.AMBIENTES],
        numeracao=[NumeracaoOut(**asdict(n)) for n in dados_fiscais.ler_numeracao(sessao)],
        numeracao_conferida=dados_fiscais.numeracao_conferida(sessao),
        contador=ContadorIO(**asdict(dados_fiscais.ler_contador(sessao))),
        categorias=[
            CategoriaOut(**asdict(c), completa=c.completa)
            for c in dados_fiscais.resumo_por_categoria(sessao, empresa.crt)
        ],
        pendencias=[PendenciaOut(**asdict(p)) for p in pendencias],
        faltam=sum(1 for p in pendencias if p.situacao == "falta"),
        crts=_opcoes(dados_fiscais.CRTS),
        respostas=_opcoes(dados_fiscais.RESPOSTAS),
        origens=_opcoes(dados_fiscais.ORIGENS),
        cfops=_opcoes(dados_fiscais.CFOPS_DA_NFCE),
    )


@router.get("/fiscal", response_model=FiscalOut)
def ver(sessao: Session = Depends(db.sessao)) -> FiscalOut:
    return montar(sessao)


@router.put("/fiscal/empresa", response_model=FiscalOut)
def gravar_empresa(
    dados: EmpresaIO,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FiscalOut:
    dados_fiscais.gravar_empresa(sessao, dados_fiscais.Empresa(**dados.model_dump()), gerente.login)
    sessao.commit()
    return montar(sessao)


@router.put("/fiscal/contador", response_model=FiscalOut)
def gravar_contador(dados: ContadorIO, sessao: Session = Depends(db.sessao)) -> FiscalOut:
    dados_fiscais.gravar_contador(sessao, dados_fiscais.Contador(**dados.model_dump()))
    sessao.commit()
    return montar(sessao)


def _texto_secreto(valor: Any, nome: str) -> str:
    """Lê um campo que pode trazer segredo, sem nunca repetir o valor na mensagem."""
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise RegraError(f"{nome}: formato inválido.")
    return valor


class CscIn(BaseModel):
    id_homologacao: str = ""
    codigo_homologacao: Any = ""  # vazio = manter o código guardado
    apagar_homologacao: bool = False
    id_producao: str = ""
    codigo_producao: Any = ""
    apagar_producao: bool = False


@router.put("/fiscal/csc", response_model=FiscalOut)
def gravar_csc(
    dados: CscIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FiscalOut:
    pedidos = [
        (
            "homologacao",
            dados.id_homologacao,
            _texto_secreto(dados.codigo_homologacao, "Código CSC de homologação"),
            dados.apagar_homologacao,
        ),
        (
            "producao",
            dados.id_producao,
            _texto_secreto(dados.codigo_producao, "Código CSC de produção"),
            dados.apagar_producao,
        ),
    ]
    # Confere os dois antes de gravar qualquer um: nada fica pela metade.
    for ambiente, identificador, codigo, _apagar in pedidos:
        dados_fiscais.conferir_csc(ambiente, identificador, codigo)
    for ambiente, identificador, codigo, apagar in pedidos:
        dados_fiscais.gravar_csc(sessao, ambiente, identificador, codigo, apagar, gerente.login)
    sessao.commit()
    return montar(sessao)


class NumeracaoIn(BaseModel):
    caixa_id: int
    serie: int
    proximo_numero: int


@router.put("/fiscal/numeracao", response_model=FiscalOut)
def gravar_numeracao(
    dados: NumeracaoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FiscalOut:
    dados_fiscais.gravar_numeracao(
        sessao, dados.caixa_id, dados.serie, dados.proximo_numero, gerente.login
    )
    sessao.commit()
    return montar(sessao)


class CertificadoIn(BaseModel):
    nome_arquivo: str = ""
    conteudo_base64: Any = ""
    senha: Any = ""


def _conteudo(texto: str) -> bytes:
    bruto = texto.split(",", 1)[1] if texto.startswith("data:") else texto
    if len(bruto) > certificado.LIMITE_BYTES * 4 // 3 + 8:
        raise RegraError(
            "Este arquivo é grande demais para ser um certificado A1. "
            "Confira se escolheu o arquivo certo (termina em .pfx ou .p12)."
        )
    try:
        return base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise RegraError("O arquivo do certificado não chegou inteiro. Escolha de novo.") from erro


@router.post("/fiscal/certificado", response_model=FiscalOut, status_code=201)
def instalar_certificado(
    dados: CertificadoIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FiscalOut:
    conteudo = _conteudo(_texto_secreto(dados.conteudo_base64, "Arquivo do certificado"))
    senha = _texto_secreto(dados.senha, "Senha do certificado")
    if len(senha) > 200:
        raise RegraError("Senha do certificado grande demais.")
    certificado.instalar(sessao, conteudo, senha, dados.nome_arquivo, gerente.login)
    sessao.commit()
    return montar(sessao)


class ConferenciaOut(BaseModel):
    titular: str
    cnpj: str
    fim: str
    mensagem: str


@router.post("/fiscal/certificado/conferir", response_model=ConferenciaOut)
def conferir_certificado(sessao: Session = Depends(db.sessao)) -> ConferenciaOut:
    """Abre de novo o certificado guardado com a senha guardada."""
    lido = certificado.conferir(sessao)
    return ConferenciaOut(
        titular=lido.titular,
        cnpj=lido.cnpj,
        fim=lido.fim.astimezone(FUSO).isoformat(timespec="seconds"),
        mensagem=(
            f"O certificado abriu com a senha guardada: válido até {certificado.data_br(lido.fim)}."
        ),
    )


class RemoverIn(BaseModel):
    confirmo: bool = False


@router.post("/fiscal/certificado/remover", response_model=FiscalOut)
def remover_certificado(
    dados: RemoverIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> FiscalOut:
    if not dados.confirmo:
        raise RegraError("Confirme que quer remover o certificado deste computador.")
    certificado.remover(sessao, gerente.login)
    sessao.commit()
    return montar(sessao)


class CategoriaIn(BaseModel):
    categoria: str | None = None  # None ou vazio = produtos sem categoria
    ncm: str | None = None
    cest: str | None = None
    cfop: str | None = None
    cst_csosn: str | None = None
    origem: str | None = None  # None ou vazio = não mexer
    sobrescrever: bool = False


class PreenchidoOut(BaseModel):
    alterados: int
    fiscal: FiscalOut


@router.post("/fiscal/produtos/categoria", response_model=PreenchidoOut)
def preencher_categoria(
    dados: CategoriaIn,
    sessao: Session = Depends(db.sessao),
    gerente: Operador = Depends(acesso.exigir_gerente),
) -> PreenchidoOut:
    alterados = dados_fiscais.preencher_categoria(
        sessao,
        dados.categoria,
        dados_fiscais.Preenchimento(
            ncm=dados.ncm,
            cest=dados.cest,
            cfop=dados.cfop,
            cst_csosn=dados.cst_csosn,
            origem=dados.origem,
        ),
        dados.sobrescrever,
        gerente.login,
    )
    sessao.commit()
    return PreenchidoOut(alterados=alterados, fiscal=montar(sessao))
