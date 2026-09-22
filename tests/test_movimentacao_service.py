"""Testes da camada de regras de negócio (app/services/movimentacao_service.py)
sem passar por HTTP — testa diretamente contra um banco temporário.

Esta é a parte mais crítica do sistema: se algo aqui quebrar, o inventário
pode ficar com um equipamento "fantasma" (alocado a duas pessoas, ou
devolvido sem nunca ter sido entregue). Por isso cobrimos explicitamente
os casos de transição inválida, não só o caminho feliz.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from app.db import Database
from app.models import StatusEquipamento
from app.services import movimentacao_service as svc
from app import repositories as repo


class TesteMovimentacaoService(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.db = Database(self.db_path)
        self.db.init_schema()
        with self.db.connection() as conn:
            self.analista = repo.criar_ou_atualizar_usuario_microsoft(
                conn, "mock-1", "Analista Teste", "analista@teste.com", papel_padrao="ANALISTA"
            )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_entrada_cria_equipamento_em_estoque(self):
        with self.db.connection() as conn:
            equipamento, mov = svc.registrar_entrada(
                conn, nr_ativo="NB-100", tipo="Notebook", analista_id=self.analista.id
            )
        self.assertEqual(equipamento.status, StatusEquipamento.EM_ESTOQUE)
        self.assertEqual(mov.tipo, "ENTRADA")

    def test_entrada_com_nr_ativo_duplicado_falha(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-101", tipo="Notebook", analista_id=self.analista.id)
        with self.assertRaises(repo.ViolacaoDeUnicidade):
            with self.db.connection() as conn:
                svc.registrar_entrada(conn, nr_ativo="NB-101", tipo="Desktop", analista_id=self.analista.id)

    def test_ciclo_completo_entrada_entrega_devolucao(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-200", tipo="Notebook", analista_id=self.analista.id)

        with self.db.connection() as conn:
            equipamento, _ = svc.registrar_entrega(
                conn,
                nr_ativo="NB-200",
                nome_colaborador="Fulano de Tal",
                empresa_colaborador="Empresa A",
                analista_id=self.analista.id,
            )
        self.assertEqual(equipamento.status, StatusEquipamento.ALOCADO)
        self.assertEqual(equipamento.colaborador_atual, "Fulano de Tal")

        with self.db.connection() as conn:
            equipamento, _ = svc.registrar_devolucao(
                conn, nr_ativo="NB-200", condicao_devolucao="Bom", analista_id=self.analista.id
            )
        self.assertEqual(equipamento.status, StatusEquipamento.EM_ESTOQUE)
        self.assertIsNone(equipamento.colaborador_atual)

    def test_devolucao_ruim_vai_para_manutencao(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-201", tipo="Notebook", analista_id=self.analista.id)
            svc.registrar_entrega(
                conn, nr_ativo="NB-201", nome_colaborador="Beltrano", empresa_colaborador="Empresa C",
                analista_id=self.analista.id,
            )
        with self.db.connection() as conn:
            equipamento, _ = svc.registrar_devolucao(
                conn, nr_ativo="NB-201", condicao_devolucao="Ruim", analista_id=self.analista.id
            )
        self.assertEqual(equipamento.status, StatusEquipamento.MANUTENCAO)

    def test_nao_pode_entregar_equipamento_ja_alocado(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-202", tipo="Notebook", analista_id=self.analista.id)
            svc.registrar_entrega(
                conn, nr_ativo="NB-202", nome_colaborador="Primeira Pessoa", empresa_colaborador="Empresa A",
                analista_id=self.analista.id,
            )
        with self.assertRaises(svc.TransicaoInvalida):
            with self.db.connection() as conn:
                svc.registrar_entrega(
                    conn, nr_ativo="NB-202", nome_colaborador="Segunda Pessoa", empresa_colaborador="Empresa B",
                    analista_id=self.analista.id,
                )

    def test_nao_pode_devolver_equipamento_em_estoque(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-203", tipo="Notebook", analista_id=self.analista.id)
        with self.assertRaises(svc.TransicaoInvalida):
            with self.db.connection() as conn:
                svc.registrar_devolucao(
                    conn, nr_ativo="NB-203", condicao_devolucao="Bom", analista_id=self.analista.id
                )

    def test_entrega_de_equipamento_inexistente_falha_com_erro_claro(self):
        with self.assertRaises(repo.NaoEncontrado):
            with self.db.connection() as conn:
                svc.registrar_entrega(
                    conn, nr_ativo="NAO-EXISTE", nome_colaborador="Alguém", empresa_colaborador="Empresa A",
                    analista_id=self.analista.id,
                )

    def test_entrega_sem_nome_colaborador_falha(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-204", tipo="Notebook", analista_id=self.analista.id)
        with self.assertRaises(ValueError):
            with self.db.connection() as conn:
                svc.registrar_entrega(
                    conn, nr_ativo="NB-204", nome_colaborador="   ", empresa_colaborador="Empresa A",
                    analista_id=self.analista.id,
                )

    def test_devolucao_com_condicao_invalida_falha(self):
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-205", tipo="Notebook", analista_id=self.analista.id)
            svc.registrar_entrega(
                conn, nr_ativo="NB-205", nome_colaborador="Alguém", empresa_colaborador="Empresa A",
                analista_id=self.analista.id,
            )
        with self.assertRaises(ValueError):
            with self.db.connection() as conn:
                svc.registrar_devolucao(
                    conn, nr_ativo="NB-205", condicao_devolucao="Excelente", analista_id=self.analista.id
                )

    def test_rollback_automatico_em_caso_de_erro(self):
        """Se uma operação no meio de uma transação falhar, nada deve ser
        gravado — o context manager de Database.connection() deve dar
        rollback automaticamente."""
        with self.db.connection() as conn:
            svc.registrar_entrada(conn, nr_ativo="NB-206", tipo="Notebook", analista_id=self.analista.id)

        try:
            with self.db.connection() as conn:
                repo.atualizar_status_equipamento(
                    conn,
                    repo.obter_equipamento_por_nr_ativo(conn, "NB-206").id,
                    status=StatusEquipamento.ALOCADO,
                    colaborador_atual="Temporário",
                    empresa_colaborador_atual="Empresa A",
                )
                raise ValueError("Erro simulado no meio da transação")
        except ValueError:
            pass

        with self.db.connection() as conn:
            equipamento = repo.obter_equipamento_por_nr_ativo(conn, "NB-206")
        self.assertEqual(equipamento.status, StatusEquipamento.EM_ESTOQUE)


if __name__ == "__main__":
    unittest.main()
