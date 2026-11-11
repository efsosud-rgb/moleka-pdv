"""Cópia de segurança do banco.

O banco é um arquivo só. A cópia é feita pelo próprio SQLite (cópia "online"), que funciona
com o sistema em uso e nunca pega o arquivo pela metade. Depois de copiar, a cópia é aberta e
conferida; só então recebe o nome definitivo.

- Uma cópia por dia, em `<dados>/backups/moleka-AAAA-MM-DD.db`. A do dia é refeita quando o
  caixa fecha e quando o gerente pede; ao abrir o programa, é feita se ainda não existir.
- Pasta extra (pendrive, outro disco, pasta da nuvem): recebe a mesma cópia. É ela que salva
  os dados se o disco do computador estragar, porque a pasta do sistema fica no mesmo disco.
- Ficam guardadas as últimas N cópias diárias (N está em Configurações). As mais antigas são
  apagadas, aqui e na pasta extra, e só os arquivos com o nome `moleka-AAAA-MM-DD.db`: as
  cópias feitas antes de uma mudança de formato do banco não são tocadas.

Nada aqui derruba o sistema: se a cópia falhar, o erro fica no log e aparece no rodapé.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app import config, configuracoes, db, tempo
from app.operadores import RegraError

log = logging.getLogger("moleka.backup")

_NOME = re.compile(r"^moleka-(\d{4})-(\d{2})-(\d{2})\.db$")
_uma_por_vez = threading.Lock()


@dataclass(frozen=True)
class Copia:
    arquivo: Path
    dia: date
    feita_em: datetime  # horário da loja
    tamanho: int  # bytes


@dataclass(frozen=True)
class Resultado:
    copia: Copia
    apagadas: int  # cópias antigas removidas da pasta do sistema
    extra_pasta: str  # vazio = não há pasta extra configurada
    extra_erro: str  # vazio = a cópia na pasta extra deu certo (ou não há pasta extra)


def pasta() -> Path:
    destino = config.pasta_dados() / "backups"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def nome_do_dia(dia: date) -> str:
    return f"moleka-{dia:%Y-%m-%d}.db"


def _dia_do_nome(nome: str) -> date | None:
    achado = _NOME.match(nome)
    if achado is None:
        return None
    try:
        return date(int(achado[1]), int(achado[2]), int(achado[3]))
    except ValueError:
        return None


def listar(onde: Path | None = None) -> list[Copia]:
    """As cópias diárias de uma pasta (padrão: a do sistema), da mais nova para a mais antiga."""
    copias = []
    for arquivo in onde.iterdir() if onde is not None else pasta().iterdir():
        dia = _dia_do_nome(arquivo.name)
        if dia is None or not arquivo.is_file():
            continue
        dados = arquivo.stat()
        feita_em = datetime.fromtimestamp(dados.st_mtime, tempo.FUSO)
        copias.append(Copia(arquivo, dia, feita_em, dados.st_size))
    return sorted(copias, key=lambda c: c.dia, reverse=True)


def ultima() -> Copia | None:
    copias = listar()
    return copias[0] if copias else None


def _conferir(arquivo: Path) -> None:
    """Abre a cópia e pede ao SQLite para conferir o arquivo inteiro."""
    conexao = sqlite3.connect(arquivo)
    try:
        resultado = conexao.execute("PRAGMA integrity_check").fetchone()
        tabelas = conexao.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        conexao.close()
    if resultado is None or resultado[0] != "ok":
        raise RegraError("A cópia foi feita, mas não passou na conferência do banco.", status=500)
    if tabelas is None or tabelas[0] == 0:
        raise RegraError("A cópia saiu vazia.", status=500)


def _apagar_antigas(onde: Path, manter: int) -> int:
    apagadas = 0
    for velha in listar(onde)[manter:]:
        try:
            velha.arquivo.unlink()
            apagadas += 1
            log.info("cópia de segurança antiga apagada: %s", velha.arquivo)
        except OSError as erro:
            log.warning("não consegui apagar a cópia antiga %s: %s", velha.arquivo, erro)
    return apagadas


def _copiar_para_a_pasta_extra(copia: Path, pasta_extra: str, manter: int) -> str:
    """Devolve "" se deu certo, ou o motivo de não ter dado (pendrive fora, pasta apagada...)."""
    destino = Path(pasta_extra)
    try:
        if not destino.is_dir():
            return f"a pasta “{destino}” não foi encontrada (o pendrive está conectado?)"
        provisorio = destino / (copia.name + ".parcial")
        shutil.copyfile(copia, provisorio)
        provisorio.replace(destino / copia.name)
        _apagar_antigas(destino, manter)
    except OSError as erro:
        log.warning("cópia de segurança na pasta extra falhou: %s", erro)
        return f"não consegui gravar em “{destino}”: {erro.strerror or erro}"
    return ""


def copiar(sessao: Session, motivo: str) -> Resultado:
    """Faz (ou refaz) a cópia de hoje, confere, manda para a pasta extra e apaga as antigas."""
    opcoes = configuracoes.ler_backup(sessao)
    hoje = tempo.hoje()
    destino = pasta() / nome_do_dia(hoje)
    provisorio = destino.with_name(destino.name + ".parcial")
    with _uma_por_vez:
        provisorio.unlink(missing_ok=True)
        origem = db.engine().raw_connection()
        try:
            copia = sqlite3.connect(provisorio)
            try:
                origem.driver_connection.backup(copia)  # type: ignore[union-attr]
            finally:
                copia.close()
        except sqlite3.Error as erro:
            provisorio.unlink(missing_ok=True)
            log.exception("cópia de segurança falhou")
            raise RegraError(f"Não consegui fazer a cópia de segurança: {erro}", 500) from erro
        finally:
            origem.close()
        try:
            _conferir(provisorio)
        except (RegraError, sqlite3.Error):
            provisorio.unlink(missing_ok=True)
            raise
        provisorio.replace(destino)
        apagadas = _apagar_antigas(pasta(), opcoes.manter)
        extra_erro = ""
        if opcoes.pasta_extra:
            extra_erro = _copiar_para_a_pasta_extra(destino, opcoes.pasta_extra, opcoes.manter)
        # O resultado da pasta extra fica gravado: o rodapé mostra se a última tentativa falhou.
        configuracoes.gravar_valor(sessao, "backup.extra_erro", extra_erro)
        configuracoes.gravar_valor(
            sessao,
            "backup.extra_em",
            (tempo.iso_na_loja(tempo.agora()) or "")
            if opcoes.pasta_extra and not extra_erro
            else "",
        )
        sessao.commit()
    feita = next(c for c in listar() if c.arquivo == destino)
    log.info(
        "cópia de segurança feita (%s): %s, %d bytes%s",
        motivo,
        destino,
        feita.tamanho,
        f"; pasta extra: {extra_erro}" if extra_erro else "",
    )
    return Resultado(feita, apagadas, opcoes.pasta_extra, extra_erro)


def falta_a_pasta_extra(sessao: Session) -> bool:
    """Há pasta extra escolhida e ela ainda não recebeu a cópia de hoje?"""
    if not configuracoes.ler_backup(sessao).pasta_extra:
        return False
    recebeu_em = configuracoes.ler_valor(sessao, "backup.extra_em")
    return recebeu_em[:10] != tempo.hoje().isoformat()


def garantir_a_de_hoje() -> None:
    """Ao abrir o programa, e depois de hora em hora: faz a cópia do dia se ela ainda não
    existe, ou de novo se a pasta extra ainda não a recebeu (o pendrive pode ter voltado).
    Nunca levanta erro."""
    try:
        feita = (pasta() / nome_do_dia(tempo.hoje())).exists()
        with db.nova_sessao() as sessao:
            if feita and not falta_a_pasta_extra(sessao):
                return
            copiar(sessao, "pasta extra em falta" if feita else "abertura do programa")
    except Exception:  # noqa: BLE001 - a cópia não pode impedir o sistema de abrir
        log.exception("cópia de segurança da abertura falhou")


def tentar(sessao: Session, motivo: str) -> None:
    """Para depois de um fechamento de caixa: faz a cópia e, se falhar, só registra no log."""
    try:
        copiar(sessao, motivo)
    except Exception:  # noqa: BLE001 - o fechamento do caixa já foi gravado e não volta atrás
        log.exception("cópia de segurança (%s) falhou", motivo)
