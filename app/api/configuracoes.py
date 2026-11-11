"""Configurações pela API: dados da loja, impressão do cupom e cópia de segurança. Só o gerente.

A impressão dos documentos do dia a dia (comprovante de venda, resumo do caixa) fica em
`app/api/impressao.py` e vale para qualquer operador.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import acesso, backup, config, configuracoes, cupom, db, impressao, impressoras, tempo
from app.models import Operador
from app.operadores import RegraError

router = APIRouter(tags=["configurações"], dependencies=[Depends(acesso.exigir_gerente)])


class LojaIO(BaseModel):
    nome_fantasia: str = ""
    razao_social: str = ""
    cnpj: str = ""
    ie: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    telefone: str = ""
    rodape: str = ""


class ImpressaoIn(BaseModel):
    impressora: str = ""
    colunas: int = 48
    acentos: str = "cp850"
    cortar: bool = True
    gaveta: bool = False
    quando: str = "perguntar"
    vias: int = 1


class ImpressaoOut(ImpressaoIn):
    confirmada: bool  # o gerente viu o teste sair no papel


class BackupIn(BaseModel):
    pasta_extra: str = ""
    manter: int = 30


class CopiaOut(BaseModel):
    arquivo: str
    dia: str
    feita_em: str
    tamanho: int


class BackupOut(BackupIn):
    pasta: str  # onde ficam as cópias neste computador
    copias: list[CopiaOut]
    extra_erro: str  # por que a última cópia na pasta extra falhou (vazio = não falhou)
    extra_em: str | None  # quando a pasta extra recebeu a última cópia


class Opcao(BaseModel):
    valor: str
    rotulo: str


class ImpressoraOut(BaseModel):
    nome: str
    padrao: bool


class ImpressorasOut(BaseModel):
    disponivel: bool
    motivo: str
    impressoras: list[ImpressoraOut]


class ConfiguracoesOut(BaseModel):
    loja: LojaIO
    impressao: ImpressaoOut
    backup: BackupOut
    ufs: list[str]
    colunas: list[int]
    acentos: list[Opcao]
    quando: list[Opcao]


def _copia_out(copia: backup.Copia) -> CopiaOut:
    return CopiaOut(
        arquivo=copia.arquivo.name,
        dia=copia.dia.isoformat(),
        feita_em=copia.feita_em.isoformat(timespec="seconds"),
        tamanho=copia.tamanho,
    )


def _backup_out(sessao: Session) -> BackupOut:
    opcoes = configuracoes.ler_backup(sessao)
    return BackupOut(
        pasta_extra=opcoes.pasta_extra,
        manter=opcoes.manter,
        pasta=str(backup.pasta()),
        copias=[_copia_out(c) for c in backup.listar()[:10]],
        extra_erro=configuracoes.ler_valor(sessao, "backup.extra_erro"),
        extra_em=configuracoes.ler_valor(sessao, "backup.extra_em") or None,
    )


def _impressoras_out() -> ImpressorasOut:
    pode, motivo = impressoras.disponivel()
    lista = impressoras.listar() if pode else []
    if pode and not lista:
        motivo = "O Windows não tem nenhuma impressora instalada."
    return ImpressorasOut(
        disponivel=pode,
        motivo=motivo,
        impressoras=[ImpressoraOut(nome=i.nome, padrao=i.padrao) for i in lista],
    )


@router.get("/configuracoes", response_model=ConfiguracoesOut)
def ver(sessao: Session = Depends(db.sessao)) -> ConfiguracoesOut:
    return ConfiguracoesOut(
        loja=LojaIO(**asdict(configuracoes.ler_loja(sessao))),
        impressao=ImpressaoOut(**asdict(configuracoes.ler_impressao(sessao))),
        backup=_backup_out(sessao),
        ufs=list(configuracoes.UFS),
        colunas=list(configuracoes.COLUNAS),
        acentos=[Opcao(valor=v, rotulo=r) for v, r in configuracoes.ACENTOS.items()],
        quando=[Opcao(valor=v, rotulo=r) for v, r in configuracoes.QUANDO.items()],
    )


@router.put("/configuracoes/loja", response_model=LojaIO)
def gravar_loja(dados: LojaIO, sessao: Session = Depends(db.sessao)) -> LojaIO:
    loja = configuracoes.gravar_loja(sessao, configuracoes.Loja(**dados.model_dump()))
    sessao.commit()
    return LojaIO(**asdict(loja))


@router.get("/impressoras", response_model=ImpressorasOut)
def listar_impressoras() -> ImpressorasOut:
    return _impressoras_out()


@router.put("/configuracoes/impressao", response_model=ImpressaoOut)
def gravar_impressao(dados: ImpressaoIn, sessao: Session = Depends(db.sessao)) -> ImpressaoOut:
    nome = dados.impressora.strip()
    if nome:
        pode, motivo = impressoras.disponivel()
        if not pode:
            raise RegraError(motivo, status=409)
        if nome not in {i.nome for i in impressoras.listar()}:
            raise RegraError(
                f"A impressora “{nome}” não está instalada neste computador. Escolha na lista."
            )
    nova = configuracoes.gravar_impressao(sessao, configuracoes.Impressao(**dados.model_dump()))
    sessao.commit()
    return ImpressaoOut(**asdict(nova))


class TesteOut(BaseModel):
    impressora: str
    linhas: list[str]  # o que foi mandado, para comparar com o papel


@router.post("/impressao/teste", response_model=TesteOut)
def imprimir_teste(
    sessao: Session = Depends(db.sessao), gerente: Operador = Depends(acesso.exigir_gerente)
) -> TesteOut:
    """Manda a página de teste. A resposta só diz que o Windows aceitou o trabalho na fila:
    quem confirma que saiu no papel é o gerente (rota abaixo)."""
    opcoes = configuracoes.ler_impressao(sessao)
    pagina = cupom.pagina_de_teste(configuracoes.ler_loja(sessao), opcoes, versao=config.VERSAO)
    impressao.imprimir(sessao, pagina, vias=1)
    return TesteOut(impressora=opcoes.impressora, linhas=[linha.texto for linha in pagina.linhas])


class ConfirmarIn(BaseModel):
    saiu: bool


@router.post("/impressao/teste/confirmar", response_model=ImpressaoOut)
def confirmar_teste(dados: ConfirmarIn, sessao: Session = Depends(db.sessao)) -> ImpressaoOut:
    nova = configuracoes.confirmar_impressao(sessao, dados.saiu)
    sessao.commit()
    return ImpressaoOut(**asdict(nova))


@router.put("/configuracoes/backup", response_model=BackupOut)
def gravar_backup(dados: BackupIn, sessao: Session = Depends(db.sessao)) -> BackupOut:
    configuracoes.gravar_backup(sessao, configuracoes.Backup(**dados.model_dump()))
    sessao.commit()
    return _backup_out(sessao)


class CopiaFeitaOut(BaseModel):
    copia: CopiaOut
    apagadas: int
    extra_pasta: str
    extra_erro: str
    backup: BackupOut


@router.post("/backup", response_model=CopiaFeitaOut, status_code=201)
def fazer_copia(
    sessao: Session = Depends(db.sessao), gerente: Operador = Depends(acesso.exigir_gerente)
) -> CopiaFeitaOut:
    """Faz agora a cópia de segurança de hoje (substitui a que já houver do dia)."""
    feito = backup.copiar(sessao, f"pedido de {gerente.login} às {tempo.agora():%H:%M}")
    return CopiaFeitaOut(
        copia=_copia_out(feito.copia),
        apagadas=feito.apagadas,
        extra_pasta=feito.extra_pasta,
        extra_erro=feito.extra_erro,
        backup=_backup_out(sessao),
    )
