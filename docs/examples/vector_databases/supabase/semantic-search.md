---
translated: true
source: examples/vector_databases/supabase/semantic-search.mdx
---
# 用 Supabase Vector 做語意搜尋

> 原文：[examples/vector_databases/supabase/semantic-search.mdx](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/supabase/semantic-search.mdx)



## 這篇在做什麼

示範怎麼把 OpenAI 的 embedding 存進 [Supabase Vector](https://supabase.com/docs/guides/ai)（Postgres + pgvector），拿來做語意搜尋。Embedding 跟你的應用資料放在同一個資料庫，不用另外養一套向量資料庫。

## 學完你會

- 在 Supabase 啟用 pgvector，建立有 `vector` 欄位、HNSW index 和 row level security 的資料表
- 用 JavaScript 產生 OpenAI embedding，並透過 Supabase client 存進資料庫
- 寫一個 Postgres match 函式，用 `supabase.rpc()` 做語意搜尋

## 開跑前

- Supabase 專案（雲端或本機 Docker 皆可）
- OpenAI API key，設成環境變數 `OPENAI_API_KEY`
- Supabase URL 和 service role key

---

[Supabase](https://supabase.com/docs) 是建在 [Postgres](https://en.wikipedia.org/wiki/PostgreSQL) 上的開源 Firebase 替代品，Postgres 是正式環境等級的 SQL 資料庫。Supabase Vector 建在 [pgvector](https://github.com/pgvector/pgvector) 上，所以可以把 embedding 跟其他應用資料存在同一個資料庫。搭配 pgvector 的索引演算法，資料量大時向量搜尋也[依然很快](https://supabase.com/blog/increase-performance-pgvector-hnsw)。

Supabase 還有一堆服務和工具讓開發更快（例如[自動產生的 REST API](https://postgrest.org/)）。我們會用這些服務在 Postgres 裡存和查 embedding。

這份指南會走過：

1. [設定資料庫](#setup-database)
2. [建立能存向量資料的 SQL 表](#create-a-vector-table)
3. 用 OpenAI 的 JavaScript client [產生 OpenAI embedding](#generate-openai-embeddings)
4. 用 Supabase JavaScript client [把 embedding 存進 SQL 表](#store-embeddings-in-database)
5. 用 Postgres 函式和 Supabase JavaScript client 對 embedding [做語意搜尋](#semantic-search)

## 設定資料庫

先到 https://database.new 建立 Supabase 資料庫，這會在 Supabase 雲端平台上建一個 Postgres 資料庫。如果想在本機用 Docker 跑，也可以照[本機開發](https://supabase.com/docs/guides/cli/getting-started)的方式。

在 studio 裡進到 [SQL editor](https://supabase.com/dashboard/project/_/sql/new)，執行下面的 SQL 來啟用 pgvector：

```sql
-- Enable the pgvector extension
create extension if not exists vector;
```

> 正式的應用最好用[資料庫 migration](https://supabase.com/docs/guides/cli/local-development#database-migrations)，讓所有 SQL 操作都受版本控制。為了簡單，這份指南直接在 SQL Editor 執行。做正式應用的話，可以把這些改成 migration。

## 建立向量表

接著建一個存文件和 embedding 的表。在 SQL Editor 執行：

```sql
create table documents (
  id bigint primary key generated always as identity,
  content text not null,
  embedding vector (1536) not null
);
```

因為 Supabase 建在 Postgres 上，這裡用的就是一般的 SQL。表的結構可以隨意改成適合你的應用。如果已經有資料表，直接在對應的表加一個 `vector` 欄位就好。

要理解的重點是 `vector` 資料型別，它是前面啟用 pgvector extension 之後才有的新型別。這裡的 1536 是 embedding 的維度數。這個例子用 OpenAI 的 `text-embedding-3-small`，所以向量大小設 1536。

接著在這個表建 vector index，資料變多之後查詢才不會變慢：

```sql
create index on documents using hnsw (embedding vector_ip_ops);
```

這個 index 用 [HNSW](https://supabase.com/docs/guides/ai/vector-indexes/hnsw-indexes) 演算法，對 `embedding` 欄位裡的向量建索引，而且是針對內積運算子（`<#>`）。這個運算子後面實作 match 函式時會再解釋。

再照資安最佳實踐，對這個表啟用 row level security：

```sql
alter table documents enable row level security;
```

這樣可以防止未授權的人透過自動產生的 REST API 存取這個表（後面會講到）。

## 產生 OpenAI embedding

這份指南用 JavaScript 產生 embedding，但你可以輕鬆改成任何 [OpenAI 支援的語言](https://platform.openai.com/docs/libraries)。

用 JavaScript 的話，伺服器端的 runtime 隨你選（Node.js、Deno、Supabase Edge Functions）。

如果用 Node.js，先安裝 `openai`：

```shell
npm install openai
```

然後匯入：

```js
import OpenAI from "openai";
```

如果用 Deno 或 Supabase Edge Functions，可以直接從 URL 匯入 `openai`：

```js
import OpenAI from "https://esm.sh/openai@4";
```

> 這個例子從 https://esm.sh 匯入，它是一個 CDN，會自動幫你抓對應的 NPM 模組，再用 HTTP 提供。

接著用 [`text-embedding-3-small`](https://platform.openai.com/docs/guides/embeddings/embedding-models) 產生一個 OpenAI embedding：

```js
const openai = new OpenAI();

const input = "The cat chases the mouse";

const result = await openai.embeddings.create({
  input,
  model: "text-embedding-3-small",
});

const [{ embedding }] = result.data;
```

呼叫 OpenAI API 需要 [OpenAI API key](https://platform.openai.com/api-keys)。可以用環境變數 `OPENAI_API_KEY` 傳入，或在建立 OpenAI client 時手動設定：

```js
const openai = new OpenAI({
  apiKey: "<openai-api-key>",
});
```

_**記得：** 絕對不要把 API key 寫死在程式裡。最好存在 `.env` 檔，用 [`dotenv`](https://github.com/motdotla/dotenv) 之類的套件載入，或從外部的金鑰管理系統讀取。_

## 把 embedding 存進資料庫

Supabase 有[自動產生的 REST API](https://postgrest.org/)，會為每個表動態建立 REST endpoint。也就是說不用直接連 Postgres，用 REST API 操作就行。在 serverless 這種短命 process 的環境特別有用，因為每次都重新建立資料庫連線很貴。

Supabase 有不少 [client library](https://supabase.com/docs#client-libraries) 簡化 REST API 的操作。這份指南用 [JavaScript client library](https://supabase.com/docs/reference/javascript)，你也可以改成自己慣用的語言。

如果用 Node.js，安裝 `@supabase/supabase-js`：

```shell
npm install @supabase/supabase-js
```

然後匯入：

```js
import { createClient } from "@supabase/supabase-js";
```

如果用 Deno 或 Supabase Edge Functions，可以直接從 URL 匯入 `@supabase/supabase-js`：

```js
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
```

接著建立 Supabase client，指向你的 Supabase 專案。這份指南把 Supabase URL 和 key 存在 `.env` 檔，你可以依自己應用處理設定的方式調整。

用 Node.js 或 Deno 的話，把 Supabase URL 和 service role key 加進 `.env`。如果用雲端平台，可以在 Supabase dashboard 的[設定頁](https://supabase.com/dashboard/project/_/settings/api)找到。如果是本機跑 Supabase，在終端機執行 `npx supabase status` 就能看到。

_.env_

```
SUPABASE_URL=<supabase-url>
SUPABASE_SERVICE_ROLE_KEY=<supabase-service-role-key>
```

如果用 Supabase Edge Functions，這些環境變數會自動注入你的 function，上面這步可以跳過。

接著把這些環境變數讀進程式。

在 Node.js 裡，先安裝 `dotenv`：

```shell
npm install dotenv
```

然後從 `process.env` 取得環境變數：

```js
import { config } from "dotenv";

// Load .env file
config();

const supabaseUrl = process.env["SUPABASE_URL"];
const supabaseServiceRoleKey = process.env["SUPABASE_SERVICE_ROLE_KEY"];
```

在 Deno 裡，用標準函式庫的 `dotenv` 載入 `.env`：

```js
import { load } from "https://deno.land/std@0.208.0/dotenv/mod.ts";

// Load .env file
const env = await load();

const supabaseUrl = env["SUPABASE_URL"];
const supabaseServiceRoleKey = env["SUPABASE_SERVICE_ROLE_KEY"];
```

在 Supabase Edge Functions 裡，直接讀取注入的環境變數：

```js
const supabaseUrl = Deno.env.get("SUPABASE_URL");
const supabaseServiceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
```

接著建立 `supabase` client：

```js
const supabase = createClient(supabaseUrl, supabaseServiceRoleKey, {
  auth: { persistSession: false },
});
```

然後用 `supabase` client 把文字和前面產生的 embedding 插進資料庫：

```js
const { error } = await supabase.from("documents").insert({
  content: input,
  embedding,
});
```

> 正式環境最好檢查回應裡的 `error`，看插入有沒有出問題並妥善處理。

## 語意搜尋

最後對資料庫裡的 embedding 做語意搜尋。這裡假設你的 `documents` 表已經有很多筆資料可以搜。

先在 Postgres 建一個執行語意搜尋查詢的 match 函式。到 [SQL Editor](https://supabase.com/dashboard/project/_/sql/new) 執行：

```sql
create function match_documents (
  query_embedding vector (1536),
  match_threshold float,
)
returns setof documents
language plpgsql
as $$
begin
  return query
  select *
  from documents
  where documents.embedding <#> query_embedding < -match_threshold
  order by documents.embedding <#> query_embedding;
end;
$$;
```

這個函式接收 `query_embedding`，也就是搜尋文字產生的 embedding（後面會講）。還接收 `match_threshold`，指定文件 embedding 要多相似才算跟 `query_embedding` 匹配。

函式裡的查詢做兩件事：

- 過濾文件，只留下 embedding 在上述 `match_threshold` 內的。因為 `<#>` 運算子算的是負內積（相對於正內積），所以比較前要把相似度門檻取負。也就是說 `match_threshold` 為 1 最相似，-1 最不相似。
- 依負內積（`<#>`）由小到大排序，讓最接近的文件排最前面。

> OpenAI 的 embedding 是正規化過的，所以我們選內積（`<#>`），它比餘弦距離（`<=>`）之類的運算子稍微快一點。要注意這只有在 embedding 已正規化時才成立，沒正規化就該用餘弦距離。

現在可以用 `supabase.rpc()` 從應用程式呼叫這個函式：

```js
const query = "What does the cat chase?";

// First create an embedding on the query itself
const result = await openai.embeddings.create({
  input: query,
  model: "text-embedding-3-small",
});

const [{ embedding }] = result.data;

// Then use this embedding to search for matches
const { data: documents, error: matchError } = await supabase
  .rpc("match_documents", {
    query_embedding: embedding,
    match_threshold: 0.8,
  })
  .select("content")
  .limit(5);
```

這個例子把 match threshold 設成 0.8，可以依你的資料調整到最好的值。

注意 `match_documents` 回傳的是一組 `documents`，所以這個 `rpc()` 可以當一般的表查詢用，也就是能接著串其他指令，像 `select()` 和 `limit()`。這裡只選我們要的 `documents` 欄位（`content`），並限制回傳的文件數量（這個例子最多 5 筆）。

到這裡你就拿到一份依語意關聯匹配的文件列表，最相似的排最前面。

## 下一步

可以拿這個例子當基礎，做其他語意搜尋技術，像 retrieval augmented generation（RAG）。

想多了解 OpenAI embedding，看 [Embedding](https://platform.openai.com/docs/guides/embeddings) 文件。

想多了解 Supabase Vector，看 [AI & Vector](https://supabase.com/docs/guides/ai) 文件。

## 重點整理

- pgvector 讓 embedding 跟應用資料放在同一個 Postgres，不用另外維護向量資料庫。
- `vector(1536)` 的維度要跟 embedding 模型一致，`text-embedding-3-small` 是 1536。
- OpenAI embedding 已正規化，所以內積（`<#>`）比餘弦距離快，結果一樣。
- Supabase 的 REST API 加上 `rpc()`，讓你不用直接連資料庫就能呼叫 Postgres 函式。
- API key 和 service role key 都不要寫死，放環境變數。

## 練習

1. 把 match 函式呼叫的 `match_threshold` 從 0.8 改成 0.5 和 0.95，觀察回傳筆數怎麼變。
2. 把 `limit(5)` 改成 `limit(2)`，並在 `select()` 多加一個欄位（例如 `id`）。
3. 把 match 函式的運算子改成餘弦距離 `<=>`，index 的 operator class 也要一起改，確認排序結果跟內積版本一致。
