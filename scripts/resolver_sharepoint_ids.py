"""Descobre o SHAREPOINT_DRIVE_ID e o SHAREPOINT_ITEM_ID a partir do link
da sua planilha — os dois valores que faltam preencher no .env para a
sincronização funcionar.

Uso:
    python scripts/resolver_sharepoint_ids.py "https://empresa-my.sharepoint.com/:x:/g/personal/..."

Cole o link exatamente como aparece na barra de endereço do navegador
quando você abre a planilha (funciona tanto para um arquivo dentro de um
site do SharePoint quanto para um arquivo no OneDrive pessoal de alguém,
como o link em .../personal/... que aparece no seu caso).

Exige que GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET e GRAPH_TENANT_ID (ou os
MICROSOFT_* equivalentes) já estejam preenchidos no .env — veja
AZURE_SETUP.md se ainda não configurou isso.
"""

from __future__ import annotations

import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import requests

from app.config import Config


def _codificar_url_compartilhada(url: str) -> str:
    """Converte um link comum em um 'shareId' que o Graph aceita — algoritmo
    documentado pela Microsoft para o endpoint /shares/{id}."""
    base64_padrao = base64.b64encode(url.encode("utf-8")).decode("ascii")
    base64_url_safe = base64_padrao.rstrip("=").replace("/", "_").replace("+", "-")
    return "u!" + base64_url_safe


def _obter_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"Falha ao autenticar no Graph ({resp.status_code}): {resp.text[:500]}")
        print(
            "\nConfira: GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET no .env, "
            "e se o app registrado no Entra ID já tem a permissão de aplicativo consentida "
            "(ver AZURE_SETUP.md)."
        )
        sys.exit(1)
    return resp.json()["access_token"]


def main() -> None:
    if len(sys.argv) != 2:
        print('Uso: python scripts/resolver_sharepoint_ids.py "<link da planilha>"')
        sys.exit(1)

    link = sys.argv[1].strip()
    cfg = Config()
    tenant_id = cfg.GRAPH_TENANT_ID or cfg.MICROSOFT_TENANT_ID
    client_id = cfg.GRAPH_CLIENT_ID or cfg.MICROSOFT_CLIENT_ID
    client_secret = cfg.GRAPH_CLIENT_SECRET or cfg.MICROSOFT_CLIENT_SECRET

    faltando = [
        nome
        for nome, valor in [
            ("GRAPH_TENANT_ID (ou MICROSOFT_TENANT_ID)", tenant_id),
            ("GRAPH_CLIENT_ID (ou MICROSOFT_CLIENT_ID)", client_id),
            ("GRAPH_CLIENT_SECRET (ou MICROSOFT_CLIENT_SECRET)", client_secret),
        ]
        if not valor
    ]
    if faltando:
        print("Faltam variáveis no .env antes de rodar isto: " + ", ".join(faltando))
        sys.exit(1)

    token = _obter_token(tenant_id, client_id, client_secret)
    share_id = _codificar_url_compartilhada(link)

    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/shares/{share_id}/driveItem",
        headers={"Authorization": f"Bearer {token}"},
        params={"$select": "id,name,parentReference,webUrl"},
        timeout=20,
    )
    if resp.status_code != 200:
        print(f"Não consegui resolver esse link ({resp.status_code}): {resp.text[:500]}")
        print(
            "\nCausas comuns: o app do Entra ID ainda não tem permissão de aplicativo "
            "consentida por um admin (Sites.Selected ou Sites.ReadWrite.All), ou o link "
            "não é acessível pela conta do app."
        )
        sys.exit(1)

    dados = resp.json()
    drive_id = dados["parentReference"]["driveId"]
    item_id = dados["id"]

    print(f"Arquivo encontrado: {dados.get('name')}")
    print("\nAdicione isto ao seu .env:\n")
    print(f"SHAREPOINT_DRIVE_ID={drive_id}")
    print(f"SHAREPOINT_ITEM_ID={item_id}")
    print(
        "\nFalta ainda: SHAREPOINT_WORKSHEET_NAME (o nome da aba) e SHAREPOINT_TABLE_NAME "
        "(o nome da Tabela do Excel dentro dessa aba — Inserir > Tabela, se a sua planilha "
        "ainda for só um intervalo de células sem nome). Veja AZURE_SETUP.md."
    )


if __name__ == "__main__":
    main()
