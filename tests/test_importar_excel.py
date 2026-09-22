"""Testa scripts/importar_excel.py de ponta a ponta, chamando-o exatamente
como o usuário chamaria (subprocess), para não se distanciar do
comportamento real da ferramenta de linha de comando.

O caso mais importante aqui é o último: importar uma planilha desatualizada
por cima de um equipamento que já foi devolvido ao vivo pelo sistema NÃO
pode re-alocá-lo."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

import openpyxl

from app.db import Database
from app import repositories as repo

RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ_PROJETO, "scripts", "importar_excel.py")


def _rodar_script(*args: str, db_path: str) -> subprocess.CompletedProcess:
    ambiente = dict(os.environ, DATABASE_PATH=db_path, AUTH_MODE="mock")
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=RAIZ_PROJETO,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TesteImportarExcel(unittest.TestCase):
    def setUp(self):
        fd_db, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd_db)
        os.unlink(self.db_path)

        fd_xlsx, self.xlsx_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd_xlsx)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Nº Ativo", "Nº de Série", "Tipo Equip.", "Empresa", "Nome Colaborador", "Nº Chamado"])
        ws.append(["IMP-001", "SER-1", "Notebook", "Empresa A", "Maria Souza", "RITM0001"])
        ws.append(["IMP-002", "SER-2", "Desktop", "Empresa B", "", ""])
        wb.save(self.xlsx_path)

    def tearDown(self):
        for caminho in (self.db_path, self.xlsx_path):
            if os.path.exists(caminho):
                os.unlink(caminho)

    def test_simulacao_nao_grava_nenhum_equipamento(self):
        r = _rodar_script(self.xlsx_path, db_path=self.db_path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SIMULAÇÃO", r.stdout)

        db = Database(self.db_path)
        with db.connection() as conn:
            equipamentos = repo.buscar_equipamentos(conn)
        self.assertEqual(equipamentos, [])

    def test_confirmar_cria_equipamentos_com_status_correto(self):
        r = _rodar_script(self.xlsx_path, "--confirmar", db_path=self.db_path)
        self.assertEqual(r.returncode, 0, r.stderr)

        db = Database(self.db_path)
        with db.connection() as conn:
            com_colaborador = repo.obter_equipamento_por_nr_ativo(conn, "IMP-001")
            sem_colaborador = repo.obter_equipamento_por_nr_ativo(conn, "IMP-002")

        self.assertEqual(com_colaborador.status, "ALOCADO")
        self.assertEqual(com_colaborador.colaborador_atual, "Maria Souza")
        self.assertEqual(sem_colaborador.status, "EM_ESTOQUE")

    def test_reimportar_planilha_desatualizada_nao_sobrescreve_devolucao_ja_feita(self):
        """O teste mais importante deste arquivo: um equipamento devolvido
        ao vivo pelo sistema não pode ser re-alocado por causa de uma
        planilha antiga sendo reimportada por engano."""
        _rodar_script(self.xlsx_path, "--confirmar", db_path=self.db_path)

        db = Database(self.db_path)
        with db.connection() as conn:
            usuario = repo.criar_ou_atualizar_usuario_microsoft(conn, "oid-1", "Admin", "admin@empresa.com")
            from app.services import movimentacao_service as svc

            svc.registrar_devolucao(
                conn, nr_ativo="IMP-001", condicao_devolucao="Bom", analista_id=usuario.id
            )

        r = _rodar_script(self.xlsx_path, "--confirmar", db_path=self.db_path)
        self.assertEqual(r.returncode, 0, r.stderr)

        with db.connection() as conn:
            equipamento = repo.obter_equipamento_por_nr_ativo(conn, "IMP-001")
            historico = repo.listar_movimentacoes_por_equipamento(conn, equipamento.id)

        self.assertEqual(
            equipamento.status, "EM_ESTOQUE",
            "reimportar a planilha antiga não deveria ter re-alocado o equipamento",
        )
        self.assertEqual(len(historico), 3, "não deveria ter duplicado nenhuma movimentação")

    def test_rodar_duas_vezes_seguidas_nao_duplica(self):
        _rodar_script(self.xlsx_path, "--confirmar", db_path=self.db_path)
        _rodar_script(self.xlsx_path, "--confirmar", db_path=self.db_path)

        db = Database(self.db_path)
        with db.connection() as conn:
            equipamentos = repo.buscar_equipamentos(conn)
            equipamento = repo.obter_equipamento_por_nr_ativo(conn, "IMP-001")
            historico = repo.listar_movimentacoes_por_equipamento(conn, equipamento.id)

        self.assertEqual(len(equipamentos), 2, "reimportar não deveria criar duplicatas")
        self.assertEqual(len(historico), 2, "reimportar não deveria duplicar o histórico (ENTRADA + ENTREGA)")


if __name__ == "__main__":
    unittest.main()
