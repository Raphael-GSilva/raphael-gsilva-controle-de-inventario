"""Decorators de autenticação/autorização para as rotas Flask.

Não dependem de qual provedor de login foi usado (mock ou Microsoft) —
só olham para g.usuario_atual, que é populado uma vez por requisição
em app/__init__.py (before_request), a partir da sessão.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, g, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("usuario_atual") is None:
            session["proxima_url"] = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def papel_required(*papeis_permitidos: str):
    """Exige login E que o usuário tenha um dos papéis informados.
    Ex: @papel_required("ADMIN", "ANALISTA")"""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.usuario_atual.papel not in papeis_permitidos:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
