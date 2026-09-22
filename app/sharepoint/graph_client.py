"""Cliente HTTP fino para a API de Excel do Microsoft Graph.

Usa o fluxo "client credentials" (app-only, sem usuário interativo) — é o
correto para um processo em segundo plano como esse. Exige que o app
registrado no Entra ID tenha a permissão de aplicativo Sites.Selected (ou
Sites.ReadWrite.All) consentida por um admin — ver AZURE_SETUP.md.

Este módulo não usa o SDK oficial do Graph (msgraph-sdk) de propósito: o
SDK é assíncrono por padrão e traz bem mais dependências. Para o volume de
chamadas de um sync de inventário interno, chamadas REST diretas com
`requests` são mais simples de ler, testar e depurar.
"""

from __future__ import annotations

import time

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TIMEOUT_PADRAO = 20


class GraphAuthError(Exception):
    """Falha ao obter token de acesso do Microsoft Graph."""


class GraphAPIError(Exception):
    """A API do Graph respondeu com um erro."""


class GraphClient:
    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expira_em: float = 0.0

    def _obter_token(self) -> str:
        agora = time.time()
        if self._token and agora < self._token_expira_em - 60:
            return self._token

        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = requests.post(
            url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=TIMEOUT_PADRAO,
        )
        if resp.status_code != 200:
            raise GraphAuthError(
                f"Falha ao autenticar no Microsoft Graph ({resp.status_code}): {resp.text[:300]}"
            )
        dados = resp.json()
        self._token = dados["access_token"]
        self._token_expira_em = agora + float(dados.get("expires_in", 3600))
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._obter_token()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _tratar_erro(resp: requests.Response, contexto: str) -> None:
        if resp.status_code >= 300:
            raise GraphAPIError(f"{contexto} ({resp.status_code}): {resp.text[:300]}")

    def _url_tabela(self, drive_id: str, item_id: str, worksheet: str, table: str) -> str:
        # /drives/{id}/... (em vez de /sites/{id}/drive/...) funciona tanto
        # para uma biblioteca de documentos de um site do SharePoint quanto
        # para o OneDrive pessoal de alguém — o Graph trata os dois como
        # "drives". Isso importa porque um link do tipo
        # https://empresa-my.sharepoint.com/:x:/g/personal/... é OneDrive
        # pessoal, não um site de equipe do SharePoint.
        return (
            f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}"
            f"/workbook/worksheets/{worksheet}/tables/{table}"
        )

    def listar_colunas(self, drive_id: str, item_id: str, worksheet: str, table: str) -> list[str]:
        url = self._url_tabela(drive_id, item_id, worksheet, table) + "/columns"
        resp = requests.get(url, headers=self._headers(), timeout=TIMEOUT_PADRAO)
        self._tratar_erro(resp, "Erro ao listar colunas da tabela")
        return [c["name"] for c in resp.json().get("value", [])]

    def listar_linhas(self, drive_id: str, item_id: str, worksheet: str, table: str) -> list[dict]:
        url = self._url_tabela(drive_id, item_id, worksheet, table) + "/rows"
        resp = requests.get(url, headers=self._headers(), timeout=TIMEOUT_PADRAO)
        self._tratar_erro(resp, "Erro ao listar linhas da tabela")
        return resp.json().get("value", [])

    def adicionar_linha(
        self, drive_id: str, item_id: str, worksheet: str, table: str, valores: list
    ) -> dict:
        url = self._url_tabela(drive_id, item_id, worksheet, table) + "/rows/add"
        resp = requests.post(
            url, headers=self._headers(), json={"values": [valores]}, timeout=TIMEOUT_PADRAO
        )
        self._tratar_erro(resp, "Erro ao adicionar linha na tabela")
        return resp.json()

    def atualizar_linha(
        self, drive_id: str, item_id: str, worksheet: str, table: str, indice: int, valores: list
    ) -> dict:
        url = (
            self._url_tabela(drive_id, item_id, worksheet, table)
            + f"/rows/itemAt(index={indice})"
        )
        resp = requests.patch(
            url, headers=self._headers(), json={"values": [valores]}, timeout=TIMEOUT_PADRAO
        )
        self._tratar_erro(resp, f"Erro ao atualizar linha {indice} da tabela")
        return resp.json()
