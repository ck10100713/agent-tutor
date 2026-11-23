---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/redis/README.md
---

# Redis

> 原文：[examples/vector_databases/redis/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis/README.md)



## 這篇在做什麼

這頁是 Redis 當 vector database 的背景介紹，沒有程式碼。講 Redis 和 RediSearch 是什麼、有哪些功能、怎麼部署，並列出相關範例和資源。後面的 Redis 範例筆記本都是以這些概念為基礎。

## 學完你會

- 說得出 Redis、Redis Stack、RediSearch 各自是什麼、差在哪
- 知道本機開發和正式環境各有哪些部署方式
- 知道 RediSearch 支援哪些搜尋能力（全文、vector similarity、filter、aggregation），判斷適不適合你的需求

## 開跑前

本篇沒有要跑的東西。之後實作 Redis 的範例時，本機最快的方式是跑 Redis Stack 的 docker container。


### Redis 是什麼？

有做過 web 服務的開發者大多聽過 Redis。Redis 的核心是開源的 key-value store，可以當 cache、message broker 和資料庫。開發者選 Redis，是因為它快、client library 生態系大，而且已經被大企業用了很多年。

除了傳統用途，Redis 還有 [Redis Modules](https://redis.io/modules)，用來擴充新的功能、指令和資料型別。例如 [RedisJSON](https://redis.io/docs/stack/json/)、[RedisTimeSeries](https://redis.io/docs/stack/timeseries/)、[RedisBloom](https://redis.io/docs/stack/bloom/) 和 [RediSearch](https://redis.io/docs/stack/search/)。


### 部署選項

Redis 有很多種部署方式。本機開發最快的是用 [Redis Stack docker container](https://hub.docker.com/r/redis/redis-stack)，我們這裡也用它。Redis Stack 包含多個 Redis module，可以組成快速的多模型資料儲存和查詢引擎。

正式環境最簡單的起手式是用 [Redis Cloud](https://redislabs.com/redis-enterprise-cloud/overview/)，這是全託管的 Redis 服務。你也可以用 [Redis Enterprise](https://redislabs.com/redis-enterprise/overview/) 部署在自己的基礎設施上。Redis Enterprise 是全託管的 Redis 服務，可以部署在 kubernetes、on-premises 或雲端。

此外，每個主要雲端平台（[AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-e6y7ork67pjwg?sr=0-2&ref_=beagle&applicationId=AWSMPContessa)、[Google Marketplace](https://console.cloud.google.com/marketplace/details/redislabs-public/redis-enterprise?pli=1) 或 [Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps/garantiadata.redis_enterprise_1sp_public_preview?tab=Overview)）都有提供 Redis Enterprise 的 marketplace 方案。


### RediSearch 是什麼？

RediSearch 是一個 [Redis module](https://redis.io/modules)，幫 Redis 加上查詢、secondary index、全文搜尋和 vector search。使用時先對 Redis 資料宣告 index，再用 RediSearch client 查詢。完整功能請看 [RediSearch documentation](https://redis.io/docs/stack/search/)。


### 功能

RediSearch 用壓縮的 inverted index，索引快、記憶體用量低。RediSearch index 讓 Redis 多了精確片語比對、模糊搜尋、數值過濾等功能，還有：

* 對 Redis hash 的多個欄位做全文索引
* 增量索引，效能不會下降
* Vector similarity search
* 文件排序（用 [tf-idf](https://en.wikipedia.org/wiki/Tf%E2%80%93idf)，可選擇自訂權重）
* 欄位加權
* 用 AND、OR、NOT 組成的複雜 boolean 查詢
* 前綴比對、模糊比對和精確片語查詢
* 支援 [double-metaphone 發音比對](https://redis.io/docs/stack/search/reference/phonetic_matching/)
* 自動完成建議（含模糊前綴建議）
* 以 stemming 擴充查詢，支援[多種語言](https://redis.io/docs/stack/search/reference/stemming/)（使用 [Snowball](http://snowballstem.org/)）
* 支援中文斷詞與查詢（使用 [Friso](https://github.com/lionsoul2014/friso)）
* 數值過濾與範圍
* 用 [Redis geospatial indexing](https://github.com/openai/openai-cookbook/blob/main/commands/georadius) 做地理空間搜尋
* 強大的 aggregation 引擎
* 支援所有 utf-8 編碼的文字
* 可取回完整文件、指定欄位，或只取文件 ID
* 結果排序（例如依建立日期）
* 透過 RedisJSON 支援 JSON


### Clients

Redis 的生態系很大，你用的語言大概都有 client library。任何標準的 Redis client library 都能下 RediSearch 指令，但用有包好 RediSearch API 的 library 最方便。下面是幾個例子，更多 client library 看[這裡](https://redis.io/resources/clients/)。

| Project | Language | License | Author | Stars |
|----------|---------|--------|---------|-------|
| [jedis][jedis-url] | Java | MIT | [Redis][redis-url] | ![Stars][jedis-stars] |
| [redis-py][redis-py-url] | Python | MIT | [Redis][redis-url] | ![Stars][redis-py-stars] |
| [node-redis][node-redis-url] | Node.js | MIT | [Redis][redis-url] | ![Stars][node-redis-stars] |
| [nredisstack][nredisstack-url] | .NET | MIT | [Redis][redis-url] | ![Stars][nredisstack-stars] |

[redis-url]: https://redis.com

[redis-py-url]: https://github.com/redis/redis-py
[redis-py-stars]: https://img.shields.io/github/stars/redis/redis-py.svg?style=social&amp;label=Star&amp;maxAge=2592000
[redis-py-package]: https://pypi.python.org/pypi/redis

[jedis-url]: https://github.com/redis/jedis
[jedis-stars]: https://img.shields.io/github/stars/redis/jedis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[Jedis-package]: https://search.maven.org/artifact/redis.clients/jedis

[nredisstack-url]: https://github.com/redis/nredisstack
[nredisstack-stars]: https://img.shields.io/github/stars/redis/nredisstack.svg?style=social&amp;label=Star&amp;maxAge=2592000
[nredisstack-package]: https://www.nuget.org/packages/nredisstack/

[node-redis-url]: https://github.com/redis/node-redis
[node-redis-stars]: https://img.shields.io/github/stars/redis/node-redis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[node-redis-package]: https://www.npmjs.com/package/redis

[redis-om-python-url]: https://github.com/redis/redis-om-python
[redis-om-python-author]: https://redis.com
[redis-om-python-stars]: https://img.shields.io/github/stars/redis/redis-om-python.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-go-url]: https://github.com/RediSearch/redisearch-go
[redisearch-go-author]: https://redis.com
[redisearch-go-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-go.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-api-rs-url]: https://github.com/RediSearch/redisearch-api-rs
[redisearch-api-rs-author]: https://redis.com
[redisearch-api-rs-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-api-rs.svg?style=social&amp;label=Star&amp;maxAge=2592000


### 部署選項

部署帶 RediSearch 的 Redis 有很多方式。最簡單的是用 Docker，其他可能的選項還有：

- [Redis Cloud](https://redis.com/redis-enterprise-cloud/overview/)
- 雲端 marketplace：[AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-e6y7ork67pjwg?sr=0-2&ref_=beagle&applicationId=AWSMPContessa)、[Google Marketplace](https://console.cloud.google.com/marketplace/details/redislabs-public/redis-enterprise?pli=1) 或 [Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps/garantiadata.redis_enterprise_1sp_public_preview?tab=Overview)
- On-premise：[Redis Enterprise Software](https://redis.com/redis-enterprise-software/overview/)
- Kubernetes：[Redis Enterprise Software on Kubernetes](https://docs.redis.com/latest/kubernetes/)
- [Docker (RediSearch)](https://hub.docker.com/r/redislabs/redisearch)
- [Docker (Redis Stack)](https://hub.docker.com/r/redis/redis-stack)


### Cluster 支援

RediSearch 有分散式 cluster 版本，可以擴展到上百台伺服器、數十億份文件。目前分散式 RediSearch 包含在 [Redis Enterprise Cloud](https://redis.com/redis-enterprise-cloud/overview/) 和 [Redis Enterprise Software](https://redis.com/redis-enterprise-software/overview/) 裡。

更多資訊請看 [RediSearch on Redis Enterprise](https://redis.com/modules/redisearch/)。

### 範例

- [Product Search](https://github.com/RedisVentures/redis-product-search) - 電商商品搜尋（圖片與文字）
- [Product Recommendations with DocArray / Jina](https://github.com/jina-ai/product-recommendation-redis-docarray) - 用 Redis 和 DocArray 做的 content-based 商品推薦範例。
- [Redis VSS in RecSys](https://github.com/RedisVentures/Redis-Recsys) - 3 個端到端的 Redis 與 NVIDIA Merlin 推薦系統架構。
- [Azure OpenAI Embeddings Q&A](https://github.com/ruoccofabrizio/azure-open-ai-embeddings-qna) - 在 Azure 上用 OpenAI 和 Redis 做的問答服務。
- [ArXiv Paper Search](https://github.com/RedisVentures/redis-arXiv-search) - 對 arXiv 學術論文做 semantic search


### 更多資源

想知道怎麼把 Redis 當 vector database 用，可以看這些資源：

- [Redis Vector Similarity Docs](https://redis.io/docs/stack/search/reference/vectors/) - Redis 官方的 Vector Search 文件。
- [Redis-py Search Docs](https://redis.readthedocs.io/en/latest/redismodules.html#redisearch-commands) - Redis-py client library 的 RediSearch 文件。
- [Vector Similarity Search: From Basics to Production](https://mlops.community/vector-similarity-search-from-basics-to-production/) - VSS 與 Redis 當 VectorDB 的入門部落格文章。
- [AI-Powered Document Search](https://datasciencedojo.com/blog/ai-powered-document-search/) - 介紹 AI 文件搜尋的使用情境與架構。
- [Vector Database Benchmarks](https://jina.ai/news/benchmark-vector-search-databases-with-one-million-data/) - Jina AI 比較 Redis 與其他 VectorDB 的 benchmark。

## 重點整理

- Redis 本來是快速的 key-value store，靠 module 擴充出 JSON、時序、搜尋等能力。
- RediSearch 讓 Redis 有 secondary index、全文搜尋和 vector similarity search，所以可以當 vector database。
- 先對資料宣告 index，再用 RediSearch client 查詢，這是用法的基本流程。
- 本機開發用 Redis Stack docker container 最快，正式環境用 Redis Cloud 或 Redis Enterprise。
- 分散式 RediSearch 只在 Redis Enterprise 系列提供。

## 練習

1. 用 `docker run` 啟動 `redis/redis-stack` container，並用 `redis-cli` 執行 `PING` 確認連得上。
2. 用 redis-py 連到這個 Redis，對一個 hash 建立只含文字欄位的 RediSearch index，並用全文查詢撈出一筆資料。
3. 在上面的 index 加一個 vector 欄位，存幾筆自己用 embedding 模型產生的向量，下 vector similarity 查詢，比較結果跟全文查詢有什麼不同。
