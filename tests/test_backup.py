"""Cópia de segurança do banco: a do dia, a da pasta extra, a limpeza das antigas e o status."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from app import backup, config, configuracoes, db, tempo
from app.operadores import RegraError


def _hoje():
    return config.pasta_dados() / "backups" / backup.nome_do_dia(tempo.hoje())


def _status(cliente):
    return cliente.get("/api/status").json()["backup"]


def test_copia_do_dia_e_feita_conferida_e_aparece_no_status(cliente, loja):
    assert not _hoje().exists()
    antes = _status(cliente)
    assert (antes["ok"], antes["estado"]) == (False, "nunca feita")

    feita = cliente.post("/api/backup")
    assert feita.status_code == 201, feita.text
    dados = feita.json()
    assert dados["copia"]["arquivo"] == backup.nome_do_dia(tempo.hoje())
    assert dados["copia"]["dia"] == tempo.hoje().isoformat()
    assert (dados["apagadas"], dados["extra_pasta"], dados["extra_erro"]) == (0, "", "")
    assert dados["copia"]["tamanho"] == _hoje().stat().st_size > 0
    assert not list(_hoje().parent.glob("*.parcial"))  # o arquivo provisório não fica para trás

    # A cópia é um banco de verdade, com o que havia: os 3 produtos e o gerente da loja de teste.
    with sqlite3.connect(_hoje()) as copia:
        assert copia.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copia.execute("SELECT count(*) FROM produto").fetchone()[0] == 3
        assert copia.execute("SELECT login FROM operador").fetchall() == [("gerente",)]

    depois = _status(cliente)
    assert depois["ok"] is True and depois["texto"].startswith("hoje ")
    assert "só neste computador" in depois["motivo"]  # sem pasta extra, o status avisa
    listadas = cliente.get("/api/configuracoes").json()["backup"]
    assert [c["arquivo"] for c in listadas["copias"]] == [backup.nome_do_dia(tempo.hoje())]
    assert listadas["pasta"] == str(_hoje().parent)

    # Pedindo de novo no mesmo dia, a cópia é refeita (já com o que mudou), não duplicada.
    cliente.post("/api/clientes", json={"nome": "Cliente de Teste"})
    assert cliente.post("/api/backup").status_code == 201
    assert len(backup.listar()) == 1
    with sqlite3.connect(_hoje()) as copia:
        assert copia.execute("SELECT count(*) FROM cliente").fetchone()[0] == 1


def test_fechar_o_caixa_faz_a_copia_do_dia(cliente, loja):
    assert not _hoje().exists()
    contado = {"dinheiro": 10000, "pix": 0, "debito": 0, "credito": 0}
    fechado = cliente.post("/api/caixa/fechar", json={"contado": contado})
    assert fechado.status_code == 200, fechado.text
    with sqlite3.connect(_hoje()) as copia:
        # A cópia já tem o caixa fechado.
        assert copia.execute(
            "SELECT count(*) FROM sessao_caixa WHERE fechado_em IS NOT NULL"
        ).fetchone() == (1,)


def test_se_a_copia_falhar_o_caixa_fecha_do_mesmo_jeito(cliente, loja, monkeypatch):
    def quebrada(sessao, motivo):
        raise OSError("disco cheio (teste)")

    monkeypatch.setattr(backup, "copiar", quebrada)
    contado = {"dinheiro": 10000, "pix": 0, "debito": 0, "credito": 0}
    fechado = cliente.post("/api/caixa/fechar", json={"contado": contado})
    assert fechado.status_code == 200 and fechado.json()["fechado_em"] is not None
    assert cliente.get("/api/caixa").json()["aberto"] is False
    backup.garantir_a_de_hoje()  # na abertura do programa também não derruba nada


def test_ao_abrir_o_programa_faz_a_copia_que_falta_e_nao_refaz_a_que_existe(cliente, loja):
    backup.garantir_a_de_hoje()
    assert _hoje().exists()
    primeira = _hoje().stat().st_mtime_ns
    backup.garantir_a_de_hoje()
    assert _hoje().stat().st_mtime_ns == primeira


def test_guarda_as_ultimas_copias_e_nao_toca_nos_outros_arquivos(cliente, loja):
    pasta = backup.pasta()
    hoje = tempo.hoje()
    for dias in range(1, 11):  # dez cópias diárias antigas (de mentira)
        (pasta / backup.nome_do_dia(hoje - timedelta(days=dias))).write_bytes(b"antiga")
    de_formato = pasta / "moleka-antes-do-formato-3-20261111-101500.db"
    de_formato.write_bytes(b"antes de mudar o formato")
    outro = pasta / "anotacoes.txt"
    outro.write_text("arquivo de outra coisa", encoding="utf-8")

    assert (
        cliente.put("/api/configuracoes/backup", json={"pasta_extra": "", "manter": 7}).status_code
        == 200
    )
    feita = cliente.post("/api/backup").json()
    assert feita["apagadas"] == 4  # 11 diárias (10 antigas + a de hoje): ficam as 7 mais novas
    dias_guardados = [c.dia for c in backup.listar()]
    assert dias_guardados == [hoje - timedelta(days=n) for n in range(7)]
    assert de_formato.read_bytes() == b"antes de mudar o formato"
    assert outro.exists()

    for errado in (6, 366):
        recusa = cliente.put(
            "/api/configuracoes/backup", json={"pasta_extra": "", "manter": errado}
        )
        assert recusa.status_code == 422 and "de 7 a 365" in recusa.json()["detail"]


def test_pasta_extra_recebe_a_copia_e_o_status_avisa_quando_ela_some(
    cliente, loja, tmp_path_factory
):
    extra = tmp_path_factory.mktemp("pendrive de teste")
    velha = extra / backup.nome_do_dia(tempo.hoje() - timedelta(days=40))
    velha.write_bytes(b"antiga")
    do_usuario = extra / "fotos.txt"
    do_usuario.write_text("arquivo do dono do pendrive", encoding="utf-8")

    gravado = cliente.put(
        "/api/configuracoes/backup", json={"pasta_extra": f'  "{extra}"  ', "manter": 30}
    )
    assert gravado.status_code == 200, gravado.text
    assert gravado.json()["pasta_extra"] == str(extra)  # aspas e espaços de quem colou saem

    feita = cliente.post("/api/backup").json()
    assert (feita["extra_pasta"], feita["extra_erro"]) == (str(extra), "")
    na_extra = extra / backup.nome_do_dia(tempo.hoje())
    assert na_extra.read_bytes() == _hoje().read_bytes()
    assert not list(extra.glob("*.parcial"))
    assert do_usuario.exists()  # o que é do usuário fica
    assert velha.exists()  # 2 cópias na pasta extra, e o combinado é guardar 30
    status = _status(cliente)
    assert status["ok"] is True and status["motivo"] == f"também copiada para {extra}"
    assert cliente.get("/api/configuracoes").json()["backup"]["extra_em"] is not None

    # Com "guardar 7", a cópia de 40 dias atrás sai da pasta extra; o arquivo do usuário, não.
    cliente.put("/api/configuracoes/backup", json={"pasta_extra": str(extra), "manter": 7})
    for dias in range(1, 8):
        (extra / backup.nome_do_dia(tempo.hoje() - timedelta(days=dias))).write_bytes(b"x")
    cliente.post("/api/backup")
    assert not velha.exists() and do_usuario.exists()
    assert len(backup.listar(extra)) == 7

    # O pendrive foi tirado: a cópia deste computador é feita, e o status avisa da pasta extra.
    for arquivo in extra.iterdir():
        arquivo.unlink()
    extra.rmdir()
    sem_pendrive = cliente.post("/api/backup")
    assert sem_pendrive.status_code == 201
    assert "não foi encontrada" in sem_pendrive.json()["extra_erro"]
    assert _hoje().exists()
    status = _status(cliente)
    assert status["ok"] is False and status["estado"].endswith("sem a pasta extra")
    assert "a da pasta extra falhou" in status["motivo"]
    tudo = cliente.get("/api/configuracoes").json()["backup"]
    assert "não foi encontrada" in tudo["extra_erro"] and tudo["extra_em"] is None


def test_pasta_extra_escolhida_depois_da_copia_fica_avisada_ate_receber(
    cliente, loja, tmp_path_factory
):
    cliente.post("/api/backup")  # a cópia de hoje, só neste computador
    assert _status(cliente)["ok"] is True
    extra = tmp_path_factory.mktemp("pendrive novo")
    cliente.put("/api/configuracoes/backup", json={"pasta_extra": str(extra), "manter": 30})
    status = _status(cliente)
    assert status["ok"] is False and status["estado"].endswith("sem a pasta extra")
    assert "ainda não recebeu a cópia de hoje" in status["motivo"]

    # De hora em hora o sistema tenta de novo sozinho (o pendrive pode ter voltado).
    backup.garantir_a_de_hoje()
    assert (extra / backup.nome_do_dia(tempo.hoje())).exists()
    status = _status(cliente)
    assert status["ok"] is True and status["motivo"] == f"também copiada para {extra}"
    # A hora gravada é a da loja, com o fuso, e não a hora UTC do banco.
    recebeu = datetime.fromisoformat(cliente.get("/api/configuracoes").json()["backup"]["extra_em"])
    assert recebeu.utcoffset() == datetime.now(tempo.FUSO).utcoffset()
    assert abs(recebeu - datetime.now(tempo.FUSO)) < timedelta(minutes=1)
    # Com tudo em dia, a conferência de hora em hora não refaz a cópia.
    antes = (extra / backup.nome_do_dia(tempo.hoje())).stat().st_mtime_ns
    backup.garantir_a_de_hoje()
    assert (extra / backup.nome_do_dia(tempo.hoje())).stat().st_mtime_ns == antes

    # Trocar de pasta zera o que se sabia da anterior: a nova ainda não recebeu nada.
    outra = tmp_path_factory.mktemp("outro pendrive")
    cliente.put("/api/configuracoes/backup", json={"pasta_extra": str(outra), "manter": 30})
    tudo = cliente.get("/api/configuracoes").json()["backup"]
    assert tudo["extra_em"] is None and tudo["extra_erro"] == ""
    assert _status(cliente)["ok"] is False


def test_pasta_extra_precisa_existir_e_ficar_fora_da_pasta_do_sistema(cliente, tmp_path_factory):
    def recusa(pasta, trecho):
        resposta = cliente.put(
            "/api/configuracoes/backup", json={"pasta_extra": pasta, "manter": 30}
        )
        assert resposta.status_code == 422, resposta.text
        assert trecho in resposta.json()["detail"], resposta.json()["detail"]

    recusa("backup", "Digite o caminho inteiro")
    recusa(str(tmp_path_factory.mktemp("x") / "nao-existe"), "não existe neste computador")
    recusa(str(config.pasta_dados()), "pasta do próprio sistema")
    recusa(str(backup.pasta()), "pasta do próprio sistema")
    arquivo = tmp_path_factory.mktemp("y") / "arquivo.txt"
    arquivo.write_text("x", encoding="utf-8")
    recusa(str(arquivo), "não existe neste computador")  # é um arquivo, não uma pasta
    with db.nova_sessao() as sessao:
        assert configuracoes.ler_backup(sessao).pasta_extra == ""  # nada ficou gravado


def test_copia_atrasada_aparece_como_atrasada(cliente, loja):
    ontem = tempo.hoje() - timedelta(days=1)
    (backup.pasta() / backup.nome_do_dia(ontem)).write_bytes(b"de ontem")
    status = _status(cliente)
    assert status["ok"] is False and status["estado"].startswith("atrasada (ontem ")
    assert status["motivo"] == f"a última cópia de segurança é de {ontem:%d/%m/%Y}"


def test_copia_que_nao_passa_na_conferencia_nao_vira_a_copia_do_dia(cliente, loja, monkeypatch):
    def reprovada(arquivo):
        raise RegraError("A cópia foi feita, mas não passou na conferência do banco.", status=500)

    monkeypatch.setattr(backup, "_conferir", reprovada)
    with db.nova_sessao() as sessao, pytest.raises(RegraError, match="não passou na conferência"):
        backup.copiar(sessao, "teste")
    assert not _hoje().exists() and not list(backup.pasta().glob("*.parcial"))
