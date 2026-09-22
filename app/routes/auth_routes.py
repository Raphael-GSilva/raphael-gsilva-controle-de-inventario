"""Rotas de autenticação. Funcionam nos dois modos (mock e microsoft) —
o modo é decidido uma vez, a partir de current_app.config['AUTH_MODE'],
e cada modo delega para o provedor correspondente em app/auth/.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import repositories as repo
from app.auth import microsoft_provider, mock_provider

bp = Blueprint("auth", __name__)


def _completar_login(microsoft_oid: str, tenant_id: str, nome: str, email: str) -> None:
    db = current_app.extensions["db"]
    with db.connection() as conn:
        usuario = repo.criar_ou_atualizar_usuario_microsoft(
            conn,
            microsoft_oid,
            nome,
            email,
            tenant_id=tenant_id,
            papel_padrao=current_app.config["PAPEL_PADRAO_NOVO_USUARIO"],
        )
    session.clear()
    session["user_id"] = usuario.id


def _redirecionar_pos_login():
    destino = session.pop("proxima_url", None)
    return redirect(destino or url_for("dashboard.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("usuario_atual") is not None:
        return redirect(url_for("dashboard.index"))

    modo = current_app.config["AUTH_MODE"]

    if modo == "microsoft":
        return microsoft_provider.iniciar_login()

    # --- modo mock (desenvolvimento/testes) — não existe tenant real ---
    if request.method == "POST":
        resultado = mock_provider.processar_login_mock()
        if resultado is None:
            return render_template(
                "login.html", modo_mock=True, erro="Preencha um nome e um e-mail válido."
            )
        microsoft_oid, nome, email = resultado
        _completar_login(microsoft_oid, "", nome, email)
        return _redirecionar_pos_login()

    return mock_provider.tela_login_mock()


@bp.route("/auth/callback")
def callback():
    try:
        microsoft_oid, tenant_id, nome, email = microsoft_provider.processar_callback()
    except microsoft_provider.ErroDeLogin as erro:
        return render_template("login.html", modo_mock=False, erro=str(erro))

    _completar_login(microsoft_oid, tenant_id, nome, email)
    return _redirecionar_pos_login()


@bp.route("/logout")
def logout():
    modo = current_app.config["AUTH_MODE"]
    session.clear()
    if modo == "microsoft":
        url_pos_logout = url_for("auth.login", _external=True)
        return redirect(microsoft_provider.url_logout_microsoft(url_pos_logout))
    return redirect(url_for("auth.login"))
