---
translated: true
source: observability/usage_cost_api.ipynb
---

# Usage & Cost Admin API cookbook

> 原文：[observability/usage_cost_api.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/observability/usage_cost_api.ipynb)

透過 Admin API，用程式存取並分析你的 Claude API 用量與費用資料。

## 這篇在做什麼

這篇是用程式取得 Claude API 用量與費用資料的實用指南。你會用兩個 endpoint 查 token 用量和 USD 費用，做分組、過濾、分頁，最後匯出成 CSV。

## 學完你會

- 查詢 Messages Usage API 的 token 用量，並看懂 time bucket 與各項指標。
- 用 Cost API 取得費用，並依 workspace、model 等維度分組、過濾。
- 處理大量資料的分頁，並把結果匯出成 CSV 給外部工具分析。

## 開跑前

需要 Admin API key（格式 `sk-ant-admin...`），到 Claude Console 取得。

**用程式存取 Claude API 用量與費用資料的實用指南**

### 你可以做什麼

**用量追蹤：**
- 監控 token 消耗（uncached input、output、cache creation/reads）
- 追蹤各 model、workspace、API key 的用量
- 分析 cache 效率與 server tool 的使用

**費用分析：**
- 取得依服務類型拆分的詳細費用
- 監控各 workspace 的花費趨勢
- 為財務與分攤情境產生報表

**常見使用情境：**
- **用量監控**：追蹤消耗模式並優化費用
- **費用歸屬**：依 workspace 把支出分攤給各團隊或專案
- **Cache 分析**：衡量並改善 cache 效率
- **財務報告**：產生主管摘要與預算報告

### API 概覽

兩個主要 endpoint：
1. **Messages Usage API**：token 層級的用量資料，分組很有彈性
2. **Cost API**：以 USD 計價的財務資料，附服務拆分

### 前置需求與安全

- **Admin API Key**：從 [Claude Console](https://console.anthropic.com/settings/admin-keys) 取得（格式：`sk-ant-admin...`）
- **安全**：把 key 存在環境變數、定期輪換、絕對不要 commit 進版本控制

```python
import os
from datetime import datetime, time, timedelta
from typing import Any

import requests


class AnthropicAdminAPI:
    """Secure wrapper for Anthropic Admin API endpoints."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_ADMIN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Admin API key required. Set ANTHROPIC_ADMIN_API_KEY environment variable."
            )

        if not self.api_key.startswith("sk-ant-admin"):
            raise ValueError("Invalid Admin API key format.")

        self.base_url = "https://api.anthropic.com/v1/organizations"
        self.headers = {
            "anthropic-version": "2023-06-01",
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _make_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Make authenticated request with basic error handling."""
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise ValueError("Invalid API key or insufficient permissions") from e
            elif response.status_code == 429:
                raise requests.exceptions.RequestException(
                    "Rate limit exceeded - try again later"
                ) from e
            else:
                raise requests.exceptions.RequestException(f"API error: {e}") from e


# Test connection
def test_connection():
    try:
        client = AnthropicAdminAPI()

        # Simple test query - snap to start of day to align with bucket boundaries
        params = {
            "starting_at": (
                datetime.combine(datetime.utcnow(), time.min) - timedelta(days=1)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ending_at": datetime.combine(datetime.utcnow(), time.min).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "bucket_width": "1d",
            "limit": 1,
        }

        client._make_request("usage_report/messages", params)
        print("✅ Connection successful!")
        return client

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None


client = test_connection()
```

## 基本用量與費用追蹤

### 了解用量資料

Messages Usage API 以 **time bucket**（時間桶）提供 token 消耗，也就是包含彙總用量的固定區間。

**主要指標：**
- **uncached_input_tokens**：新的 input token（prompt、system message）
- **output_tokens**：Claude 的回應
- **cache_creation**：為了重複使用而 cache 的 token
- **cache_read_input_tokens**：重複使用之前 cache 的 token

### 基本用量查詢

```python
def get_daily_usage(client, days_back=7):
    """Get usage data for the last N days."""
    end_time = datetime.combine(datetime.utcnow(), time.min)
    start_time = end_time - timedelta(days=days_back)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",
        "limit": days_back,
    }

    return client._make_request("usage_report/messages", params)


def analyze_usage_data(response):
    """Process and display usage data."""
    if not response or not response.get("data"):
        print("No usage data found.")
        return

    total_uncached_input = total_output = total_cache_creation = 0
    total_cache_reads = total_web_searches = 0
    daily_data = []

    for bucket in response["data"]:
        date = bucket["starting_at"][:10]

        # Sum all results in bucket
        bucket_uncached = bucket_output = bucket_cache_creation = 0
        bucket_cache_reads = bucket_web_searches = 0

        for result in bucket["results"]:
            bucket_uncached += result.get("uncached_input_tokens", 0)
            bucket_output += result.get("output_tokens", 0)

            cache_creation = result.get("cache_creation", {})
            bucket_cache_creation += cache_creation.get(
                "ephemeral_1h_input_tokens", 0
            ) + cache_creation.get("ephemeral_5m_input_tokens", 0)
            bucket_cache_reads += result.get("cache_read_input_tokens", 0)

            server_tools = result.get("server_tool_use", {})
            bucket_web_searches += server_tools.get("web_search_requests", 0)

        daily_data.append(
            {
                "date": date,
                "uncached_input_tokens": bucket_uncached,
                "output_tokens": bucket_output,
                "cache_creation": bucket_cache_creation,
                "cache_reads": bucket_cache_reads,
                "web_searches": bucket_web_searches,
                "total_tokens": bucket_uncached + bucket_output,
            }
        )

        # Add to totals
        total_uncached_input += bucket_uncached
        total_output += bucket_output
        total_cache_creation += bucket_cache_creation
        total_cache_reads += bucket_cache_reads
        total_web_searches += bucket_web_searches

    # Calculate cache efficiency
    total_input_tokens = total_uncached_input + total_cache_creation + total_cache_reads
    cache_efficiency = (
        (total_cache_reads / total_input_tokens * 100) if total_input_tokens > 0 else 0
    )

    # Display summary
    print("📊 Usage Summary:")
    print(f"Uncached input tokens: {total_uncached_input:,}")
    print(f"Output tokens: {total_output:,}")
    print(f"Cache creation: {total_cache_creation:,}")
    print(f"Cache reads: {total_cache_reads:,}")
    print(f"Cache efficiency: {cache_efficiency:.1f}%")
    print(f"Web searches: {total_web_searches:,}")

    return daily_data


# Example usage
if client:
    usage_response = get_daily_usage(client, days_back=7)
    daily_usage = analyze_usage_data(usage_response)
```

??? note "輸出"

    ```text
    📊 Usage Summary:
    Uncached input tokens: 267,751
    Output tokens: 2,848,746
    Cache creation: 0
    Cache reads: 0
    Cache efficiency: 0.0%
    Web searches: 0
    ```

## 基本費用追蹤

注意：Priority Tier 的費用採用不同的計費模型，永遠不會出現在 cost endpoint。你可以在 usage endpoint 追蹤 Priority Tier 的用量，但看不到費用。

```python
def get_daily_costs(client, days_back=7):
    """Get cost data for the last N days."""
    end_time = datetime.combine(datetime.utcnow(), time.min)
    start_time = end_time - timedelta(days=days_back)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",  # Only 1d supported for cost API
        "limit": min(days_back, 31),  # Max 31 days per request
    }

    return client._make_request("cost_report", params)


def analyze_cost_data(response):
    """Process and display cost data."""
    if not response or not response.get("data"):
        print("No cost data found.")
        return

    total_cost_minor_units = 0
    daily_costs = []

    for bucket in response["data"]:
        date = bucket["starting_at"][:10]

        # Sum all costs in this bucket
        bucket_cost = 0
        for result in bucket["results"]:
            # Convert string amounts to float if needed
            amount = result.get("amount", 0)
            if isinstance(amount, str):
                try:
                    amount = float(amount)
                except (ValueError, TypeError):
                    amount = 0
            bucket_cost += amount

        daily_costs.append(
            {
                "date": date,
                "cost_minor_units": bucket_cost,
                "cost_usd": bucket_cost / 100,  # Convert to dollars
            }
        )

        total_cost_minor_units += bucket_cost

    total_cost_usd = total_cost_minor_units / 100

    print("💰 Cost Summary:")
    print(f"Total cost: ${total_cost_usd:.4f}")
    print(f"Average daily cost: ${total_cost_usd / len(daily_costs):.4f}")

    return daily_costs


# Example usage
if client:
    cost_response = get_daily_costs(client, days_back=7)
    daily_costs = analyze_cost_data(cost_response)
```

??? note "輸出"

    ```text
    💰 Cost Summary:
    Total cost: $83.7574
    Average daily cost: $11.9653
    ```

## 分組、過濾與分頁

### 時間粒度選項

**Usage API** 支援三種粒度：
- `1m`（1 分鐘）：高解析度分析，每個 request 最多 1440 個 bucket
- `1h`（1 小時）：中解析度，每個 request 最多 168 個 bucket
- `1d`（1 天）：每日分析，每個 request 最多 31 個 bucket

**Cost API** 支援：
- `1d`（1 天）：唯一的選項，每個 request 最多 31 個 bucket

### 分組與過濾

```python
def get_usage_by_model(client, days_back=7):
    """Get usage data grouped by model, handling pagination automatically."""
    end_time = datetime.combine(datetime.utcnow(), time.min)
    start_time = end_time - timedelta(days=days_back)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "group_by[]": ["model"],
        "bucket_width": "1d",
    }

    # Aggregate across all pages of data
    model_usage = {}
    page_count = 0
    max_pages = 10  # Reasonable limit to avoid infinite loops

    try:
        next_page = None

        while page_count < max_pages:
            current_params = params.copy()
            if next_page:
                current_params["page"] = next_page

            response = client._make_request("usage_report/messages", current_params)
            page_count += 1

            # Process this page's data
            for bucket in response.get("data", []):
                for result in bucket.get("results", []):
                    model = result.get("model", "Unknown")
                    uncached = result.get("uncached_input_tokens", 0)
                    output = result.get("output_tokens", 0)
                    cache_creation = result.get("cache_creation", {})
                    cache_creation_tokens = cache_creation.get(
                        "ephemeral_1h_input_tokens", 0
                    ) + cache_creation.get("ephemeral_5m_input_tokens", 0)
                    cache_reads = result.get("cache_read_input_tokens", 0)
                    tokens = uncached + output + cache_creation_tokens + cache_reads

                    if model not in model_usage:
                        model_usage[model] = 0
                    model_usage[model] += tokens

            # Check if there's more data
            if not response.get("has_more", False):
                break

            next_page = response.get("next_page")
            if not next_page:
                break

    except Exception as e:
        print(f"❌ Error retrieving usage data: {e}")
        return {}

    # Display results
    print("📊 Usage by Model:")
    if not model_usage:
        print(f"  No usage data found in the last {days_back} days")
        print("  💡 Try increasing the time range or check if you have recent API usage")
    else:
        for model, tokens in sorted(model_usage.items(), key=lambda x: x[1], reverse=True):
            print(f"  {model}: {tokens:,} tokens")

    return model_usage


def filter_usage_example(client):
    """Example of filtering usage data."""
    params = {
        "starting_at": (datetime.combine(datetime.utcnow(), time.min) - timedelta(days=7)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "ending_at": datetime.combine(datetime.utcnow(), time.min).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "models[]": ["claude-sonnet-5-5"],  # Filter to specific model
        "service_tiers[]": ["standard"],  # Filter to standard tier
        "bucket_width": "1d",
    }

    response = client._make_request("usage_report/messages", params)
    print(f"Found {len(response.get('data', []))} days of filtered usage data")
    return response


# Example usage
if client:
    model_usage = get_usage_by_model(client, days_back=14)
    filtered_usage = filter_usage_example(client)
```

??? note "輸出"

    ```text
    📊 Usage by Model:
      claude-3-5-haiku-20241022: 995,781 tokens
      claude-sonnet-4-6: 861,880 tokens
      claude-opus-4-1: 394,646 tokens
      claude-sonnet-4-6: 356,766 tokens
      claude-opus-4-20250514: 308,223 tokens
      claude-opus-4-1: 199,201 tokens
    Found 7 days of filtered usage data
    ```

### 大型資料集的分頁

```python
def fetch_all_usage_data(client, params, max_pages=10):
    """Fetch all paginated usage data."""
    all_data = []
    page_count = 0
    next_page = None

    print("📥 Fetching paginated data...")

    while page_count < max_pages:
        current_params = params.copy()
        if next_page:
            current_params["page"] = next_page

        try:
            response = client._make_request("usage_report/messages", current_params)

            if not response or not response.get("data"):
                break

            page_data = response["data"]
            all_data.extend(page_data)
            page_count += 1

            print(f"  Page {page_count}: {len(page_data)} time buckets")

            if not response.get("has_more", False):
                print(f"✅ Complete: Retrieved all data in {page_count} pages")
                break

            next_page = response.get("next_page")
            if not next_page:
                break

        except Exception as e:
            print(f"❌ Error on page {page_count + 1}: {e}")
            break

    print(f"📊 Total retrieved: {len(all_data)} time buckets")
    return all_data


def large_dataset_example(client, days_back=3):
    """Example of handling a large dataset with pagination."""
    # Use recent time range to ensure we have data
    start_time = datetime.combine(datetime.utcnow(), time.min) - timedelta(days=days_back)
    end_time = datetime.combine(datetime.utcnow(), time.min)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1h",  # Hourly data for more buckets
        "group_by[]": ["model"],
        "limit": 24,  # One day per page
    }

    all_buckets = fetch_all_usage_data(client, params, max_pages=5)

    # Process the large dataset
    if all_buckets:
        total_tokens = sum(
            sum(
                result.get("uncached_input_tokens", 0) + result.get("output_tokens", 0)
                for result in bucket["results"]
            )
            for bucket in all_buckets
        )
        print(f"📈 Total tokens across all data: {total_tokens:,}")

    return all_buckets


# Example usage - use shorter time range to find recent data
if client:
    large_dataset = large_dataset_example(client, days_back=3)
```

??? note "輸出"

    ```text
    📥 Fetching paginated data...
      Page 1: 24 time buckets
      Page 2: 24 time buckets
      Page 3: 24 time buckets
    ✅ Complete: Retrieved all data in 3 pages
    📊 Total retrieved: 72 time buckets
    📈 Total tokens across all data: 1,336,287
    ```

## 簡單的資料匯出

### 匯出 CSV 供外部分析

```python
import csv


def export_usage_to_csv(client, output_file="usage_data.csv", days_back=30):
    """Export usage data to CSV for external analysis."""

    end_time = datetime.combine(datetime.utcnow(), time.min)
    start_time = end_time - timedelta(days=days_back)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "group_by[]": ["model", "service_tier", "workspace_id"],
        "bucket_width": "1d",
    }

    try:
        # Collect all data across pages
        rows = []
        page_count = 0
        max_pages = 20  # Allow more pages for export
        next_page = None

        while page_count < max_pages:
            current_params = params.copy()
            if next_page:
                current_params["page"] = next_page

            response = client._make_request("usage_report/messages", current_params)
            page_count += 1

            # Process this page's data
            for bucket in response.get("data", []):
                date = bucket["starting_at"][:10]
                for result in bucket["results"]:
                    rows.append(
                        {
                            "date": date,
                            "model": result.get("model", ""),
                            "service_tier": result.get("service_tier", ""),
                            "workspace_id": result.get("workspace_id", ""),
                            "uncached_input_tokens": result.get("uncached_input_tokens", 0),
                            "output_tokens": result.get("output_tokens", 0),
                            "cache_creation_tokens": (
                                result.get("cache_creation", {}).get("ephemeral_1h_input_tokens", 0)
                                + result.get("cache_creation", {}).get(
                                    "ephemeral_5m_input_tokens", 0
                                )
                            ),
                            "cache_read_tokens": result.get("cache_read_input_tokens", 0),
                            "web_search_requests": result.get("server_tool_use", {}).get(
                                "web_search_requests", 0
                            ),
                        }
                    )

            # Check if there's more data
            if not response.get("has_more", False):
                break

            next_page = response.get("next_page")
            if not next_page:
                break

        # Write CSV
        if rows:
            with open(output_file, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            print(f"✅ Exported {len(rows)} rows to {output_file}")
        else:
            print(f"No usage data to export for the last {days_back} days")
            print("💡 Try increasing days_back or check if you have recent API usage")

    except Exception as e:
        print(f"❌ Export failed: {e}")


def export_costs_to_csv(client, output_file="cost_data.csv", days_back=30):
    """Export cost data to CSV."""

    end_time = datetime.combine(datetime.utcnow(), time.min)
    start_time = end_time - timedelta(days=days_back)

    params = {
        "starting_at": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "group_by[]": ["workspace_id", "description"],
    }

    try:
        # Collect all data across pages
        rows = []
        page_count = 0
        max_pages = 20
        next_page = None

        while page_count < max_pages:
            current_params = params.copy()
            if next_page:
                current_params["page"] = next_page

            response = client._make_request("cost_report", current_params)
            page_count += 1

            # Process this page's data
            for bucket in response.get("data", []):
                date = bucket["starting_at"][:10]
                for result in bucket["results"]:
                    # Handle both string and numeric amounts
                    amount = result.get("amount", 0)
                    if isinstance(amount, str):
                        try:
                            amount = float(amount)
                        except (ValueError, TypeError):
                            amount = 0

                    rows.append(
                        {
                            "date": date,
                            "workspace_id": result.get(
                                "workspace_id", ""
                            ),  # null for default workspace
                            "description": result.get("description", ""),
                            "currency": result.get("currency", "USD"),
                            "amount_usd": amount / 100,
                        }
                    )

            # Check if there's more data
            if not response.get("has_more", False):
                break

            next_page = response.get("next_page")
            if not next_page:
                break

        if rows:
            with open(output_file, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            print(f"✅ Exported {len(rows)} cost records to {output_file}")
        else:
            print(f"No cost data to export for the last {days_back} days")
            print("💡 Try increasing days_back or check if you have recent API usage")

    except Exception as e:
        print(f"❌ Cost export failed: {e}")


# Example usage
if client:
    export_usage_to_csv(client, "my_usage_data.csv", days_back=14)
    export_costs_to_csv(client, "my_cost_data.csv", days_back=14)
```

??? note "輸出"

    ```text
    ✅ Exported 36 rows to my_usage_data.csv
    ✅ Exported 72 cost records to my_cost_data.csv
    ```

## 總結

這份 cookbook 涵蓋使用 Usage & Cost Admin API 的重要模式：

- 用量與費用資料的**基本查詢**
- 做詳細分析的**分組與過濾**
- 大型資料集的**分頁**
- 用於分類的**費用描述解析**
- 避免問題的**常見陷阱**
- 給外部工具用的**簡單 CSV 匯出**

### 下一步

- 查看[官方 API 文件](https://docs.claude.com)了解最新的欄位定義
- 先用小的日期範圍測試你的整合
- 考慮你的使用情境需要的資料保存期限
- 留意可能強化分析的新 API 功能

### 重要注意事項

- 欄位名稱和可用選項可能隨 API 成熟而演變
- 正式環境的程式碼要妥善處理未知的值
- 這個 API 是為歷史分析設計，不是即時監控
- Priority Tier 的費用採用不同的計費模型，不會出現在 cost endpoint

分析愉快！📊

## 重點整理

- 用量（Messages Usage API）和費用（Cost API）是兩個不同的 endpoint，用量看 token，費用看 USD。
- 資料是以 time bucket 彙總，不同粒度有不同的 bucket 上限，查大範圍要分頁。
- 分組與過濾（workspace、model、API key）是做費用歸屬和 cache 分析的基礎。
- Priority Tier 只出現在 usage，不會出現在 cost。
- 這是歷史分析用的 API，不適合即時監控。

## 練習

1. 把基本用量查詢的日期範圍縮小到一天，粒度改成 `1h`，看每個 bucket 的 token 數。
2. 在分組的範例裡，改成依 workspace 分組，統計各 workspace 的總費用。
3. 擴充 CSV 匯出，額外算出每個 model 的 cache 命中比例（cache_read 佔總 input 的比例）並寫進檔案。
