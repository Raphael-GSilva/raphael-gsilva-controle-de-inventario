"""
Camada de acesso ao banco de dados (SQLite puro, sem ORM).

Por que SQLite puro em vez de SQLAlchemy?
- Zero dependências externas para a parte mais crítica do sistema (menos
  pontos de falha).
- SQLite lida bem com a carga de um time interno (dezenas de usuários,
  milhares de equipamentos) especialmente com WAL habilitado.
- Todo o SQL fica centralizado e explícito, o que facilita auditoria e
  testes unitários sem precisar de um banco real rodando.

Se no futuro o time crescer muito e precisar de acesso concorrente pesado,
a camada de repositórios (app/repositories.py) foi escrita para que trocar
o backend (ex: Postgres) não exija mudar as camadas de cima (services,
routes).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    microsoft_oid TEXT,
    -- Tenant (empresa) de origem no Microsoft Entra ID. Vazio ('') no modo
    -- mock. Importante: em cenário multi-tenant (app aceitando login de
    -- várias empresas clientes diferentes), a Microsoft recomenda NUNCA
    -- usar só o "oid" como identidade — dois tenants diferentes podem, em
    -- teoria, gerar valores de oid coincidentes. A combinação (oid +
    -- tenant_id) é o identificador seguro.
    tenant_id TEXT NOT NULL DEFAULT '',
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    papel TEXT NOT NULL DEFAULT 'ANALISTA'
        CHECK (papel IN ('ADMIN', 'ANALISTA', 'CONSULTA')),
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    ultimo_login TEXT,
    UNIQUE (microsoft_oid, tenant_id)
);

CREATE TABLE IF NOT EXISTS equipamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nr_ativo TEXT NOT NULL UNIQUE,
    nr_serie TEXT,
    tipo TEXT NOT NULL,
    modelo TEXT,
    empresa_id INTEGER REFERENCES empresas(id),
    owner_ativo TEXT,
    status TEXT NOT NULL DEFAULT 'EM_ESTOQUE'
        CHECK (status IN ('EM_ESTOQUE', 'ALOCADO', 'MANUTENCAO', 'BAIXADO')),
    colaborador_atual TEXT,
    empresa_colaborador_atual TEXT,
    data_recebimento TEXT,
    maquina_preparada INTEGER NOT NULL DEFAULT 0,
    previsao_alocacao INTEGER NOT NULL DEFAULT 0,
    observacoes TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    sharepoint_row_key TEXT,
    sincronizado_em TEXT
);

CREATE TABLE IF NOT EXISTS movimentacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipamento_id INTEGER NOT NULL REFERENCES equipamentos(id),
    tipo TEXT NOT NULL CHECK (tipo IN ('ENTRADA', 'ENTREGA', 'DEVOLUCAO')),
    data_movimentacao TEXT NOT NULL DEFAULT (datetime('now')),
    nome_colaborador TEXT,
    empresa_colaborador TEXT,
    nr_chamado TEXT,
    condicao_devolucao TEXT
        CHECK (condicao_devolucao IN ('Bom', 'Regular', 'Ruim') OR condicao_devolucao IS NULL),
    analista_id INTEGER REFERENCES usuarios(id),
    observacoes TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_equipamentos_status ON equipamentos(status);
CREATE INDEX IF NOT EXISTS idx_equipamentos_tipo ON equipamentos(tipo);
CREATE INDEX IF NOT EXISTS idx_equipamentos_nr_serie ON equipamentos(nr_serie);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_equipamento ON movimentacoes(equipamento_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_data ON movimentacoes(data_movimentacao);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_tipo ON movimentacoes(tipo);
"""


class Database:
    """Gerencia a conexão SQLite e a inicialização do schema."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Contexto que abre uma conexão, faz commit se tudo der certo e
        rollback automático em caso de exceção. Sempre fecha a conexão."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Cria as tabelas (se não existirem). De propósito NÃO insere
        nenhuma empresa, tipo de equipamento ou qualquer outro dado de
        exemplo — o sistema nasce 100% vazio, pronto para ser usado por
        qualquer empresa. Empresas e tipos de equipamento crescem
        organicamente conforme o uso (ver obter_ou_criar_empresa e
        listar_tipos_equipamento_usados em repositories.py), ou podem ser
        carregados de uma vez via scripts/importar_excel.py."""
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
