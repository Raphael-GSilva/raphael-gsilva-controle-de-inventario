"""Inicializa o banco de dados (cria as tabelas se não existirem).

Uso:
    python scripts/init_db.py

Não é estritamente necessário rodar isso à parte — a aplicação já
inicializa o schema sozinha ao subir (veja app/__init__.py). Este script
existe para quem quiser preparar o banco antes do primeiro `python run.py`,
ou verificar que a configuração de DATABASE_PATH está correta.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from app.config import Config
from app.db import Database


def main() -> None:
    caminho = Config.DATABASE_PATH
    db = Database(caminho)
    db.init_schema()
    print(f"Banco de dados pronto em: {caminho}")


if __name__ == "__main__":
    main()
