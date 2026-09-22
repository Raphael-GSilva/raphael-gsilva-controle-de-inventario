"""Ponto de entrada. Rode com: python run.py

Carrega variáveis do .env automaticamente (python-dotenv) antes de montar
a aplicação, para que app/config.py já enxergue os valores configurados.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402 — precisa vir depois do load_dotenv()

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "true").strip().lower() in ("1", "true", "sim")
    app.run(host=host, port=port, debug=debug)
