---
translated: true
source: examples/chatgpt/sharepoint_site_access/sharepoint_site_access.md
---

# 用 ChatGPT Admin API 管理 SharePoint 網站存取

> 原文：[examples/chatgpt/sharepoint_site_access/sharepoint_site_access.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_site_access/sharepoint_site_access.md)

把 SharePoint URL 解析成 site collection 識別碼，再用 Admin API 安全地管理 ChatGPT workspace 的 allowlist。

## 這篇在做什麼

ChatGPT workspace 管理員可以把 SharePoint app 限制在核准的 site collection 範圍內。這篇用一支 Python 腳本，把一般的 SharePoint URL 透過 Microsoft Graph 解析成 site collection 的 GUID，先預覽再套用，並透過 ChatGPT Admin API 管理 allowlist。

## 學完你會

- 把 SharePoint URL 解析成 allowlist 要用的 site collection GUID。
- 用腳本讀取、新增、移除、清空 workspace 的 SharePoint allowlist，並先 dry-run 預覽。
- 用 `Idempotency-Key` 安全地重試 policy 寫入。

## 開跑前

- Python 3.10 以上。
- ChatGPT workspace ID，以及有 `chatgpt.enterprise.apps.write` 權限的 workspace Admin API key。
- 能解析 SharePoint 網站的 Microsoft Graph access token（通常需要 `Sites.Read.All`）。
- workspace 已啟用 SharePoint 網站存取控制和 Admin API。

ChatGPT workspace 管理員可以把 SharePoint app 限制在核准的
SharePoint site collection 內。這個範例會把一般的 SharePoint URL 解析成
Microsoft Graph 的 site collection 識別碼，預覽變更，並透過 ChatGPT Admin API
管理 workspace 的 allowlist。

附帶的[管理腳本](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_site_access/sharepoint_site_access_admin.py)只用
Python 標準函式庫。它能接受多個 URL 或 CSV/文字檔，對 site collection 去重，
新增時保留既有的 allowlist 項目，支援選用的 idempotency key，
清空 policy 前也一定要明確確認。

> allowlist 是空的，代表使用者個人能存取的所有 SharePoint 網站都可以用。
> 清空 allowlist 是移除網站限制，不是封鎖所有網站。個人 OneDrive 的存取是另外控制的，
> 不會自動被 SharePoint site-collection allowlist 限制。

## 前置條件

- Python 3.10 或更新版本。
- 一個 ChatGPT workspace ID。
- 一把有 `chatgpt.enterprise.apps.write` 權限的 ChatGPT workspace Admin API key。
- 一個能解析相關 SharePoint 網站的 Microsoft Graph access token，
  通常需要 `Sites.Read.All` 權限。
- workspace 已啟用 SharePoint 網站存取控制和 Admin API。

Microsoft Graph token 只有在要解析 SharePoint URL 的指令才需要。
讀取或清空既有 allowlist，只需要 ChatGPT workspace Admin API key。

### 建立 workspace Admin API key

1. 打開 ChatGPT Admin Console 並選擇你的 workspace。
2. 到 **Credentials**，選 **Admin keys** 分頁。
3. 建立一把 **Restricted** 權限的 key，把 **Apps** 設成 **Write**。
4. 安全地保存 key，並用 `CHATGPT_ADMIN_TOKEN` 環境變數傳給腳本。

需要的權限是 `chatgpt.enterprise.apps.write`。OpenAI API
Platform key 和 Microsoft Graph token 是不同的憑證，不能取代 ChatGPT workspace Admin API key。

在 Bash shell 裡，用互動式提示輸入每個憑證，值不會寫進指令或 shell history：

```bash
read -r -s -p "ChatGPT workspace admin key: " CHATGPT_ADMIN_TOKEN
echo
export CHATGPT_ADMIN_TOKEN

read -r -s -p "Microsoft Graph access token: " MICROSOFT_GRAPH_TOKEN
echo
export MICROSOFT_GRAPH_TOKEN
```

不要把 token commit 進 repo、放進截圖，或複製到共用文件。

## 了解 SharePoint 網站識別碼

Microsoft Graph 會把 SharePoint URL 解析成一個識別碼，內含三個用逗號分隔的部分：

```text
hostname,site-collection-GUID,site-GUID
```

例如，查詢 `https://contoso.sharepoint.com/sites/Finance`
會回傳像這樣的識別碼：

```json
{
  "id": "contoso.sharepoint.com,da60e844-ba1d-49bc-b4d4-d5e36bae9019,712a596e-90a1-49e3-9b48-bfa80bee8740",
  "webUrl": "https://contoso.sharepoint.com/sites/Finance"
}
```

allowlist 接受的是中間那個值：
`da60e844-ba1d-49bc-b4d4-d5e36bae9019`。這個 GUID 代表整個
SharePoint site collection，所以該 collection 底下所有 site 或 web 都包含在內。不同的 URL 可能解析到同一個 collection GUID。allowlist
不會限制個別的子網站、資料夾或檔案。

## 檢查 SharePoint URL

在含有 `sharepoint_site_access_admin.py` 的目錄下執行：

```bash
python3 sharepoint_site_access_admin.py inspect \
  --site-url https://contoso.sharepoint.com/sites/Finance \
  --site-url https://contoso.sharepoint.com/sites/Research
```

這個指令會呼叫 Microsoft Graph，印出每個解析出的網站識別碼，以及去重後的 collection GUID。它不會讀取或修改 ChatGPT
workspace 的 allowlist。根網域 URL 和有 percent-encode 的路徑，例如
`https://contoso.sharepoint.com/sites/Finance%20Team`，都支援。

## 準備網站清單

大量更新時，建立一個叫 `sites.csv` 的 CSV 檔，裡面有 `site_url` 或
`url` 欄位：

```csv
site_url
https://contoso.sharepoint.com/sites/Finance
https://contoso.sharepoint.com/sites/Research
https://contoso.sharepoint.com/sites/Operations
```

一行一個 URL 的文字檔也可以。空行和 `#` 開頭的行會被忽略，沒有網站 URL 的 CSV 列也會被忽略。每個 request
最多支援 10,000 個不重複的 site collection。

## 讀取現有 allowlist

把 `<workspace-id>` 換成你的 ChatGPT workspace UUID：

```bash
python3 sharepoint_site_access_admin.py list \
  --workspace-id <workspace-id>
```

這個指令從下面這個位置讀取目前的 policy：

```text
GET https://api.chatgpt.com/v1/manage/workspaces/<workspace-id>/sharepoint/site-access/allow-list
```

## 預覽並新增 site collection

在改動 workspace 存取權限前，先預覽 URL、解析出的 collection GUID 和現有 policy：

```bash
python3 sharepoint_site_access_admin.py add \
  --workspace-id <workspace-id> \
  --sites-file sites.csv \
  --dry-run
```

預覽沒問題之後，新增核准的 site collection：

```bash
python3 sharepoint_site_access_admin.py add \
  --workspace-id <workspace-id> \
  --sites-file sites.csv
```

腳本會送出一個累加式的 `PUT` request：

```http
PUT /v1/manage/workspaces/<workspace-id>/sharepoint/site-access/allow-list
Authorization: Bearer <CHATGPT_ADMIN_TOKEN>
Content-Type: application/json

{
  "collection_guids": [
    "da60e844-ba1d-49bc-b4d4-d5e36bae9019"
  ]
}
```

既有允許的 collection 會保留。腳本會拒絕空的輸入清單，避免不小心送出空的 `PUT` 把網站限制清掉。

## 移除 site collection

解析網站 URL，並把它的 collection 從 allowlist 移除：

```bash
python3 sharepoint_site_access_admin.py remove \
  --workspace-id <workspace-id> \
  --site-url https://contoso.sharepoint.com/sites/Finance
```

腳本對每個不重複的 collection GUID 各送一個 request：

```text
DELETE /v1/manage/workspaces/<workspace-id>/sharepoint/site-access/allow-list/<collection-guid>
```

要移除多個 site collection，用 `--sites-file sites.csv`。加上
`--dry-run` 可以在刪除前先檢視識別碼和目前的 policy。

## 清空 allowlist

在移除所有網站限制之前，先預覽現有的 policy：

```bash
python3 sharepoint_site_access_admin.py clear \
  --workspace-id <workspace-id> \
  --dry-run
```

清空 allowlist 會恢復成每位使用者的 Microsoft 帳號有權限的所有 SharePoint 網站都能用。腳本會要求明確確認：

```bash
python3 sharepoint_site_access_admin.py clear \
  --workspace-id <workspace-id> \
  --yes
```

這個指令會送出：

```text
DELETE /v1/manage/workspaces/<workspace-id>/sharepoint/site-access/allow-list
```

## 安全地重試 policy 更新

如果你的 workspace 啟用了 idempotent 的 policy 寫入，新增、移除或清空 site collection 時可以提供一個 UUID：

```bash
python3 sharepoint_site_access_admin.py add \
  --workspace-id <workspace-id> \
  --sites-file sites.csv \
  --idempotency-key 3b5e9666-f01e-4f8b-9336-e70b67c07cf5
```

腳本會把這個值放在選用的 `Idempotency-Key` header 送出。只有在重試同一個邏輯上的寫入時，才重複使用同一個 key。移除多個 site collection 時，腳本會替每個 collection 衍生出不同但穩定的 key，這樣各自的刪除 request 不會互相衝突。

除非你的 workspace 已啟用 idempotency 支援，否則不要提供 `--idempotency-key`。不加這個選項，就是標準的 request 行為。

## 疑難排解

- **HTTP 401 或 403：** 檢查 workspace Admin API key、選擇的
  workspace、`chatgpt.enterprise.apps.write` 權限，以及這個功能是否已對 workspace 啟用。
- **Microsoft Graph HTTP 404：** 檢查 SharePoint URL 和 Microsoft
  Graph token 的網站權限。
- **HTTP 409：** 檢查是否有衝突的 policy 變更，或確認 idempotency key 沒有被用在不同的 request 上。
- **HTTP 429 或 503：** 腳本遇到限流和暫時性的服務失敗，最多會重試兩次。
- **多個 URL 解析成同一個 GUID：** 這些 URL 屬於同一個
  SharePoint site collection，腳本只會對那個 collection 新增或移除一次。

## 執行離線測試

範例附有測試，Microsoft Graph 和 ChatGPT Admin
API 都用 mock，不需要憑證，也不用連網：

```bash
python3 -m unittest discover \
  -s examples/chatgpt/sharepoint_site_access \
  -p 'test_*.py'
```

## 重點整理

- allowlist 的單位是 site collection GUID，不是個別網站、資料夾或檔案。
- 空的 allowlist 代表不限制，清空是解除限制，不是全部封鎖。
- 三種憑證各管各的：ChatGPT Admin API key、OpenAI API Platform key、Microsoft Graph token，不能互相取代。
- 先 dry-run 預覽再寫入，新增是累加式，腳本也擋掉空輸入，避免誤清。
- 重試寫入用 `Idempotency-Key`，同一個邏輯寫入才能共用同一個 key。

## 練習

1. 準備一個 `sites.csv`，放三個其中兩個屬於同一個 collection 的 URL，執行檢查指令，確認去重後只有兩個 GUID。
2. 對這份 CSV 先加 `--dry-run` 預覽新增，再實際新增，最後讀取 allowlist 確認原有項目都還在。
3. 用 `--idempotency-key` 帶同一個 UUID 重送同一個新增指令兩次，觀察結果，再試著對移除多個 collection 的指令也加上 key。
