"""Configuração da aplicação, lida de variáveis de ambiente (.env).

Ver .env.example para a lista completa com comentários explicando onde
conseguir cada valor no Azure Portal.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(nome: str, padrao: bool = False) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


class Config:
    # --- Geral ---
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "inventario.db"))

    # --- Modo de autenticação ---
    # "mock"      -> login local sem Azure, só para desenvolvimento/testes.
    # "microsoft" -> login real via Microsoft Entra ID (MSAL). Exige as
    #                variáveis MICROSOFT_* abaixo preenchidas.
    AUTH_MODE = os.environ.get("AUTH_MODE", "mock").strip().lower()

    # --- Microsoft Entra ID (login) ---
    MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET", "")
    MICROSOFT_TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID", "")
    MICROSOFT_REDIRECT_PATH = "/auth/callback"
    # Escopos delegados pedidos no login do usuário (perfil básico apenas).
    MICROSOFT_SCOPE = ["User.Read"]
    # Nota: de propósito NÃO é uma @property aqui. Flask's Config.from_object
    # faz getattr(ClasseOuInstancia, chave) para cada chave maiúscula — numa
    # @property isso devolveria o descritor, não o valor, quando from_object
    # recebe a classe (e não uma instância). Para não depender de lembrar
    # disso, a authority URL é montada como string simples onde é usada
    # (ver app/auth/microsoft_provider.py).

    # --- Sincronização com SharePoint (Microsoft Graph) ---
    SHAREPOINT_SYNC_ENABLED = _env_bool("SHAREPOINT_SYNC_ENABLED", False)
    # DRIVE_ID + ITEM_ID identificam o arquivo Excel de forma única no
    # Graph API — funciona tanto para um arquivo dentro de um site do
    # SharePoint quanto para um arquivo no OneDrive pessoal de alguém.
    # Descubra os dois valores com: python scripts/resolver_sharepoint_ids.py "<link do arquivo>"
    SHAREPOINT_DRIVE_ID = os.environ.get("SHAREPOINT_DRIVE_ID", "")
    SHAREPOINT_ITEM_ID = os.environ.get("SHAREPOINT_ITEM_ID", "")
    SHAREPOINT_WORKSHEET_NAME = os.environ.get("SHAREPOINT_WORKSHEET_NAME", "Estoque")
    SHAREPOINT_TABLE_NAME = os.environ.get("SHAREPOINT_TABLE_NAME", "TabelaEstoque")
    # Client credentials (app-only) usadas apenas pelo serviço de sincronização
    # em segundo plano — não confundir com o login delegado do usuário acima.
    GRAPH_CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID", MICROSOFT_CLIENT_ID)
    GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", MICROSOFT_CLIENT_SECRET)
    GRAPH_TENANT_ID = os.environ.get("GRAPH_TENANT_ID", MICROSOFT_TENANT_ID)

    # --- Papel padrão para novos usuários (a partir do segundo) ---
    # O PRIMEIRO usuário que loga no sistema vira ADMIN automaticamente
    # (ver repositories.criar_ou_atualizar_usuario_microsoft) — não precisa
    # mexer aqui para isso. Esta variável só afeta quem loga depois dele.
    PAPEL_PADRAO_NOVO_USUARIO = os.environ.get("PAPEL_PADRAO_NOVO_USUARIO", "CONSULTA")

    def validar_para_producao(self) -> list[str]:
        """Retorna uma lista de problemas de configuração. Lista vazia = ok.
        Chamada no boot quando AUTH_MODE=microsoft para falhar cedo e com
        uma mensagem clara, em vez de um erro obscuro no meio do login."""
        problemas = []
        if self.AUTH_MODE == "microsoft":
            if not self.MICROSOFT_CLIENT_ID:
                problemas.append("MICROSOFT_CLIENT_ID não configurado")
            if not self.MICROSOFT_CLIENT_SECRET:
                problemas.append("MICROSOFT_CLIENT_SECRET não configurado")
            if not self.MICROSOFT_TENANT_ID:
                problemas.append("MICROSOFT_TENANT_ID não configurado")
        if self.SHAREPOINT_SYNC_ENABLED:
            if not self.SHAREPOINT_DRIVE_ID:
                problemas.append("SHAREPOINT_DRIVE_ID não configurado (SHAREPOINT_SYNC_ENABLED=true)")
            if not self.SHAREPOINT_ITEM_ID:
                problemas.append("SHAREPOINT_ITEM_ID não configurado (SHAREPOINT_SYNC_ENABLED=true)")
        return problemas
