# Raphael-GSilva Controle de Inventário
![Dashboard](Controle%20Invent%C3%A1rio.jpeg)

Sistema de controle de inventário de equipamentos: entrada/devolução,
entrega a colaboradores, consulta e dashboard, com login via Microsoft
Entra ID e sincronização com uma planilha do SharePoint/OneDrive.

Não vem com nenhuma empresa, tipo de equipamento ou qualquer outro dado
pré-cadastrado — nasce 100% zerado e serve qualquer empresa. As listas de
empresa e de tipo de equipamento nas telas são texto livre com sugestão:
crescem sozinhas conforme você cadastra, ou você carrega tudo de uma vez
com `scripts/importar_excel.py` a partir de uma planilha existente.

## Por que foi construído assim

Três decisões vale a pena entender antes de mexer no código:

1. **O banco local (SQLite) é a fonte da verdade, não a planilha.** Toda
   operação grava no banco primeiro; a sincronização com o SharePoint
   acontece depois, em segundo plano, e nunca bloqueia nem desfaz uma
   operação que já teve sucesso. Isso evita que uma instabilidade de rede
   ou da API da Microsoft derrube o sistema.
2. **Dependências mínimas de propósito.** Sem SQLAlchemy, sem Flask-Login,
   sem Flask-WTF — só `sqlite3` (biblioteca padrão), Flask puro e `msal`
   para o login (esse não dá pra evitar, é o jeito certo de falar com o
   Entra ID). Menos dependências, menos coisa que pode quebrar ou ficar
   desatualizada.
3. **Zero dado de exemplo embutido.** Empresa e tipo de equipamento não
   são listas fixas no código — são gerados a partir do que já existe no
   banco (`repositories.listar_empresas` e
   `repositories.listar_tipos_equipamento_usados`). Isso é o que permite
   entregar o mesmo sistema para qualquer empresa sem precisar editar
   código nenhum.

Todo o núcleo (banco, regras de negócio, rotas, painel de admin) tem
**41 testes automatizados** cobrindo o caminho feliz e os casos que devem
falhar de propósito (entregar equipamento já alocado, ativo duplicado,
etc). Rode `python -m unittest discover -s tests` a qualquer momento para
conferir.

## Passo a passo — rodar localmente (sem Microsoft ainda)

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # Windows: copy .env.example .env
# Não precisa editar nada ainda — o padrão (AUTH_MODE=mock) já funciona.

python run.py
```

Abra `http://127.0.0.1:5000`. Você verá uma tela de login simplificada
(sem Microsoft) — digite qualquer nome e e-mail para entrar. Esse é o
`AUTH_MODE=mock`, pensado para você validar todas as telas e o fluxo
completo antes de configurar o Azure AD.

### Primeiro acesso

**A primeira pessoa que logar no sistema (em qualquer modo) vira ADMIN
automaticamente.** A partir da segunda, todo mundo entra com o papel
`CONSULTA` (só visualiza) — um ADMIN promove quem precisar em
**Administração > Usuários**. Se em algum momento ninguém mais tiver
acesso de admin, use `python scripts/promover_admin.py email@empresa.com`.

Os três papéis:

| Papel | Pode |
|---|---|
| `CONSULTA` | Ver dashboard, consultar equipamentos e histórico |
| `ANALISTA` | Tudo do CONSULTA + registrar entrada, entrega e devolução |
| `ADMIN` | Tudo do ANALISTA + promover/rebaixar usuários |

## Rodando os testes

```bash
python -m unittest discover -s tests -v
```

## Trazendo os dados que já existem

Se você tem os equipamentos hoje numa planilha, exporte a aba principal
como `.xlsx` e rode:

```bash
python scripts/importar_excel.py caminho/planilha.xlsx        # simula, não grava nada
python scripts/importar_excel.py caminho/planilha.xlsx --confirmar   # grava de verdade
```

O script reconhece várias variações dos nomes de coluna que apareceram na
sua planilha (Nº Ativo, Nº de Série, Tipo Equip., Modelo, Empresa, Owner
Ativo, Nome Colaborador, Nº Chamado, Máq. Preparada, Previsão
Alocação...). Equipamento novo **sem** colaborador reconhecido na linha
entra como "Em estoque"; **com** colaborador reconhecido, já entra
"Alocado" a essa pessoa, com o histórico de entrada+entrega devidamente
registrado. Para um equipamento que **já existe** no banco, o script só
atualiza dados de catálogo (série, modelo) — nunca mexe em status ou
colaborador atual, porque isso já é controlado ao vivo pelo sistema, que é
sempre mais confiável que uma planilha que pode estar desatualizada.

## Ligando o login Microsoft e a sincronização com o SharePoint

Isso exige configurar um "app registration" no Microsoft Entra ID —
passo a passo completo em **[AZURE_SETUP.md](AZURE_SETUP.md)**. Depois de
configurado, é só preencher as variáveis correspondentes no `.env` e
trocar `AUTH_MODE=microsoft`.

**Um aviso importante:** o código do login Microsoft e da sincronização
foi escrito seguindo à risca os padrões oficiais da Microsoft (o mesmo
usado no exemplo oficial `ms-identity-python-webapp`), mas eu não
consegui testá-lo de ponta a ponta com credenciais reais — o ambiente
onde este projeto foi montado não tem acesso à internet/Azure. Reserve um
tempo para testar esse fluxo especificamente com as suas credenciais
antes de confiar 100% nele. Tudo o mais (banco, regras de negócio, telas,
painel de admin) foi testado de verdade e está coberto pelos 41 testes.

## Colocando no ar para o time (não só no seu computador)

O `python run.py` usa o servidor de desenvolvimento do Flask, que não
aguenta bem múltiplos usuários simultâneos. Para o time todo acessar,
rode com um servidor de verdade num computador/servidor sempre ligado na
rede da empresa:

```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 run:app
```

Depois disso, o time acessa por `http://<ip-ou-nome-da-máquina>:5000`.
Lembre-se de atualizar o **Redirect URI** no app registration do Azure
para apontar para esse endereço em vez de `127.0.0.1` — ver
AZURE_SETUP.md.

## Estrutura do projeto

```
app/
  db.py                    Conexão SQLite e schema
  models.py                Dataclasses (Equipamento, Movimentacao, Usuario...)
  repositories.py          Todo o SQL da aplicação, centralizado
  config.py                Configuração via variáveis de ambiente
  auth/                    Login mock e login Microsoft (MSAL)
  services/                Regras de negócio (a máquina de estados)
  routes/                  Rotas Flask (dashboard, equipamentos, movimentações, admin)
  sharepoint/               Cliente do Microsoft Graph e sincronização
  templates/, static/      Telas
scripts/
  init_db.py                Inicializa o banco
  promover_admin.py         Promove alguém a ADMIN via linha de comando
  importar_excel.py         Importa dados de uma planilha existente
  resolver_sharepoint_ids.py  Descobre DRIVE_ID/ITEM_ID a partir de um link
tests/                      41 testes automatizados
```

## O que considerar mudar se o time crescer muito

SQLite aguenta bem um time interno (dezenas de pessoas, milhares de
equipamentos). Se um dia isso não for mais suficiente, a camada de
repositório (`app/repositories.py`) foi escrita separada das regras de
negócio exatamente para que trocar o banco por Postgres, por exemplo, não
exija reescrever `services/` nem `routes/`.
