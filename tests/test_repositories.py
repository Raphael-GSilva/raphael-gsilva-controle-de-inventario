"""Testes da camada de repositório que não são bem cobertos nem pelos
testes de serviço nem pelos de rota — principalmente casos de borda do
cadastro de usuários."""

from __future__ import annotations

import os
import tempfile
import unittest

from app import repositories as repo
from app.db import Database


class TesteRepositorioUsuarios(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.db = Database(self.db_path)
        self.db.init_schema()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_mesmo_oid_duas_vezes_atualiza_em_vez_de_duplicar(self):
        with self.db.connection() as conn:
            repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-1", "Nome A", "a@empresa.com")
            repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-1", "Nome A Atualizado", "a@empresa.com")
            usuarios = repo.listar_usuarios(conn)
        self.assertEqual(len(usuarios), 1)
        self.assertEqual(usuarios[0].nome, "Nome A Atualizado")

    def test_mesmo_oid_em_tenants_diferentes_nao_colide(self):
        """O caso que motivou guardar tenant_id: em um cenário multi-tenant
        (app aceitando login de mais de uma empresa cliente), dois oids
        coincidentes vindos de tenants DIFERENTES precisam ser tratados
        como duas pessoas diferentes — nunca a mesma conta."""
        with self.db.connection() as conn:
            pessoa_empresa_1 = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-coincidente", "Pessoa da Empresa 1", "p1@empresa1.com",
                tenant_id="tenant-empresa-1",
            )
            pessoa_empresa_2 = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-coincidente", "Pessoa da Empresa 2", "p2@empresa2.com",
                tenant_id="tenant-empresa-2",
            )
            usuarios = repo.listar_usuarios(conn)

        self.assertEqual(len(usuarios), 2, "deveriam ser tratadas como duas contas distintas")
        self.assertNotEqual(pessoa_empresa_1.id, pessoa_empresa_2.id)

    def test_relogar_no_mesmo_tenant_reaproveita_a_conta(self):
        with self.db.connection() as conn:
            primeiro_login = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-x", "Nome", "pessoa@empresa.com", tenant_id="tenant-1"
            )
            segundo_login = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-x", "Nome", "pessoa@empresa.com", tenant_id="tenant-1"
            )
            usuarios = repo.listar_usuarios(conn)
        self.assertEqual(len(usuarios), 1)
        self.assertEqual(primeiro_login.id, segundo_login.id)

    def test_email_existente_com_oid_diferente_atualiza_o_oid_em_vez_de_quebrar(self):
        """Simula uma conta do Entra ID apagada e recriada com o mesmo
        e-mail corporativo (oid novo). Não deve criar um segundo usuário
        nem levantar IntegrityError — deve migrar o registro existente
        para o novo oid, preservando o papel que a pessoa já tinha."""
        with self.db.connection() as conn:
            original = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-antigo", "Pessoa", "pessoa@empresa.com", papel_padrao="CONSULTA"
            )
            repo.atualizar_papel_usuario(conn, original.id, "ANALISTA")

            atualizado = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "oid-novo", "Pessoa", "pessoa@empresa.com", papel_padrao="CONSULTA"
            )
            usuarios = repo.listar_usuarios(conn)

        self.assertEqual(len(usuarios), 1)
        self.assertEqual(atualizado.id, original.id)
        self.assertEqual(atualizado.microsoft_oid, "oid-novo")
        self.assertEqual(atualizado.papel, "ANALISTA", "o papel não deveria ter sido resetado")

    def test_segundo_e_terceiro_usuario_recebem_papel_padrao_normalmente(self):
        with self.db.connection() as conn:
            repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-1", "Um", "um@e.com", papel_padrao="CONSULTA")
            dois = repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-2", "Dois", "dois@e.com", papel_padrao="CONSULTA")
            tres = repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-3", "Três", "tres@e.com", papel_padrao="CONSULTA")
        self.assertEqual(dois.papel, "CONSULTA")
        self.assertEqual(tres.papel, "CONSULTA")

    def test_buscar_equipamentos_por_termo_casa_ativo_serie_e_colaborador(self):
        with self.db.connection() as conn:
            analista = repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-a", "A", "a@e.com")
            repo.criar_equipamento(conn, nr_ativo="XYZ-1", tipo="Notebook", nr_serie="SERIE-999")
            repo.criar_equipamento(conn, nr_ativo="OUTRO-2", tipo="Desktop")

            por_serie = repo.buscar_equipamentos(conn, termo="SERIE-999")
            por_ativo = repo.buscar_equipamentos(conn, termo="XYZ")

        self.assertEqual(len(por_serie), 1)
        self.assertEqual(por_serie[0].nr_ativo, "XYZ-1")
        self.assertEqual(len(por_ativo), 1)


class TesteSistemaNasceZerado(unittest.TestCase):
    """O sistema precisa servir qualquer empresa sem nenhum dado de exemplo
    pré-carregado — nem empresas, nem tipos de equipamento. Estes testes
    travam esse comportamento: se algum dia alguém reintroduzir uma lista
    fixa ou um seed de dados por engano, é aqui que vai quebrar."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.db = Database(self.db_path)
        self.db.init_schema()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_banco_novo_nao_tem_nenhuma_empresa_pre_cadastrada(self):
        with self.db.connection() as conn:
            empresas = repo.listar_empresas(conn)
        self.assertEqual(empresas, [], "o banco não deveria vir com nenhuma empresa de exemplo")

    def test_banco_novo_nao_tem_nenhum_tipo_de_equipamento_pre_cadastrado(self):
        with self.db.connection() as conn:
            tipos = repo.listar_tipos_equipamento_usados(conn)
        self.assertEqual(tipos, [], "o banco não deveria vir com nenhum tipo de equipamento de exemplo")

    def test_tipos_de_equipamento_aparecem_conforme_sao_cadastrados(self):
        with self.db.connection() as conn:
            repo.criar_equipamento(conn, nr_ativo="A-1", tipo="Servidor")
            repo.criar_equipamento(conn, nr_ativo="A-2", tipo="Roteador")
            repo.criar_equipamento(conn, nr_ativo="A-3", tipo="Servidor")  # repetido, não deve duplicar
            tipos = repo.listar_tipos_equipamento_usados(conn)
        self.assertEqual(tipos, ["Roteador", "Servidor"])  # ordem alfabética, sem duplicar

    def test_empresa_aparece_na_lista_assim_que_alguem_a_usa(self):
        with self.db.connection() as conn:
            self.assertEqual(repo.listar_empresas(conn), [])
            repo.obter_ou_criar_empresa(conn, "Qualquer Empresa Ltda")
            nomes = [e.nome for e in repo.listar_empresas(conn)]
        self.assertEqual(nomes, ["Qualquer Empresa Ltda"])


if __name__ == "__main__":
    unittest.main()
