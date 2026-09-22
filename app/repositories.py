"""Camada de repositórios: todo o SQL da aplicação vive aqui.

Cada função recebe uma conexão sqlite3 já aberta (veja app/db.py) e
devolve dataclasses de app/models.py, nunca sqlite3.Row cru. As camadas
acima (services, routes) não escrevem SQL — isso mantém as queries
centralizadas, fáceis de revisar e fáceis de testar isoladamente.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.models import Empresa, Equipamento, Movimentacao, Usuario


def _agora_iso() -> str:
    """Timestamp UTC atual, formato ISO 8601, com precisão de segundos.
    Centralizado aqui em vez de espalhar datetime.now(timezone.utc) pelo
    arquivo — e usa a API não-obsoleta (datetime.utcnow() foi descontinuado
    no Python 3.12)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NaoEncontrado(Exception):
    """Levantada quando um registro esperado não existe."""


class ViolacaoDeUnicidade(Exception):
    """Levantada quando uma operação violaria uma constraint UNIQUE."""


# ---------------------------------------------------------------- empresas

def listar_empresas(conn: sqlite3.Connection) -> list[Empresa]:
    rows = conn.execute("SELECT * FROM empresas ORDER BY nome").fetchall()
    return [Empresa.from_row(r) for r in rows]


def obter_empresa_por_nome(conn: sqlite3.Connection, nome: str) -> Empresa | None:
    row = conn.execute("SELECT * FROM empresas WHERE nome = ?", (nome,)).fetchone()
    return Empresa.from_row(row) if row else None


def obter_ou_criar_empresa(conn: sqlite3.Connection, nome: str) -> Empresa:
    nome = nome.strip()
    existente = obter_empresa_por_nome(conn, nome)
    if existente:
        return existente
    cur = conn.execute("INSERT INTO empresas (nome) VALUES (?)", (nome,))
    return Empresa(id=cur.lastrowid, nome=nome)


# ---------------------------------------------------------------- usuarios

def obter_usuario_por_oid(conn: sqlite3.Connection, microsoft_oid: str, tenant_id: str = "") -> Usuario | None:
    row = conn.execute(
        "SELECT * FROM usuarios WHERE microsoft_oid = ? AND tenant_id = ?", (microsoft_oid, tenant_id)
    ).fetchone()
    return Usuario.from_row(row) if row else None


def obter_usuario_por_email(conn: sqlite3.Connection, email: str) -> Usuario | None:
    row = conn.execute(
        "SELECT * FROM usuarios WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    return Usuario.from_row(row) if row else None


def obter_usuario_por_id(conn: sqlite3.Connection, usuario_id: int) -> Usuario | None:
    row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    return Usuario.from_row(row) if row else None


def criar_ou_atualizar_usuario_microsoft(
    conn: sqlite3.Connection,
    microsoft_oid: str,
    nome: str,
    email: str,
    tenant_id: str = "",
    papel_padrao: str = "CONSULTA",
) -> Usuario:
    """Cria o usuário no primeiro login via Microsoft, ou atualiza nome/e-mail
    e a data de último login se ele já existir. O papel de um usuário já
    existente nunca é sobrescrito aqui — só um admin muda papéis (ou o
    próprio painel de administração).

    A identidade única é o PAR (microsoft_oid, tenant_id), não o oid
    sozinho — importante para quando o app aceitar login de mais de uma
    empresa (tenant) diferente: a Microsoft recomenda não confiar só no
    oid nesse cenário, porque tenants diferentes podem, em teoria, gerar
    valores coincidentes. No modo mock, tenant_id fica vazio ('').

    O PRIMEIRO usuário que loga no sistema (tabela usuarios ainda vazia)
    sempre vira ADMIN, não importa o que diga papel_padrao — de propósito,
    para não depender de alguém lembrar de trocar
    PAPEL_PADRAO_NOVO_USUARIO=ADMIN de volta para CONSULTA depois do
    primeiro acesso (deixar esquecido faria todo mundo virar admin).

    Também trata o caso (raro, mas real) de o e-mail já existir vinculado
    a outro microsoft_oid — acontece se uma conta é apagada e recriada no
    Entra ID com o mesmo e-mail corporativo. Em vez de deixar a constraint
    UNIQUE da coluna email estourar um IntegrityError, atualizamos o
    registro existente para o novo oid/tenant."""
    existente = obter_usuario_por_oid(conn, microsoft_oid, tenant_id)
    agora = _agora_iso()
    if existente:
        conn.execute(
            "UPDATE usuarios SET nome = ?, email = ?, ultimo_login = ? WHERE id = ?",
            (nome, email, agora, existente.id),
        )
        return obter_usuario_por_id(conn, existente.id)  # type: ignore[return-value]

    existente_por_email = obter_usuario_por_email(conn, email)
    if existente_por_email:
        conn.execute(
            "UPDATE usuarios SET microsoft_oid = ?, tenant_id = ?, nome = ?, ultimo_login = ? WHERE id = ?",
            (microsoft_oid, tenant_id, nome, agora, existente_por_email.id),
        )
        return obter_usuario_por_id(conn, existente_por_email.id)  # type: ignore[return-value]

    eh_o_primeiro_usuario = conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"] == 0
    papel = "ADMIN" if eh_o_primeiro_usuario else papel_padrao

    cur = conn.execute(
        """INSERT INTO usuarios (microsoft_oid, tenant_id, nome, email, papel, ultimo_login)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (microsoft_oid, tenant_id, nome, email, papel, agora),
    )
    return obter_usuario_por_id(conn, cur.lastrowid)  # type: ignore[return-value]


def listar_usuarios(conn: sqlite3.Connection) -> list[Usuario]:
    rows = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    return [Usuario.from_row(r) for r in rows]


def atualizar_papel_usuario(conn: sqlite3.Connection, usuario_id: int, papel: str) -> None:
    conn.execute("UPDATE usuarios SET papel = ? WHERE id = ?", (papel, usuario_id))


# ------------------------------------------------------------ equipamentos

_SELECT_EQUIPAMENTO = """
    SELECT e.*, emp.nome AS empresa_nome
    FROM equipamentos e
    LEFT JOIN empresas emp ON emp.id = e.empresa_id
"""


def listar_tipos_equipamento_usados(conn: sqlite3.Connection) -> list[str]:
    """Tipos de equipamento distintos já cadastrados, em ordem alfabética.
    Usado para sugerir no formulário de entrada (datalist) e como opções
    do filtro na tela de consulta. Não existe uma lista fixa embutida no
    sistema — começa vazia e cresce com o uso, para servir qualquer
    empresa sem categorias pré-definidas de fábrica."""
    rows = conn.execute(
        "SELECT DISTINCT tipo FROM equipamentos WHERE tipo IS NOT NULL AND tipo != '' ORDER BY tipo"
    ).fetchall()
    return [r["tipo"] for r in rows]


def obter_equipamento_por_id(conn: sqlite3.Connection, equipamento_id: int) -> Equipamento | None:
    row = conn.execute(
        _SELECT_EQUIPAMENTO + " WHERE e.id = ?", (equipamento_id,)
    ).fetchone()
    return Equipamento.from_row(row) if row else None


def obter_equipamento_por_nr_ativo(conn: sqlite3.Connection, nr_ativo: str) -> Equipamento | None:
    row = conn.execute(
        _SELECT_EQUIPAMENTO + " WHERE e.nr_ativo = ? COLLATE NOCASE", (nr_ativo,)
    ).fetchone()
    return Equipamento.from_row(row) if row else None


def criar_equipamento(
    conn: sqlite3.Connection,
    nr_ativo: str,
    tipo: str,
    nr_serie: str | None = None,
    modelo: str | None = None,
    empresa_id: int | None = None,
    owner_ativo: str | None = None,
    data_recebimento: str | None = None,
    maquina_preparada: bool = False,
    previsao_alocacao: bool = False,
    observacoes: str | None = None,
) -> Equipamento:
    nr_ativo = nr_ativo.strip()
    if obter_equipamento_por_nr_ativo(conn, nr_ativo):
        raise ViolacaoDeUnicidade(f"Já existe um equipamento com o nº de ativo '{nr_ativo}'.")

    agora = _agora_iso()
    cur = conn.execute(
        """INSERT INTO equipamentos
           (nr_ativo, nr_serie, tipo, modelo, empresa_id, owner_ativo, status,
            data_recebimento, maquina_preparada, previsao_alocacao, observacoes,
            criado_em, atualizado_em)
           VALUES (?, ?, ?, ?, ?, ?, 'EM_ESTOQUE', ?, ?, ?, ?, ?, ?)""",
        (
            nr_ativo, nr_serie, tipo, modelo, empresa_id, owner_ativo,
            data_recebimento, int(maquina_preparada), int(previsao_alocacao),
            observacoes, agora, agora,
        ),
    )
    return obter_equipamento_por_id(conn, cur.lastrowid)  # type: ignore[return-value]


def atualizar_status_equipamento(
    conn: sqlite3.Connection,
    equipamento_id: int,
    status: str,
    colaborador_atual: str | None,
    empresa_colaborador_atual: str | None,
) -> None:
    agora = _agora_iso()
    conn.execute(
        """UPDATE equipamentos
           SET status = ?, colaborador_atual = ?, empresa_colaborador_atual = ?,
               atualizado_em = ?
           WHERE id = ?""",
        (status, colaborador_atual, empresa_colaborador_atual, agora, equipamento_id),
    )


def atualizar_equipamento(conn: sqlite3.Connection, equipamento_id: int, **campos) -> None:
    """Atualiza campos livres do equipamento (modelo, observações, etc).
    Só aceita colunas conhecidas, para nunca permitir injeção via nomes de
    coluna dinâmicos."""
    colunas_permitidas = {
        "nr_serie", "tipo", "modelo", "empresa_id", "owner_ativo",
        "data_recebimento", "maquina_preparada", "previsao_alocacao",
        "observacoes",
    }
    sets = []
    valores = []
    for chave, valor in campos.items():
        if chave not in colunas_permitidas:
            raise ValueError(f"Campo '{chave}' não pode ser atualizado por esta função.")
        sets.append(f"{chave} = ?")
        valores.append(valor)
    if not sets:
        return
    sets.append("atualizado_em = ?")
    valores.append(_agora_iso())
    valores.append(equipamento_id)
    conn.execute(f"UPDATE equipamentos SET {', '.join(sets)} WHERE id = ?", valores)


def marcar_sincronizado(conn: sqlite3.Connection, equipamento_id: int, row_key: str) -> None:
    agora = _agora_iso()
    conn.execute(
        "UPDATE equipamentos SET sharepoint_row_key = ?, sincronizado_em = ? WHERE id = ?",
        (row_key, agora, equipamento_id),
    )


def buscar_equipamentos(
    conn: sqlite3.Connection,
    termo: str | None = None,
    status: str | None = None,
    tipo: str | None = None,
    empresa_id: int | None = None,
    limite: int = 200,
) -> list[Equipamento]:
    """Busca usada pela tela de Consulta. `termo` casa contra nº de ativo,
    nº de série e nome do colaborador atual."""
    condicoes = []
    valores: list = []

    if termo:
        termo_like = f"%{termo.strip()}%"
        condicoes.append(
            "(e.nr_ativo LIKE ? OR e.nr_serie LIKE ? OR e.colaborador_atual LIKE ?)"
        )
        valores.extend([termo_like, termo_like, termo_like])
    if status:
        condicoes.append("e.status = ?")
        valores.append(status)
    if tipo:
        condicoes.append("e.tipo = ?")
        valores.append(tipo)
    if empresa_id:
        condicoes.append("e.empresa_id = ?")
        valores.append(empresa_id)

    sql = _SELECT_EQUIPAMENTO
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY e.atualizado_em DESC LIMIT ?"
    valores.append(limite)

    rows = conn.execute(sql, valores).fetchall()
    return [Equipamento.from_row(r) for r in rows]


def contar_por_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS total FROM equipamentos GROUP BY status"
    ).fetchall()
    return {r["status"]: r["total"] for r in rows}


def contar_por_tipo(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT tipo, COUNT(*) AS total FROM equipamentos GROUP BY tipo ORDER BY total DESC"
    ).fetchall()
    return {r["tipo"]: r["total"] for r in rows}


def contar_por_empresa(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """SELECT emp.nome AS empresa, COUNT(*) AS total
           FROM equipamentos e
           JOIN empresas emp ON emp.id = e.empresa_id
           GROUP BY emp.nome ORDER BY total DESC"""
    ).fetchall()
    return {r["empresa"]: r["total"] for r in rows}


def listar_pendentes_preparacao(conn: sqlite3.Connection, limite: int = 20) -> list[Equipamento]:
    rows = conn.execute(
        _SELECT_EQUIPAMENTO
        + " WHERE e.status = 'EM_ESTOQUE' AND e.maquina_preparada = 0"
        + " ORDER BY e.criado_em ASC LIMIT ?",
        (limite,),
    ).fetchall()
    return [Equipamento.from_row(r) for r in rows]


# ----------------------------------------------------------- movimentacoes

_SELECT_MOVIMENTACAO = """
    SELECT m.*, u.nome AS analista_nome, e.nr_ativo AS equipamento_nr_ativo
    FROM movimentacoes m
    LEFT JOIN usuarios u ON u.id = m.analista_id
    LEFT JOIN equipamentos e ON e.id = m.equipamento_id
"""


def criar_movimentacao(
    conn: sqlite3.Connection,
    equipamento_id: int,
    tipo: str,
    analista_id: int | None,
    nome_colaborador: str | None = None,
    empresa_colaborador: str | None = None,
    nr_chamado: str | None = None,
    condicao_devolucao: str | None = None,
    observacoes: str | None = None,
) -> Movimentacao:
    cur = conn.execute(
        """INSERT INTO movimentacoes
           (equipamento_id, tipo, nome_colaborador, empresa_colaborador,
            nr_chamado, condicao_devolucao, analista_id, observacoes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            equipamento_id, tipo, nome_colaborador, empresa_colaborador,
            nr_chamado, condicao_devolucao, analista_id, observacoes,
        ),
    )
    row = conn.execute(
        _SELECT_MOVIMENTACAO + " WHERE m.id = ?", (cur.lastrowid,)
    ).fetchone()
    return Movimentacao.from_row(row)


def listar_movimentacoes_por_equipamento(
    conn: sqlite3.Connection, equipamento_id: int
) -> list[Movimentacao]:
    rows = conn.execute(
        _SELECT_MOVIMENTACAO + " WHERE m.equipamento_id = ? ORDER BY m.data_movimentacao DESC",
        (equipamento_id,),
    ).fetchall()
    return [Movimentacao.from_row(r) for r in rows]


def listar_movimentacoes_recentes(conn: sqlite3.Connection, limite: int = 15) -> list[Movimentacao]:
    rows = conn.execute(
        _SELECT_MOVIMENTACAO + " ORDER BY m.data_movimentacao DESC LIMIT ?", (limite,)
    ).fetchall()
    return [Movimentacao.from_row(r) for r in rows]
