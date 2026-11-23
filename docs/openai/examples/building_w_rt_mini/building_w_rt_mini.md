---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/building_w_rt_mini/building_w_rt_mini.ipynb
---
# 用 Realtime Mini 打造語音 Agent

> 原文：[examples/building_w_rt_mini/building_w_rt_mini.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/building_w_rt_mini/building_w_rt_mini.ipynb)

## 這篇在做什麼

用 Agents SDK（TypeScript）和 GPT Realtime Mini，做一個航空客服語音 app。主 agent 負責判斷使用者意圖，再用 handoff 交給 QA agent（一般問題）或 Flight Status agent（需要驗證身分的個人問題）。

## 學完你會

- 用 `RealtimeAgent` 建立主 agent，讓它當意圖分類器並 handoff 給專門的 agent
- 幫 agent 掛上 `documentLookupTool`，做出（mock 版）文件查詢的 QA agent
- 用 tool 的 `needsApproval` 參數加上驗證關卡，並監聽 `tool_approval_requested` 事件更新 UI

## 開跑前

- 需要 OpenAI API key
- 需要 Node.js 環境，會 clone [openai-agents-js](https://github.com/openai/openai-agents-js/tree/main) repo 並跑裡面的 web demo
- 要有麥克風，才能實際用語音測試

小時候我很迷 Jarvis 這種概念，一個能自己處理複雜工作流程的智慧助理。那時我沒意識到，我想像的其實是語音 agent 的未來。OpenAI 隨著 `4o-audio` 的推出，率先讓這個願景成真，最近又發布了 [GPT Realtime Mini](https://platform.openai.com/docs/models/gpt-realtime-mini)，成本降了 70%，更容易取得，延遲更低，tool calling 也有大幅進步。

不過，用語音模型開發跟純文字介面根本不同。除了 prompt engineering，音訊模型還帶來新的挑戰：對延遲更敏感、需要管理 WebRTC session，還有語音活動偵測（VAD）帶來的額外變數。

為了讓這件事更簡單，OpenAI 推出了 Python 和 TypeScript 版的 Agents SDK，並附上詳細範例，展示我們建議的、用來打造可靠語音 agent 的設計模式。

動手寫程式之前，先搞清楚我們要做什麼，以及它在整個 agent handoff 架構裡的位置。

## 系統架構

今天我們要做一個非常簡單的客服 app，用的是**「handoff 架構」**。**「Handoff 架構」**是指由一個**主 agent** 負責協調所有進來的客戶問題。它不直接處理每個請求，而是分析使用者訊息背後的意圖，並**歸類到兩條核心路徑之一**：

1. 一般問題和基本支援（不需要驗證）。
2. 特定問題（查詢前需要先驗證使用者身分）。

依照分類結果，主 agent 會**把對話 handoff** 給專門處理該任務的 specialist agent。

![alt text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/byo_realtime_diagram.png)

## 設定

我們不從零開始，而是從 [openai-agents-js](https://github.com/openai/openai-agents-js/tree/main) repo 改起，所以先 clone、安裝必要的相依套件，並 build web demo
```bash
git clone https://github.com/openai/openai-agents-js/tree/main
```

clone 完之後，照 readme 的步驟開始
```bash
npm install @openai/agents zod@3
pnpm examples:realtime-next
```

如果一切正常，你會看到一個簡單的聊天介面
![alt text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/byo_realtime_starting.png)

## 主 Agent

好！repo 已經 clone 好了，接下來要修改 `openai-agents-js/examples/realtime-next/src/app/page.tsx`，先從**主 Agent** 開始。**主 Agent** 是整個應用的進入點，它是所有使用者問題的意圖分類器，決定要在不同層之間怎麼轉送。

實作相當直接
```js
const mainAgent = new RealtimeAgent({
  name: 'Main Agent',
  instructions:
    'You are the entry point for all customer queries. Default to the no-auth QA flow. If authentication is needed and validated, escalate to the Auth Layer by handing off to either the Flight Status Checker or Rebooking Agent. Do not answer policy questions from your own knowledge; rely on subordinate agents and tools.',
  tools: [
    checkFlightsTool,
  ],
  handoffs: [qaAgent],
});
```

## QA Agent

主 agent 做好了，下一步是加一個專門的輔助 agent，處理某一類客戶問題。針對一般的航空公司政策問題，這個 agent 就是 QA Agent。

在真實產品裡，這個 agent 會支撐更完整的體驗：匯入公司專屬的 PDF 和其他參考資料、做 embedding，並在 runtime 動態查詢這些文件，提供準確、有政策依據的答案。

```
┌────────────┐      ┌────────────┐      ┌────────────────────────┐      ┌────────────┐
│ User Query │ ───► │ QA Agent   │ ───► │ Vector DB / Retriever  │ ───► │ LLM Answer │
└────────────┘      └────────────┘      └────────────────────────┘      └────────────┘
                          │                     │
                          │ build search        │ top-k context
                          ▼                     ▼
                 (semantic search)      (grounded generation)

```

這通常需要建一整套 vector database 服務，把客戶的查詢做 embedding 並取回最相關的結果。為了讓 demo 簡單，我們把這部分流程 mock 掉。

如果你想學怎麼實作功能完整的檢索系統，可以看我們關於這個主題的其他 cookbook，在[這裡](https://cookbook.openai.com/examples/vector_databases/pinecone/readme)。

```js
const documentLookupTool = tool({
  name: 'document_lookup_tool',
  description: 'Looks up answers from known airline documentation to handle general questions without authentication.',
  parameters: z.object({
    request: z.string(),
  }),
  execute: async ({ request }) => {
    const mockDocument = `**Airline Customer Support — Quick Reference**

1. Each passenger may bring 1 carry-on (22 x 14 x 9) and 1 personal item.
2. Checked bags must be under 50 lbs; overweight fees apply.
3. Online check-in opens 24 hours before departure.
4. Seat upgrades can be requested up to 1 hour before boarding.
5. Wi‑Fi is complimentary on all flights over 2 hours.
6. Customers can change flights once for free within 24 hours of booking.
7. Exit rows offer extra legroom and require passengers to meet safety criteria.
8. Refunds can be requested for canceled or delayed flights exceeding 3 hours.
9. Pets are allowed in the cabin if under 20 lbs and in an approved carrier.
10. For additional help, contact our support team via chat or call center.`;
    return mockDocument;
  },
});
```

跟前面定義主 Agent 時一樣，我們要建立另一個 `RealtimeAgent` 實例，但這次要提供一個 `documentLookupTool`。

```js
const qaAgent = new RealtimeAgent({
  name: 'QA Agent',
  instructions:
    'You handle general customer questions using the document lookup tool. Use only the document lookup for answers. If the request may involve personal data or operations (rebooking, flight status), call the auth check tool. If auth is required and validated, handoff to the appropriate Auth Layer agent.',
  tools: [documentLookupTool],
});
```

## Flight Status Agent

我們已經打好很強的基礎：一個能處理進線客戶問題的主 agent，和一個搜尋文件庫、提供有政策依據答案的 QA agent。

缺的是處理客戶專屬資訊的那一層，例如「我的航班狀態是什麼？」或「我該去哪個航廈？」。要支援這類個人化互動，必須在流程裡嵌入驗證層，系統才能安全地存取並回覆使用者專屬的資料。

```
┌────────────┐      ┌──────────────┐      ┌───────────────────────┐      ┌───────────────────────┐
│ User Query │ ───► │ Auth Layer   │ ───► │ Customer Data Access  │ ───► │ LLM Answer (Personal) │
└────────────┘      └──────────────┘      └───────────────────────┘      └───────────────────────┘
                        │                          │
                        │ verify identity          │ query flight / account
                        ▼                          ▼
                (token, SSO, OTP, etc.)   (e.g., flight status, profile info)
```
還好，Agents SDK 就是為這種情境設計的。對涉及敏感、帳號層級資訊的客服情境，我們可以在 `tool` 裡使用 `needsApproval` 參數來確保適當的存取控制，它要求使用者在任何受保護資料被存取之前先通過驗證。

```js
const checkFlightsTool = tool({
  name: 'checkFlightsTool',
  description: 'Call this tool if the user queries about their current flight status',
  parameters: z.object({}),
  // Require approval so the UI can collect creds before executing.
  needsApproval: true,
  execute: async () => {
    if (!credState.username || !credState.password) {
      return 'Authentication missing.';
    }
    return `${credState.username} you are currently booked on the 8am flight from SFO to JFK`;
  },
});
```

當 tool 註冊了 `needsApproval`，session 期間它會自動發出 `tool_approval_requested` 事件。這讓我們可以在網頁應用的 `RealtimeAgent` 實例化區塊裡加入邏輯，監聽這些事件並相應更新 UI，例如在繼續之前提示使用者核准或驗證。

```js
  const [credUsername, setCredUsername] = useState('');
  const [credPassword, setCredPassword] = useState('');
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);

  useEffect(() => {
    session.current = new RealtimeSession(mainAgent, {
        // other configs go here! 
    });
    // various other event based logic goes here!
    session.current.on(
      'tool_approval_requested',
      (_context, _agent, approvalRequest) => {
        setPendingApproval(approvalRequest.approvalItem); // <- Alterations to react state!
        setCredUsername('');
        setCredPassword('');
        setCredOpen(true);
      },
    );
  }, []);
  // ....
  return (
    {credOpen && (
        <div className="fixed inset-0 z-50">
          // ... remainder of component logic
        </div>
      )}
  )
```

## 最終程式碼

這樣就完成了！你已經做好客服應用的核心元件：

* 一個能處理各種客服問題的通用 agent
* 一個驗證使用者身分並取回客戶專屬資訊的驗證流程

全部就位後，`realtime-next/src/app/page.tsx` 的最終版本應該長這樣。

```js
'use client';

import {
  RealtimeAgent,
  RealtimeSession,
  tool,
  TransportEvent,
  RealtimeOutputGuardrail,
  OutputGuardrailTripwireTriggered,
  RealtimeItem,
} from '@openai/agents/realtime';
import { useEffect, useRef, useState } from 'react';
import { z } from 'zod';
import { getToken } from './server/token.action';
import { App } from '@/components/App';
import { CameraCapture } from '@/components/CameraCapture';

// Demo-only credential store the tool can read at execution time
const credState: { username?: string; password?: string } = {};

// ---------------------------------------------
// Tools.

const documentLookupTool = tool({
  name: 'document_lookup_tool',
  description: 'Looks up answers from known airline documentation to handle general questions without authentication.',
  parameters: z.object({
    request: z.string(),
  }),
  execute: async ({ request }) => {
    const mockDocument = `**Airline Customer Support — Quick Reference**

1. Each passenger may bring 1 carry-on (22 x 14 x 9) and 1 personal item.
2. Checked bags must be under 50 lbs; overweight fees apply.
3. Online check-in opens 24 hours before departure.
4. Seat upgrades can be requested up to 1 hour before boarding.
5. Wi‑Fi is complimentary on all flights over 2 hours.
6. Customers can change flights once for free within 24 hours of booking.
7. Exit rows offer extra legroom and require passengers to meet safety criteria.
8. Refunds can be requested for canceled or delayed flights exceeding 3 hours.
9. Pets are allowed in the cabin if under 20 lbs and in an approved carrier.
10. For additional help, contact our support team via chat or call center.`;
    return mockDocument;
  },
});

const checkFlightsTool = tool({
  name: 'checkFlightsTool',
  description: 'Call this tool if the user queries about their current flight status',
  parameters: z.object({}),
  // Require approval so the UI can collect creds before executing.
  needsApproval: true,
  execute: async () => {
    if (!credState.username || !credState.password) {
      return 'Authentication missing.';
    }
    return `${credState.username} you are currently booked on the 8am flight from SFO to JFK`;
  },
});

// ---------------------------------------------
// Agents for each layer.

// 2. No-Auth Layer: QA Agent with doc lookup and auth check tool.
const qaAgent = new RealtimeAgent({
  name: 'QA Agent',
  instructions:
    'You handle general customer questions using the document lookup tool. Use only the document lookup for answers. If the request may involve personal data or operations (rebooking, flight status), call the auth check tool. If auth is required and validated, handoff to the appropriate Auth Layer agent.',
  tools: [documentLookupTool],
});

// 1. Main Agent: entry point and routing.
const mainAgent = new RealtimeAgent({
  name: 'Main Agent',
  instructions:
    'You are the entry point for all customer queries. Default to the no-auth QA flow. If authentication is needed and validated, escalate to the Auth Layer by handing off to either the Flight Status Checker or Rebooking Agent. Do not answer policy questions from your own knowledge; rely on subordinate agents and tools.',
  tools: [
    checkFlightsTool,
  ],
  handoffs: [qaAgent],
});

// Cross-handoffs so agents can return or escalate.
qaAgent.handoffs = [mainAgent];

export default function Home() {
  const session = useRef<RealtimeSession<any> | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [outputGuardrailResult, setOutputGuardrailResult] =
    useState<OutputGuardrailTripwireTriggered<any> | null>(null);

  const [events, setEvents] = useState<TransportEvent[]>([]);
  const [history, setHistory] = useState<RealtimeItem[]>([]);
  const [mcpTools, setMcpTools] = useState<string[]>([]);
  const [credOpen, setCredOpen] = useState(false);
  const [credUsername, setCredUsername] = useState('');
  const [credPassword, setCredPassword] = useState('');
  const [pendingApproval, setPendingApproval] = useState<any | null>(null);

  useEffect(() => {
    session.current = new RealtimeSession(mainAgent, {
      model: 'gpt-realtime-mini',
      outputGuardrailSettings: {
        debounceTextLength: 200,
      },
      config: {
        audio: {
          output: {
            voice: 'cedar',
          },
        },
      },
    });
    session.current.on('transport_event', (event) => {
      setEvents((events) => [...events, event]);
    });
    session.current.on('mcp_tools_changed', (tools) => {
      setMcpTools(tools.map((t) => t.name));
    });
    session.current.on(
      'guardrail_tripped',
      (_context, _agent, guardrailError) => {
        setOutputGuardrailResult(guardrailError);
      },
    );
    session.current.on('history_updated', (history) => {
      setHistory(history);
    });
    session.current.on(
      'tool_approval_requested',
      (_context, _agent, approvalRequest) => {
        setPendingApproval(approvalRequest.approvalItem);
        setCredUsername('');
        setCredPassword('');
        setCredOpen(true);
      },
    );
  }, []);

  async function connect() {
    if (isConnected) {
      await session.current?.close();
      setIsConnected(false);
    } else {
      const token = await getToken();
      try {
        await session.current?.connect({
          apiKey: token,
        });
        setIsConnected(true);
      } catch (error) {
        console.error('Error connecting to session', error);
      }
    }
  }

  async function toggleMute() {
    if (isMuted) {
      await session.current?.mute(false);
      setIsMuted(false);
    } else {
      await session.current?.mute(true);
      setIsMuted(true);
    }
  }

  function handleCredCancel() {
    const approval = pendingApproval;
    setCredOpen(false);
    setPendingApproval(null);
    if (approval) session.current?.reject(approval);
  }

  function handleCredSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!credUsername || !credPassword) return;
    // Store creds for the tool to read
    credState.username = credUsername;
    credState.password = credPassword;
    const approval = pendingApproval;
    setCredOpen(false);
    setPendingApproval(null);
    setCredUsername('');
    setCredPassword('');
    if (approval) session.current?.approve(approval);
  }

  return (
    <div className="relative">
      {credOpen && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/50" />
          <div className="fixed top-0 left-0 right-0 flex justify-center p-4">
            <form
              onSubmit={handleCredSubmit}
              className="w-full max-w-sm rounded-lg bg-white p-4 shadow-xl"
            >
              <div className="mb-2 text-sm font-semibold">Authentication Required</div>
              <div className="mb-3 text-xs text-gray-600">
                Enter username and password to continue.
              </div>
              <input
                className="mb-2 w-full rounded border border-gray-300 p-2 text-sm focus:border-gray-500 focus:outline-none"
                placeholder="Username"
                value={credUsername}
                onChange={(e) => setCredUsername(e.target.value)}
              />
              <input
                type="password"
                className="mb-3 w-full rounded border border-gray-300 p-2 text-sm focus:border-gray-500 focus:outline-none"
                placeholder="Password"
                value={credPassword}
                onChange={(e) => setCredPassword(e.target.value)}
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  className="rounded bg-gray-100 px-3 py-1.5 text-sm hover:bg-gray-200"
                  onClick={handleCredCancel}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded bg-black px-3 py-1.5 text-sm text-white hover:bg-gray-800 disabled:opacity-50"
                  disabled={!credUsername || !credPassword}
                >
                  Continue
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <App
        isConnected={isConnected}
        isMuted={isMuted}
        toggleMute={toggleMute}
        connect={connect}
        history={history}
        outputGuardrailResult={outputGuardrailResult}
        events={events}
        mcpTools={mcpTools}
      />
      <div className="fixed bottom-4 right-4 z-50">
        <CameraCapture
          disabled={!isConnected}
          onCapture={(dataUrl) => {
            if (!session.current) return;
            session.current.addImage(dataUrl, { triggerResponse: false });
          }}
        />
      </div>
    </div>
  );
}
```

## 重點整理

- 語音 agent 跟文字不同，要多顧延遲、WebRTC session 和 VAD 帶來的變數。
- Handoff 架構讓主 agent 只負責分類意圖，實際工作交給專門的 agent，各自單純好維護。
- 每個 specialist agent 就是一個掛了自己 tool 的 `RealtimeAgent`。
- 敏感資料的存取控制，用 tool 的 `needsApproval` 加上 `tool_approval_requested` 事件，在 UI 層做驗證關卡。
- 範例裡的文件查詢是 mock，真實產品會換成 embedding 加 vector database 的檢索。

## 練習

1. 在 QA agent 的 mock 文件查詢裡多加一筆政策資料（例如行李規定），用語音問一個相關問題，確認它能答出來。
2. 修改主 agent 的 instructions，讓它在使用者問題不明確時先追問一句，再決定 handoff 給誰。
3. 新增第三個 specialist agent（例如改簽航班），給它一個同樣設了 `needsApproval` 的 tool，並在 `tool_approval_requested` 的監聽裡，依 tool 名稱顯示不同的驗證提示。
