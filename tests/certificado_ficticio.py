"""Certificados digitais FICTÍCIOS, só para os testes. Nenhum é de empresa de verdade.

Gera um arquivo .pfx parecido com o e-CNPJ A1 da ICP-Brasil: o titular no formato
"RAZÃO SOCIAL:CNPJ" e o CNPJ também no campo próprio (OID 2.16.76.1.3.3). É autoassinado por
uma "AC" inventada: não vale para assinar nada fora dos testes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cache

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID, ObjectIdentifier

CNPJ = "11222333000181"  # fictício, com os dígitos verificadores certos
TITULAR = "EMPRESA FICTICIA DE TESTE LTDA"
SENHA = "senha-ficticia-de-teste"
EMISSOR = "AC FICTICIA DE TESTE"


@cache
def _chave() -> rsa.RSAPrivateKey:
    # Uma chave só para todos os testes: gerar chave RSA demora.
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _octet_string(texto: str) -> bytes:
    dados = texto.encode("ascii")
    assert len(dados) < 128
    return b"\x04" + bytes([len(dados)]) + dados


def gerar(
    *,
    titular: str = TITULAR,
    cnpj: str = CNPJ,
    senha: str = SENHA,
    dias_de_validade: int = 365,
    comeca_em_dias: int = -1,
    com_chave: bool = True,
    cnpj_no_campo_proprio: bool = True,
    cnpj_no_nome: bool = True,
    pessoa_fisica: bool = False,
) -> bytes:
    """O conteúdo de um arquivo .pfx fictício."""
    agora = datetime.now(UTC)
    inicio = agora + timedelta(days=comeca_em_dias)
    fim = agora + timedelta(days=dias_de_validade)
    nome = f"{titular}:{cnpj}" if cnpj and cnpj_no_nome else titular
    sujeito = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ICP-Brasil FICTICIA"),
            x509.NameAttribute(NameOID.COMMON_NAME, nome),
        ]
    )
    emissor = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, EMISSOR)])
    construtor = (
        x509.CertificateBuilder()
        .subject_name(sujeito)
        .issuer_name(emissor)
        .public_key(_chave().public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(min(inicio, fim - timedelta(days=1)))
        .not_valid_after(fim)
    )
    outros: list[x509.GeneralName] = []
    if cnpj and cnpj_no_campo_proprio:
        outros.append(x509.OtherName(ObjectIdentifier("2.16.76.1.3.3"), _octet_string(cnpj)))
    if pessoa_fisica:
        # Nascimento + CPF + NIS + RG + órgão, todos fictícios.
        dados = "01011980" + "11144477735" + "0" * 11 + "0" * 15 + "SSP SP"
        outros.append(x509.OtherName(ObjectIdentifier("2.16.76.1.3.1"), _octet_string(dados)))
    if outros:
        construtor = construtor.add_extension(x509.SubjectAlternativeName(outros), critical=False)
    certificado = construtor.sign(_chave(), hashes.SHA256())
    protecao: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(senha.encode("utf-8"))
        if senha
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        b"certificado ficticio", _chave() if com_chave else None, certificado, None, protecao
    )
