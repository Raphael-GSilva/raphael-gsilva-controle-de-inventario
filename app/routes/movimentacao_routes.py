"""Rotas de entrada, entrega e devolução de equipamentos.

Todas exigem papel ADMIN ou ANALISTA (usuários CONSULTA só podem visualizar,
não registrar movimentações — ver app/models.py PapelUsuario).

Depois de cada movimentação bem-sucedida, tentamos sincronizar com o
SharePoint em seguida. Se a sincronização falhar (rede fora, credencial
expirada, etc.) isso NUNCA desfaz nem bloqueia a movimentação, que já foi
gravada com sucesso no banco local — só avisamos o usuário que a cópia do
SharePoint vai ficar desatualizada até a próxima sincronização.
"""

from __future__ import annotations

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app import repositories as repo
from app.auth.decorators import papel_required
from app.services import movimentacao_service as svc
from app.sharepoint.sync_service import tentar_sincronizar_equipamento

bp = Blueprint("movimentacoes", __name__, url_prefix="/movimentacoes")


@bp.route("/historico")
@papel_required("ADMIN", "ANALISTA", "CONSULTA")
def historico():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        movimentacoes = repo.listar_movimentacoes_recentes(conn, limite=100)
    return render_template("movimentacoes/historico.html", movimentacoes=movimentacoes)


@bp.route("/entrada", methods=["GET", "POST"])
@papel_required("ADMIN", "ANALISTA")
def entrada():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        empresas = repo.listar_empresas(conn)
        tipos = repo.listar_tipos_equipamento_usados(conn)

    if request.method == "POST":
        form = request.form
        try:
            with db.connection() as conn:
                equipamento, _mov = svc.registrar_entrada(
                    conn,
                    nr_ativo=form["nr_ativo"].strip(),
                    tipo=form["tipo"],
                    analista_id=g.usuario_atual.id,
                    nr_serie=form.get("nr_serie", "").strip() or None,
                    modelo=form.get("modelo", "").strip() or None,
                    empresa_nome=form.get("empresa_nome") or None,
                    owner_ativo=form.get("owner_ativo", "").strip() or None,
                    data_recebimento=form.get("data_recebimento") or None,
                    maquina_preparada=form.get("maquina_preparada") == "on",
                    previsao_alocacao=form.get("previsao_alocacao") == "on",
                    observacoes=form.get("observacoes", "").strip() or None,
                    nr_chamado=form.get("nr_chamado", "").strip() or None,
                )
            flash(f"Equipamento {equipamento.nr_ativo} registrado em estoque.", "sucesso")
            tentar_sincronizar_equipamento(equipamento.id)
            return redirect(url_for("equipamentos.detalhe", equipamento_id=equipamento.id))
        except repo.ViolacaoDeUnicidade as erro:
            flash(str(erro), "erro")
        except (ValueError, KeyError) as erro:
            flash(f"Dados inválidos: {erro}", "erro")

    return render_template("movimentacoes/entrada.html", empresas=empresas, tipos=tipos)


@bp.route("/entrega", methods=["GET", "POST"])
@papel_required("ADMIN", "ANALISTA")
def entrega():
    db = current_app.extensions["db"]

    if request.method == "POST":
        form = request.form
        try:
            with db.connection() as conn:
                equipamento, _mov = svc.registrar_entrega(
                    conn,
                    nr_ativo=form["nr_ativo"].strip(),
                    nome_colaborador=form["nome_colaborador"].strip(),
                    empresa_colaborador=form.get("empresa_colaborador", "").strip(),
                    analista_id=g.usuario_atual.id,
                    nr_chamado=form.get("nr_chamado", "").strip() or None,
                    observacoes=form.get("observacoes", "").strip() or None,
                )
            flash(
                f"Equipamento {equipamento.nr_ativo} entregue a {equipamento.colaborador_atual}.",
                "sucesso",
            )
            tentar_sincronizar_equipamento(equipamento.id)
            return redirect(url_for("equipamentos.detalhe", equipamento_id=equipamento.id))
        except repo.NaoEncontrado as erro:
            flash(str(erro), "erro")
        except svc.TransicaoInvalida as erro:
            flash(str(erro), "erro")
        except (ValueError, KeyError) as erro:
            flash(f"Dados inválidos: {erro}", "erro")

    return render_template("movimentacoes/entrega.html")


@bp.route("/devolucao", methods=["GET", "POST"])
@papel_required("ADMIN", "ANALISTA")
def devolucao():
    db = current_app.extensions["db"]

    if request.method == "POST":
        form = request.form
        try:
            with db.connection() as conn:
                equipamento, _mov = svc.registrar_devolucao(
                    conn,
                    nr_ativo=form["nr_ativo"].strip(),
                    condicao_devolucao=form["condicao_devolucao"],
                    analista_id=g.usuario_atual.id,
                    nr_chamado=form.get("nr_chamado", "").strip() or None,
                    observacoes=form.get("observacoes", "").strip() or None,
                )
            flash(f"Devolução de {equipamento.nr_ativo} registrada.", "sucesso")
            tentar_sincronizar_equipamento(equipamento.id)
            return redirect(url_for("equipamentos.detalhe", equipamento_id=equipamento.id))
        except repo.NaoEncontrado as erro:
            flash(str(erro), "erro")
        except svc.TransicaoInvalida as erro:
            flash(str(erro), "erro")
        except (ValueError, KeyError) as erro:
            flash(f"Dados inválidos: {erro}", "erro")

    return render_template("movimentacoes/devolucao.html")
