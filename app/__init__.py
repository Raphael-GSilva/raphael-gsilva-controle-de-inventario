"""App factory. Ponto único onde a aplicação Flask é montada: config,
banco de dados, blueprints, hooks e handlers de erro.
"""

from __future__ import annotations

import logging

from flask import Flask, g, render_template, session

from app.config import Config
from app.db import Database


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Falha cedo e com mensagem clara se AUTH_MODE=microsoft (ou sync
    # habilitado) mas faltar alguma variável de ambiente — é bem melhor
    # que um erro obscuro no meio de um login de usuário real.
    problemas = config_class().validar_para_producao()
    if problemas:
        for problema in problemas:
            app.logger.warning("Configuração incompleta: %s", problema)
        if app.config["AUTH_MODE"] == "microsoft" and not app.testing:
            raise RuntimeError(
                "AUTH_MODE=microsoft mas faltam variáveis de configuração: "
                + "; ".join(problemas)
                + ". Veja o arquivo .env.example e AZURE_SETUP.md."
            )

    db = Database(app.config["DATABASE_PATH"])
    db.init_schema()
    app.extensions["db"] = db

    _registrar_blueprints(app)
    _registrar_hooks(app)
    _registrar_handlers_de_erro(app)
    _registrar_filtros_jinja(app)

    return app


def _registrar_blueprints(app: Flask) -> None:
    from app.routes import (
        admin_routes,
        auth_routes,
        dashboard_routes,
        equipamento_routes,
        movimentacao_routes,
    )

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(equipamento_routes.bp)
    app.register_blueprint(movimentacao_routes.bp)
    app.register_blueprint(admin_routes.bp)


def _registrar_hooks(app: Flask) -> None:
    from app import repositories as repo

    @app.before_request
    def carregar_usuario_atual():
        g.usuario_atual = None
        usuario_id = session.get("user_id")
        if usuario_id is None:
            return
        db: Database = app.extensions["db"]
        with db.connection() as conn:
            g.usuario_atual = repo.obter_usuario_por_id(conn, usuario_id)
        if g.usuario_atual is None:
            # Usuário foi removido do banco depois de logar — limpa a sessão
            # órfã em vez de deixar o resto da aplicação lidar com isso.
            session.clear()

    @app.context_processor
    def injetar_globais():
        return {
            "usuario_atual": g.get("usuario_atual"),
            "auth_mode": app.config["AUTH_MODE"],
        }


def _registrar_handlers_de_erro(app: Flask) -> None:
    @app.errorhandler(403)
    def acesso_negado(_erro):
        return render_template(
            "erro_404.html",
            mensagem="Você não tem permissão para acessar esta página.",
        ), 403

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        return render_template("erro_404.html", mensagem="Página não encontrada."), 404


def _registrar_filtros_jinja(app: Flask) -> None:
    @app.template_filter("sim_nao")
    def sim_nao(valor: bool) -> str:
        return "Sim" if valor else "Não"

    @app.template_filter("data_br")
    def data_br(valor: str | None) -> str:
        """Converte 'YYYY-MM-DD' (ou um timestamp ISO começando assim) para
        o formato brasileiro 'DD/MM/YYYY'. Devolve o valor original se não
        reconhecer o formato, em vez de quebrar a página."""
        if not valor:
            return "—"
        partes = valor[:10].split("-")
        if len(partes) != 3:
            return valor
        ano, mes, dia = partes
        return f"{dia}/{mes}/{ano}"
