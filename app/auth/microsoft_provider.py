"""Login real via Microsoft Entra ID, usando MSAL (Microsoft Authentication
Library) com o fluxo "authorization code" — o fluxo recomendado pela própria
Microsoft para aplicações web com back-end confidencial (como este Flask).

Importante: este módulo não pode ser testado de verdade neste ambiente de
desenvolvimento (sandbox sem acesso à rede/Azure). Ele segue o padrão
oficial da Microsoft ao pé da letra (mesmo usado no exemplo oficial
"ms-identity-python-webapp"), mas TESTE de ponta a ponta com as suas
credenciais reais antes de considerar isso pronto — ver AZURE_SETUP.md.

O import de `msal` é feito dentro das funções (não no topo do arquivo) de
propósito: assim, um ambiente que só usa AUTH_MODE=mock (ex: rodando os
testes automatizados) não precisa ter o pacote `msal` instalado.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from flask import current_app, redirect, request, session, url_for

if TYPE_CHECKING:
    import msal


def _msal_app() -> "msal.ConfidentialClientApplication":
    import msal

    cfg = current_app.config
    return msal.ConfidentialClientApplication(
        cfg["MICROSOFT_CLIENT_ID"],
        authority=f"https://login.microsoftonline.com/{cfg['MICROSOFT_TENANT_ID']}",
        client_credential=cfg["MICROSOFT_CLIENT_SECRET"],
    )


def iniciar_login():
    """GET /login quando AUTH_MODE=microsoft: redireciona para a tela de
    login da Microsoft, com um 'state' aleatório para proteção contra CSRF."""
    session["auth_state"] = str(uuid.uuid4())
    redirect_uri = url_for("auth.callback", _external=True)
    auth_url = _msal_app().get_authorization_request_url(
        current_app.config["MICROSOFT_SCOPE"],
        state=session["auth_state"],
        redirect_uri=redirect_uri,
    )
    return redirect(auth_url)


class ErroDeLogin(Exception):
    """Erro ao processar o retorno da Microsoft — mensagem já pronta para o usuário."""


def processar_callback() -> tuple[str, str, str, str]:
    """GET /auth/callback: troca o código de autorização por um token e
    extrai (microsoft_oid, tenant_id, nome, email) do id_token. Levanta
    ErroDeLogin com uma mensagem segura para mostrar ao usuário em caso de
    problema."""
    estado_esperado = session.pop("auth_state", None)
    if not estado_esperado or request.args.get("state") != estado_esperado:
        raise ErroDeLogin("Sessão de login expirada ou inválida. Tente novamente.")

    if "error" in request.args:
        raise ErroDeLogin(request.args.get("error_description", "Login cancelado ou negado."))

    code = request.args.get("code")
    if not code:
        raise ErroDeLogin("Código de autorização ausente no retorno da Microsoft.")

    redirect_uri = url_for("auth.callback", _external=True)
    resultado = _msal_app().acquire_token_by_authorization_code(
        code,
        scopes=current_app.config["MICROSOFT_SCOPE"],
        redirect_uri=redirect_uri,
    )

    if "error" in resultado:
        detalhe = resultado.get("error_description", resultado.get("error", "erro desconhecido"))
        raise ErroDeLogin(f"Falha ao autenticar com a Microsoft: {detalhe}")

    claims = resultado.get("id_token_claims") or {}
    oid = claims.get("oid")
    tenant_id = claims.get("tid") or ""
    nome = claims.get("name") or "Usuário Microsoft"
    email = claims.get("preferred_username") or claims.get("email")

    if not oid or not email:
        raise ErroDeLogin("O token da Microsoft não trouxe os dados esperados do usuário.")

    return oid, tenant_id, nome, email


def url_logout_microsoft(url_pos_logout: str) -> str:
    """Monta a URL de logout da própria Microsoft, para encerrar também a
    sessão dela (não só a sessão local do Flask)."""
    cfg = current_app.config
    return (
        f"https://login.microsoftonline.com/{cfg['MICROSOFT_TENANT_ID']}"
        f"/oauth2/v2.0/logout?post_logout_redirect_uri={url_pos_logout}"
    )
