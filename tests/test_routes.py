"""Testes de integração via test client do Flask — cobrem as rotas HTTP
de ponta a ponta: login, controle de acesso por papel, e o ciclo completo
de movimentações através das telas (não só da camada de serviço)."""

from __future__ import annotations

import os
import unittest

from tests.auxiliar import TesteComBanco, montar_app_teste


class TesteLogin(TesteComBanco):
    def test_pagina_protegida_redireciona_para_login_sem_sessao(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_login_mock_cria_usuario_e_redireciona(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Dashboard", r.data)

    def test_login_com_campos_vazios_mostra_erro_sem_quebrar(self):
        r = self.client.post("/login", data={"nome": "", "email": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIn("válido".encode(), r.data)

    def test_logout_limpa_sessao(self):
        self.login()
        self.client.get("/logout")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)

    def test_mesmo_email_reaproveita_o_mesmo_usuario(self):
        from app import repositories as repo

        self.login(nome="Nome Um", email="mesma@pessoa.com")
        with self.app.app_context():
            db = self.app.extensions["db"]
            with db.connection() as conn:
                usuarios_antes = len(repo.listar_usuarios(conn))

        self.client.get("/logout")
        self.login(nome="Nome Um Atualizado", email="mesma@pessoa.com")
        with self.app.app_context():
            with db.connection() as conn:
                usuarios_depois = repo.listar_usuarios(conn)
                usuario_atualizado = repo.obter_usuario_por_email(conn, "mesma@pessoa.com")

        self.assertEqual(len(usuarios_depois), usuarios_antes)
        self.assertEqual(usuario_atualizado.nome, "Nome Um Atualizado")

    def test_primeiro_usuario_do_banco_vira_admin_automaticamente(self):
        # Banco novo, ninguém logou ainda — usa papel_padrao=CONSULTA de
        # propósito para provar que o primeiro usuário ainda assim vira ADMIN.
        app, db_path = montar_app_teste(papel_padrao="CONSULTA")
        try:
            client = app.test_client()
            client.post("/login", data={"nome": "Primeira Pessoa", "email": "primeira@empresa.com"})
            r = client.get("/movimentacoes/entrada")
            self.assertEqual(r.status_code, 200, "primeiro usuário deveria ser ADMIN e acessar a tela")

            client2 = app.test_client()
            client2.post("/login", data={"nome": "Segunda Pessoa", "email": "segunda@empresa.com"})
            r2 = client2.get("/movimentacoes/entrada")
            self.assertEqual(r2.status_code, 403, "segundo usuário deveria respeitar PAPEL_PADRAO_NOVO_USUARIO")
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TesteControleDeAcesso(TesteComBanco):
    papel_padrao = "CONSULTA"

    def test_consulta_nao_acessa_telas_de_movimentacao(self):
        self.login()
        for rota in ("/movimentacoes/entrada", "/movimentacoes/entrega", "/movimentacoes/devolucao"):
            with self.subTest(rota=rota):
                r = self.client.get(rota)
                self.assertEqual(r.status_code, 403)

    def test_consulta_acessa_dashboard_e_consulta_normalmente(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/equipamentos/").status_code, 200)
        self.assertEqual(self.client.get("/movimentacoes/historico").status_code, 200)


class TesteCicloDeVidaViaHTTP(TesteComBanco):
    papel_padrao = "ANALISTA"

    def setUp(self):
        super().setUp()
        self.login()

    def _criar_equipamento(self, nr_ativo="NB-900", **extra):
        dados = {"nr_ativo": nr_ativo, "tipo": "Notebook"}
        dados.update(extra)
        return self.client.post("/movimentacoes/entrada", data=dados, follow_redirects=True)

    def test_entrada_aparece_na_consulta(self):
        self._criar_equipamento("NB-901")
        r = self.client.get("/equipamentos/?q=NB-901")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"NB-901", r.data)

    def test_entrada_duplicada_nao_quebra_e_mostra_erro(self):
        self._criar_equipamento("NB-902")
        r = self._criar_equipamento("NB-902")
        self.assertEqual(r.status_code, 200)
        self.assertIn("existe".encode(), r.data.lower())

    def test_equipamento_inexistente_retorna_404(self):
        r = self.client.get("/equipamentos/999999")
        self.assertEqual(r.status_code, 404)

    def test_entrega_e_devolucao_atualizam_status_na_tela(self):
        self._criar_equipamento("NB-903")
        r = self.client.post(
            "/movimentacoes/entrega",
            data={"nr_ativo": "NB-903", "nome_colaborador": "Fulano", "empresa_colaborador": "Empresa A"},
            follow_redirects=True,
        )
        self.assertIn("Alocado".encode(), r.data)

        r = self.client.post(
            "/movimentacoes/devolucao",
            data={"nr_ativo": "NB-903", "condicao_devolucao": "Bom"},
            follow_redirects=True,
        )
        self.assertIn("Em estoque".encode(), r.data)

    def test_formularios_get_carregam_sem_erro(self):
        for rota in ("/movimentacoes/entrada", "/movimentacoes/entrega", "/movimentacoes/devolucao"):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)


class TesteAdministracao(TesteComBanco):
    papel_padrao = "ADMIN"

    def test_admin_acessa_lista_de_usuarios(self):
        self.login(email="admin@empresa.com")
        r = self.client.get("/admin/usuarios")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"admin@empresa.com", r.data)

    def test_nao_admin_nao_acessa_painel(self):
        from app import repositories as repo

        self.login(email="admin@empresa.com")
        with self.app.app_context():
            db = self.app.extensions["db"]
            with db.connection() as conn:
                repo.criar_ou_atualizar_usuario_microsoft(
                    conn, "mock-analista", "Analista", "analista@empresa.com", papel_padrao="ANALISTA"
                )

        client_analista = self.app.test_client()
        client_analista.post("/login", data={"nome": "Analista", "email": "analista@empresa.com"})
        r = client_analista.get("/admin/usuarios")
        self.assertEqual(r.status_code, 403)

    def test_admin_promove_usuario_e_efeito_e_imediato(self):
        from app import repositories as repo

        self.login(email="admin@empresa.com")
        with self.app.app_context():
            db = self.app.extensions["db"]
            with db.connection() as conn:
                novo = repo.criar_ou_atualizar_usuario_microsoft(
                    conn, "mock-novo", "Novo", "novo@empresa.com", papel_padrao="CONSULTA"
                )

        client_novo = self.app.test_client()
        client_novo.post("/login", data={"nome": "Novo", "email": "novo@empresa.com"})
        self.assertEqual(client_novo.get("/movimentacoes/entrada").status_code, 403)

        r = self.client.post(
            f"/admin/usuarios/{novo.id}/papel", data={"papel": "ANALISTA"}, follow_redirects=True
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(client_novo.get("/movimentacoes/entrada").status_code, 200)

    def test_admin_nao_consegue_remover_o_proprio_papel_de_admin(self):
        from app import repositories as repo

        self.login(email="admin@empresa.com")
        with self.app.app_context():
            db = self.app.extensions["db"]
            with db.connection() as conn:
                eu = repo.obter_usuario_por_email(conn, "admin@empresa.com")

        r = self.client.post(
            f"/admin/usuarios/{eu.id}/papel", data={"papel": "CONSULTA"}, follow_redirects=True
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/movimentacoes/entrada").status_code, 200)


if __name__ == "__main__":
    unittest.main()
