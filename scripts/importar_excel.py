"""Importa equipamentos a partir de um arquivo .xlsx exportado da sua
planilha atual — útil para popular o banco com os dados que já existem,
antes mesmo de configurar a sincronização com o SharePoint.

Uso:
    python scripts/importar_excel.py caminho/para/planilha.xlsx ["Nome da Aba"]

Se você não passar o nome da aba, usa a primeira aba do arquivo.

IMPORTANTE — leia antes de rodar em cima dos dados de verdade:
Se a sua planilha tiver abas com layouts diferentes (uma aba de estoque
"mestre", abas de entregas com histórico separadas, etc), rode este
script apontando para a aba no estilo "estoque mestre" — uma linha por
equipamento, com colunas como Nº Ativo, Nº de Série, Empresa, Tipo Equip.,
Modelo, Nome... Ele reconhece várias variações de nome de coluna (ver
MAPEAMENTOS abaixo, ajuste se a sua planilha usar nomes diferentes), e o
comportamento muda dependendo do que encontra em cada linha:

  - Equipamento NOVO (nº de ativo ainda não existe no banco) SEM nome de
    colaborador reconhecido na linha -> criado com status "Em estoque".
  - Equipamento NOVO COM nome de colaborador reconhecido -> criado e
    imediatamente marcado como "Alocado" a essa pessoa (gera um registro
    de ENTRADA seguido de um de ENTREGA no histórico, com a observação
    "Migrado da planilha anterior" para diferenciar de uma entrega feita
    ao vivo pelo sistema).
  - Equipamento que JÁ EXISTE no banco -> só atualiza campos de catálogo
    (série, modelo...). Nunca mexe no status nem no colaborador atual de
    um equipamento que já existe — o estado dele já é controlado pelas
    movimentações registradas ao vivo pelo sistema, que são mais
    confiáveis que uma planilha que pode estar desatualizada.

Outros detalhes:
  - roda em modo simulação por padrão (só mostra o que faria, não grava
    nada) — use --confirmar para gravar de verdade;
  - sempre revise o resumo impresso no final antes de confiar 100% nos
    dados importados, e confira uma amostra pelo próprio sistema depois.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import openpyxl

from app import repositories as repo
from app.config import Config
from app.db import Database
from app.services import movimentacao_service as svc

# Cada campo aceita várias variações de nome de coluna (minúsculas, sem
# acento é comparado à parte). Adicione mais variações aqui se sua planilha
# usar nomes diferentes.
MAPEAMENTOS: dict[str, list[str]] = {
    "nr_ativo": ["nº ativo", "nr ativo", "n° ativo", "nr. ativo", "numero ativo", "ativo"],
    "nr_serie": ["nº de série", "nr de serie", "número de série", "n° de série", "serie"],
    "tipo": ["tipo equip.", "tipo equipamento", "tipo máq.", "tipo maquina", "tipo"],
    "modelo": ["modelo"],
    "empresa": ["empresa"],
    "owner_ativo": ["owner ativo", "owner"],
    "data_recebimento": ["data recebimento", "data de recebimento"],
    "maquina_preparada": ["máq. preparada", "maquina preparada", "máquina preparada"],
    "previsao_alocacao": ["previsão alocação", "previsao alocacao", "previsão de alocação"],
    "observacoes": ["observações", "observacoes", "obs"],
    "colaborador": ["nome colaborador", "colaborador", "nome"],
    "empresa_colaborador": ["empresa colaborador", "empresa do colaborador"],
    "nr_chamado": ["nº chamado", "nr chamado", "n° chamado", "nº chamado2", "nr chamado2", "chamado"],
}


def _normalizar(texto: str) -> str:
    import unicodedata

    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sem_acento.strip().lower()


def _mapear_colunas(cabecalhos: list[str]) -> dict[str, int]:
    """Devolve {campo_interno: índice_da_coluna} para os campos que
    conseguiu reconhecer no cabeçalho da planilha."""
    normalizados = [_normalizar(str(c or "")) for c in cabecalhos]
    encontrado: dict[str, int] = {}
    for campo, variantes in MAPEAMENTOS.items():
        variantes_norm = [_normalizar(v) for v in variantes]
        for indice, cabecalho in enumerate(normalizados):
            if cabecalho in variantes_norm:
                encontrado[campo] = indice
                break
    return encontrado


def _valor(linha, colunas: dict[str, int], campo: str):
    indice = colunas.get(campo)
    if indice is None or indice >= len(linha):
        return None
    valor = linha[indice]
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


def _verdadeiro(valor) -> bool:
    if valor is None:
        return False
    return str(valor).strip().upper() in ("SIM", "TRUE", "1", "YES", "X")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arquivo", help="Caminho do arquivo .xlsx")
    parser.add_argument("aba", nargs="?", default=None, help="Nome da aba (opcional, usa a primeira por padrão)")
    parser.add_argument("--confirmar", action="store_true", help="Grava de verdade (sem isso, só simula)")
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        print(f"Arquivo não encontrado: {args.arquivo}")
        sys.exit(1)

    livro = openpyxl.load_workbook(args.arquivo, data_only=True, read_only=True)
    aba = livro[args.aba] if args.aba else livro.worksheets[0]
    print(f"Lendo aba '{aba.title}' de {args.arquivo}...")

    linhas = list(aba.iter_rows(values_only=True))
    if not linhas:
        print("A aba está vazia.")
        return

    cabecalhos = list(linhas[0])
    colunas = _mapear_colunas(cabecalhos)

    if "nr_ativo" not in colunas:
        print(
            "Não encontrei uma coluna de nº de ativo reconhecível no cabeçalho.\n"
            f"Cabeçalhos encontrados: {cabecalhos}\n"
            "Ajuste MAPEAMENTOS no início deste script para incluir o nome exato da sua coluna."
        )
        sys.exit(1)

    print("Colunas reconhecidas:")
    for campo, indice in colunas.items():
        print(f"  {campo:20s} <- '{cabecalhos[indice]}'")
    campos_nao_reconhecidos = set(MAPEAMENTOS) - set(colunas)
    if campos_nao_reconhecidos:
        print(f"Campos não encontrados na planilha (serão deixados em branco): {sorted(campos_nao_reconhecidos)}")

    modo = "GRAVANDO DE VERDADE" if args.confirmar else "SIMULAÇÃO (--dry-run, nada será gravado)"
    print(f"\nModo: {modo}\n")

    db = Database(Config.DATABASE_PATH)
    db.init_schema()

    criados = alocados = atualizados = ignorados = 0

    with db.connection() as conn:
        for linha in linhas[1:]:
            nr_ativo = _valor(linha, colunas, "nr_ativo")
            if not nr_ativo:
                ignorados += 1
                continue
            nr_ativo = str(nr_ativo).strip()

            tipo = _valor(linha, colunas, "tipo") or "Outro"
            dados = dict(
                nr_serie=_valor(linha, colunas, "nr_serie"),
                modelo=_valor(linha, colunas, "modelo"),
                owner_ativo=_valor(linha, colunas, "owner_ativo"),
                observacoes=_valor(linha, colunas, "observacoes"),
            )
            data_recebimento = _valor(linha, colunas, "data_recebimento")
            maquina_preparada = _verdadeiro(_valor(linha, colunas, "maquina_preparada"))
            previsao_alocacao = _verdadeiro(_valor(linha, colunas, "previsao_alocacao"))
            empresa_nome = _valor(linha, colunas, "empresa")
            colaborador = _valor(linha, colunas, "colaborador")
            empresa_colaborador = _valor(linha, colunas, "empresa_colaborador") or empresa_nome
            nr_chamado = _valor(linha, colunas, "nr_chamado")

            existente = repo.obter_equipamento_por_nr_ativo(conn, nr_ativo)

            if existente:
                # Já existe: só catálogo. Nunca mexe em status/colaborador
                # de algo que o sistema já está controlando ao vivo.
                if args.confirmar:
                    repo.atualizar_equipamento(conn, existente.id, **{k: v for k, v in dados.items() if v})
                atualizados += 1
                continue

            if colaborador:
                alocados += 1
                if args.confirmar:
                    svc.registrar_entrada(
                        conn,
                        nr_ativo=nr_ativo,
                        tipo=str(tipo),
                        analista_id=None,
                        nr_serie=dados["nr_serie"],
                        modelo=dados["modelo"],
                        empresa_nome=empresa_nome,
                        owner_ativo=dados["owner_ativo"],
                        data_recebimento=str(data_recebimento) if data_recebimento else None,
                        maquina_preparada=maquina_preparada,
                        previsao_alocacao=previsao_alocacao,
                        observacoes=dados["observacoes"],
                    )
                    svc.registrar_entrega(
                        conn,
                        nr_ativo=nr_ativo,
                        nome_colaborador=str(colaborador).strip(),
                        empresa_colaborador=str(empresa_colaborador).strip() if empresa_colaborador else "",
                        analista_id=None,
                        nr_chamado=str(nr_chamado).strip() if nr_chamado else None,
                        observacoes="Migrado da planilha anterior.",
                    )
            else:
                criados += 1
                if args.confirmar:
                    svc.registrar_entrada(
                        conn,
                        nr_ativo=nr_ativo,
                        tipo=str(tipo),
                        analista_id=None,
                        nr_serie=dados["nr_serie"],
                        modelo=dados["modelo"],
                        empresa_nome=empresa_nome,
                        owner_ativo=dados["owner_ativo"],
                        data_recebimento=str(data_recebimento) if data_recebimento else None,
                        maquina_preparada=maquina_preparada,
                        previsao_alocacao=previsao_alocacao,
                        observacoes=dados["observacoes"],
                    )

    print(
        f"\nResumo: {criados} novo(s) em estoque, {alocados} novo(s) já marcado(s) como alocado(s), "
        f"{atualizados} existente(s) atualizado(s), {ignorados} linha(s) ignorada(s) (sem nº de ativo)."
    )
    if not args.confirmar:
        print("Isso foi só uma simulação — rode de novo com --confirmar para gravar de verdade.")


if __name__ == "__main__":
    main()
