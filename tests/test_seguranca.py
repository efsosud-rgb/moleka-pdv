"""Senhas: o banco guarda só o hash, e só a senha certa confere."""

from app import seguranca


def test_hash_nao_contem_a_senha_e_confere_so_com_a_certa():
    gravado = seguranca.gerar_hash("sorvete de manga")
    assert gravado.startswith("scrypt$16384$8$1$")
    assert "sorvete" not in gravado
    assert len(gravado) <= 200  # cabe na coluna operador.senha_hash
    assert seguranca.conferir("sorvete de manga", gravado) is True
    assert seguranca.conferir("sorvete de Manga", gravado) is False
    assert seguranca.conferir("", gravado) is False


def test_a_mesma_senha_gera_hashes_diferentes():
    """Cada senha tem o seu sal: duas pessoas com a mesma senha não ficam com o mesmo hash."""
    a = seguranca.gerar_hash("1234")
    b = seguranca.gerar_hash("1234")
    assert a != b
    assert seguranca.conferir("1234", a) and seguranca.conferir("1234", b)


def test_senha_com_acento_e_emoji():
    gravado = seguranca.gerar_hash("açaí 🍦 100%")
    assert seguranca.conferir("açaí 🍦 100%", gravado)
    assert not seguranca.conferir("acai 🍦 100%", gravado)


def test_hash_malformado_nunca_confere():
    for gravado in (
        "",
        "1234",  # senha em texto puro gravada por engano
        "md5$abc",
        "scrypt$16384$8$1$sal-invalido$hash",
        "scrypt$3$8$1$AAAA$AAAA",  # n precisa ser potência de 2
        "scrypt$1048576$8$1$AAAA$AAAA",  # custo absurdo: recusado sem tentar calcular
        "scrypt$16384$8$1$$",
    ):
        assert seguranca.conferir("1234", gravado) is False, gravado


def test_senha_provisoria_e_numerica_e_sorteada():
    senhas = {seguranca.senha_provisoria() for _ in range(20)}
    assert all(len(s) == 6 and s.isdigit() for s in senhas)
    assert len(senhas) > 1
