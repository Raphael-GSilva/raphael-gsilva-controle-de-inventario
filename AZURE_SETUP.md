# Configurando o Microsoft Entra ID

Este guia cobre os dois usos da Microsoft neste projeto:

- **Login dos usuários** (delegado, interativo) — para `AUTH_MODE=microsoft`.
- **Sincronização com o SharePoint/OneDrive** (app-only, em segundo
  plano) — para `SHAREPOINT_SYNC_ENABLED=true`.

Você pode configurar só o login primeiro e deixar a sincronização
desligada (`SHAREPOINT_SYNC_ENABLED=false`) — o sistema funciona
normalmente sem ela, só não replica os dados para a planilha.

Os nomes de tela abaixo são os usados pela Microsoft no momento em que
este guia foi escrito — o portal muda com frequência, então se algum nome
estiver um pouco diferente, procure por algo equivalente (a função é mais
estável que o rótulo exato).

## 1. Criar o app registration

1. Acesse [entra.microsoft.com](https://entra.microsoft.com) (ou
   portal.azure.com > Microsoft Entra ID) com uma conta que tenha
   permissão para registrar aplicativos no seu tenant.
2. **Identidade > Aplicativos > Registros de aplicativo > Novo registro.**
3. Nome: algo como `Raphael-GSilva Controle de Inventário` (só um rótulo,
   não afeta o funcionamento).
4. Tipos de conta com suporte: **Somente contas neste diretório
   organizacional** (single tenant) — a menos que vocês tenham um motivo
   específico para multi-tenant.
5. Redirect URI: escolha **Web** e informe
   `http://127.0.0.1:5000/auth/callback` para testar localmente. Quando
   for colocar no ar para o time (ver README, seção "Colocando no ar"),
   volte aqui e adicione também o endereço real, ex:
   `http://10.0.0.5:5000/auth/callback` — pode ter mais de um Redirect
   URI cadastrado ao mesmo tempo.
6. Clique em **Registrar**.

Na página de visão geral do app que aparece, anote:

- **ID do aplicativo (cliente)** → vai virar `MICROSOFT_CLIENT_ID`
- **ID do diretório (locatário)** → vai virar `MICROSOFT_TENANT_ID`

## 2. Criar o Client Secret

1. No menu do app registration: **Certificados e segredos > Segredos do
   cliente > Novo segredo do cliente.**
2. Descrição livre, validade (ex: 12 ou 24 meses — marque um lembrete
   para renovar antes de expirar, porque quando expira o login para de
   funcionar sem aviso prévio na tela).
3. **Copie o "Valor" (Value) imediatamente após criar** — ele some da
   tela depois e não tem como recuperar, só gerar um novo.
4. Isso vira `MICROSOFT_CLIENT_SECRET`.

## 3. Permissão delegada para o login (User.Read)

1. **APIs Permissions > Add a permission > Microsoft Graph > Delegated
   permissions.**
2. Marque `User.Read` (geralmente já vem adicionada por padrão).
3. Não precisa de consentimento de admin para essa permissão específica
   — cada usuário consente para si mesmo no primeiro login.

Isso é tudo que o **login** precisa. Preencha `MICROSOFT_CLIENT_ID`,
`MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` no `.env`, troque
`AUTH_MODE=microsoft` e teste o login antes de seguir para a
sincronização.

---

## 4. (Opcional) Permissão de aplicativo para a sincronização

A sincronização roda em segundo plano, sem um usuário logado no momento,
então usa uma **permissão de aplicativo** (não delegada) — precisa de
consentimento de um administrador do tenant.

1. No mesmo app registration: **API Permissions > Add a permission >
   Microsoft Graph > Application permissions.**
2. Duas opções, dependendo do quanto vocês querem restringir o acesso:
   - **`Sites.Selected`** (recomendado): o app só acessa os sites/drives
     que forem explicitamente liberados para ele (passo 5 abaixo). Mais
     trabalho de configurar, bem mais seguro — o app não consegue ler
     nada além do que foi liberado.
   - **`Sites.ReadWrite.All`**: o app consegue ler/escrever em qualquer
     site do SharePoint do tenant. Mais simples de configurar, mas é uma
     permissão ampla — avalie com o time de segurança/TI antes de usar em
     produção.
3. Depois de adicionar, clique em **"Conceder consentimento do
   administrador"** (precisa ser Global Admin ou Privileged Role Admin do
   tenant). Sem esse consentimento, a sincronização falha com erro de
   permissão.

## 5. Se escolheu Sites.Selected: liberar o site/drive específico

Isso não dá para fazer pela tela do Entra — é uma chamada à API do Graph.
A forma mais simples é usar o **Graph Explorer**
([aka.ms/ge](https://aka.ms/ge)), logado como admin:

```
POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions
Content-Type: application/json

{
  "roles": ["write"],
  "grantedToIdentities": [{
    "application": {
      "id": "<MICROSOFT_CLIENT_ID do seu app>",
      "displayName": "Raphael-GSilva Controle de Inventário"
    }
  }]
}
```

Se o arquivo estiver no OneDrive pessoal de alguém (como no link
`.../personal/...` que aparece quando você abre a planilha pelo
navegador) em vez de um site de equipe do SharePoint, o conceito de
"site" do Graph ainda existe por trás — rode primeiro
`python scripts/resolver_sharepoint_ids.py "<link>"` para achar o
`driveId`, e use o endpoint equivalente para o drive pessoal
(`/drives/{drive-id}/permissions/...` — a Microsoft documenta os detalhes
em "Manage OneDrive/SharePoint permissions via Graph").

## 6. Preparar a planilha

A sincronização lê/escreve através de uma **Tabela do Excel** nomeada
(não só um intervalo de células soltas):

1. Abra a planilha, selecione o intervalo com os dados (incluindo
   cabeçalho).
2. **Inserir > Tabela** (ou Ctrl+T).
3. Com a tabela selecionada, vá em **Estrutura da Tabela / Table Design**
   e dê um nome a ela (ex: `TabelaEstoque`) — esse nome vai em
   `SHAREPOINT_TABLE_NAME`.
4. O nome da aba (a guia lá embaixo, ex: "Estoque") vai em
   `SHAREPOINT_WORKSHEET_NAME`.

## 7. Descobrir DRIVE_ID e ITEM_ID

Com `GRAPH_CLIENT_ID`/`GRAPH_CLIENT_SECRET`/`GRAPH_TENANT_ID` (ou os
`MICROSOFT_*` equivalentes) já no `.env`:

```bash
python scripts/resolver_sharepoint_ids.py "https://sua-empresa-my.sharepoint.com/:x:/g/personal/..."
```

Cole exatamente o link que aparece na barra de endereço quando você abre
a planilha no navegador. O script imprime as linhas prontas para colar no
`.env`.

## 8. Ativar

No `.env`:

```
SHAREPOINT_SYNC_ENABLED=true
SHAREPOINT_DRIVE_ID=...
SHAREPOINT_ITEM_ID=...
SHAREPOINT_WORKSHEET_NAME=Estoque
SHAREPOINT_TABLE_NAME=TabelaEstoque
```

Reinicie a aplicação. Registre uma entrada de teste e confira se a linha
aparece na planilha. Se não aparecer, olhe o log do processo (os erros de
sincronização são registrados como aviso, não travam a aplicação) — a
causa mais comum é falta de consentimento de admin (passo 4) ou o site
não ter sido liberado para o app (passo 5, se usou Sites.Selected).

## Conferindo se está tudo certo

Resumo do que precisa estar preenchido em cada cenário:

| Cenário | Variáveis obrigatórias |
|---|---|
| Só testando localmente | nenhuma (padrões do `.env.example` já funcionam) |
| Login Microsoft real | `AUTH_MODE=microsoft` + os 3 `MICROSOFT_*` |
| + Sincronização com SharePoint | + `SHAREPOINT_SYNC_ENABLED=true` + `SHAREPOINT_DRIVE_ID`/`ITEM_ID`/`WORKSHEET_NAME`/`TABLE_NAME` |

A aplicação verifica isso sozinha ao subir: se `AUTH_MODE=microsoft` mas
faltar alguma variável, ela recusa iniciar com uma mensagem dizendo
exatamente o que falta, em vez de deixar você descobrir isso no meio de
um login de alguém do time.

## Multi-tenant — se este sistema for virar produto para várias empresas

Tudo acima descreve o cenário padrão: login restrito à SUA empresa
(`MICROSOFT_TENANT_ID` = o ID do seu diretório). Isso é o certo para um
sistema interno de uma única empresa.

Se a ideia é vender este sistema para OUTRAS empresas fazerem login com
as próprias contas Microsoft, sem cada uma precisar criar um cadastro de
app do zero no Azure delas, existe o modo **multi-tenant**:

1. No passo 5 (**Tipos de conta com suporte**) do cadastro do app, escolha
   **Contas em qualquer diretório organizacional** em vez de "Somente
   contas neste diretório".
2. No `.env`, defina `MICROSOFT_TENANT_ID=organizations` (em vez do ID de
   um tenant específico).
3. Cada empresa cliente, na primeira vez que alguém de lá tentar entrar,
   vê uma tela da própria Microsoft pedindo consentimento — um
   administrador da empresa cliente clica em "Aceitar" uma vez, e pronto,
   o app fica liberado para todo mundo de lá.

O código já foi ajustado para esse cenário: a identidade de cada pessoa é
guardada como o PAR (oid + tenant de origem), não só o oid sozinho — a
própria Microsoft recomenda isso para apps multi-tenant, porque dois
tenants diferentes podem, em teoria, gerar valores de oid coincidentes.

**Atenção a um detalhe se for hospedar uma instância separada por
cliente** (uma URL/servidor só para a Empresa X): com o app em modo
multi-tenant, tecnicamente qualquer pessoa com QUALQUER conta Microsoft
corporativa do mundo consegue tentar logar naquela URL — não só gente da
Empresa X. Hoje o sistema não bloqueia isso sozinho (ele so dá o papel
`CONSULTA`, o mais restrito, para quem não é reconhecido, mas ainda deixa
entrar). Antes de operar assim de verdade, vale adicionar uma checagem
"o tenant de quem logou é o tenant esperado desta instância" — me avise
quando chegar nesse ponto que eu implemento.

## Validando de verdade antes de cobrar de alguém

Este código segue os padrões oficiais da Microsoft, mas nunca foi testado
de ponta a ponta com credenciais reais — o ambiente onde foi construído
não tem acesso à internet. Antes de usar isso com o primeiro cliente
pagante, valide de verdade. Algumas opções, do mais simples ao mais
completo (chequei a disponibilidade de cada uma agora, porque isso muda
com frequência):

- **Só para testar o login:** crie uma conta Azure gratuita e, dentro
  dela, um tenant novo do Microsoft Entra ID (gratuito, sem cartão de
  crédito cobrado — "Microsoft Entra ID Free"). Isso é suficiente para
  testar o fluxo de login inteiro (passos 1 a 7 deste guia), mas não vem
  com SharePoint, então não serve para testar a sincronização.
- **Para testar login + sincronização com SharePoint:** precisa de um
  tenant com Microsoft 365 de verdade (não só Entra ID). O "sandbox
  gratuito" que a Microsoft costumava liberar para qualquer
  desenvolvedor (Microsoft 365 Developer Program) ficou mais restrito
  recentemente — hoje exige ser assinante Visual Studio, ou participar de
  programas de parceiro específicos da Microsoft. Se você não se
  qualificar, as alternativas são: testar num espaço de teste dentro do
  Microsoft 365 da sua própria empresa atual (um site/planilha nova, sem
  encostar em nada de produção), ou uma assinatura Microsoft 365 Business
  Basic de baixo custo só para isso.

Qualquer erro que aparecer nesse teste, me manda a mensagem exata — mesmo
sem poder rodar isso aqui, consigo ler o erro e ajustar o código.
