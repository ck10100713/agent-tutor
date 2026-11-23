---
translated: true
source: tool_use/threat_intel_enrichment_agent.ipynb
---
# Threat intelligence enrichment agent

> 原文：[tool_use/threat_intel_enrichment_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/threat_intel_enrichment_agent.ipynb)

做一個能自主調查 IOC 的 agent：查詢多個 threat intel 來源、交叉比對結果、對應到 MITRE ATT&CK，並產出給 SIEM 跟 SOAR 整合用的結構化報告。

## 這篇在做什麼

資安分析師要花很多時間在不同情資來源之間來回查，這篇用 Claude 的 tool use 把整個流程自動化。Agent 拿到 IP、檔案 hash 或 domain 後，自己決定查哪些來源，最後輸出結構化的 JSON 報告。範例的 tool 是模擬的，換成真的 API 時不用改 orchestration 邏輯。

## 學完你會

- 設計 tool schema，讓 Claude 有足夠資訊選對情資來源。
- 寫出 agentic loop，讓 Claude 根據查到的結果串接後續的 tool call。
- 把自由文字的分析轉成給下游系統用的結構化 JSON 報告。

## 開跑前

- Python 3.10+。
- Anthropic API key，放在 `.env` 檔：`ANTHROPIC_API_KEY=sk-ant-...`。在 Colab 的話，可以直接用環境變數或 Colab secrets 設定。

資安分析師常常要花好幾個小時手動在各個情資來源之間查：用 VirusTotal 查檔案 hash、用 AbuseIPDB 查 IP、對照 MITRE ATT&CK，再整理成報告。這份 cookbook 示範怎麼用 Claude 做出一個 agent，把整個流程自動化。

Agent 的輸入是原始的 Indicators of Compromise (IOC)，也就是 IP 位址、檔案 hash 或 domain。它用 Claude 的 tool use 能力決定要查哪些情資來源、跨來源比對發現，並產出結構化、可交給分析師的威脅報告。這個範例的 tool 是模擬的，但架構設計成你可以換成真的 API（VirusTotal、AbuseIPDB、Shodan 等），不用改 orchestration 邏輯。

不管你是在資安產品裡加入威脅情資功能（ISV），還是替企業 SOC 自動化 enrichment 流程，這個模式都直接適用。

## 你會學到

- 怎麼設計 tool schema，讓 Claude 有足夠的 context 選到對的情資來源
- 怎麼寫 agentic loop，讓 Claude 根據發現的內容串接 tool call
- 怎麼用 prompt 引導多來源關聯分析跟 MITRE ATT&CK 對應
- 怎麼把自由文字分析轉成給下游系統用的結構化 JSON 報告

## 先決條件

- Python 3.10+
- Anthropic API key，放在 `.env` 檔：`ANTHROPIC_API_KEY=sk-ant-...`
- 熟悉 [Claude 的 tool use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview) 會有幫助，但不是必要

## Step 1: 設定環境

安裝 Anthropic SDK 跟 `python-dotenv`。在這個 notebook 同一個目錄建立 `.env` 檔，放入你的 API key：

```
ANTHROPIC_API_KEY=sk-ant-...
```

```python
%pip install anthropic python-dotenv --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

```python
import json

import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

## Step 2: 定義 threat intelligence tool

我們定義四個 tool，代表常見的 threat intelligence 資料來源。每個 tool 都有清楚的 description，幫助 Claude 理解什麼時候、為什麼要用它，這對 agentic 行為是否有效非常關鍵。在 production，這些 tool 會包真正的 API 呼叫，schema 則維持不變。

```python
# Define tools for threat intelligence gathering
tools = [
    {
        "name": "lookup_ip_reputation",
        "description": "Query IP reputation database to get geolocation, ISP information, abuse history, open ports, and known malicious associations for an IP address. Returns threat types, malware associations, and abuse confidence scoring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "The IPv4 or IPv6 address to investigate.",
                }
            },
            "required": ["ip_address"],
        },
    },
    {
        "name": "lookup_file_hash",
        "description": "Query file reputation service with a cryptographic hash. Returns detection ratio across antivirus engines, malware family classification, behavioral summary, contacted infrastructure, and temporal indicators (first/last seen).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_hash": {
                    "type": "string",
                    "description": "The MD5, SHA1, or SHA256 hash of the suspicious file.",
                },
                "hash_type": {
                    "type": "string",
                    "enum": ["md5", "sha1", "sha256"],
                    "description": "The type of hash provided.",
                },
            },
            "required": ["file_hash", "hash_type"],
        },
    },
    {
        "name": "lookup_domain",
        "description": "Investigate a domain's reputation including registration details, DNS records, SSL certificate information, hosting provider, and threat categorization. Useful for analyzing phishing domains, malware distribution sites, and C2 infrastructure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "The domain name to investigate (e.g., example.com).",
                }
            },
            "required": ["domain"],
        },
    },
    {
        "name": "get_mitre_techniques",
        "description": "Map observed behaviors, malware families, or attack patterns to the MITRE ATT&CK framework. Returns matching technique IDs, tactic categories, associated threat groups, and detection recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Description of the behavior, malware family, or attack pattern to map (e.g., 'command and control beaconing', 'credential theft', 'lateral movement').",
                }
            },
            "required": ["query"],
        },
    },
]

print(f"Defined {len(tools)} threat intelligence tools:")
for tool in tools:
    print(f"  - {tool['name']}: {tool['description'][:80]}...")
```

??? note "輸出"

    ```text
    Defined 4 threat intelligence tools:
      - lookup_ip_reputation: Query IP reputation database to get geolocation, ISP information, abuse history,...
      - lookup_file_hash: Query file reputation service with a cryptographic hash. Returns detection ratio...
      - lookup_domain: Investigate a domain's reputation including registration details, DNS records, S...
      - get_mitre_techniques: Map observed behaviors, malware families, or attack patterns to the MITRE ATT&CK...
    ```

## Step 3: 建立模擬的 threat intel backend

這些 function 模擬真正的 threat intelligence API。每個都回傳擬真的資料結構，對應 VirusTotal、AbuseIPDB 或 MITRE ATT&CK 查詢服務會給你的內容。要上 production，只要把每個 function 的內容換成 API 呼叫，介面不變。

```python
# Simulated threat intelligence data sources
# In production, replace each function body with real API calls:
#   lookup_ip_reputation  -> AbuseIPDB, GreyNoise, Shodan
#   lookup_file_hash      -> VirusTotal, MalwareBazaar, Hybrid Analysis
#   lookup_domain         -> URLhaus, DomainTools, WHOIS
#   get_mitre_techniques  -> MITRE ATT&CK STIX/TAXII feed


def lookup_ip_reputation(ip_address: str) -> dict:
    """Query IP reputation. In production: AbuseIPDB, GreyNoise, or Shodan API."""
    ip_database = {
        "203.0.113.42": {
            "ip": "203.0.113.42",
            "country": "Russia",
            "city": "Saint Petersburg",
            "asn": "AS48666",
            "isp": "MnogoByte LLC",
            "abuse_confidence_score": 87,
            "total_reports": 1243,
            "last_reported": "2026-03-10T14:22:00Z",
            "threat_types": ["botnet_c2", "malware_distribution", "brute_force"],
            "known_malware_associations": ["Emotet", "Trickbot"],
            "open_ports": [443, 8080, 4444],
            "is_tor_exit_node": False,
            "is_known_proxy": True,
            "first_seen": "2025-08-15T00:00:00Z",
            "tags": ["banking-trojan-c2", "spam-source"],
        },
        "198.51.100.17": {
            "ip": "198.51.100.17",
            "country": "China",
            "city": "Shanghai",
            "asn": "AS4134",
            "isp": "ChinaNet",
            "abuse_confidence_score": 94,
            "total_reports": 3891,
            "last_reported": "2026-03-12T09:15:00Z",
            "threat_types": ["apt_c2", "data_exfiltration", "scanning"],
            "known_malware_associations": ["PlugX", "ShadowPad"],
            "open_ports": [443, 8443, 53],
            "is_tor_exit_node": False,
            "is_known_proxy": False,
            "first_seen": "2024-11-02T00:00:00Z",
            "tags": ["apt-infrastructure", "state-sponsored"],
        },
    }
    return ip_database.get(
        ip_address,
        {
            "ip": ip_address,
            "country": "Unknown",
            "abuse_confidence_score": 0,
            "total_reports": 0,
            "threat_types": [],
            "note": "No records found for this IP",
        },
    )


def lookup_file_hash(file_hash: str, hash_type: str) -> dict:
    """Query file reputation. In production: VirusTotal or MalwareBazaar API."""
    hash_database = {
        "d131dd02c5e6eec4693d9a0698aff95c": {
            "hash": "d131dd02c5e6eec4693d9a0698aff95c",
            "hash_type": "md5",
            "sha256": "a1b2c3d4e5f6789012345678abcdef0123456789abcdef0123456789abcdef01",
            "detections": 58,
            "total_engines": 72,
            "detection_rate": "80.6%",
            "malware_family": "Emotet",
            "malware_type": "banking_trojan",
            "severity": "critical",
            "file_type": "PE32 executable (DLL)",
            "file_size_bytes": 237568,
            "file_name": "update_service.dll",
            "first_seen": "2025-12-01T08:30:00Z",
            "last_seen": "2026-03-09T22:14:00Z",
            "ssdeep": "6144:Kl2a8JG1oPRqMDFlOGnA8g0ZFBFSqBKiDEF:Kl2a8Q1oPRDF3",
            "tags": ["emotet", "epoch5", "banking-trojan", "dropper"],
            "behavior_summary": "Drops secondary payload via regsvr32, establishes persistence via scheduled task, communicates with C2 over HTTPS on non-standard ports",
            "contacted_ips": ["203.0.113.42", "203.0.113.88", "192.0.2.101"],
            "contacted_domains": ["update-service-cdn.ru", "cdn-api-gateway.cc"],
        },
        "7b3a0c8f2e1d4a5b6c9d8e7f0a1b2c3d": {
            "hash": "7b3a0c8f2e1d4a5b6c9d8e7f0a1b2c3d",
            "hash_type": "md5",
            "sha256": "f0e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d",
            "detections": 47,
            "total_engines": 70,
            "detection_rate": "67.1%",
            "malware_family": "Trickbot",
            "malware_type": "modular_trojan",
            "severity": "critical",
            "file_type": "PE32 executable (EXE)",
            "file_size_bytes": 524288,
            "file_name": "windefupdate.exe",
            "first_seen": "2025-10-18T12:00:00Z",
            "last_seen": "2026-03-11T06:45:00Z",
            "tags": ["trickbot", "gtag-mor84", "credential-stealer", "lateral-movement"],
            "behavior_summary": "Injects into svchost.exe, harvests browser credentials, performs network reconnaissance, attempts lateral movement via EternalBlue",
            "contacted_ips": ["198.51.100.17", "198.51.100.22"],
            "contacted_domains": ["api-check-update.cc", "telemetry-cdn.ru"],
        },
    }
    return hash_database.get(
        file_hash,
        {
            "hash": file_hash,
            "hash_type": hash_type,
            "detections": 0,
            "total_engines": 72,
            "malware_family": "Unknown",
            "severity": "unknown",
            "note": "No records found for this hash",
        },
    )


def lookup_domain(domain: str) -> dict:
    """Query domain reputation. In production: URLhaus, DomainTools, or WHOIS API."""
    domain_database = {
        "secure-bankofamerica-login.com": {
            "domain": "secure-bankofamerica-login.com",
            "reputation_score": 98,
            "category": "phishing",
            "subcategory": "credential_harvesting",
            "active": True,
            "registrar": "NameSilo LLC",
            "registration_date": "2026-02-28T00:00:00Z",
            "registrant_country": "Panama",
            "hosting_provider": "BulletProof Hosting Ltd",
            "hosting_country": "Moldova",
            "ip_addresses": ["192.0.2.55", "192.0.2.56"],
            "mx_records": [],
            "ssl_issuer": "Let's Encrypt",
            "ssl_valid_from": "2026-02-28T00:00:00Z",
            "targeted_brand": "Bank of America",
            "similar_domains_found": 12,
            "urlhaus_reference": "https://urlhaus.abuse.ch/url/2345678/",
            "tags": ["phishing-kit", "credential-harvest", "typosquat"],
            "associated_ips_with_other_malicious_domains": True,
            "dns_records": {
                "A": ["192.0.2.55"],
                "NS": ["ns1.bulletproof-dns.cc", "ns2.bulletproof-dns.cc"],
                "TXT": [],
            },
        },
        "update-service-cdn.ru": {
            "domain": "update-service-cdn.ru",
            "reputation_score": 91,
            "category": "malware",
            "subcategory": "c2_server",
            "active": True,
            "registrar": "REG.RU LLC",
            "registration_date": "2025-07-14T00:00:00Z",
            "registrant_country": "Russia",
            "hosting_provider": "MnogoByte LLC",
            "hosting_country": "Russia",
            "ip_addresses": ["203.0.113.42"],
            "ssl_issuer": "Self-signed",
            "tags": ["emotet-c2", "malware-distribution", "fast-flux"],
            "associated_malware": ["Emotet", "Trickbot"],
            "dns_records": {
                "A": ["203.0.113.42", "203.0.113.88"],
                "NS": ["ns1.reg.ru", "ns2.reg.ru"],
                "TXT": [],
            },
        },
    }
    return domain_database.get(
        domain,
        {
            "domain": domain,
            "reputation_score": 0,
            "category": "unknown",
            "active": None,
            "note": "No records found for this domain",
        },
    )


def get_mitre_techniques(query: str) -> dict:
    """Map behaviors to MITRE ATT&CK. In production: query ATT&CK STIX/TAXII feed or local DB."""
    mitre_mappings = {
        "command and control": {
            "techniques": [
                {
                    "id": "T1071.001",
                    "name": "Web Protocols",
                    "tactic": "Command and Control",
                    "description": "Adversaries communicate using application layer protocols associated with web traffic to avoid detection",
                },
                {
                    "id": "T1573.002",
                    "name": "Asymmetric Cryptography",
                    "tactic": "Command and Control",
                    "description": "Use asymmetric encryption for C2 communications",
                },
                {
                    "id": "T1008",
                    "name": "Fallback Channels",
                    "tactic": "Command and Control",
                    "description": "Use alternate communication channels if primary C2 is disrupted",
                },
            ],
            "associated_groups": ["APT28", "APT29", "Lazarus Group", "Wizard Spider"],
            "detection_suggestions": [
                "Monitor for unusual outbound HTTPS to non-standard ports",
                "Inspect TLS certificates for self-signed or recently issued certs",
                "Track beaconing patterns in network flow data",
            ],
        },
        "credential theft": {
            "techniques": [
                {
                    "id": "T1056.001",
                    "name": "Keylogging",
                    "tactic": "Collection",
                    "description": "Log keystrokes to intercept credentials as they are typed",
                },
                {
                    "id": "T1555.003",
                    "name": "Credentials from Web Browsers",
                    "tactic": "Credential Access",
                    "description": "Acquire credentials from web browser credential stores",
                },
                {
                    "id": "T1003.001",
                    "name": "LSASS Memory",
                    "tactic": "Credential Access",
                    "description": "Access credential material stored in LSASS process memory",
                },
            ],
            "associated_groups": ["Trickbot operators", "Emotet operators", "FIN7"],
            "detection_suggestions": [
                "Monitor for LSASS access by unusual processes",
                "Alert on credential store file access",
                "Deploy credential guard on endpoints",
            ],
        },
        "phishing": {
            "techniques": [
                {
                    "id": "T1566.001",
                    "name": "Spearphishing Attachment",
                    "tactic": "Initial Access",
                    "description": "Send emails with a malicious attachment to gain access",
                },
                {
                    "id": "T1566.002",
                    "name": "Spearphishing Link",
                    "tactic": "Initial Access",
                    "description": "Send emails with malicious links to credential-harvesting sites",
                },
                {
                    "id": "T1598.003",
                    "name": "Spearphishing Link (for Information)",
                    "tactic": "Reconnaissance",
                    "description": "Send spearphishing links to gather information for targeting",
                },
            ],
            "associated_groups": ["APT28", "Lazarus Group", "Kimsuky", "TA505"],
            "detection_suggestions": [
                "Implement DMARC/DKIM/SPF for email authentication",
                "Deploy URL rewriting and sandboxing for links",
                "Monitor for newly registered look-alike domains",
            ],
        },
        "lateral movement": {
            "techniques": [
                {
                    "id": "T1210",
                    "name": "Exploitation of Remote Services",
                    "tactic": "Lateral Movement",
                    "description": "Exploit remote services to move laterally within the environment",
                },
                {
                    "id": "T1021.002",
                    "name": "SMB/Windows Admin Shares",
                    "tactic": "Lateral Movement",
                    "description": "Use valid accounts to interact with remote network shares using SMB",
                },
            ],
            "associated_groups": ["Wizard Spider", "FIN6", "Sandworm Team"],
            "detection_suggestions": [
                "Monitor for anomalous SMB traffic patterns",
                "Alert on use of PsExec or similar tools",
                "Track authentication events across endpoints",
            ],
        },
    }
    query_lower = query.lower()
    for key, mapping in mitre_mappings.items():
        if key in query_lower:
            return mapping
    # Fuzzy fallback: check if any keyword appears
    for key, mapping in mitre_mappings.items():
        for word in key.split():
            if word in query_lower:
                return mapping
    return {
        "techniques": [],
        "associated_groups": [],
        "note": "No direct MITRE ATT&CK mapping found for this query. Try broader terms like 'command and control', 'credential theft', 'phishing', or 'lateral movement'.",
    }


print(
    "Simulated threat intel backends ready. In production, replace function bodies with real API calls."
)
```

??? note "輸出"

    ```text
    Simulated threat intel backends ready. In production, replace function bodies with real API calls.
    ```

## Step 4: 建立 agent loop

這是核心的 orchestration。我們給 Claude 一個 system prompt，把它定位成資深 threat intelligence 分析師，然後讓它自己決定要呼叫哪些 tool、順序如何。只要 Claude 還想呼叫 tool，`while` loop 就繼續：它可能先呼叫一個 tool、檢視結果，再根據發現決定呼叫另一個。這種多輪推理讓它成為 agent，而不只是 API 的包裝。

```python
SYSTEM_PROMPT = """You are a senior threat intelligence analyst. When given an Indicator of Compromise (IOC), you systematically investigate it by:

1. Identifying the IOC type and querying the most relevant intelligence source first
2. Analyzing initial results to determine what follow-up queries would be valuable
3. Cross-referencing findings across multiple sources when related indicators are found
4. Mapping observed behaviors and malware families to MITRE ATT&CK techniques
5. Synthesizing all findings into a clear, evidence-based assessment

Always query multiple sources when possible. If an IP lookup reveals associated malware, look up the MITRE techniques for that malware. If a hash lookup reveals contacted domains or IPs, investigate those too. Build the fullest picture you can before forming your assessment.

State your confidence level (low/medium/high) and explain what evidence supports it."""

MAX_TURNS = 10  # cap the agent loop to prevent runaway costs


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    """Route tool calls to the appropriate backend function."""
    handlers = {
        "lookup_ip_reputation": lambda inp: lookup_ip_reputation(inp["ip_address"]),
        "lookup_file_hash": lambda inp: lookup_file_hash(inp["file_hash"], inp["hash_type"]),
        "lookup_domain": lambda inp: lookup_domain(inp["domain"]),
        "get_mitre_techniques": lambda inp: get_mitre_techniques(inp["query"]),
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return json.dumps(handler(tool_input), indent=2)


def run_threat_intel_agent(ioc: str, ioc_type: str) -> tuple[str, list[dict]]:
    """
    Run the threat intel enrichment agent on a single IOC.
    Returns (analysis_text, list_of_tool_calls_made).
    """
    user_message = (
        f"Investigate this indicator of compromise and provide a threat assessment:\n"
        f"  IOC: {ioc}\n"
        f"  Type: {ioc_type}\n\n"
        f"Query all relevant intelligence sources, cross-reference findings, "
        f"map to MITRE ATT&CK where applicable, and provide your assessment with "
        f"severity rating, confidence score, and recommended response actions."
    )

    messages = [{"role": "user", "content": user_message}]
    tool_calls_made = []

    for _turn in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # If Claude is done reasoning, extract final text
        if response.stop_reason == "end_turn":
            final_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "No analysis generated.",
            )
            return final_text, tool_calls_made

        # If Claude wants to use tools, process all tool calls in this turn
        if response.stop_reason == "tool_use":
            # Add assistant's response (contains both text and tool_use blocks)
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  -> Calling {block.name}({json.dumps(block.input)})")
                    tool_calls_made.append({"tool": block.name, "input": block.input})
                    result = process_tool_call(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            # Send tool results back to Claude
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            return f"Agent stopped unexpectedly: {response.stop_reason}", tool_calls_made

    # Hit turn limit without end_turn
    return (
        f"Agent reached max_turns limit ({MAX_TURNS}) without completing analysis. "
        f"Consider raising MAX_TURNS or simplifying the investigation scope.",
        tool_calls_made,
    )


print("Agent loop ready.")
```

??? note "輸出"

    ```text
    Agent loop ready.
    ```

## Step 5: 用範例 IOC 執行 agent

用三種不同的 IOC 類型測試 agent。注意看 tool call 的軌跡，Claude 會決定要查哪些來源，也可能根據發現做後續查詢（例如查在 hash 分析裡發現的 domain）。

```python
# Three test cases covering different IOC types
test_cases = [
    {
        "ioc": "203.0.113.42",
        "type": "ip_address",
        "description": "Suspicious IP flagged by firewall for outbound C2 beaconing",
    },
    {
        "ioc": "d131dd02c5e6eec4693d9a0698aff95c",
        "type": "file_hash",
        "description": "File hash from endpoint detection alert (suspected Emotet)",
    },
    {
        "ioc": "secure-bankofamerica-login.com",
        "type": "domain",
        "description": "Domain found in phishing email reported by employee",
    },
]

# Store results for structured report generation
all_results = []

for i, test in enumerate(test_cases, 1):
    print(f"\n{'=' * 70}")
    print(f"  Test Case {i}: {test['description']}")
    print(f"  IOC: {test['ioc']} (Type: {test['type']})")
    print(f"{'=' * 70}\n")
    print("Tool call trace:")

    analysis, tools_used = run_threat_intel_agent(test["ioc"], test["type"])

    all_results.append(
        {
            "ioc": test["ioc"],
            "type": test["type"],
            "description": test["description"],
            "analysis": analysis,
            "tools_used": tools_used,
        }
    )

    print(f"\n--- Agent queried {len(tools_used)} tool(s) ---")
    print(f"\nAnalysis:\n{analysis}")
    print()
```

??? note "輸出"

    ```text

    ======================================================================
      Test Case 1: Suspicious IP flagged by firewall for outbound C2 beaconing
      IOC: 203.0.113.42 (Type: ip_address)
    ======================================================================

    Tool call trace:
    ```

    ```text
      -> Calling lookup_ip_reputation({"ip_address": "203.0.113.42"})
      -> Calling get_mitre_techniques({"query": "malicious IP command and control beaconing reconnaissance scanning"})
    ```

    ```text
      -> Calling get_mitre_techniques({"query": "Emotet banking trojan command and control lateral movement credential theft"})
      -> Calling get_mitre_techniques({"query": "TrickBot banking trojan credential stealing lateral movement ransomware dropper"})
      -> Calling get_mitre_techniques({"query": "brute force credential access initial access"})
    ```

    ```text
      -> Calling get_mitre_techniques({"query": "malware distribution phishing dropper initial access malspam"})
      -> Calling get_mitre_techniques({"query": "botnet proxy obfuscation port 4444 reverse shell netcat meterpreter"})
      -> Calling get_mitre_techniques({"query": "Wizard Spider Emotet TrickBot Ryuk ransomware deployment multi-stage attack"})
    ```

    ```text
      -> Calling get_mitre_techniques({"query": "ransomware deployment data encryption impact"})
      -> Calling get_mitre_techniques({"query": "proxy anonymization traffic obfuscation multi-hop C2"})
    ```

    ```text

    --- Agent queried 10 tool(s) ---

    Analysis:
    I now have comprehensive intelligence across all relevant dimensions. Let me compile the full threat assessment.

    ---

    # 🔴 THREAT INTELLIGENCE ASSESSMENT REPORT
    **IOC:** `203.0.113.42` | **Type:** IPv4 Address
    **Report Generated:** 2026-03-10 | **Analyst Level:** Senior Threat Intelligence

    ---

    ## 🧭 EXECUTIVE SUMMARY

    > **SEVERITY: CRITICAL** | **Confidence: HIGH (87%)**

    IP `203.0.113.42` is a **confirmed high-confidence malicious infrastructure node** operating from Saint Petersburg, Russia via ISP **MnogoByte LLC (AS48666)**. With an abuse confidence score of **87/100** and **1,243 community abuse reports**, this IP is actively associated with **Emotet and TrickBot botnet C2 infrastructure** — a combination historically used as a precursor to **Ryuk/Conti ransomware deployment**. The IP is also flagged as a known proxy, expanding its threat surface to traffic obfuscation and attribution evasion.

    **Any organization with traffic to/from this IP should treat it as an active compromise and respond immediately.**

    ---

    ## 📡 INTELLIGENCE FINDINGS

    ### 1. IP Reputation Summary

    | Field | Value |
    |---|---|
    | **IP Address** | 203.0.113.42 |
    | **Geolocation** | Saint Petersburg, Russia 🇷🇺 |
    | **ASN / ISP** | AS48666 / MnogoByte LLC |
    | **Abuse Confidence Score** | **87 / 100** 🔴 |
    | **Total Abuse Reports** | 1,243 |
    | **Last Reported** | March 10, 2026 (Active) |
    | **First Observed** | August 15, 2025 |
    | **Known Proxy** | ✅ Yes |
    | **Tor Exit Node** | ❌ No |

    ... (省略 145 行)
    ```

    ```text
      -> Calling lookup_file_hash({"file_hash": "d131dd02c5e6eec4693d9a0698aff95c", "hash_type": "md5"})
    ```

    ```text
      -> Calling lookup_ip_reputation({"ip_address": "203.0.113.42"})
      -> Calling lookup_ip_reputation({"ip_address": "203.0.113.88"})
      -> Calling lookup_ip_reputation({"ip_address": "192.0.2.101"})
      -> Calling lookup_domain({"domain": "update-service-cdn.ru"})
      -> Calling lookup_domain({"domain": "cdn-api-gateway.cc"})
      -> Calling get_mitre_techniques({"query": "Emotet banking trojan dropper persistence scheduled task regsvr32 C2 HTTPS beaconing credential theft lateral movement"})
    ```

    ```text
      -> Calling get_mitre_techniques({"query": "regsvr32 living off the land execution DLL side-loading dropper payload delivery"})
      -> Calling get_mitre_techniques({"query": "scheduled task persistence Windows registry autorun startup"})
      -> Calling get_mitre_techniques({"query": "Emotet spambot lateral movement email thread hijacking network propagation"})
    ```

    ```text

    --- Agent queried 10 tool(s) ---

    Analysis:
    I now have comprehensive intelligence across all dimensions. Let me compile the full threat assessment.

    ---

    # 🔴 THREAT INTELLIGENCE ASSESSMENT REPORT

    **IOC:** `d131dd02c5e6eec4693d9a0698aff95c` (MD5)
    **Analyst Confidence:** 🔴 **HIGH**
    **Severity Rating:** 🚨 **CRITICAL**
    **Generated:** Active investigation — multi-source corroborated

    ---

    ## 1. IOC IDENTIFICATION

    | Attribute | Detail |
    |-----------|--------|
    | **File Name** | `update_service.dll` |
    | **File Type** | PE32 Executable (DLL) |
    | **File Size** | 237,568 bytes |
    | **SHA256** | `a1b2c3d4...abcdef01` |
    | **First Seen** | 2025-12-01 |
    | **Last Seen** | 2026-03-09 (very recent — **actively circulating**) |
    | **Malware Family** | **Emotet (Epoch 5)** |
    | **Malware Type** | Banking Trojan / Dropper |

    ---

    ## 2. FILE REPUTATION

    - **Detection Rate: 58/72 engines (80.6%) — widely flagged as CRITICAL**
    - Tagged as: `emotet`, `epoch5`, `banking-trojan`, `dropper`
    - The **Epoch 5** designation identifies this as part of Emotet's post-2021 resurgence infrastructure, a well-documented and highly sophisticated botnet cluster operated by **Wizard Spider / TA542**.

    ---

    ... (省略 121 行)
    ```

    ```text
      -> Calling lookup_domain({"domain": "secure-bankofamerica-login.com"})
      -> Calling get_mitre_techniques({"query": "phishing credential harvesting fake banking login page brand impersonation"})
    ```

    ```text
      -> Calling lookup_ip_reputation({"ip_address": "192.0.2.55"})
      -> Calling lookup_ip_reputation({"ip_address": "192.0.2.56"})
      -> Calling get_mitre_techniques({"query": "bulletproof hosting infrastructure credential theft web form data exfiltration"})
    ```

    ```text
      -> Calling get_mitre_techniques({"query": "typosquatting domain spoofing lookalike domain brand impersonation financial institution"})
      -> Calling get_mitre_techniques({"query": "phishing kit deployment credential exfiltration C2 data collection victim redirection"})
    ```

    ```text

    --- Agent queried 7 tool(s) ---

    Analysis:
    I now have comprehensive intelligence across all dimensions. Let me synthesize everything into a full threat assessment.

    ---

    # 🚨 THREAT INTELLIGENCE ASSESSMENT REPORT

    **IOC:** `secure-bankofamerica-login.com`
    **IOC Type:** Domain
    **Report Generated:** Based on multi-source intelligence correlation
    **Analyst Confidence:** 🔴 **HIGH (92%)**
    **Severity Rating:** 🔴 **CRITICAL**

    ---

    ## 📋 EXECUTIVE SUMMARY

    `secure-bankofamerica-login.com` is a **confirmed, actively operating phishing domain** impersonating Bank of America. It is registered on privacy-shielding infrastructure in Panama, hosted by a bulletproof hosting provider in Moldova, and has already been indexed by URLhaus as a known malicious URL. The domain uses multiple evasion and legitimacy-spoofing tactics — including a valid TLS certificate and deceptive subdomain-style naming — to deceive victims into surrendering banking credentials. **This is a live, ongoing threat requiring immediate containment action.**

    ---

    ## 🔬 DETAILED FINDINGS

    ### 1. Domain Intelligence
    | Attribute | Finding | Threat Signal |
    |---|---|---|
    | **Reputation Score** | 98/100 (Malicious) | 🔴 Critical |
    | **Category** | Phishing / Credential Harvesting | 🔴 Critical |
    | **Status** | **ACTIVE** | 🔴 Critical |
    | **Registrar** | NameSilo LLC | 🟡 Privacy-enabling registrar commonly abused |
    | **Registration Date** | 2026-02-28 | 🔴 Newly registered — classic phishing tactic |
    | **Registrant Country** | **Panama** | 🔴 Jurisdiction chosen to avoid takedown cooperation |
    | **Hosting Provider** | **BulletProof Hosting Ltd** | 🔴 Critical — provider known for ignoring abuse reports |
    | **Hosting Country** | **Moldova** | 🔴 Low law-enforcement cooperation jurisdiction |
    | **SSL Certificate** | Let's Encrypt (auto-issued) | 🟡 Lends false legitimacy; trivially obtained |
    | **Similar Domains Found** | **12 related domains** | 🔴 Part of organized, scalable phishing campaign |
    | **URLhaus Reference** | Confirmed malicious listing | 🔴 Critical |
    ... (省略 142 行)
    ```

## Step 6: 產生結構化威脅報告

Agent 原始的分析對人類分析師很好用，但下游系統（SIEM、ticketing、SOC dashboard）需要結構化資料。這個步驟把 agent 的自由文字分析轉成標準化的 JSON 報告。在 production，你可以輸出 STIX 2.1 物件，或直接餵給事件回應平台。

````python
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "ioc": {
            "type": "string",
            "description": "The indicator of compromise that was investigated",
        },
        "ioc_type": {
            "type": "string",
            "enum": ["ip_address", "file_hash", "domain", "url", "email"],
        },
        "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low", "informational"],
        },
        "confidence": {"type": "integer", "description": "Confidence score from 0-100"},
        "threat_classification": {
            "type": "string",
            "description": "Primary threat category (e.g., 'banking_trojan_c2', 'phishing', 'apt_infrastructure')",
        },
        "summary": {"type": "string", "description": "One-paragraph executive summary of findings"},
        "related_malware": {"type": "array", "items": {"type": "string"}},
        "related_threat_groups": {"type": "array", "items": {"type": "string"}},
        "mitre_techniques": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "technique_id": {"type": "string"},
                    "technique_name": {"type": "string"},
                    "tactic": {"type": "string"},
                },
            },
        },
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "related_iocs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Other IOCs discovered during investigation",
        },
    },
    "required": [
        "ioc",
        "ioc_type",
        "severity",
        "confidence",
        "threat_classification",
        "summary",
        "recommended_actions",
    ],
}


def generate_structured_report(analysis: str, ioc: str, ioc_type: str) -> dict:
    """Transform free-text agent analysis into a structured JSON report."""
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        system=(
            "You are a threat intelligence report formatter. Convert the analyst's "
            "findings into a structured JSON report matching the provided schema EXACTLY. "
            "Include ONLY the fields listed in the schema — do not add extra fields, "
            "nested objects, or elaboration. Keep array values as simple strings, not "
            "objects. Keep the summary to 2-3 sentences. Return ONLY valid JSON, no "
            "markdown fences."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Convert this threat intelligence analysis into a structured JSON report.\n\n"
                    f"IOC investigated: {ioc} (type: {ioc_type})\n\n"
                    f"Analysis:\n{analysis}\n\n"
                    f"Schema (include ONLY these fields):\n{json.dumps(REPORT_SCHEMA, indent=2)}\n\n"
                    f"Return the JSON object directly with no markdown formatting."
                ),
            }
        ],
    )

    response_text = "".join(block.text for block in response.content if block.type == "text")

    # Extract JSON from response (handle markdown code blocks if present)
    if "```json" in response_text:
        json_str = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        json_str = response_text.split("```")[1].split("```")[0].strip()
    else:
        json_str = response_text.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse structured report: {e}", "raw": response_text}


# Generate structured reports for all test cases
print("=" * 70)
print("  STRUCTURED THREAT INTELLIGENCE REPORTS")
print("=" * 70)

structured_reports = []
for result in all_results:
    report = generate_structured_report(result["analysis"], result["ioc"], result["type"])
    structured_reports.append(report)

    print(f"\n--- {result['ioc']} ---")
    print(json.dumps(report, indent=2))
    print()
````

??? note "輸出"

    ```text
    ======================================================================
      STRUCTURED THREAT INTELLIGENCE REPORTS
    ======================================================================
    ```

    ```text

    --- 203.0.113.42 ---
    {
      "ioc": "203.0.113.42",
      "ioc_type": "ip_address",
      "severity": "critical",
      "confidence": 87,
      "threat_classification": "botnet_c2",
      "summary": "IP 203.0.113.42 is a confirmed malicious infrastructure node hosted in Saint Petersburg, Russia via MnogoByte LLC (AS48666), with an abuse confidence score of 87/100 and 1,243 community abuse reports. It is actively associated with Emotet and TrickBot botnet C2 operations, malware distribution, brute-force attacks, and banking trojan activity \u2014 a combination strongly attributed to the Wizard Spider threat group and historically used as a precursor to Ryuk/Conti ransomware deployment. The infrastructure is currently active as of March 10, 2026, and any observed connections from an organization's environment should be treated as a high-priority security incident requiring immediate response.",
      "related_malware": [
        "Emotet",
        "TrickBot",
        "Ryuk",
        "Conti"
      ],
      "related_threat_groups": [
        "Wizard Spider",
        "TA542",
        "FIN6",
        "Sandworm Team",
        "APT28"
      ],
      "mitre_techniques": [
        {
          "technique_id": "T1566.001",
          "technique_name": "Spearphishing Attachment",
          "tactic": "Initial Access"
        },
        {
          "technique_id": "T1566.002",
          "technique_name": "Spearphishing Link",
          "tactic": "Initial Access"
        },
        {
          "technique_id": "T1071.001",
          "technique_name": "Web Protocols",
          "tactic": "Command and Control"
        },
        {
          "technique_id": "T1573.002",
    ... (省略 57 行)
    ```

    ```text

    --- d131dd02c5e6eec4693d9a0698aff95c ---
    {
      "ioc": "d131dd02c5e6eec4693d9a0698aff95c",
      "ioc_type": "file_hash",
      "severity": "critical",
      "confidence": 85,
      "threat_classification": "banking_trojan_dropper",
      "summary": "The investigated MD5 hash corresponds to update_service.dll, identified as Emotet Epoch 5, a banking trojan and dropper operated by Wizard Spider/TA542, detected by 80.6% of 72 AV engines. The sample communicates with confirmed C2 infrastructure hosted in Russia and exhibits credential harvesting, persistence, and lateral movement behaviors consistent with a multi-stage attack chain. The co-presence of TrickBot infrastructure indicates a high risk of downstream ransomware deployment via Ryuk, Conti, or BlackBasta.",
      "related_malware": [
        "Emotet",
        "TrickBot",
        "Ryuk",
        "Conti",
        "BlackBasta"
      ],
      "related_threat_groups": [
        "Wizard Spider",
        "TA542",
        "FIN7"
      ],
      "mitre_techniques": [
        {
          "technique_id": "T1218.010",
          "technique_name": "Regsvr32",
          "tactic": "Execution"
        },
        {
          "technique_id": "T1053.005",
          "technique_name": "Scheduled Task/Job",
          "tactic": "Persistence"
        },
        {
          "technique_id": "T1071.001",
          "technique_name": "Web Protocols (HTTPS)",
          "tactic": "Command and Control"
        },
        {
          "technique_id": "T1573.002",
          "technique_name": "Asymmetric Cryptography",
    ... (省略 64 行)
    ```

    ```text

    --- secure-bankofamerica-login.com ---
    {
      "ioc": "secure-bankofamerica-login.com",
      "ioc_type": "domain",
      "severity": "critical",
      "confidence": 92,
      "threat_classification": "phishing",
      "summary": "secure-bankofamerica-login.com is a confirmed, actively operating phishing domain impersonating Bank of America, registered via a privacy-shielding registrar in Panama and hosted on bulletproof infrastructure in Moldova. The domain employs credential harvesting tactics including TLS certificate spoofing and deceptive keyword-stuffed naming, and has been corroborated as malicious by URLhaus. Immediate blocking and incident response actions are required, as this domain is part of an organized phishing campaign cluster with 12 identified related domains.",
      "related_malware": [
        "phishing-kit"
      ],
      "related_threat_groups": [
        "TA505",
        "FIN7",
        "Wizard Spider"
      ],
      "mitre_techniques": [
        {
          "technique_id": "T1598.003",
          "technique_name": "Spearphishing Link for Information",
          "tactic": "Reconnaissance"
        },
        {
          "technique_id": "T1566.002",
          "technique_name": "Phishing: Spearphishing Link",
          "tactic": "Initial Access"
        },
        {
          "technique_id": "T1056.001",
          "technique_name": "Input Capture: Keylogging / Web Form",
          "tactic": "Credential Access"
        },
        {
          "technique_id": "T1555.003",
          "technique_name": "Credentials from Web Browsers",
          "tactic": "Credential Access"
        },
        {
          "technique_id": "T1071.001",
    ... (省略 37 行)
    ```

## 總結與後續

這份 cookbook 示範了怎麼做一個 threat intelligence enrichment agent，它能自主查詢多個資料來源、交叉比對發現，並產出結構化報告。可以帶走的重點模式：

- **Tool-use agentic loop**：Claude 自己決定要呼叫哪些 tool，並根據結果追查，不用寫死查詢順序
- **模組化 tool 設計**：每個情資來源都是介面清楚、schema 明確的 function，要換成真的 API 很直接
- **多來源關聯**：system prompt 鼓勵 Claude 在來源之間 pivot（例如 hash → 連線的 IP → IP 信譽 → MITRE 對應）
- **結構化輸出**：把原始分析轉成機器可讀的報告給下游系統

### 要做到 production-ready

**換成真的 API**：把 mock function 換成呼叫 VirusTotal、AbuseIPDB、Shodan、GreyNoise、URLhaus、DomainTools 或你組織內部的 threat intel feed。Tool schema 跟 agent loop 不變。

**加更多 tool**：WHOIS 查詢、passive DNS、SSL 憑證透明度紀錄、sandbox 引爆（例如 Joe Sandbox、Hybrid Analysis），以及 EDR/SIEM enrichment 查詢。

**用 async 擴展**：大量處理 IOC 時，用 `asyncio` 平行執行 tool call 並處理 IOC queue。考慮用有 TTL 的快取避免重複呼叫 API。

**強化結構化輸出**：用 Claude 的 tool use 能力強制符合 JSON schema，而不是解析自由文字，或是依 Step 6 定義的 `REPORT_SCHEMA` 驗證報告。

**整合你的技術棧**：把結構化報告匯出成 STIX 2.1 bundle，推送到 Splunk/Elastic/SOAR 平台，或餵給 ticketing 系統自動建立事件。

**加入信心校準**：依來源可靠度、資料新鮮度跟跨來源佐證來加權信心分數。獨立來源彼此一致時應該提高信心。

### 延伸閱讀

- [Building effective agents](https://anthropic.com/research/building-effective-agents)：Anthropic 對 agent 模式的研究
- [Tool use documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview)：Claude tool use 能力的完整指南
- [MITRE ATT&CK](https://attack.mitre.org/)：這份 cookbook 參考的框架

## 重點整理

- Agent 跟單純 API 包裝的差別在於 loop：Claude 看完 tool 結果後自己決定下一步。
- Tool 的 description 寫得清楚，Claude 才會選對來源；schema 穩定，後端才能隨時換成真 API。
- System prompt 引導跨來源 pivot，是做出關聯分析的關鍵。
- 自由文字給人看、結構化 JSON 給系統用，兩種輸出可以串成同一條流程。
- 上 production 要考慮真實 API、async、快取、schema 強制與信心校準。

## 練習

1. 在 Step 5 加入一個新的 IOC（例如另一個 IP），看 agent 會呼叫哪些 tool、順序如何。
2. 在 Step 2 新增第五個 tool（例如 WHOIS 查詢），並在 Step 3 補一個模擬 function，確認 agent 會用到它。
3. 把 Step 6 改用 tool use 強制輸出符合 `REPORT_SCHEMA` 的 JSON，不再解析自由文字。
