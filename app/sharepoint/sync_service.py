"""Sincronização entre o banco local (fonte da verdade) e a planilha do
SharePoint (cópia espelhada, para quem prefere olhar/filtrar no Excel).

Duas direções, com responsabilidades bem separadas:

1) tentar_sincronizar_equipamento(equipamento_id) — chamada depois de toda
   entrada/entrega/devolução. Roda em uma thread separada para não atrasar
   a resposta ao usuário, e NUNCA levanta exceção para quem chamou: se
   falhar, só fica registrado no log. O equipamento já foi salvo com
   sucesso no banco local antes disso ser sequer chamado.

2) importar_do_sharepoint(app) — chamada manualmente (botão no dashboard,
   ou pelo script scripts/importar_excel.py) para trazer linhas que alguém
   tenha criado ou editado direto na planilha. Só atualiza campos de
   "catálogo" (série, modelo) em equipamentos que já existem — nunca
   sobrescreve status ou colaborador atual, porque esses só devem mudar
   através de uma movimentação registrada no próprio sistema. Isso evita
   que uma edição manual desalinhada na planilha corrompa o estado.

MAPEAMENTO_COLUNAS abaixo é o único lugar que você precisa editar se os
nomes das colunas na sua tabela do SharePoint forem diferentes dos
sugeridos.
"""

from __future__ import annotations

import threading

from flask import current_app

from app import repositories as repo
from app.models import Equipamento
from app.sharepoint.graph_client import GraphClient

# Ajuste os valores (nomes de coluna) para bater com o cabeçalho exato da
# sua tabela no SharePoint. As chaves (lado esquerdo) não devem mudar.
MAPEAMENTO_COLUNAS = {
    "nr_ativo": "Nr. Ativo",
    "nr_serie": "Nº de Série",
    "tipo": "Tipo Equip.",
    "modelo": "Modelo",
    "empresa_nome": "Empresa",
    "owner_ativo": "Owner Ativo",
    "status_label": "Status",
    "colaborador_atual": "Nome",
    "data_recebimento": "Data Recebimento",
    "maquina_preparada": "Máq. Preparada",
    "previsao_alocacao": "Previsão Alocação",
    "observacoes": "Observações",
}


def _cliente_graph(app) -> GraphClient:
    return GraphClient(
        tenant_id=app.config["GRAPH_TENANT_ID"],
        client_id=app.config["GRAPH_CLIENT_ID"],
        client_secret=app.config["GRAPH_CLIENT_SECRET"],
    )


def _config_tabela(app) -> tuple[str, str, str, str]:
    return (
        app.config["SHAREPOINT_DRIVE_ID"],
        app.config["SHAREPOINT_ITEM_ID"],
        app.config["SHAREPOINT_WORKSHEET_NAME"],
        app.config["SHAREPOINT_TABLE_NAME"],
    )


def _montar_valores_linha(equipamento: Equipamento, cabecalhos: list[str]) -> list:
    dados = {
        "nr_ativo": equipamento.nr_ativo,
        "nr_serie": equipamento.nr_serie or "",
        "tipo": equipamento.tipo,
        "modelo": equipamento.modelo or "",
        "empresa_nome": equipamento.empresa_nome or "",
        "owner_ativo": equipamento.owner_ativo or "",
        "status_label": equipamento.status_label,
        "colaborador_atual": equipamento.colaborador_atual or "",
        "data_recebimento": equipamento.data_recebimento or "",
        "maquina_preparada": "SIM" if equipamento.maquina_preparada else "NÃO",
        "previsao_alocacao": "SIM" if equipamento.previsao_alocacao else "NÃO",
        "observacoes": equipamento.observacoes or "",
    }
    coluna_para_valor = {
        MAPEAMENTO_COLUNAS[campo]: valor
        for campo, valor in dados.items()
        if campo in MAPEAMENTO_COLUNAS
    }
    return [coluna_para_valor.get(cabecalho, "") for cabecalho in cabecalhos]


def enviar_equipamento_para_sharepoint(app, equipamento: Equipamento) -> str:
    """Envia (cria ou atualiza) a linha de UM equipamento na planilha.
    Devolve a chave da linha (índice na tabela) para salvar em
    equipamento.sharepoint_row_key."""
    cliente = _cliente_graph(app)
    drive_id, item_id, worksheet, table = _config_tabela(app)

    cabecalhos = cliente.listar_colunas(drive_id, item_id, worksheet, table)
    valores = _montar_valores_linha(equipamento, cabecalhos)

    if equipamento.sharepoint_row_key:
        cliente.atualizar_linha(
            drive_id, item_id, worksheet, table, int(equipamento.sharepoint_row_key), valores
        )
        return equipamento.sharepoint_row_key

    resultado = cliente.adicionar_linha(drive_id, item_id, worksheet, table, valores)
    novo_indice = resultado.get("index")
    return str(novo_indice) if novo_indice is not None else "0"


def _sincronizar_em_thread(app, equipamento_id: int) -> None:
    with app.app_context():
        db = app.extensions["db"]
        try:
            with db.connection() as conn:
                equipamento = repo.obter_equipamento_por_id(conn, equipamento_id)
            if not equipamento:
                return
            row_key = enviar_equipamento_para_sharepoint(app, equipamento)
            with db.connection() as conn:
                repo.marcar_sincronizado(conn, equipamento_id, row_key)
        except Exception as exc:  # noqa: BLE001 — best-effort de propósito, ver docstring do módulo
            app.logger.warning(
                "Falha ao sincronizar equipamento %s com o SharePoint: %s", equipamento_id, exc
            )


def tentar_sincronizar_equipamento(equipamento_id: int) -> None:
    """Dispara a sincronização em segundo plano, se estiver habilitada.
    Retorna imediatamente — nunca bloqueia a requisição HTTP."""
    if not current_app.config.get("SHAREPOINT_SYNC_ENABLED"):
        return
    app = current_app._get_current_object()
    threading.Thread(target=_sincronizar_em_thread, args=(app, equipamento_id), daemon=True).start()


def importar_do_sharepoint(app) -> dict[str, int]:
    """Lê todas as linhas da tabela no SharePoint e cria/atualiza os
    equipamentos correspondentes localmente, casando pelo nº de ativo.
    Só toca em campos de catálogo — nunca em status/colaborador atual."""
    cliente = _cliente_graph(app)
    drive_id, item_id, worksheet, table = _config_tabela(app)

    cabecalhos = cliente.listar_colunas(drive_id, item_id, worksheet, table)
    linhas = cliente.listar_linhas(drive_id, item_id, worksheet, table)

    resumo = {"criados": 0, "atualizados": 0, "ignorados": 0}
    db = app.extensions["db"]

    col_ativo = MAPEAMENTO_COLUNAS["nr_ativo"]
    col_serie = MAPEAMENTO_COLUNAS["nr_serie"]
    col_tipo = MAPEAMENTO_COLUNAS["tipo"]
    col_modelo = MAPEAMENTO_COLUNAS["modelo"]

    with db.connection() as conn:
        for linha in linhas:
            valores = linha.get("values", [[]])[0]
            dados = dict(zip(cabecalhos, valores))
            nr_ativo = str(dados.get(col_ativo, "")).strip()
            if not nr_ativo:
                resumo["ignorados"] += 1
                continue

            existente = repo.obter_equipamento_por_nr_ativo(conn, nr_ativo)
            nr_serie = str(dados.get(col_serie, "")).strip() or None
            modelo = str(dados.get(col_modelo, "")).strip() or None

            if existente:
                repo.atualizar_equipamento(
                    conn,
                    existente.id,
                    nr_serie=nr_serie or existente.nr_serie,
                    modelo=modelo or existente.modelo,
                )
                resumo["atualizados"] += 1
            else:
                tipo = str(dados.get(col_tipo, "")).strip() or "Outro"
                repo.criar_equipamento(
                    conn, nr_ativo=nr_ativo, tipo=tipo, nr_serie=nr_serie, modelo=modelo
                )
                resumo["criados"] += 1

    return resumo
