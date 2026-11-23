---
translated: true
source: misc/admin_api.ipynb
---
# 用 Admin API 管理你的組織

> 原文：[misc/admin_api.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/admin_api.ipynb)

用 Python SDK 的 client.beta.organization 邀請使用者、建立 workspace、稽核 API key、建立 service account、讀取 rate limit。

## 這篇在做什麼

把一個團隊導入 Claude API 時，Console 上要點的步驟每次都一樣：邀請每個人、建 workspace、加成員、檢查有哪些 API key、幫 CI 設一個身分。手動做不留紀錄，團隊一多也做不完。

Admin API 把這些操作做成 `/v1/organizations` 底下的 REST endpoint，Python SDK 包成 `client.beta.organization`。這個 notebook 會從頭到尾導入一個團隊，順便稽核組織的 API key，最後把建出來的東西全部清掉。

## 學完你會

- 用 OAuth 登入或 Console 的 Admin API key，以組織 admin 身分認證
- 邀請使用者、設定組織角色、建立 workspace 並加入成員
- 稽核組織的 API key，並讀取 rate limit
- 建立給自動化用的 service account，並授權它存取 workspace

## 開跑前

- Python 3.11+ 和 `anthropic>=1.1.0`（第一個有 `client.beta.organization` 的版本）
- 一個 Claude Console **組織**，而且你的角色是 `admin`、`owner` 或 `primary_owner`。個人帳號不能用 Admin API。
- 選用：[`ant` CLI](https://platform.claude.com/docs/en/cli-sdks-libraries/cli/authentication)，走 OAuth 登入時會用到

## 以 admin 身分認證

只限單一 workspace 的 API key 不能呼叫 Admin API。它接受三種憑證：`org:admin` OAuth token、Admin API key，以及沒有限定單一 workspace 的個人或 service account key。這個 notebook 用前兩種，兩種都只有組織 admin 能建立：

| Credential | How to get it | Coverage |
|---|---|---|
| OAuth token with the `org:admin` scope | `ant auth login --profile admin --scope org:admin` | Every endpoint in this notebook |
| Admin API key (`sk-ant-admin01-...`) | Claude Console → Settings → [Admin keys](https://platform.claude.com/settings/admin-keys) | Everything except service accounts and workload identity federation |

OAuth 登入會開瀏覽器、請你選組織，並把可更新的 token 存在 `~/.config/anthropic/`。建立 client 時指定 `profile="admin"`，SDK 就會載入它。

想改用 Admin API key，就在 notebook 旁邊的 `.env` 加上 `ANTHROPIC_ADMIN_API_KEY=sk-ant-admin01-...`。setup cell 有設這個 key 就用它，沒有就退回 OAuth profile。

```python
%%capture
%pip install -U "anthropic>=1.1.0" python-dotenv
```

```python
import os
import time
from datetime import UTC, datetime
from itertools import islice

import anthropic
from dotenv import load_dotenv

load_dotenv()

ADMIN_KEY = os.getenv("ANTHROPIC_ADMIN_API_KEY")
# The profile name you passed to `ant auth login --profile`.
PROFILE = os.getenv("ANTHROPIC_PROFILE", "admin")
# Only used to pick which rate limit group to print.
MODEL = "claude-sonnet-5-5"

if ADMIN_KEY:
    client = anthropic.Anthropic(api_key=ADMIN_KEY)
else:
    client = anthropic.Anthropic(profile=PROFILE)

org = client.beta.organization.retrieve()
auth = "an Admin API key" if ADMIN_KEY else f"OAuth profile {PROFILE!r}"
print(f"Connected to {org.name} ({org.id}) with {auth}")
```

??? note "輸出"

    ```text
    Connected to Example Org (1f6e8a52-93c4-4d7b-a1e0-5b2c9d8e4f37) with OAuth profile 'admin'
    ```

`organization.retrieve()` 會呼叫 `GET /v1/organizations/me`。繼續之前先確認名稱：admin 憑證綁定一個組織，後面每個呼叫都是在讀寫這個組織。

後面的 notebook 會用同一個團隊的名字替建出來的東西命名，方便你在 Console 找到。

```python
RUN_ID = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
TEAM = f"research-{RUN_ID}"
print(TEAM)
```

??? note "輸出"

    ```text
    research-20260826-180659
    ```

## 邀請隊友並設定角色

邀請會寄一封註冊連結給對方，並記下對方接受後會拿到的角色。Console 組織的 API 接受 `user`、`developer`、`billing`、`claude_code_user`。`admin` 角色只能在 Console 授予。

新成員先給 `user`（可進 Console 和 playground，但沒有 API key），需要更多權限再升級。

邀請會寄出真的 email。有些組織只接受自己 email 網域的邀請，寄到其他網域會回 `400`。下一個 cell 預設用某位現有 admin 網域下的假地址，所以在任何組織都能跑。想試完整流程，就把 `INVITE_EMAIL` 設成隊友的地址。

```python
INVITE_EMAIL = os.getenv("INVITE_EMAIL")
if not INVITE_EMAIL:
    # Invites to other domains return a 400 in organizations that restrict invite domains.
    users = client.beta.organization.users.list(limit=100)
    admin = next((u for u in users if u.role in {"admin", "owner", "primary_owner"}), None)
    if admin is None:
        raise RuntimeError("No admin user to borrow an email domain from. Set INVITE_EMAIL.")
    INVITE_EMAIL = f"new.teammate+{RUN_ID}@{admin.email.split('@', 1)[1]}"

invite = client.beta.organization.invites.create(email=INVITE_EMAIL, role="user")
print(f"{invite.id}  {invite.email}  role={invite.role}  status={invite.status}")
print(f"expires {invite.expires_at:%Y-%m-%d}")
```

??? note "輸出"

    ```text
    invite_015gWxHNr6h6TdRPZTmuCGnn  new.teammate+20260826-180659@example.com  role=user  status=pending
    expires 2026-09-16
    ```

邀請 21 天後過期。`invites.list()` 會列出組織所有邀請和狀態，`invites.delete()` 可以撤銷還沒接受的邀請。

```python
for inv in client.beta.organization.invites.list(limit=100):
    print(f"{inv.email:<45} {inv.role:<16} {inv.status:<9} sent {inv.invited_at:%Y-%m-%d}")
```

??? note "輸出"

    ```text
    new.teammate+20260826-180659@example.com                 user             pending   sent 2026-08-26
    ```

對方接受後就會出現在 `users.list()`。下一個 cell 印出前 10 位。用 `email` 過濾可以找特定的人，再用 `users.update()` 改角色，或用 `users.remove()` 讓他離開組織。admin 不能透過 API 移除。

邀請還在等待時，下一個 cell 找不到使用者就會跳過升級，後面的成員 cell 也會跳過加入。對方接受之後兩者才會執行。

```python
# Iterating a list call fetches every page, so cap what gets printed.
for user in islice(client.beta.organization.users.list(limit=100), 10):
    print(f"{user.email:<45} {user.role:<16} joined {user.added_at:%Y-%m-%d}")

teammate = next(iter(client.beta.organization.users.list(email=INVITE_EMAIL)), None)
if teammate is None:
    print(f"\n{INVITE_EMAIL} hasn't accepted yet, nothing to promote")
else:
    teammate = client.beta.organization.users.update(teammate.id, role="developer")
    print(f"\n{teammate.email} is now {teammate.role}")
```

??? note "輸出"

    ```text
    ada@example.com                              admin            joined 2026-06-01
    ```

    ```text

    new.teammate+20260826-180659@example.com hasn't accepted yet, nothing to promote
    ```

## 為團隊建立 workspace

Workspace 在一個組織內切分 API key、花費上限、rate limit 和用量報表。通常一個團隊或一個環境一個 workspace。`tags` 放你自己的 metadata（例如成本中心），每次讀取都會帶回來。

```python
workspace = client.beta.organization.workspaces.create(
    name=TEAM,
    tags={"team": "research", "cost-center": "4711"},
)
print(workspace.id, workspace.name, workspace.tags)
```

??? note "輸出"

    ```text
    wrkspc_01JwQvzr7rXLA5AGx3HKfFUJ research-20260826-180659 {'team': 'research', 'cost-center': '4711'}
    ```

`workspaces.update()` 可以改名稱、顯示顏色或 tag。tag 會和既有的合併，把某個 tag 設成 `None` 就是移除。

```python
workspace = client.beta.organization.workspaces.update(
    workspace.id, tags={"env": "sandbox", "cost-center": None}
)
print(workspace.tags)
```

??? note "輸出"

    ```text
    {'env': 'sandbox', 'team': 'research'}
    ```

組織 admin 和 billing 使用者是每個 workspace 的隱含成員，不會出現在 `members.list()`。其他人都要有明確的 workspace 角色，例如 `workspace_user`、`workspace_developer`、`workspace_admin`。

`members.update()` 改角色，`members.remove()` 把人移出 workspace，但不影響他在組織裡的身分。

```python
if teammate:
    client.beta.organization.workspaces.members.add(
        workspace.id, user_id=teammate.id, workspace_role="workspace_developer"
    )

members = list(client.beta.organization.workspaces.members.list(workspace.id))
print(f"{workspace.name}: {len(members)} explicit member(s)")
for m in members:
    print(f"  {m.user_id} {m.workspace_role}")
```

??? note "輸出"

    ```text
    research-20260826-180659: 0 explicit member(s)
    ```

## 稽核 API key

Admin API 可以列出、改名、停用、封存 API key，但不能建立：新 key 只能從 Console 建。所以它適合拿來做排程稽核，不適合做 provisioning。

下一個 cell 會走過組織內所有啟用中的 key，標出超過 `MAX_KEY_AGE_DAYS` 的 key，以及沒有到期日的 key。

```python
MAX_KEY_AGE_DAYS = 90
now = datetime.now(UTC)

# The default workspace isn't returned by workspaces.list(), so any ID missing here is it.
workspace_names = {w.id: w.name for w in client.beta.organization.workspaces.list(limit=1000)}

flagged = []
for key in client.beta.organization.api_keys.list(status="active", limit=1000):
    if key.scope.type == "workspace":
        where = workspace_names.get(key.scope.workspace_id, "Default")
    else:
        where = "(organization)"
    age = (now - key.created_at).days
    expires = f"{key.expires_at:%Y-%m-%d}" if key.expires_at else "never"
    flags = []
    if age > MAX_KEY_AGE_DAYS:
        flags.append("old")
    if key.expires_at is None:
        flags.append("no-expiry")
    if flags:
        flagged.append(key)
    hint = key.partial_key_hint or "-"
    print(f"{key.name:<28} {where:<18} {hint:<24}", end=" ")
    print(f"{age:>4}d  expires {expires:<10} {' '.join(flags)}")

print(f"\n{len(flagged)} key(s) flagged")
```

??? note "輸出"

    ```text
    backend-prod                 production         sk-ant-api03-R2D...igAA    14d  expires 2027-08-12 
    ci-deploy                    production         sk-ant-api03-9xQ...0mAA    14d  expires 2026-12-09 

    0 key(s) flagged
    ```

停用 key 可以復原（`status="active"` 就會重新啟用），封存不行。`APPLY = False` 是 dry run，設成 `True` 才會真的停用被標記的 key。

先看過被標記的清單。沒有到期日的 key 即使正在服務正式流量也會被標記，而停用的 key 會讓請求立刻失敗。

```python
APPLY = False

if not flagged:
    print("no flagged keys, nothing to do")
for key in flagged:
    if APPLY:
        key = client.beta.organization.api_keys.update(key.id, status="inactive")
    print(f"{key.name:<28} -> {key.status}{'' if APPLY else '  (dry run, unchanged)'}")
```

??? note "輸出"

    ```text
    no flagged keys, nothing to do
    ```

## 建立自動化用的 service account

Service account 是組織裡的非人類成員，給 CI job 和後端服務用。它跟人一樣有組織角色和 workspace 角色，所以發給它的憑證不會綁在某個員工的帳號上。service account 的 endpoint 只接受 `org:admin` OAuth 憑證，Admin API key 會被拒絕。

`name` 是由小寫字母、數字、連字號組成的 slug，在組織內不能重複。service account endpoint 可能比建立動作慢一步：幾秒前才建好的物件，從這些 endpoint 讀可能暫時回 `404`，或是沒出現在列表裡。呼叫的對象是剛建的東西時，遇到 `404` 就重試，下一個 cell 的 helper 就是這樣做。

```python
# New objects can briefly 404 on the service account endpoints.
def retry_on_not_found(call, attempts: int = 6, delay: float = 5.0):
    for attempt in range(attempts):
        try:
            return call()
        except anthropic.NotFoundError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)


service_account = None
if ADMIN_KEY:
    print("Skipped: service account endpoints need the org:admin OAuth credential")
else:
    service_account = client.beta.organization.service_accounts.create(
        name=f"ci-{TEAM}",
        description="Deploy pipeline for the research team",
    )
    print(service_account.id, service_account.name, service_account.organization_role)
```

??? note "輸出"

    ```text
    svac_01ABCDEFabcdef0123456789XY ci-research-20260826-180659 developer
    ```

給它團隊 workspace 的角色，然後列出它的 membership。每個 service account 在預設 workspace 也都是隱含的 `workspace_user`，而且剛授予的權限可能要稍等才會出現在列表。

```python
if service_account:
    grant = retry_on_not_found(
        lambda: client.beta.organization.service_accounts.workspaces.add(
            service_account.id, workspace_id=workspace.id, workspace_role="workspace_developer"
        )
    )
    print(f"granted {grant.workspace_role} in {workspace.name}\n")
    for m in client.beta.organization.service_accounts.workspaces.list(service_account.id):
        name = workspace.name if m.workspace_id == workspace.id else "Default"
        print(f"{name:<28} {m.workspace_role:<22} {'implicit' if m.implicit else 'explicit'}")
```

??? note "輸出"

    ```text
    granted workspace_developer in research-20260826-180659

    Default                      workspace_user         implicit
    research-20260826-180659     workspace_developer    explicit
    ```

想讓 pipeline 用這個 service account 認證又不用存 secret，就把你的 CI provider 註冊成 federation issuer，再加一條規則把它的 OIDC token 對應到這個帳號。設定方式見 [Workload identity federation](https://platform.claude.com/docs/en/manage-claude/workload-identity-federation)。

## 檢查 rate limit

Rate limit 是設在組織層級。每個 group 涵蓋一個模型家族或 API 的其他部分，例如 `batch`、`files`、`web_search`。`rate_limits.list()` 回傳所有 group。下一個 cell 會印出涵蓋 `MODEL`（setup cell 定義的）的 group，加上不綁特定模型的 group。

```python
for rl in client.beta.organization.rate_limits.list():
    if rl.group.type == "model_group" and MODEL not in (rl.models or []):
        continue
    label = MODEL if rl.group.type == "model_group" else rl.group.type
    limits = ", ".join(f"{limit.type}={limit.value:,}" for limit in rl.limits)
    print(f"{label:<18} {limits}")
```

??? note "輸出"

    ```text
    batch              enqueued_batch_requests=500,000, requests_per_minute=4,000
    claude-sonnet-5    input_tokens_per_minute=10,000,000, output_tokens_per_minute=2,000,000, requests_per_minute=10,000
    ```

Workspace 繼承這些值。admin 可以在 Console 把某個 workspace 的上限壓得更低，而 `workspaces.rate_limits.list()` 只會回傳被覆蓋過的值。

```python
overrides = list(client.beta.organization.workspaces.rate_limits.list(workspace.id))
if not overrides:
    print(f"{workspace.name} has no overrides and inherits the organization limits")
for rl in overrides:
    print(rl.group.type, rl.models, [(limit.type, limit.value) for limit in rl.limits])
```

??? note "輸出"

    ```text
    research-20260826-180659 has no overrides and inherits the organization limits
    ```

## 清理

把這個 notebook 建的東西移除。**封存 workspace 是永久的，而且會撤銷裡面所有 API key**，所以在真實組織上跑之前，先確認 `workspace.name`。封存的 workspace 不算進 100 個 workspace 的上限。

如果前面有 cell 出錯，請手動跑這個 cell。它需要 kernel 裡有 `workspace`、`service_account` 和 `invite`。

```python
archived = client.beta.organization.workspaces.archive(workspace.id)
print(f"archived workspace {archived.name} at {archived.archived_at:%Y-%m-%d %H:%M}")

if service_account:
    retry_on_not_found(
        lambda: client.beta.organization.service_accounts.archive(service_account.id)
    )
    print(f"archived service account {service_account.name}")

# Deleting an accepted invite returns a 400, because that person is a member now.
if client.beta.organization.invites.retrieve(invite.id).status == "pending":
    client.beta.organization.invites.delete(invite.id)
    print(f"deleted invite for {invite.email}")
else:
    print(f"{invite.email} joined the organization, offboard them with users.remove()")
```

??? note "輸出"

    ```text
    archived workspace research-20260826-180659 at 2026-08-26 18:07
    archived service account ci-research-20260826-180659
    deleted invite for new.teammate+20260826-180659@example.com
    ```

## 下一步

你以 admin 身分認證、邀請了使用者、建了 workspace、讓 service account 能存取它、稽核了組織的 API key、也讀了 rate limit，全部都透過 `client.beta.organization`。

這裡沒涵蓋的相關 admin 功能：

- [Usage and cost cookbook](../observability/usage_cost_api.md) 和 [Usage and Cost API](https://platform.claude.com/docs/en/manage-claude/usage-cost-api)：依 workspace、key、model 回報 token 和金額
- [Claude Code Analytics API](https://platform.claude.com/docs/en/manage-claude/claude-code-analytics-api)：組織內每位使用者的 Claude Code 活動
- [Workload identity federation](https://platform.claude.com/docs/en/manage-claude/workload-identity-federation)：用 `client.beta.organization.federation` 為你建的 service account 做免 key 認證
- [Admin API reference](https://platform.claude.com/docs/en/api/admin)：所有 endpoint，包括 SDK 放在 `external_keys` 和 `federation` 下的那些

## 重點整理

- Admin API 管的是組織層級的事：成員、workspace、key、rate limit，憑證綁定單一組織。
- 單一 workspace 的 API key 不能用，要用 `org:admin` OAuth token 或 Admin API key；service account endpoint 只收 OAuth。
- API key 只能稽核（列出、改名、停用、封存），建立只能走 Console。
- 停用可復原、封存不可逆；先 dry run 再套用。
- 剛建立的物件在部分 endpoint 可能暫時 `404`，要有重試。

## 練習

1. 把 `MAX_KEY_AGE_DAYS` 改小，看稽核 cell 標出的 key 數量怎麼變。
2. 邀請時把角色從 `user` 改成 `developer`，再改 `users.update()` 的目標角色，確認升級流程。
3. 在 workspace 建立時多加一個 tag（例如 `cost_center`），再用 `workspaces.update()` 把它設成 `None` 移除，印出前後的 tags 對照。
