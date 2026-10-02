# Raphael-GSilva Controle de Inventário

Sistema de controle de inventário de equipamentos: entrada/devolução,
entrega a colaboradores, consulta e dashboard, com login via Microsoft
Entra ID e sincronização com uma planilha do SharePoint/OneDrive.

Nasce 100% zerado — sem nenhuma empresa, tipo de equipamento ou dado de
exemplo pré-carregado. As listas de empresa e tipo nas telas crescem
organicamente conforme o uso, ou você carrega tudo de uma vez com
`scripts/importar_excel.py` a partir de uma planilha existente.

## Por que foi construído assim

1. **O banco local (SQLite) é a fonte da verdade, não a planilha.** Toda
   operação grava no banco primeiro; a sincronização com o SharePoint
   acontece depois, em segundo plano, e nunca bloqueia nem desfaz uma
   operação que já teve sucesso.
2. **Dependências mínimas de propósito.** Sem SQLAlchemy, sem Flask-Login,
   sem Flask-WTF — só `sqlite3` (biblioteca padrão), Flask puro, `msal`
   para o login e `openpyxl` para importar planilhas. A proteção CSRF é
   implementada em `app/csrf.py` usando `itsdangerous` (já incluso no
   Flask), sem depender de biblioteca externa.
3. **Zero dado de exemplo embutido.** Empresa e tipo de equipamento não
   são listas fixas — crescem a partir do que já existe no banco.

Todo o núcleo tem **47 testes automatizados** cobrindo o caminho feliz e
os casos que devem falhar de propósito (entregar equipamento já alocado,
ativo duplicado, POST sem token CSRF, etc). Rode
`python -m unittest discover -s tests` a qualquer momento para conferir.

## Ciclo de vida de um equipamento

```
Entrada → Em estoque → Entrega → Alocado → Devolução → Em estoque
                                                      ↘ Em manutenção (condição Ruim)
Em estoque ──────────────────────────────── Baixa → Baixado
Em manutenção ───────────────────────────── Baixa → Baixado
```

**Baixa de equipamento** — retira definitivamente o equipamento do
inventário ativo. Disponível no menu lateral em **Movimentações > Baixa
de equipamento**. Não é possível baixar um equipamento que ainda está
alocado a alguém (é necessário registrar a devolução primeiro).

## Passo a passo — rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt

copy .env.example .env          # Windows
# cp .env.example .env          # Mac/Linux
# Não precisa editar nada — AUTH_MODE=mock já funciona.

python run.py
```

Abra `http://127.0.0.1:5000`. A primeira pessoa que logar vira ADMIN
automaticamente.

## Para rodar de novo (próximos dias)

```bash
.venv\Scripts\activate
python run.py
```

## Os três papéis

| Papel | Pode |
|---|---|
| `CONSULTA` | Ver dashboard, consultar equipamentos e histórico |
| `ANALISTA` | Tudo do CONSULTA + registrar entrada, entrega e devolução |
| `ADMIN` | Tudo do ANALISTA + promover/rebaixar usuários |

Se em algum momento ninguém mais tiver acesso de admin:
```bash
python scripts/promover_admin.py email@empresa.com
```

## Backup do banco de dados

O banco é um arquivo em `instance/inventario.db`. Para fazer uma cópia
de segurança segura (mesmo com o programa rodando):
```bash
python scripts/backup_banco.py
```
Cria uma cópia em `backups/inventario_AAAA-MM-DD_HHhMMm.db`. Configure
o Agendador de Tarefas do Windows (ou crontab no Linux) para rodar isso
automaticamente todo dia — o script já tem as instruções.

## Importando dados de uma planilha existente

```bash
python scripts/importar_excel.py planilha.xlsx        # simula
python scripts/importar_excel.py planilha.xlsx --confirmar  # grava
```

## Ligando o login Microsoft e a sincronização com SharePoint

Ver **AZURE_SETUP.md** para o passo a passo completo.

## Rodando os testes

```bash
python -m unittest discover -s tests -v
```

## Colocando no ar para o time

O `python run.py` é para uso local/desenvolvimento. Para o time todo
acessar, use um servidor adequado:

```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 run:app
```

O time acessa por `http://<ip-da-máquina>:5000`.

## Estrutura do projeto

```
app/
  db.py                    Conexão SQLite, schema e backup seguro
  models.py                Dataclasses (Equipamento, Movimentacao, Usuario...)
  repositories.py          Todo o SQL centralizado
  config.py                Configuração + persistência da SECRET_KEY
  csrf.py                  Proteção CSRF (sem dependência externa)
  auth/                    Login mock e login Microsoft (MSAL)
  services/                Regras de negócio (máquina de estados)
  routes/                  Rotas Flask
  sharepoint/              Cliente Graph API e sincronização
  templates/, static/      Telas
scripts/
  init_db.py               Inicializa o banco
  backup_banco.py          Backup seguro do banco
  promover_admin.py        Promove alguém a ADMIN via linha de comando
  importar_excel.py        Importa dados de uma planilha existente
  resolver_sharepoint_ids.py  Descobre DRIVE_ID/ITEM_ID de um link
tests/
  test_movimentacao_service.py  Regras de negócio (máquina de estados)
  test_repositories.py         Repositórios, multi-tenant, backup
  test_routes.py               Rotas HTTP e controle de acesso
  test_csrf.py                 Proteção CSRF com CSRF genuinamente ligado
  test_importar_excel.py       Script de importação ponta a ponta
```
