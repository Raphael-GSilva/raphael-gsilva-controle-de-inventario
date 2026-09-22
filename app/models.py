"""Dataclasses que representam as entidades do sistema.

Servem como a "forma" tipada dos dados em toda a aplicação — routes e
templates nunca manipulam sqlite3.Row diretamente, sempre um destes objetos.
Isso evita erros bobos de nome de coluna errado, que só apareceriam em
tempo de execução se usássemos dicionários soltos.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime


class StatusEquipamento:
    EM_ESTOQUE = "EM_ESTOQUE"
    ALOCADO = "ALOCADO"
    MANUTENCAO = "MANUTENCAO"
    BAIXADO = "BAIXADO"

    LABELS = {
        EM_ESTOQUE: "Em estoque",
        ALOCADO: "Alocado",
        MANUTENCAO: "Em manutenção",
        BAIXADO: "Baixado",
    }

    TODOS = [EM_ESTOQUE, ALOCADO, MANUTENCAO, BAIXADO]


class TipoMovimentacao:
    ENTRADA = "ENTRADA"
    ENTREGA = "ENTREGA"
    DEVOLUCAO = "DEVOLUCAO"

    LABELS = {
        ENTRADA: "Entrada",
        ENTREGA: "Entrega",
        DEVOLUCAO: "Devolução",
    }


class PapelUsuario:
    ADMIN = "ADMIN"
    ANALISTA = "ANALISTA"
    CONSULTA = "CONSULTA"

    # Papéis autorizados a registrar movimentações (entrada/entrega/devolução)
    PODEM_MOVIMENTAR = {ADMIN, ANALISTA}


# Não existe mais uma lista fixa de tipos de equipamento (como
# "Notebook Padrão", "Monitor 22'" etc.) — isso era específico de uma
# empresa em particular. O campo "tipo" no formulário de entrada é texto
# livre; as sugestões que aparecem nele vêm dos tipos que a própria
# empresa que estiver usando o sistema já cadastrou (ver
# repositories.listar_tipos_equipamento_usados), crescendo organicamente
# a partir de uma base zerada.


@dataclass
class Empresa:
    id: int
    nome: str

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Empresa":
        return Empresa(id=row["id"], nome=row["nome"])


@dataclass
class Usuario:
    id: int
    microsoft_oid: str | None
    tenant_id: str
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: str
    ultimo_login: str | None

    @property
    def pode_movimentar(self) -> bool:
        return self.papel in PapelUsuario.PODEM_MOVIMENTAR

    @property
    def eh_admin(self) -> bool:
        return self.papel == PapelUsuario.ADMIN

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Usuario":
        return Usuario(
            id=row["id"],
            microsoft_oid=row["microsoft_oid"],
            tenant_id=row["tenant_id"] if "tenant_id" in row.keys() else "",
            nome=row["nome"],
            email=row["email"],
            papel=row["papel"],
            ativo=bool(row["ativo"]),
            criado_em=row["criado_em"],
            ultimo_login=row["ultimo_login"],
        )


@dataclass
class Equipamento:
    id: int
    nr_ativo: str
    nr_serie: str | None
    tipo: str
    modelo: str | None
    empresa_id: int | None
    empresa_nome: str | None
    owner_ativo: str | None
    status: str
    colaborador_atual: str | None
    empresa_colaborador_atual: str | None
    data_recebimento: str | None
    maquina_preparada: bool
    previsao_alocacao: bool
    observacoes: str | None
    criado_em: str
    atualizado_em: str
    sharepoint_row_key: str | None
    sincronizado_em: str | None

    @property
    def status_label(self) -> str:
        return StatusEquipamento.LABELS.get(self.status, self.status)

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Equipamento":
        keys = row.keys()
        return Equipamento(
            id=row["id"],
            nr_ativo=row["nr_ativo"],
            nr_serie=row["nr_serie"],
            tipo=row["tipo"],
            modelo=row["modelo"],
            empresa_id=row["empresa_id"],
            empresa_nome=row["empresa_nome"] if "empresa_nome" in keys else None,
            owner_ativo=row["owner_ativo"],
            status=row["status"],
            colaborador_atual=row["colaborador_atual"],
            empresa_colaborador_atual=row["empresa_colaborador_atual"],
            data_recebimento=row["data_recebimento"],
            maquina_preparada=bool(row["maquina_preparada"]),
            previsao_alocacao=bool(row["previsao_alocacao"]),
            observacoes=row["observacoes"],
            criado_em=row["criado_em"],
            atualizado_em=row["atualizado_em"],
            sharepoint_row_key=row["sharepoint_row_key"],
            sincronizado_em=row["sincronizado_em"],
        )


@dataclass
class Movimentacao:
    id: int
    equipamento_id: int
    tipo: str
    data_movimentacao: str
    nome_colaborador: str | None
    empresa_colaborador: str | None
    nr_chamado: str | None
    condicao_devolucao: str | None
    analista_id: int | None
    analista_nome: str | None
    observacoes: str | None
    criado_em: str
    # Preenchido apenas em consultas que fazem join com equipamentos
    equipamento_nr_ativo: str | None = field(default=None)

    @property
    def tipo_label(self) -> str:
        return TipoMovimentacao.LABELS.get(self.tipo, self.tipo)

    @staticmethod
    def from_row(row: sqlite3.Row) -> "Movimentacao":
        keys = row.keys()
        return Movimentacao(
            id=row["id"],
            equipamento_id=row["equipamento_id"],
            tipo=row["tipo"],
            data_movimentacao=row["data_movimentacao"],
            nome_colaborador=row["nome_colaborador"],
            empresa_colaborador=row["empresa_colaborador"],
            nr_chamado=row["nr_chamado"],
            condicao_devolucao=row["condicao_devolucao"],
            analista_id=row["analista_id"],
            analista_nome=row["analista_nome"] if "analista_nome" in keys else None,
            observacoes=row["observacoes"],
            criado_em=row["criado_em"],
            equipamento_nr_ativo=row["equipamento_nr_ativo"] if "equipamento_nr_ativo" in keys else None,
        )
