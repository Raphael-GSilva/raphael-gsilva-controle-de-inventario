"""Utilitário compartilhado pelos testes: monta uma app Flask com um banco
SQLite temporário e isolado por teste.

De propósito NÃO usamos variáveis de ambiente aqui (os.environ) — como
app.config.Config lê os valores padrão uma vez, na primeira importação do
módulo, mudar os.environ depois não teria efeito de forma confiável em uma
suíte com vários testes. Em vez disso, cada teste cria uma subclasse de
Config com os valores desejados como atributos diretos.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app import create_app
from app.config import Config


def montar_app_teste(auth_mode: str = "mock", papel_padrao: str = "ANALISTA"):
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.unlink(db_path)  # Database.init_schema recria o arquivo do zero

    class ConfigTeste(Config):
        DATABASE_PATH = db_path
        AUTH_MODE = auth_mode
        PAPEL_PADRAO_NOVO_USUARIO = papel_padrao
        SHAREPOINT_SYNC_ENABLED = False

    app = create_app(ConfigTeste)
    app.testing = True
    return app, db_path


class TesteComBanco(unittest.TestCase):
    """Classe base: cria uma app + client novos para cada teste, com banco
    isolado (nada de estado vazando de um teste pro outro).

    Importante: o PRIMEIRO usuário a logar em qualquer banco novo vira
    ADMIN automaticamente (ver repositories.criar_ou_atualizar_usuario_microsoft).
    Quando self.papel_padrao pede um papel diferente de ADMIN, criamos antes
    um usuário descartável (em outro client, sessão separada) só para
    "consumir" essa posição de primeiro usuário — assim self.login() nos
    testes realmente resulta no papel esperado."""

    auth_mode = "mock"
    papel_padrao = "ANALISTA"

    def setUp(self):
        self.app, self.db_path = montar_app_teste(self.auth_mode, self.papel_padrao)
        self.client = self.app.test_client()
        if self.papel_padrao != "ADMIN":
            self.app.test_client().post(
                "/login", data={"nome": "Admin Bootstrap (descartável)", "email": "bootstrap@interno.local"}
            )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def login(self, nome: str = "Usuária Teste", email: str = "teste@exemplo.com"):
        return self.client.post("/login", data={"nome": nome, "email": email}, follow_redirects=True)
