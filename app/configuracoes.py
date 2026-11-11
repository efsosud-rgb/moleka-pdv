"""Configurações da loja: dados da loja, impressão do cupom e cópia de segurança.

Ficam na tabela `configuracao`, uma linha por chave, sempre em texto. Chave sem linha no banco
vale o padrão. Segredos (senha do certificado, tokens) NÃO entram aqui.

- Dados da loja: saem no cabeçalho do cupom e, depois, servem para a NFC-e. Nada é obrigatório:
  o cupom imprime o que estiver preenchido.
- Impressão do cupom: a fila do Windows da impressora térmica e como ela imprime. Mudar a
  impressora, as colunas ou os acentos desfaz a confirmação do teste (é preciso testar de novo).
- Cópia de segurança: a pasta extra (pendrive, pasta da nuvem) e quantas cópias diárias guardar.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy.orm import Session

from app import config, documentos
from app.models import Configuracao
from app.operadores import RegraError

log = logging.getLogger("moleka.configuracoes")

UFS = ("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO").split()
COLUNAS = (48, 42, 32)
# Como as letras com acento vão para a impressora. A ELGIN i9 usa os comandos ESC/POS da Epson:
# o número é o da tabela "ESC t n" (página de código).
ACENTOS: dict[str, str] = {
    "cp850": "CP850 (mais comum)",
    "cp860": "CP860 (português)",
    "cp1252": "Windows-1252",
    "sem": "Sem acento (á vira a)",
}
QUANDO: dict[str, str] = {
    "perguntar": "Oferecer o botão de imprimir depois de cada venda",
    "sempre": "Imprimir sozinho em toda venda",
    "nunca": "Não imprimir comprovante de venda",
}
VIAS = (1, 2)
COPIAS_MINIMO, COPIAS_MAXIMO = 7, 365


# ---------------------------------------------------------------- leitura e gravação


def ler_valor(sessao: Session, chave: str) -> str:
    item = sessao.get(Configuracao, chave)
    return item.valor or "" if item else ""


def gravar_valor(sessao: Session, chave: str, valor: str) -> None:
    item = sessao.get(Configuracao, chave)
    if item is None:
        sessao.add(Configuracao(chave=chave, valor=valor or None))
    else:
        item.valor = valor or None


def _texto(valor: str | None, maximo: int, nome: str) -> str:
    limpo = " ".join((valor or "").split())
    if len(limpo) > maximo:
        raise RegraError(f"{nome}: no máximo {maximo} caracteres.")
    return limpo


# ---------------------------------------------------------------- dados da loja


@dataclass(frozen=True)
class Loja:
    nome_fantasia: str = ""
    razao_social: str = ""
    cnpj: str = ""  # só os 14 caracteres, sem pontuação
    ie: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""  # só os 8 dígitos
    telefone: str = ""
    rodape: str = ""  # mensagem no fim do cupom

    @property
    def preenchida(self) -> bool:
        return bool(self.nome_fantasia or self.razao_social)


_CAMPOS_DA_LOJA = (
    "nome_fantasia razao_social cnpj ie logradouro numero bairro cidade uf cep telefone rodape"
).split()


def ler_loja(sessao: Session) -> Loja:
    return Loja(**{campo: ler_valor(sessao, f"loja.{campo}") for campo in _CAMPOS_DA_LOJA})


def gravar_loja(sessao: Session, dados: Loja) -> Loja:
    cnpj = documentos.limpar(dados.cnpj)
    if cnpj and not (len(cnpj) == 14 and documentos.cnpj_valido(cnpj)):
        raise RegraError("CNPJ inválido. Confira os números (são 14, com os dois do final).")
    cep = "".join(c for c in (dados.cep or "") if c.isdigit())
    if cep and len(cep) != 8:
        raise RegraError("CEP inválido: são 8 números.")
    uf = (dados.uf or "").strip().upper()
    if uf and uf not in UFS:
        raise RegraError("Estado (UF) inválido. Escolha na lista.")
    ie = _texto(dados.ie, 20, "Inscrição estadual").upper()
    if ie and ie != "ISENTO" and not all(c.isdigit() or c in ".-/" for c in ie):
        raise RegraError('Inscrição estadual: só números (ou a palavra "ISENTO").')
    loja = Loja(
        nome_fantasia=_texto(dados.nome_fantasia, 60, "Nome da loja"),
        razao_social=_texto(dados.razao_social, 120, "Razão social"),
        cnpj=cnpj,
        ie=ie,
        logradouro=_texto(dados.logradouro, 60, "Endereço"),
        numero=_texto(dados.numero, 10, "Número"),
        bairro=_texto(dados.bairro, 40, "Bairro"),
        cidade=_texto(dados.cidade, 40, "Cidade"),
        uf=uf,
        cep=cep,
        telefone=_texto(dados.telefone, 20, "Telefone"),
        rodape=_texto(dados.rodape, 120, "Mensagem do cupom"),
    )
    for campo in _CAMPOS_DA_LOJA:
        gravar_valor(sessao, f"loja.{campo}", getattr(loja, campo))
    return loja


# ---------------------------------------------------------------- impressão do cupom


@dataclass(frozen=True)
class Impressao:
    impressora: str = ""  # nome da fila do Windows; vazio = nenhuma
    colunas: int = 48
    acentos: str = "cp850"
    cortar: bool = True
    gaveta: bool = False  # abrir a gaveta na venda com dinheiro
    quando: str = "perguntar"
    vias: int = 1
    # O gerente viu o teste sair no papel. "Configurada" não é "testada": só isto diz que imprime.
    confirmada: bool = False


def _inteiro(texto: str, padrao: int, permitidos: tuple[int, ...]) -> int:
    try:
        valor = int(texto)
    except ValueError:
        return padrao
    return valor if valor in permitidos else padrao


def ler_impressao(sessao: Session) -> Impressao:
    padrao = Impressao()
    acentos = ler_valor(sessao, "impressao.cupom_acentos")
    quando = ler_valor(sessao, "impressao.cupom_quando")
    cortar = ler_valor(sessao, "impressao.cupom_cortar")
    return Impressao(
        impressora=ler_valor(sessao, "impressao.cupom"),
        colunas=_inteiro(ler_valor(sessao, "impressao.cupom_colunas"), padrao.colunas, COLUNAS),
        acentos=acentos if acentos in ACENTOS else padrao.acentos,
        cortar=cortar != "0",
        gaveta=ler_valor(sessao, "impressao.cupom_gaveta") == "1",
        quando=quando if quando in QUANDO else padrao.quando,
        vias=_inteiro(ler_valor(sessao, "impressao.cupom_vias"), padrao.vias, VIAS),
        confirmada=ler_valor(sessao, "impressao.cupom_confirmada") == "1",
    )


def gravar_impressao(sessao: Session, dados: Impressao) -> Impressao:
    """Grava as opções. A confirmação do teste não vem de quem chama: é mantida só se a
    impressora, as colunas e os acentos continuarem os mesmos."""
    if dados.colunas not in COLUNAS:
        raise RegraError("Colunas: escolha 48, 42 ou 32.")
    if dados.acentos not in ACENTOS:
        raise RegraError("Acentos: escolha uma das opções da lista.")
    if dados.quando not in QUANDO:
        raise RegraError("Quando imprimir: escolha uma das opções da lista.")
    if dados.vias not in VIAS:
        raise RegraError("Vias: 1 ou 2.")
    impressora = (dados.impressora or "").strip()
    if len(impressora) > 200:
        raise RegraError("Nome da impressora grande demais.")
    antes = ler_impressao(sessao)
    mesma = (antes.impressora, antes.colunas, antes.acentos) == (
        impressora,
        dados.colunas,
        dados.acentos,
    )
    nova = replace(dados, impressora=impressora, confirmada=antes.confirmada and mesma)
    if not impressora:
        nova = replace(nova, confirmada=False)
    gravar_valor(sessao, "impressao.cupom", nova.impressora)
    gravar_valor(sessao, "impressao.cupom_colunas", str(nova.colunas))
    gravar_valor(sessao, "impressao.cupom_acentos", nova.acentos)
    gravar_valor(sessao, "impressao.cupom_cortar", "1" if nova.cortar else "0")
    gravar_valor(sessao, "impressao.cupom_gaveta", "1" if nova.gaveta else "0")
    gravar_valor(sessao, "impressao.cupom_quando", nova.quando)
    gravar_valor(sessao, "impressao.cupom_vias", str(nova.vias))
    gravar_valor(sessao, "impressao.cupom_confirmada", "1" if nova.confirmada else "0")
    return nova


def confirmar_impressao(sessao: Session, saiu: bool) -> Impressao:
    """O gerente respondeu se o teste saiu no papel."""
    atual = ler_impressao(sessao)
    if not atual.impressora:
        raise RegraError("Escolha a impressora de cupom antes.", status=409)
    gravar_valor(sessao, "impressao.cupom_confirmada", "1" if saiu else "0")
    log.info("teste de impressão em %s: %s", atual.impressora, "saiu" if saiu else "não saiu")
    return replace(atual, confirmada=saiu)


# ---------------------------------------------------------------- cópia de segurança


@dataclass(frozen=True)
class Backup:
    pasta_extra: str = ""  # pendrive ou pasta da nuvem; vazio = só a pasta do sistema
    manter: int = 30  # quantas cópias diárias ficam guardadas


def ler_backup(sessao: Session) -> Backup:
    padrao = Backup()
    try:
        manter = int(ler_valor(sessao, "backup.manter"))
    except ValueError:
        manter = padrao.manter
    if not COPIAS_MINIMO <= manter <= COPIAS_MAXIMO:
        manter = padrao.manter
    return Backup(pasta_extra=ler_valor(sessao, "backup.pasta_extra"), manter=manter)


def conferir_pasta_extra(texto: str) -> str:
    """A pasta extra precisa existir, aceitar gravação e não ser a própria pasta do sistema."""
    caminho = (texto or "").strip().strip('"')
    if not caminho:
        return ""
    if len(caminho) > 250:
        raise RegraError("Caminho da pasta grande demais.")
    pasta = Path(caminho).expanduser()
    if not pasta.is_absolute():
        raise RegraError("Digite o caminho inteiro da pasta. Por exemplo: E:\\Backup Moleka")
    if not pasta.is_dir():
        raise RegraError(f"A pasta “{pasta}” não existe neste computador. Crie a pasta antes.")
    dados = config.pasta_dados().resolve()
    if pasta.resolve() == dados or dados in pasta.resolve().parents:
        raise RegraError(
            "Esta é a pasta do próprio sistema. A cópia extra precisa ficar em outro lugar "
            "(pendrive, outro disco ou a pasta da nuvem)."
        )
    try:
        descritor, provisorio = tempfile.mkstemp(prefix="moleka-teste-", dir=pasta)
        os.close(descritor)
        os.unlink(provisorio)
    except OSError as erro:
        raise RegraError(f"Não consegui gravar na pasta “{pasta}”: {erro.strerror}.") from erro
    return str(pasta)


def gravar_backup(sessao: Session, dados: Backup) -> Backup:
    if not COPIAS_MINIMO <= dados.manter <= COPIAS_MAXIMO:
        raise RegraError(f"Cópias guardadas: de {COPIAS_MINIMO} a {COPIAS_MAXIMO}.")
    novo = Backup(pasta_extra=conferir_pasta_extra(dados.pasta_extra), manter=dados.manter)
    gravar_valor(sessao, "backup.pasta_extra", novo.pasta_extra)
    gravar_valor(sessao, "backup.manter", str(novo.manter))
    return novo
