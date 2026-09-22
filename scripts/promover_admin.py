"""Promove um usuário existente a ADMIN diretamente no banco, sem passar
pela interface web.

Normalmente você NÃO precisa disso: o primeiro usuário que loga no sistema
já vira ADMIN automaticamente, e um ADMIN pode promover qualquer outra
pessoa pela tela "Administração > Usuários". Este script serve para
situações de recuperação (ex: o único admin saiu da empresa e ninguém mais
tem acesso à tela de administração).

Uso:
    python scripts/promover_admin.py alguem@empresa.com

A pessoa precisa já ter feito login pelo menos uma vez (ou seja, já existir
na tabela usuarios) para poder ser promovida.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app import repositories as repo
from app.config import Config
from app.db import Database


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python scripts/promover_admin.py <email>")
        sys.exit(1)

    email = sys.argv[1].strip()
    db = Database(Config.DATABASE_PATH)
    db.init_schema()

    with db.connection() as conn:
        usuario = repo.obter_usuario_por_email(conn, email)
        if not usuario:
            print(
                f"Não encontrei nenhum usuário com o e-mail '{email}'. "
                "A pessoa precisa logar pelo menos uma vez no sistema antes."
            )
            sys.exit(1)

        if usuario.papel == "ADMIN":
            print(f"{usuario.nome} <{usuario.email}> já é ADMIN.")
            return

        repo.atualizar_papel_usuario(conn, usuario.id, "ADMIN")
        print(f"Pronto: {usuario.nome} <{usuario.email}> agora é ADMIN.")


if __name__ == "__main__":
    main()
