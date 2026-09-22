"""Login "mock" — só para desenvolvimento e testes locais.

NÃO usa Microsoft de verdade. Mostra um formulário simples onde quem está
testando digita um nome e e-mail, e a aplicação cria/reaproveita um usuário
local. Serve para validar todas as telas e regras de negócio ANTES de
configurar o Azure AD, e também é o que os testes automatizados usam.

Continua funcionando mesmo depois do Azure configurado, mas só se
AUTH_MODE=mock no .env — nunca habilitado por acidente em produção, porque
nesse modo qualquer pessoa pode "logar" como qualquer e-mail.
"""

from __future__ import annotations

import hashlib

from flask import render_template, request


def oid_para_email_mock(email: str) -> str:
    """Gera um 'microsoft_oid' falso, mas estável, a partir do e-mail
    digitado — assim o mesmo e-mail sempre vira o mesmo usuário local."""
    email_normalizado = email.strip().lower()
    return "mock-" + hashlib.sha256(email_normalizado.encode()).hexdigest()[:24]


def tela_login_mock():
    """Renderiza o formulário de login mock (GET /login quando AUTH_MODE=mock)."""
    return render_template("login.html", modo_mock=True)


def processar_login_mock() -> tuple[str, str, str] | None:
    """Lê nome/e-mail do formulário enviado (POST /login). Devolve
    (microsoft_oid, nome, email) ou None se os campos estiverem vazios.
    Não existe tenant real no modo mock — quem chama trata isso como ''."""
    nome = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()
    if not nome or not email or "@" not in email:
        return None
    return oid_para_email_mock(email), nome, email
