r"""Regras de negócio para entrada, entrega e devolução de equipamentos.

Esta é a camada mais importante para o objetivo de "zero falhas": todo
equipamento segue uma máquina de estados simples,

    EM_ESTOQUE --(entrega)--> ALOCADO --(devolução)--> EM_ESTOQUE
                                                     \--> MANUTENCAO (se condição = Ruim)

e cada transição é validada aqui, nunca nas rotas HTTP. Isso significa que
mesmo que uma tela tenha um bug e mande uma requisição "impossível" (ex:
entregar um equipamento que já está com outra pessoa), o banco nunca fica
em um estado inconsistente — a exceção é levantada antes de qualquer
escrita.
"""

from __future__ import annotations

import sqlite3

from app import repositories as repo
from app.models import Equipamento, Movimentacao, StatusEquipamento, TipoMovimentacao


class TransicaoInvalida(Exception):
    """Levantada quando a movimentação pedida não é permitida no estado atual
    do equipamento. A mensagem já vem pronta para mostrar ao usuário."""


def _resolver_equipamento(conn: sqlite3.Connection, nr_ativo: str) -> Equipamento:
    equipamento = repo.obter_equipamento_por_nr_ativo(conn, nr_ativo)
    if not equipamento:
        raise repo.NaoEncontrado(f"Nenhum equipamento encontrado com o nº de ativo '{nr_ativo}'.")
    return equipamento


def registrar_entrada(
    conn: sqlite3.Connection,
    *,
    nr_ativo: str,
    tipo: str,
    analista_id: int | None,
    nr_serie: str | None = None,
    modelo: str | None = None,
    empresa_nome: str | None = None,
    owner_ativo: str | None = None,
    data_recebimento: str | None = None,
    maquina_preparada: bool = False,
    previsao_alocacao: bool = False,
    observacoes: str | None = None,
    nr_chamado: str | None = None,
) -> tuple[Equipamento, Movimentacao]:
    """Registra a entrada de um equipamento novo (ou reincorporado) no estoque."""
    empresa_id = None
    if empresa_nome:
        empresa_id = repo.obter_ou_criar_empresa(conn, empresa_nome).id

    equipamento = repo.criar_equipamento(
        conn,
        nr_ativo=nr_ativo,
        tipo=tipo,
        nr_serie=nr_serie,
        modelo=modelo,
        empresa_id=empresa_id,
        owner_ativo=owner_ativo,
        data_recebimento=data_recebimento,
        maquina_preparada=maquina_preparada,
        previsao_alocacao=previsao_alocacao,
        observacoes=observacoes,
    )
    movimentacao = repo.criar_movimentacao(
        conn,
        equipamento_id=equipamento.id,
        tipo=TipoMovimentacao.ENTRADA,
        analista_id=analista_id,
        nr_chamado=nr_chamado,
        observacoes=observacoes,
    )
    return equipamento, movimentacao


def registrar_entrega(
    conn: sqlite3.Connection,
    *,
    nr_ativo: str,
    nome_colaborador: str,
    empresa_colaborador: str,
    analista_id: int | None,
    nr_chamado: str | None = None,
    observacoes: str | None = None,
) -> tuple[Equipamento, Movimentacao]:
    """Entrega um equipamento em estoque a um colaborador."""
    equipamento = _resolver_equipamento(conn, nr_ativo)

    if equipamento.status != StatusEquipamento.EM_ESTOQUE:
        raise TransicaoInvalida(
            f"O equipamento '{nr_ativo}' não está em estoque (status atual: "
            f"{equipamento.status_label}). Registre a devolução antes de "
            f"entregá-lo novamente."
        )
    if not nome_colaborador or not nome_colaborador.strip():
        raise ValueError("Informe o nome do colaborador que vai receber o equipamento.")

    repo.atualizar_status_equipamento(
        conn,
        equipamento.id,
        status=StatusEquipamento.ALOCADO,
        colaborador_atual=nome_colaborador.strip(),
        empresa_colaborador_atual=empresa_colaborador,
    )
    movimentacao = repo.criar_movimentacao(
        conn,
        equipamento_id=equipamento.id,
        tipo=TipoMovimentacao.ENTREGA,
        analista_id=analista_id,
        nome_colaborador=nome_colaborador.strip(),
        empresa_colaborador=empresa_colaborador,
        nr_chamado=nr_chamado,
        observacoes=observacoes,
    )
    equipamento_atualizado = repo.obter_equipamento_por_id(conn, equipamento.id)
    return equipamento_atualizado, movimentacao  # type: ignore[return-value]


def registrar_devolucao(
    conn: sqlite3.Connection,
    *,
    nr_ativo: str,
    condicao_devolucao: str,
    analista_id: int | None,
    nr_chamado: str | None = None,
    observacoes: str | None = None,
) -> tuple[Equipamento, Movimentacao]:
    """Devolve um equipamento alocado de volta ao estoque (ou manutenção,
    se a condição de devolução for 'Ruim')."""
    equipamento = _resolver_equipamento(conn, nr_ativo)

    if equipamento.status != StatusEquipamento.ALOCADO:
        raise TransicaoInvalida(
            f"O equipamento '{nr_ativo}' não está alocado a ninguém no momento "
            f"(status atual: {equipamento.status_label}), então não há devolução a registrar."
        )
    if condicao_devolucao not in ("Bom", "Regular", "Ruim"):
        raise ValueError("Condição de devolução deve ser Bom, Regular ou Ruim.")

    novo_status = (
        StatusEquipamento.MANUTENCAO if condicao_devolucao == "Ruim" else StatusEquipamento.EM_ESTOQUE
    )
    colaborador_anterior = equipamento.colaborador_atual
    empresa_anterior = equipamento.empresa_colaborador_atual

    repo.atualizar_status_equipamento(
        conn,
        equipamento.id,
        status=novo_status,
        colaborador_atual=None,
        empresa_colaborador_atual=None,
    )
    movimentacao = repo.criar_movimentacao(
        conn,
        equipamento_id=equipamento.id,
        tipo=TipoMovimentacao.DEVOLUCAO,
        analista_id=analista_id,
        nome_colaborador=colaborador_anterior,
        empresa_colaborador=empresa_anterior,
        nr_chamado=nr_chamado,
        condicao_devolucao=condicao_devolucao,
        observacoes=observacoes,
    )
    equipamento_atualizado = repo.obter_equipamento_por_id(conn, equipamento.id)
    return equipamento_atualizado, movimentacao  # type: ignore[return-value]
