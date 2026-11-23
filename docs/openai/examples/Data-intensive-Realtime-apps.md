---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Data-intensive-Realtime-apps.ipynb
---
# 用 Realtime API 處理大量資料的實戰指南

> 原文：[examples/Data-intensive-Realtime-apps.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Data-intensive-Realtime-apps.ipynb)



## 這篇在做什麼
這篇教你怎麼讓 Realtime API 在 function call 回傳大量資料時，還能維持快速、穩定的回應。範例是一個 NBA 選秀球探 agent，會呼叫多個 function 來分析選秀新秀。基本的 Realtime API 設定不在這篇範圍內。

## 學完你會
- 把一個肥大的 function 拆成職責清楚的小 function，縮小每次回傳的資料量
- 用過濾、攤平結構、換資料格式這幾招，讓 function call 的回傳更精簡
- 在資料量大的 function call 之後送出 hint prompt，讓模型答得更準

## 開跑前
需要有 OpenAI API key，並且已經會建立 Realtime API 的 session。

這份 cookbook 是給 AI 工程師的實戰指南，教你在遇到資料量很大的 function call 時，怎麼讓 OpenAI 的 Realtime API 發揮最好的效果。重點放在 speech-to-speech agent 常見的情境：大量資料要順暢又有效率地處理。

這篇不會講怎麼從頭架一個 Realtime API 方案，而是給你清楚的觀念和可以直接用的做法，讓即時對話 agent 的效能和穩定度更好。內容針對的是即時對話情境下，處理大量資料會碰到的特殊問題。

### 什麼是 Realtime API？

先簡單回顧一下。OpenAI Realtime API 是比較新的服務，支援低延遲的多模態互動，例如 speech-to-speech 對話和即時轉錄。想像一下即時語音客服，或是電影的即時字幕轉錄。

### 什麼是資料量大的 function call？

Agent 要有 tool 和相關資料才能完成任務。例如財務分析 agent 可能要抓即時市場資料。很多時候，你的環境裡已經有現成的服務，透過 API 提供這些資訊。

過去的 API 並不是為 agent 設計的，依服務不同常常會回傳大量資料。工程師通常會直接用 function call 把這些 API 包起來，加快 agent 開發速度，這很合理，已經有的東西何必重做。

但如果不好好最佳化，這些資料量大的 function call 很容易壓垮 Realtime API，造成回應變慢，甚至處理不了使用者的請求。

### 範例場景

我們的範例是一個 NBA 球探 agent，它會呼叫多個 function，對即將選秀的新秀做深入分析。為了示範 Realtime API 互動的實務準則，我們用了大型又貼近真實的 payload，靈感來自 NBA 選秀新秀的資料。下面是在 Realtime session 裡定義的一個肥大的 `searchDraftProspects` function。

```json
// "Hey, pull up point guards projected in the top 10 in the 2025 draft"
{
  "type": "session.update",
  "session": {
    "tools": [
      {
        "type": "function",
        "name": "searchDraftProspects",
        "description": "Search draft prospects for a given year e.g., Point Guard",
        "parameters": {
          "type": "object",
          "properties": {
            "sign": {
              "type": "string",
              "description": "The player position",
              "enum": [
                "Point Guard",
                "Shooting Guard",
                "Small Forward",
                "Power Forward",
                "Center",
                "Any"
              ]
            },
            year: { type: "number", description: "Draft year e.g., 2025" },
            mockDraftRanking: { type: "number", description: "Predicted Draft Ranking" },
          },
          "required": ["position", "year"]
        }
      }
    ],
    "tool_choice": "auto",
  }
}
```

searchDraftProspects 這個 function call 回傳的 payload 很大。範例的結構和大小是參考我們在真實場景中遇到的情況。

```json
// Example Payload
{
  "status": {
    "code": 200,
    "message": "SUCCESS"
  },
  "found": 4274,
  "offset": 0,
  "limit": 10,
  "data": [
    {
      "prospectId": 10001,
      "data": {
        "ProspectInfo": {
          "league": "NCAA",
          "collegeId": 301,
          "isDraftEligible": true,
          "Player": {
            "personalDetails": {
              "firstName": "Jalen",
              "lastName": "Storm",
              "dateOfBirth": "2003-01-15",
              "nationality": "USA"
            },
            "physicalAttributes": {
              "position": "PG",
              "height": {
                "feet": 6,
                "inches": 4
              },
              "weightPounds": 205
            },
            "hometown": {
              "city": "Springfield",
              "state": "IL"
            }
          },
          "TeamInfo": {
            "collegeTeam": "Springfield Tigers",
            "conference": "Big West",
            "teamRanking": 12,
            "coach": {
              "coachId": 987,
              "coachName": "Marcus Reed",
              "experienceYears": 10
            }
          }
        },
        "Stats": {
          "season": "2025",
          "gamesPlayed": 32,
          "minutesPerGame": 34.5,
          "shooting": {
            "FieldGoalPercentage": 47.2,
            "ThreePointPercentage": 39.1,
            "FreeThrowPercentage": 85.6
          },
          "averages": {
            "points": 21.3,
            "rebounds": 4.1,
            "assists": 6.8,
            "steals": 1.7,
            "blocks": 0.3
          }
        },
        "Scouting": {
          "evaluations": {
            "strengths": ["Court vision", "Clutch shooting"],
            "areasForImprovement": ["Defensive consistency"]
          },
          "scouts": [
            {
              "scoutId": 501,
              "name": "Greg Hamilton",
              "organization": "National Scouting Bureau"
            }
          ]
        },
        "DraftProjection": {
          "mockDraftRanking": 5,
          "lotteryPickProbability": 88,
          "historicalComparisons": [
            {
              "player": "Chris Paul",
              "similarityPercentage": 85
            }
          ]
        },
        "Media": {
          "highlightReelUrl": "https://example.com/highlights/jalen-storm",
          "socialMedia": {
            "twitter": "@jstorm23",
            "instagram": "@jstorm23_ig"
          }
        },
        "Agent": {
          "agentName": "Rick Allen",
          "agency": "Elite Sports Management",
          "contact": {
            "email": "rallen@elitesports.com",
            "phone": "555-123-4567"
          }
        }
      }
    },
    // ... Many thousands of tokens later.
  ]
}
```

## 指導原則

### 1. 把笨重的 function 拆成小的，職責清楚

這點幾乎不用多說：設計 function call 時，第一優先是把 function 設計得清楚、定義明確。這樣才容易縮小回傳大小，避免模型被資料淹沒。每個 function call 都應該一句話講得清楚、範圍收斂，只回傳它用途需要的資訊。function 之間職責重疊，一定會造成混亂。

舉例來說，我們可以讓 `searchDraftProspects` 只回傳每位新秀的一般資訊（例如球員數據），大幅縮小回傳大小。需要更多細節時，再用新的 `getProspectDetails` function call 取得完整資料。沒有萬用解法，要看你的使用情境和資料模型。

```json
{
  "tools": [
    {
      "type": "function",
      "name": "searchDraftProspects",
      "description": "Search NBA draft prospects by position, draft year, and projected ranking, returning only general statistics to optimize response size.",
      "parameters": {
        "type": "object",
        "properties": {
          "position": {
            "type": "string",
            "description": "The player's basketball position.",
            "enum": [
              "Point Guard",
              "Shooting Guard",
              "Small Forward",
              "Power Forward",
              "Center",
              "Any"
            ]
          },
          "year": {
            "type": "number",
            "description": "Draft year, e.g., 2025"
          },
          "maxMockDraftRanking": {
            "type": "number",
            "description": "Maximum predicted draft ranking (e.g., top 10)"
          }
        },
        "required": ["position", "year"]
      }
    },
    {
      "type": "function",
      "name": "getProspectDetails",
      "description": "Fetch detailed information for a specific NBA prospect, including comprehensive stats, agent details, and scouting reports.",
      "parameters": {
        "type": "object",
        "properties": {
          "playerName": {
            "type": "string",
            "description": "Full name of the prospect (e.g., Jalen Storm)"
          },
          "year": {
            "type": "number",
            "description": "Draft year, e.g., 2025"
          },
          "includeAgentInfo": {
            "type": "boolean",
            "description": "Include agent information"
          },
          "includeStats": {
            "type": "boolean",
            "description": "Include detailed player statistics"
          },
          "includeScoutingReport": {
            "type": "boolean",
            "description": "Include scouting report details"
          }
        },
        "required": ["playerName", "year"]
      }
    }
  ],
  "tool_choice": "auto"
}
```

### 2. 對話進行時，持續優化 context

Realtime 對話允許長達 30 分鐘的 session，但滾動式的 context window 只支援大約 16,000 tokens（實際依模型 snapshot 而定，context window 的限制正在改善）。所以在長時間對話中，你可能會發現效能慢慢下降。隨著對話進行、function call 越來越多，對話狀態會快速膨脹，裡面有重要資訊也有不必要的雜訊，所以要把重心放在保留最相關的細節。這樣能維持良好的效能，也能降低成本。

**i) 定期摘要對話狀態**

在對話進行中定期做摘要，是縮小 context 的好方法，成本和延遲都會下降。

可以參考 @Minhajul 寫的 Realtime 對話自動摘要實作指南（[連結](https://cookbook.openai.com/examples/context_summarization_with_realtime_api)）。

**ii) 定期提醒模型它的角色和職責**

資料量大的 payload 很快就會塞滿 context window。如果你發現模型忘了指示或可用的 tool，可以呼叫 `session.update`，定期把 system prompt 和 tool 再提醒它一次，讓它專注在自己的角色和職責上。

### 3. 資料處理與最佳化

**i) 在 function call 裡做過濾，把資料量大的回應縮減成回答問題真正需要的欄位**

一般來說，function call 回傳的 token 越少，回答品質越好。常見的坑是 function call 回傳好幾千 token 的巨大 payload。在每個 function call 裡做過濾，不管是資料層還是 function 層，都能把回應大小壓下來。

```json
// Filtered response
{
  "status": {
    "code": 200,
    "message": "SUCCESS"
  },
  "found": 4274,
  "offset": 0,
  "limit": 5,
  "data": [
    {
    "zpid": 7972122,
      "data": {
        "PropertyInfo": {
            "houseNumber": "19661",
            "directionPrefix": "N ",
            "streetName": "Central",
            "streetSuffix": "Ave",
            "city": "Phoenix",
            "state": "AZ",
            "postalCode": "85024",
            "zipPlusFour": "1641"
            "bedroomCount": 2,
            "bathroomCount": 2,
            "storyCount": 1,
            "livingAreaSize": 1089,
            "livingAreaSizeUnits": "Square Feet",
            "yearBuilt": "1985"
          }
		    }
			}
		]
		// ... 
}
```

**ii) 攤平階層式 payload，但不要丟掉關鍵資訊**

API 回傳的階層式 payload 有時會重複出現各層標題，像 "ProspectInfo" 或 "Stats"，這會增加雜訊，讓模型更難處理。在讓資料更有效率的過程中，可以試著攤平這些結構，去掉一些不必要的標籤。這樣能提升效能，不過要想清楚你的使用情境裡哪些資訊必須保留。

```json
// Flattened payload
{
  "status": {
    "code": 200,
    "message": "SUCCESS"
  },
  "found": 4274,
  "offset": 0,
  "limit": 2,
  "data": [
    {
      "prospectId": 10001,
      "league": "NCAA",
      "collegeId": 301,
      "isDraftEligible": true,
      "firstName": "Jalen",
      "lastName": "Storm",
      "position": "PG",
      "heightFeet": 6,
      "heightInches": 4,
      "weightPounds": 205,
      "hometown": "Springfield",
      "state": "IL",
      "collegeTeam": "Springfield Tigers",
      "conference": "Big West",
      "teamRanking": 12,
      "coachId": 987,
      "coachName": "Marcus Reed",
      "gamesPlayed": 32,
      "minutesPerGame": 34.5,
      "FieldGoalPercentage": 47.2,
      "ThreePointPercentage": 39.1,
      "FreeThrowPercentage": 85.6,
      "averagePoints": 21.3,
      "averageRebounds": 4.1,
      "averageAssists": 6.8,
      "stealsPerGame": 1.7,
      "blocksPerGame": 0.3,
      "strengths": ["Court vision", "Clutch shooting"],
      "areasForImprovement": ["Defensive consistency"],
      "mockDraftRanking": 5,
      "lotteryPickProbability": 88,
      "highlightReelUrl": "https://example.com/highlights/jalen-storm",
      "agentName": "Rick Allen",
      "agency": "Elite Sports Management",
      "contactEmail": "rallen@elitesports.com"
    },
		...
 }
 ```

**iii) 試試不同的資料格式**

資料怎麼組織，會直接影響模型處理和摘要 API 回應的效果。根據我們的經驗，JSON 或 YAML 這類以 key 為主的格式，比 Markdown 這類表格格式更能幫模型正確理解資料。尤其是大型表格，很容易讓模型吃不消，輸出變得不流暢也不準。不過還是值得多試幾種格式，找出最適合你情境的。

```yaml
status:
  code: 200
  message: "SUCCESS"
found: 4274
offset: 0
limit: 10
data:
  - prospectId: 10001
    data:
      ProspectInfo:
        league: "NCAA"
        collegeId: 301
        isDraftEligible: true
        Player:
          firstName: "Jalen"
          lastName: "Storm"
          position: "PG"
          heightFeet: 6
          heightInches: 4
          weightPounds: 205
          hometown: "Springfield"
          state: "IL"
        TeamInfo:
          collegeTeam: "Springfield Tigers"
          conference: "Big West"
          teamRanking: 12
          coachId: 987
          coachName: "Marcus Reed"
      Stats:
        gamesPlayed: 32
        minutesPerGame: 34.5
        FieldGoalPercentage: 47.2
        ThreePointPercentage: 39.1
        FreeThrowPercentage: 85.6
        averagePoints: 21.3
        averageRebounds: 4.1
        averageAssists: 6.8
        stealsPerGame: 1.7
        blocksPerGame: 0.3
      Scouting:
        strengths:
          - "Court vision"
          - "Clutch shooting"
        areasForImprovement:
          - "Defensive consistency"
      DraftProjection:
        mockDraftRanking: 5
        lotteryPickProbability: 88
      Media:
        highlightReelUrl: "https://example.com/highlights/jalen-storm"
      Agent:
        agentName: "Rick Allen"
        agency: "Elite Sports Management"
        contactEmail: "rallen@elitesports.com"
```

## 4. 資料量大的 function call 之後，接著送 hint prompt

底層模型常常很難從資料量大的回應順利轉成準確的答案。為了在處理複雜資料時讓回答更流暢準確，可以在 function call 之後立刻給一個 function call hint。這些 hint 會告訴模型當下的任務，教它怎麼解讀關鍵欄位和領域特有的值。

下面是一個有效的 hint prompt 範例。

```javascript
// Function call hint
let prospectSearchPrompt = `
Parse NBA prospect data and provide a concise, engaging response.

General Guidelines
- Act as an NBA scouting expert.
- Highlight key strengths and notable attributes.
- Use conversational language.
- Mention identical attributes once.
- Ignore IDs and URLs.

Player Details
- State height conversationally ("six-foot-eight").
- Round weights to nearest 5 lbs.

Stats & Draft Info
- Round stats to nearest whole number.
- Use general terms for draft ranking ("top-five pick").
Experience
- Refer to players as freshman, sophomore, etc., or mention professional experience.
- Location & TeamMention hometown city and state/country.
- Describe teams conversationally.

Skip (unless asked explicitly)
- Exact birth dates
- IDs
- Agent/contact details
- URLs

Examples
- "Jalen Storm, a dynamic six-foot-four point guard from Springfield, Illinois, averages 21 points per game."
- "Known for his clutch shooting, he's projected as a top-five pick."

Important: Respond based strictly on provided data, without inventing details.
`;
```

實際做法是先把 function call 的結果加進對話，再用 hint prompt 要 Realtime API 產生一次回應。這樣模型就能漂亮地處理所有資訊。

```javascript
// Add new conversation item for the model
const conversationItem = {
  type: 'conversation.item.create',
  previous_item_id: output.id,
  item: {
    call_id: output.call_id,
    type: 'function_call_output',
    output: `Draft Prospect Search Results: ${result}`
  }
};

dataChannel.send(JSON.stringify(conversationItem));

// Emit a response from the model including the hint prompt
const event = {
  type: 'response.create',
  conversation: "none",
  response: {
    instructions: prospectSearchPrompt # function call hint
  }
};

dataChannel.send(JSON.stringify(event));
```

## 總結

用 Realtime API 打造有效的 agent，是不斷探索和調整的過程。

**重點建議整理**

- **過濾資料：** 只放跟使用者請求或模型下一步直接相關的欄位和細節，其餘砍掉。
- **攤平並簡化結構：** 減少深層巢狀或重複的資料，讓模型和人都容易掃讀。
- **偏好清楚的結構化格式：** 用 JSON（或 YAML），欄位名稱一致、雜訊少。資料量大的回應避免用大型表格或 markdown。
- **用 hint prompt 引導模型：** 回傳大量資料之後，接著送一個明確的 prompt，說明模型該擷取或摘要什麼。

記得，實驗很重要。Realtime 模型持續在進步，我們也會繼續分享讓你把 Realtime API 用得更好的技巧。

## 重點整理
- function call 回傳的資料越大，Realtime API 越容易變慢或失敗，所以要先控制回傳大小
- function 拆小、職責單一，比一個包山包海的 function 好管理
- 對話 context 有限，要靠摘要和 `session.update` 提醒來維持模型的專注
- 過濾欄位、攤平結構、用 JSON 或 YAML，都是在減少模型要處理的雜訊
- 大量資料回傳後送 hint prompt，能幫模型順利轉成準確的回答

## 練習
1. 看 `searchDraftProspects` 的定義，挑兩個你覺得球探不一定每次都需要的欄位，從回傳裡拿掉，比較前後 payload 的大小。
2. 把你拆出來的 `getProspectDetails` 加上一個參數，只回傳指定的幾個欄位（例如只要身體數據），讓呼叫端自己決定要多少資料。
3. 改寫 hint prompt，讓模型回答時一定要先講出該球員的位置和身高，再給評價，然後觀察回答有沒有照做。
