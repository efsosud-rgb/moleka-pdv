"""Certificado digital A1 da empresa (arquivo .pfx ou .p12), que vai assinar a NFC-e.

O gerente escolhe o arquivo e digita a senha em Configurações → Fiscal. O sistema:
1. abre o arquivo com a senha (biblioteca `cryptography`) e lê titular, CNPJ, emissor e validade;
2. recusa o certificado vencido, o que ainda não vale, o que não tem a chave privada, o de pessoa
   física (e-CPF) e o de outra empresa (raiz do CNPJ diferente da do CNPJ da aba Loja);
3. guarda uma cópia do arquivo em `<dados>/certificado/certificado-a1.pfx` e a senha em
   `app/segredos.py` (cifrada pelo Windows). O que não é segredo (titular, CNPJ, validade) fica
   na tabela `configuracao`, para a tela e para o indicador.

O arquivo e a senha não vão para o banco, para a cópia de segurança, para o log nem para o
repositório. Certificado A3 (cartão ou token USB) não é lido aqui. O CNPJ vem do campo que a
ICP-Brasil reserva para ele no certificado (OID 2.16.76.1.3.3) ou, na falta, do fim do nome do
titular ("RAZÃO SOCIAL:CNPJ").
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app import config, configuracoes, documentos, segredos
from app.operadores import RegraError
from app.tempo import FUSO

log = logging.getLogger("moleka.certificado")

LIMITE_BYTES = 200 * 1024  # um A1 com a cadeia inteira tem uns 10 KB
OID_CNPJ = "2.16.76.1.3.3"  # ICP-Brasil: CNPJ da pessoa jurídica titular
OID_DADOS_PESSOA_FISICA = "2.16.76.1.3.1"  # ICP-Brasil: só existe no e-CPF
AVISO_DE_VENCIMENTO_DIAS = 30
SENHA = "certificado-senha"
_CNPJ_NO_TEXTO = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_CHAVES = {
    "caminho": "fiscal.certificado_caminho",
    "titular": "fiscal.certificado_titular",
    "cnpj": "fiscal.certificado_cnpj",
    "emissor": "fiscal.certificado_emissor",
    "inicio": "fiscal.certificado_inicio",
    "fim": "fiscal.certificado_fim",
    "instalado_em": "fiscal.certificado_instalado_em",
    "arquivo": "fiscal.certificado_arquivo",
}
SEM_BIBLIOTECA = (
    "A parte do sistema que lê certificado digital não carregou neste computador. "
    "Feche o Moleka PDV, abra de novo e tente outra vez; se continuar, avise o suporte."
)


@dataclass(frozen=True)
class Certificado:
    """O que o arquivo diz. Datas em UTC, com fuso."""

    titular: str  # nome do titular, sem o ":CNPJ" do fim
    cnpj: str  # 14 caracteres, ou vazio quando o certificado não traz CNPJ
    pessoa_fisica: bool  # e-CPF
    emissor: str  # autoridade certificadora que emitiu
    inicio: datetime
    fim: datetime


@dataclass(frozen=True)
class Situacao:
    """O certificado instalado neste computador, como está gravado."""

    titular: str
    cnpj: str
    emissor: str
    inicio: datetime
    fim: datetime
    instalado_em: datetime
    arquivo: str  # nome do arquivo que o gerente escolheu
    caminho: Path  # a cópia guardada pelo sistema
    tem_arquivo: bool
    tem_senha: bool

    def dias_restantes(self, agora: datetime | None = None) -> int:
        momento = agora or datetime.now(UTC)
        return (self.fim.astimezone(FUSO).date() - momento.astimezone(FUSO).date()).days

    def vencido(self, agora: datetime | None = None) -> bool:
        return self.fim <= (agora or datetime.now(UTC))


def data_br(momento: datetime) -> str:
    return momento.astimezone(FUSO).strftime("%d/%m/%Y")


def pasta() -> Path:
    destino = config.pasta_dados() / "certificado"
    destino.mkdir(exist_ok=True)
    return destino


def caminho_do_arquivo() -> Path:
    return pasta() / "certificado-a1.pfx"


def _documento(valor: bytes) -> str:
    """O CNPJ dentro do campo do certificado (o valor vem em DER, com o tipo na frente)."""
    texto = valor.decode("latin-1").upper()
    for achado in _CNPJ_NO_TEXTO.finditer(texto):
        if documentos.cnpj_valido(achado.group()):
            return achado.group()
    return ""


def ler(conteudo: bytes, senha: str) -> Certificado:
    """Abre o arquivo .pfx/.p12 com a senha e lê os dados. Não grava nada."""
    if not conteudo:
        raise RegraError("Escolha o arquivo do certificado (termina em .pfx ou .p12).")
    if len(conteudo) > LIMITE_BYTES:
        raise RegraError(
            "Este arquivo é grande demais para ser um certificado A1. "
            "Confira se escolheu o arquivo certo (termina em .pfx ou .p12)."
        )
    try:
        from cryptography import x509
        from cryptography.exceptions import UnsupportedAlgorithm
        from cryptography.hazmat.primitives.serialization import pkcs12
        from cryptography.x509.oid import NameOID
    except ImportError as erro:
        log.exception("a biblioteca cryptography não carregou")
        raise RegraError(SEM_BIBLIOTECA, status=503) from erro

    # Arquivo sem senha: o padrão PKCS#12 diferencia "nenhuma senha" de "senha vazia".
    tentativas: list[bytes | None] = [senha.encode("utf-8")] if senha else [None, b""]
    aberto = None
    for tentativa in tentativas:
        try:
            aberto = pkcs12.load_key_and_certificates(conteudo, tentativa)
            break
        except ValueError:
            continue
        except UnsupportedAlgorithm as erro:
            raise RegraError(
                "Este certificado foi gravado com um tipo de proteção antigo, que esta versão "
                "não abre. Peça à certificadora (ou ao contador) o arquivo exportado de novo."
            ) from erro
    if aberto is None:
        raise RegraError(
            "Não deu para abrir o certificado com esta senha. Confira a senha (maiúsculas e "
            "minúsculas fazem diferença) e se o arquivo é mesmo o certificado A1 da empresa."
        )
    chave, certificado, cadeia = aberto
    if certificado is None and not cadeia:
        raise RegraError("O arquivo abriu, mas não tem certificado dentro. Escolha o arquivo .pfx.")
    if chave is None or certificado is None:
        raise RegraError(
            "O arquivo tem o certificado, mas não a chave privada, e sem ela a nota não é "
            "assinada. Peça à certificadora o arquivo .pfx completo (com a chave privada)."
        )

    def nome_comum(nome: x509.Name) -> str:
        partes = nome.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not partes:
            return ""
        valor = partes[0].value
        return valor.decode("utf-8", "replace") if isinstance(valor, bytes) else str(valor)

    titular = nome_comum(certificado.subject)
    cnpj = ""
    pessoa_fisica = False
    try:
        nomes = certificado.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        nomes = None
    if nomes is not None:
        for outro in nomes.get_values_for_type(x509.OtherName):
            if outro.type_id.dotted_string == OID_CNPJ and not cnpj:
                cnpj = _documento(outro.value)
            elif outro.type_id.dotted_string == OID_DADOS_PESSOA_FISICA:
                pessoa_fisica = True
    final = re.search(r":\s*([0-9A-Za-z]{14})\s*$", titular)
    if final:
        if not cnpj and documentos.cnpj_valido(final.group(1)):
            cnpj = documentos.limpar(final.group(1))
        titular = titular[: final.start()].strip()
    return Certificado(
        titular=titular,
        cnpj=cnpj,
        pessoa_fisica=pessoa_fisica and not cnpj,
        emissor=nome_comum(certificado.issuer),
        inicio=certificado.not_valid_before_utc,
        fim=certificado.not_valid_after_utc,
    )


def _conferir_para_a_loja(sessao: Session, lido: Certificado) -> None:
    agora = datetime.now(UTC)
    if lido.fim <= agora:
        raise RegraError(
            f"Este certificado venceu em {data_br(lido.fim)}. Peça um novo à certificadora "
            "(o contador costuma saber qual)."
        )
    if lido.inicio > agora:
        raise RegraError(f"Este certificado só passa a valer em {data_br(lido.inicio)}.")
    if not lido.cnpj:
        if lido.pessoa_fisica:
            raise RegraError(
                "Este é um certificado de pessoa física (e-CPF). A NFC-e é assinada com o "
                "certificado da empresa (e-CNPJ, tipo A1)."
            )
        raise RegraError(
            "Não encontrei o CNPJ da empresa neste certificado. A NFC-e precisa do e-CNPJ A1."
        )
    loja = configuracoes.ler_loja(sessao).cnpj
    if loja and loja[:8] != lido.cnpj[:8]:
        raise RegraError(
            f"Este certificado é do CNPJ {documentos.formatar(lido.cnpj)}, mas o CNPJ da loja "
            f"(aba Dados da loja) é {documentos.formatar(loja)}. A nota só sai com o "
            "certificado da própria empresa."
        )


def _gravar_arquivo(destino: Path, conteudo: bytes) -> Path:
    """Grava num arquivo provisório ao lado do destino e devolve o provisório."""
    provisorio = destino.with_name(destino.name + ".gravando")
    descritor = os.open(provisorio, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "wb") as saida:
        saida.write(conteudo)
    return provisorio


def instalar(
    sessao: Session, conteudo: bytes, senha: str, nome_arquivo: str, quem: str
) -> Situacao:
    """Confere e guarda o certificado (troca o que houver). Quem chama faz o commit."""
    lido = ler(conteudo, senha)
    _conferir_para_a_loja(sessao, lido)
    destino = caminho_do_arquivo()
    try:
        provisorio = _gravar_arquivo(destino, conteudo)
    except OSError as erro:
        raise RegraError(f"Não consegui guardar o certificado: {erro.strerror}.") from erro
    try:
        segredos.gravar(SENHA, senha)
    except segredos.SegredoError as erro:
        provisorio.unlink(missing_ok=True)
        raise RegraError(f"Não consegui guardar a senha do certificado. {erro}") from erro
    os.replace(provisorio, destino)
    antes = configuracoes.ler_valor(sessao, _CHAVES["cnpj"])
    agora = datetime.now(UTC)
    nome = Path(nome_arquivo.replace("\\", "/")).name[:120] or "certificado.pfx"
    valores = {
        "caminho": str(destino),
        "titular": lido.titular[:120],
        "cnpj": lido.cnpj,
        "emissor": lido.emissor[:120],
        "inicio": lido.inicio.isoformat(timespec="seconds"),
        "fim": lido.fim.isoformat(timespec="seconds"),
        "instalado_em": agora.isoformat(timespec="seconds"),
        "arquivo": nome,
    }
    for campo, chave in _CHAVES.items():
        configuracoes.gravar_valor(sessao, chave, valores[campo])
    log.info(
        "certificado A1 %s por %s: CNPJ %s, válido até %s",
        "trocado" if antes else "instalado",
        quem,
        lido.cnpj,
        data_br(lido.fim),
    )
    situacao = situacao_gravada(sessao)
    assert situacao is not None
    return situacao


def _data(texto: str) -> datetime | None:
    try:
        momento = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def situacao_gravada(sessao: Session) -> Situacao | None:
    """O certificado instalado, pelo que está gravado. None = nenhum."""
    valores = {campo: configuracoes.ler_valor(sessao, chave) for campo, chave in _CHAVES.items()}
    if not valores["caminho"]:
        return None
    inicio, fim, instalado = (_data(valores[c]) for c in ("inicio", "fim", "instalado_em"))
    if inicio is None or fim is None or instalado is None:
        return None
    caminho = Path(valores["caminho"])
    return Situacao(
        titular=valores["titular"],
        cnpj=valores["cnpj"],
        emissor=valores["emissor"],
        inicio=inicio,
        fim=fim,
        instalado_em=instalado,
        arquivo=valores["arquivo"],
        caminho=caminho,
        tem_arquivo=caminho.is_file(),
        tem_senha=segredos.existe(SENHA),
    )


def conferir(sessao: Session) -> Certificado:
    """Abre de novo a cópia guardada com a senha guardada: prova que os dois ainda servem."""
    situacao = situacao_gravada(sessao)
    if situacao is None:
        raise RegraError("Nenhum certificado instalado.", status=409)
    if not situacao.tem_arquivo:
        raise RegraError(
            f"O arquivo do certificado sumiu deste computador ({situacao.caminho}). "
            "Instale o certificado de novo.",
            status=409,
        )
    try:
        senha = segredos.ler(SENHA)
    except segredos.SegredoError as erro:
        raise RegraError(
            f"Não consegui ler a senha guardada do certificado. {erro} Instale o certificado de "
            "novo (o Windows pode ter perdido a chave, por exemplo depois de redefinirem a "
            "senha deste usuário).",
            status=409,
        ) from erro
    if senha is None:
        raise RegraError(
            "A senha do certificado não está guardada. Instale o certificado de novo.", status=409
        )
    try:
        conteudo = situacao.caminho.read_bytes()
    except OSError as erro:
        raise RegraError(f"Não consegui ler o certificado: {erro.strerror}.", status=409) from erro
    return ler(conteudo, senha)


def remover(sessao: Session, quem: str) -> None:
    """Apaga a cópia do certificado e a senha. Quem chama confirma antes e faz o commit."""
    situacao = situacao_gravada(sessao)
    caminho = situacao.caminho if situacao else caminho_do_arquivo()
    caminho.unlink(missing_ok=True)
    segredos.apagar(SENHA)
    for chave in _CHAVES.values():
        configuracoes.gravar_valor(sessao, chave, "")
    log.warning(
        "certificado A1 removido por %s (CNPJ %s, válido até %s)",
        quem,
        situacao.cnpj if situacao else "—",
        data_br(situacao.fim) if situacao else "—",
    )
