"""Rota do dashboard: números agregados e listas rápidas para dar uma visão
geral do inventário assim que a pessoa loga."""

from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, url_for

from app import repositories as repo
from app.auth.decorators import login_required, papel_required
from app.models import StatusEquipamento
from app.sharepoint.sync_service import importar_do_sharepoint

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        por_status = repo.contar_por_status(conn)
        por_tipo = repo.contar_por_tipo(conn)
        por_empresa = repo.contar_por_empresa(conn)
        recentes = repo.listar_movimentacoes_recentes(conn, limite=8)
        pendentes_preparacao = repo.listar_pendentes_preparacao(conn, limite=8)

    total_equipamentos = sum(por_status.values())

    return render_template(
        "dashboard.html",
        total_equipamentos=total_equipamentos,
        por_status=por_status,
        status_labels=StatusEquipamento.LABELS,
        por_tipo=por_tipo,
        por_empresa=por_empresa,
        recentes=recentes,
        pendentes_preparacao=pendentes_preparacao,
        sync_habilitado=current_app.config.get("SHAREPOINT_SYNC_ENABLED", False),
    )


@bp.route("/sincronizar-sharepoint", methods=["POST"])
@papel_required("ADMIN", "ANALISTA")
def sincronizar_sharepoint():
    if not current_app.config.get("SHAREPOINT_SYNC_ENABLED"):
        flash("A sincronização com o SharePoint não está habilitada (ver .env).", "erro")
        return redirect(url_for("dashboard.index"))

    app = current_app._get_current_object()
    try:
        resumo = importar_do_sharepoint(app)
        flash(
            f"Importação concluída: {resumo['criados']} criado(s), "
            f"{resumo['atualizados']} atualizado(s), {resumo['ignorados']} ignorado(s).",
            "sucesso",
        )
    except Exception as erro:  # noqa: BLE001
        flash(f"Falha ao importar do SharePoint: {erro}", "erro")

    return redirect(url_for("dashboard.index"))
