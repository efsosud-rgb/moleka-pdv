"""Segredos (app/segredos.py): ficam fora do banco, num arquivo por segredo. Valores fictícios."""

import os
import stat
import sys

import pytest

from app import segredos


@pytest.fixture()
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("MOLEKA_PDV_DADOS", str(tmp_path))
    return tmp_path


def test_grava_le_troca_e_apaga(dados):
    assert segredos.ler("csc-homologacao") is None
    assert not segredos.existe("csc-homologacao")
    segredos.gravar("csc-homologacao", "CODIGOFICTICIO123")
    assert segredos.ler("csc-homologacao") == "CODIGOFICTICIO123"
    segredos.gravar("csc-homologacao", "OUTROCODIGO456")
    assert segredos.ler("csc-homologacao") == "OUTROCODIGO456"
    # Um segredo não mexe no outro.
    assert segredos.ler("csc-producao") is None
    segredos.gravar("csc-homologacao", "")  # vazio apaga
    assert segredos.ler("csc-homologacao") is None
    segredos.apagar("csc-homologacao")  # apagar o que não existe não é erro
    assert sorted(p.name for p in (dados / "segredos").iterdir()) == []


def test_fica_na_pasta_de_segredos_e_nao_no_banco(dados):
    segredos.gravar("certificado-senha", "senha-ficticia-ção")
    assert (dados / "segredos" / "certificado-senha").is_file()
    assert segredos.ler("certificado-senha") == "senha-ficticia-ção"  # acentos voltam iguais
    assert not list((dados / "backups").glob("*"))


def test_nome_desconhecido_e_recusado(dados):
    with pytest.raises(ValueError):
        segredos.gravar("qualquer", "x")
    with pytest.raises(ValueError):
        segredos.ler("../moleka.db")


def test_arquivo_estragado_avisa(dados):
    (dados / "segredos").mkdir(exist_ok=True)
    (dados / "segredos" / "csc-producao").write_bytes(b"lixo")
    with pytest.raises(segredos.SegredoError, match="estragado"):
        segredos.ler("csc-producao")


@pytest.mark.skipif(sys.platform != "win32", reason="a DPAPI só existe no Windows")
def test_no_windows_o_arquivo_fica_cifrado_pela_dpapi(dados):
    segredos.gravar("certificado-senha", "senha-ficticia-de-teste")
    conteudo = (dados / "segredos" / "certificado-senha").read_bytes()
    assert conteudo.startswith(b"MOLEKA-DPAPI-1\n")
    assert b"senha-ficticia" not in conteudo
    assert "senha-ficticia".encode("utf-16-le") not in conteudo
    assert segredos.ler("certificado-senha") == "senha-ficticia-de-teste"


@pytest.mark.skipif(sys.platform == "win32", reason="fora do Windows não há DPAPI")
def test_fora_do_windows_so_o_dono_le_o_arquivo(dados):
    segredos.gravar("certificado-senha", "senha-ficticia-de-teste")
    arquivo = dados / "segredos" / "certificado-senha"
    assert stat.S_IMODE(os.stat(arquivo).st_mode) == 0o600
    assert arquivo.read_bytes().startswith(b"MOLEKA-TEXTO-1\n")


@pytest.mark.skipif(sys.platform == "win32", reason="fora do Windows não há DPAPI")
def test_segredo_protegido_no_windows_nao_abre_em_outro_sistema(dados):
    (dados / "segredos").mkdir(exist_ok=True)
    (dados / "segredos" / "csc-producao").write_bytes(b"MOLEKA-DPAPI-1\n\x01\x02")
    with pytest.raises(segredos.SegredoError, match="só abre no Windows"):
        segredos.ler("csc-producao")
