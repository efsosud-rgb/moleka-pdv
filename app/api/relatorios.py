"""Relatório de vendas por período pela API. Só o gerente.

Sem dado, a resposta traz `None` no valor e o motivo em texto: a tela mostra "—" e o motivo.
As regras do relatório estão em app/relatorios.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import acesso, db, dinheiro, relatorios, tempo
from app.caixa import ROTULOS as ROTULOS_DAS_FORMAS
from app.models import FormaPagamento, Operador
from app.operadores import RegraError

router = APIRouter(tags=["relatórios"], dependencies=[Depends(acesso.exigir_gerente)])

SEM_VENDAS = "sem vendas no período"
SEM_DOCUMENTO = (
    "o sistema ainda não emite NFC-e: nenhuma venda tem documento fiscal (o comprovante "
    "impresso não é fiscal)"
)
SITUACOES = {
    "finalizada": "Finalizada",
    "cancelada_depois": "Cancelada depois de finalizada",
    "cancelada_antes": "Cancelada antes de finalizar",
}
DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    """Sem datas, vale o dia de hoje (da loja)."""
    hoje = tempo.hoje()
    return inicio or hoje, fim or inicio or hoje


def percentual(parte: int, todo: int) -> str | None:
    """ "12,5%" — quanto `parte` representa de `todo`. None quando não há sobre o que calcular."""
    pct = dinheiro.porcentagem(parte, todo)
    return None if pct is None else f"{pct}%".replace(".", ",")


def nome_do_operador(sessao: Session, operador_id: int | None) -> str:
    if operador_id is None:
        return ""
    operador = sessao.get(Operador, operador_id)
    if operador is None:
        raise RegraError("Operador não encontrado.", status=404)
    return operador.nome


# ---------------------------------------------------------------- o relatório


class DiaOut(BaseModel):
    dia: date
    vendas: int
    faturamento_centavos: int | None  # None = nenhuma venda neste dia (só cancelamento)
    ticket_medio_centavos: int | None
    canceladas: int


class MesOut(BaseModel):
    mes: date  # o dia 1 do mês
    vendas: int
    faturamento_centavos: int | None  # None = nenhuma venda neste mês (só cancelamento)
    ticket_medio_centavos: int | None
    canceladas: int


class FormaOut(BaseModel):
    forma: FormaPagamento
    rotulo: str
    vendas: int  # vendas pagas (também) nesta forma
    recebido_centavos: int | None  # None = nenhuma venda nesta forma
    ajuste_centavos: int | None  # desconto (negativo) ou acréscimo (positivo) desta forma
    participacao: str | None  # do recebido sobre o faturamento
    motivo: str


class OperadorOut(BaseModel):
    operador_id: int
    nome: str
    vendas: int
    faturamento_centavos: int | None
    ticket_medio_centavos: int | None
    participacao: str | None
    desconto_gerente_centavos: int
    canceladas_antes: int
    canceladas_depois: int
    valor_cancelado_centavos: int


class DiaDaSemanaOut(BaseModel):
    dia_semana: int  # 0 = segunda ... 6 = domingo
    rotulo: str
    dias_no_periodo: int  # quantas segundas (terças...) o período tem
    vendas: int
    faturamento_centavos: int | None  # None = nenhuma venda neste dia da semana
    ticket_medio_centavos: int | None


class HoraOut(BaseModel):
    hora: int  # 0 a 23, horário da loja
    vendas: int
    faturamento_centavos: int
    ticket_medio_centavos: int | None


class HorarioOut(BaseModel):
    dia_semana: int  # 0 = segunda ... 6 = domingo
    hora: int  # 0 a 23, horário da loja
    vendas: int
    faturamento_centavos: int


class ProdutoOut(BaseModel):
    produto_id: int
    codigo: str
    descricao: str
    unidade: str
    quantidade: Decimal
    vendas: int  # em quantas vendas apareceu
    faturamento_centavos: int
    participacao: str | None
    acumulado: str | None  # participação somada até este produto (curva ABC)
    classe: str


class ClasseOut(BaseModel):
    classe: str
    produtos: int
    faturamento_centavos: int
    participacao: str | None


class RelatorioVendasOut(BaseModel):
    inicio: date
    fim: date
    operador_id: int | None
    operador_nome: str  # "" = todos os operadores
    vendas: int
    faturamento_centavos: int | None  # None = sem vendas (ver `motivo`)
    ticket_medio_centavos: int | None
    itens_centavos: int | None  # valor dos itens, antes de qualquer desconto
    descontos_centavos: int | None  # desconto do gerente + descontos das formas de pagamento
    desconto_gerente_centavos: int | None
    descontos_formas_centavos: int | None
    acrescimos_formas_centavos: int | None
    sem_documento_fiscal: int  # vendas
    sem_documento_fiscal_centavos: int | None
    marcadas_para_nfce: int
    canceladas: int  # antes + depois de finalizar
    canceladas_centavos: int
    canceladas_antes: int
    canceladas_antes_centavos: int
    canceladas_depois: int
    canceladas_depois_centavos: int
    dias: list[DiaOut]  # só os dias com venda ou cancelamento
    meses: list[MesOut]  # só os meses com venda ou cancelamento
    formas: list[FormaOut]
    operadores: list[OperadorOut]
    horarios: list[HorarioOut]  # só os pares (dia da semana, hora) com venda
    por_dia_da_semana: list[DiaDaSemanaOut]  # sempre os 7, de segunda a domingo
    por_hora: list[HoraOut]  # só as horas com venda
    produtos: list[ProdutoOut]
    classes: list[ClasseOut]
    motivo: str  # por que não há número, quando não há
    motivo_fiscal: str


def montar(sessao: Session, inicio: date, fim: date, operador_id: int | None) -> RelatorioVendasOut:
    nome = nome_do_operador(sessao, operador_id)
    r = relatorios.vendas_do_periodo(sessao, inicio, fim, operador_id)
    fat = r.total.faturamento
    vendeu = r.total.vendas > 0

    def se_vendeu(valor: int) -> int | None:
        return valor if vendeu else None

    acumulado = 0
    produtos = []
    for p in r.produtos:
        acumulado += p.faturamento
        produtos.append(
            ProdutoOut(
                produto_id=p.produto_id,
                codigo=p.codigo,
                descricao=p.descricao,
                unidade=p.unidade,
                quantidade=p.quantidade,
                vendas=p.vendas,
                faturamento_centavos=p.faturamento,
                participacao=percentual(p.faturamento, fat),
                acumulado=percentual(acumulado, fat),
                classe=p.classe,
            )
        )
    classes = []
    for letra in ("A", "B", "C"):
        da_classe = [p for p in r.produtos if p.classe == letra]
        if da_classe:
            soma = sum(p.faturamento for p in da_classe)
            classes.append(
                ClasseOut(
                    classe=letra,
                    produtos=len(da_classe),
                    faturamento_centavos=soma,
                    participacao=percentual(soma, fat),
                )
            )
    return RelatorioVendasOut(
        inicio=inicio,
        fim=fim,
        operador_id=operador_id,
        operador_nome=nome,
        vendas=r.total.vendas,
        faturamento_centavos=se_vendeu(fat),
        ticket_medio_centavos=r.total.ticket_medio,
        itens_centavos=se_vendeu(r.itens),
        descontos_centavos=se_vendeu(r.desconto_gerente + r.descontos_formas),
        desconto_gerente_centavos=se_vendeu(r.desconto_gerente),
        descontos_formas_centavos=se_vendeu(r.descontos_formas),
        acrescimos_formas_centavos=se_vendeu(r.acrescimos_formas),
        sem_documento_fiscal=r.total.vendas,
        sem_documento_fiscal_centavos=se_vendeu(fat),
        marcadas_para_nfce=r.marcadas_para_nfce,
        canceladas=r.cancelamentos.antes + r.cancelamentos.depois,
        canceladas_centavos=r.cancelamentos.valor_antes + r.cancelamentos.valor_depois,
        canceladas_antes=r.cancelamentos.antes,
        canceladas_antes_centavos=r.cancelamentos.valor_antes,
        canceladas_depois=r.cancelamentos.depois,
        canceladas_depois_centavos=r.cancelamentos.valor_depois,
        dias=[
            DiaOut(
                dia=d.dia,
                vendas=d.soma.vendas,
                faturamento_centavos=d.soma.faturamento if d.soma.vendas else None,
                ticket_medio_centavos=d.soma.ticket_medio,
                canceladas=d.canceladas,
            )
            for d in r.por_dia
        ],
        meses=[
            MesOut(
                mes=m.mes,
                vendas=m.soma.vendas,
                faturamento_centavos=m.soma.faturamento if m.soma.vendas else None,
                ticket_medio_centavos=m.soma.ticket_medio,
                canceladas=m.canceladas,
            )
            for m in r.por_mes
        ],
        formas=[
            FormaOut(
                forma=f.forma,
                rotulo=ROTULOS_DAS_FORMAS[f.forma],
                vendas=f.vendas,
                recebido_centavos=f.recebido if f.vendas else None,
                ajuste_centavos=f.ajuste if f.vendas else None,
                participacao=percentual(f.recebido, fat) if f.vendas else None,
                motivo="" if f.vendas else "nenhuma venda nesta forma",
            )
            for f in r.por_forma
        ],
        operadores=[
            OperadorOut(
                operador_id=o.operador_id,
                nome=o.nome,
                vendas=o.soma.vendas,
                faturamento_centavos=o.soma.faturamento if o.soma.vendas else None,
                ticket_medio_centavos=o.soma.ticket_medio,
                participacao=percentual(o.soma.faturamento, fat) if o.soma.vendas else None,
                desconto_gerente_centavos=o.desconto_gerente,
                canceladas_antes=o.canceladas_antes,
                canceladas_depois=o.canceladas_depois,
                valor_cancelado_centavos=o.valor_cancelado,
            )
            for o in r.por_operador
        ],
        horarios=[
            HorarioOut(
                dia_semana=dia_semana,
                hora=hora,
                vendas=soma.vendas,
                faturamento_centavos=soma.faturamento,
            )
            for (dia_semana, hora), soma in sorted(r.por_horario.items())
        ],
        por_dia_da_semana=[
            DiaDaSemanaOut(
                dia_semana=dia_semana,
                rotulo=DIAS_DA_SEMANA[dia_semana],
                dias_no_periodo=quantos,
                vendas=soma.vendas,
                faturamento_centavos=soma.faturamento if soma.vendas else None,
                ticket_medio_centavos=soma.ticket_medio,
            )
            for dia_semana, (soma, quantos) in enumerate(
                zip(
                    relatorios.somar_por_dia_da_semana(r.por_horario),
                    relatorios.dias_da_semana_no_periodo(inicio, fim),
                    strict=True,
                )
            )
        ],
        por_hora=[
            HoraOut(
                hora=hora,
                vendas=soma.vendas,
                faturamento_centavos=soma.faturamento,
                ticket_medio_centavos=soma.ticket_medio,
            )
            for hora, soma in relatorios.somar_por_hora(r.por_horario).items()
        ],
        produtos=produtos,
        classes=classes,
        motivo="" if vendeu else SEM_VENDAS,
        motivo_fiscal=SEM_DOCUMENTO,
    )


@router.get("/relatorios/vendas", response_model=RelatorioVendasOut)
def relatorio_de_vendas(
    inicio: date | None = None,
    fim: date | None = None,
    operador_id: int | None = None,
    sessao: Session = Depends(db.sessao),
) -> RelatorioVendasOut:
    inicio, fim = periodo(inicio, fim)
    return montar(sessao, inicio, fim, operador_id)


# ---------------------------------------------------------------- a lista das vendas


class VendaDaListaOut(BaseModel):
    id: int
    numero: int
    situacao: str
    situacao_rotulo: str
    momento: str  # finalização, ou cancelamento da venda que não chegou a ser finalizada
    finalizada_em: str | None  # horário da loja, com fuso
    cancelada_em: str | None
    operador: str
    cliente: str
    formas: list[str]
    total_centavos: int
    quer_nfce: bool | None
    motivo_cancelamento: str
    cancelada_por: str


class ListaDeVendasOut(BaseModel):
    inicio: date
    fim: date
    situacao: str
    vendas: list[VendaDaListaOut]
    finalizadas: int
    finalizadas_centavos: int | None
    canceladas: int
    motivo: str


def montar_lista(
    sessao: Session, inicio: date, fim: date, operador_id: int | None, situacao: str
) -> ListaDeVendasOut:
    nome_do_operador(sessao, operador_id)
    lista = relatorios.lista_de_vendas(sessao, inicio, fim, operador_id, situacao)
    finalizadas = [v for v in lista if v.situacao == "finalizada"]
    vazia = {
        "": "nenhuma venda nem cancelamento no período",
        "finalizadas": SEM_VENDAS,
        "canceladas": "nenhuma venda cancelada no período",
    }[situacao]
    return ListaDeVendasOut(
        inicio=inicio,
        fim=fim,
        situacao=situacao,
        vendas=[
            VendaDaListaOut(
                id=v.id,
                numero=v.numero,
                situacao=v.situacao,
                situacao_rotulo=SITUACOES[v.situacao],
                momento=tempo.iso_na_loja(v.momento) or "",
                finalizada_em=tempo.iso_na_loja(v.finalizada_em),
                cancelada_em=tempo.iso_na_loja(v.cancelada_em),
                operador=v.operador,
                cliente=v.cliente,
                formas=[ROTULOS_DAS_FORMAS[f] for f in v.formas],
                total_centavos=v.total,
                quer_nfce=v.quer_nfce,
                motivo_cancelamento=v.motivo_cancelamento,
                cancelada_por=v.cancelada_por,
            )
            for v in lista
        ],
        finalizadas=len(finalizadas),
        finalizadas_centavos=sum(v.total for v in finalizadas) if finalizadas else None,
        canceladas=len(lista) - len(finalizadas),
        motivo="" if lista else vazia,
    )


@router.get("/relatorios/vendas/lista", response_model=ListaDeVendasOut)
def lista_de_vendas(
    inicio: date | None = None,
    fim: date | None = None,
    operador_id: int | None = None,
    situacao: str = "",
    sessao: Session = Depends(db.sessao),
) -> ListaDeVendasOut:
    inicio, fim = periodo(inicio, fim)
    return montar_lista(sessao, inicio, fim, operador_id, situacao or "")
