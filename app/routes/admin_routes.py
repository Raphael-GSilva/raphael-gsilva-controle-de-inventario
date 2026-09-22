"""Administração de usuários: listar quem já logou no sistema e mudar o
papel de cada um (CONSULTA / ANALISTA / ADMIN). Só ADMIN acessa.

Sem esta tela, a única forma de promover alguém seria mexer direto no
banco (scripts/promover_admin.py) — viável para o primeiro admin, mas não
como processo contínuo para um time.
"""

from __future__ import annotations

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app import repositories as repo
from app.auth.decorators import papel_required
from app.models import PapelUsuario

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAPEIS_VALIDOS = (PapelUsuario.ADMIN, PapelUsuario.ANALISTA, PapelUsuario.CONSULTA)


@bp.route("/usuarios")
@papel_required("ADMIN")
def usuarios():
    db = current_app.extensions["db"]
    with db.connection() as conn:
        lista = repo.listar_usuarios(conn)
    return render_template("admin/usuarios.html", usuarios=lista, papeis=PAPEIS_VALIDOS)


@bp.route("/usuarios/<int:usuario_id>/papel", methods=["POST"])
@papel_required("ADMIN")
def alterar_papel(usuario_id: int):
    novo_papel = request.form.get("papel")
    if novo_papel not in PAPEIS_VALIDOS:
        flash("Papel inválido.", "erro")
        return redirect(url_for("admin.usuarios"))

    if usuario_id == g.usuario_atual.id and novo_papel != PapelUsuario.ADMIN:
        flash("Você não pode remover o próprio papel de administrador por aqui.", "erro")
        return redirect(url_for("admin.usuarios"))

    db = current_app.extensions["db"]
    with db.connection() as conn:
        repo.atualizar_papel_usuario(conn, usuario_id, novo_papel)
    flash("Papel atualizado.", "sucesso")
    return redirect(url_for("admin.usuarios"))
