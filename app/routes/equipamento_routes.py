"""Rotas de consulta de equipamentos: busca com filtros e detalhe individual
com o histórico completo de movimentações."""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, request

from app import repositories as repo
from app.auth.decorators import login_required
from app.models import StatusEquipamento

bp = Blueprint("equipamentos", __name__, url_prefix="/equipamentos")


@bp.route("/")
@login_required
def lista():
    termo = request.args.get("q", "").strip() or None
    status = request.args.get("status") or None
    tipo = request.args.get("tipo") or None
    empresa_id = request.args.get("empresa_id", type=int)

    db = current_app.extensions["db"]
    with db.connection() as conn:
        equipamentos = repo.buscar_equipamentos(
            conn, termo=termo, status=status, tipo=tipo, empresa_id=empresa_id
        )
        empresas = repo.listar_empresas(conn)
        tipo_opcoes = repo.listar_tipos_equipamento_usados(conn)

    return render_template(
        "equipamentos/lista.html",
        equipamentos=equipamentos,
        empresas=empresas,
        status_opcoes=StatusEquipamento.TODOS,
        status_labels=StatusEquipamento.LABELS,
        tipo_opcoes=tipo_opcoes,
        filtros={"q": termo or "", "status": status or "", "tipo": tipo or "", "empresa_id": empresa_id or ""},
    )


@bp.route("/<int:equipamento_id>")
@login_required
def detalhe(equipamento_id: int):
    db = current_app.extensions["db"]
    with db.connection() as conn:
        equipamento = repo.obter_equipamento_por_id(conn, equipamento_id)
        if not equipamento:
            return render_template("erro_404.html", mensagem="Equipamento não encontrado."), 404
        historico = repo.listar_movimentacoes_por_equipamento(conn, equipamento_id)

    return render_template("equipamentos/detalhe.html", equipamento=equipamento, historico=historico)
