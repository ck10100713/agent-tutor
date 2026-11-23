---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/How_to_build_an_agent_with_the_node_sdk.mdx
---

# 用 OpenAI Node.js SDK 打造 agent

> 原文：[examples/How_to_build_an_agent_with_the_node_sdk.mdx](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_build_an_agent_with_the_node_sdk.mdx)



## 這篇在做什麼
用 OpenAI 的 function calling 加上最新版 Node.js SDK，做一個在瀏覽器跑的小 agent。它有取得位置和查天氣兩個 function，會自己判斷要呼叫哪個，最後根據結果推薦當地活動。

## 學完你會
- 用 `tools` schema 向模型描述 function，並從回應判斷它要你呼叫哪一個
- 把模型回傳的 function 名稱對應成真正的函式呼叫，並把結果用 `messages` 送回去
- 寫一個有上限的 for-loop，讓 agent 在 `tool_calls` 和 `stop` 之間來回直到有答案

## 開跑前
需要 OpenAI API key（存在環境變數）。程式在瀏覽器跑，用編輯器加 VS Code Live Server 就能在本機跟著做，也可以用 Scrimba 的線上 playground。

OpenAI 的 function 讓你的 app 可以根據使用者輸入採取行動。也就是說，它可以代替使用者搜尋網路、寄 email、訂票，比一般聊天機器人強大。

這份教學會用 OpenAI functions 加上最新版 Node.js SDK 做一個 app。這個 app 在瀏覽器執行，所以你只需要一個編輯器，加上像 VS Code Live Server 這樣的工具，就能在本機跟著做。也可以直接在瀏覽器裡寫程式，用 [Scrimba 的這個 code playground](https://scrimba.com/scrim/c6r3LkU9)。

## 你會做出什麼

我們的 app 是一個簡單的 agent，幫你找所在地區的活動。
它有兩個 function 可以用：`getLocation()` 和 `getCurrentWeather()`，
所以它能查出你在哪裡，以及現在天氣如何。

這裡要先搞清楚一件事：
OpenAI 不會幫你執行任何程式碼。它只會告訴你的 app 在某個情境下該用哪些
function，然後由你的 app 自己去呼叫。

Agent 知道你的位置和天氣之後，就會用 GPT 內部的知識，
推薦適合的當地活動。

## 匯入 SDK 並向 OpenAI 驗證

先在 JavaScript 檔案最上面匯入 OpenAI SDK，並用 API key 驗證，key 存在環境變數裡。

```js
import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  dangerouslyAllowBrowser: true,
});
```

因為我們在 Scrimba 的瀏覽器環境執行程式，所以還需要設定 `dangerouslyAllowBrowser: true`，表示我們了解 client 端 API 請求的風險。注意，正式的 app 要把這些請求移到 Node server 上。

## 建立兩個 function

接著建立這兩個 function。第一個 `getLocation`，
用 [IP API](https://ipapi.co/) 取得使用者的位置。

```js
async function getLocation() {
  const response = await fetch("https://ipapi.co/json/");
  const locationData = await response.json();
  return locationData;
}
```

IP API 會回傳一堆關於你位置的資料，包括經緯度，
這些會當成第二個 function `getCurrentWeather` 的參數。它用 [Open Meteo
API](https://open-meteo.com/) 取得目前的天氣資料，像這樣：

```js
async function getCurrentWeather(latitude, longitude) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&hourly=apparent_temperature`;
  const response = await fetch(url);
  const weatherData = await response.json();
  return weatherData;
}
```

## 向 OpenAI 描述我們的 function

為了讓 OpenAI 理解這些 function 的用途，我們要用特定的 schema 來描述它們。我們會建立一個叫 `tools` 的陣列，
每個 function 一個物件。每個物件有兩個 key：`type` 和 `function`，而 `function` 這個 key 底下有
三個子 key：`name`、`description` 和 `parameters`。

```js
const tools = [
  {
    type: "function",
    function: {
      name: "getCurrentWeather",
      description: "Get the current weather in a given location",
      parameters: {
        type: "object",
        properties: {
          latitude: {
            type: "string",
          },
          longitude: {
            type: "string",
          },
        },
        required: ["longitude", "latitude"],
      },
    }
  },
  {
    type: "function",
    function: {
      name: "getLocation",
      description: "Get the user's location based on their IP address",
      parameters: {
        type: "object",
        properties: {},
      },
    }
  },
];
```

## 設定 messages 陣列

我們還要定義一個 `messages` 陣列，用來記錄 app 和 OpenAI 之間來回的所有訊息。

陣列的第一個物件，`role` 屬性一定要是 `"system"`，這是告訴 OpenAI 我們希望它怎麼表現。

```js
const messages = [
  {
    role: "system",
    content:
      "You are a helpful assistant. Only use the functions you have been provided with.",
  },
];
```

## 建立 agent function

現在可以開始寫 app 的邏輯了，它放在
`agent` function 裡。這是個非同步函式，接收一個參數：
`userInput`。

先把 `userInput` push 到 messages 陣列。這次 `role` 設成 `"user"`，讓 OpenAI 知道這是使用者的輸入。

```js
async function agent(userInput) {
  messages.push({
    role: "user",
    content: userInput,
  });
  const response = await openai.chat.completions.create({
    model: "gpt-4",
    messages: messages,
    tools: tools,
  });
  console.log(response);
}
```

接著透過 Node SDK 的
`chat.completions.create()` 方法，對 Chat completions endpoint 送出請求。這個方法接收一個設定物件，我們要在裡面指定三個
屬性：

- `model`：決定要用哪個 AI 模型（這裡用
  GPT-4）。
- `messages`：到目前為止使用者和
  AI 之間的完整訊息歷史。
- `tools`：模型可以呼叫的 tool 清單。目前只
  支援 function 當 tool，這裡用的就是前面建立的 `tools` 陣列。

## 用簡單輸入執行 app

來試試用一個需要 function call 才能適當回覆的輸入執行 `agent`。

```js
agent("Where am I located right now?");
```

執行上面的程式碼後，OpenAI 的回應會像這樣印在 console：

```js
{
    id: "chatcmpl-84ojoEJtyGnR6jRHK2Dl4zTtwsa7O",
    object: "chat.completion",
    created: 1696159040,
    model: "gpt-4-0613",
    choices: [{
        index: 0,
        message: {
            role: "assistant",
            content: null,
            tool_calls: [
              id: "call_CBwbo9qoXUn1kTR5pPuv6vR1",
              type: "function",
              function: {
                name: "getLocation",
                arguments: "{}"
              }
            ]
        },
        logprobs: null,
        finish_reason: "tool_calls" // OpenAI wants us to call a function
    }],
    usage: {
        prompt_tokens: 134,
        completion_tokens: 6,
        total_tokens: 140
    }
     system_fingerprint: null
}
```

這個回應告訴我們要呼叫其中一個 function，因為它包含這個 key：`finish_reason: "tool_calls"`。

Function 的名稱可以在
`response.choices[0].message.tool_calls[0].function.name` 這個 key 找到，值是
`"getLocation"`。

## 把 OpenAI 的回應變成 function call

現在我們拿到字串形式的 function 名稱，需要把它轉成真正的 function call。為此，我們把
兩個 function 收集到一個叫 `availableTools` 的物件裡：

```js
const availableTools = {
  getCurrentWeather,
  getLocation,
};
```

這樣很方便，因為我們可以用中括號語法，搭配 OpenAI 回傳的字串來取用 `getLocation` function，
像這樣：
`availableTools["getLocation"]`。

```js
const { finish_reason, message } = response.choices[0];

if (finish_reason === "tool_calls" && message.tool_calls) {
  const functionName = message.tool_calls[0].function.name;
  const functionToCall = availableTools[functionName];
  const functionArgs = JSON.parse(message.tool_calls[0].function.arguments);
  const functionArgsArr = Object.values(functionArgs);
  const functionResponse = await functionToCall.apply(null, functionArgsArr);
  console.log(functionResponse);
}
```

我們也會取得 OpenAI 要我們傳進 function 的任何參數：`message.tool_calls[0].function.arguments`。
不過第一個 function call 用不到任何參數。

如果用同樣的輸入（`"Where am I located right now?"`）再執行一次，會看到 `functionResponse`
是一個物件，裡面是使用者目前所在位置的資料。以我的情況來說，是挪威奧斯陸。

```js
{ip: "193.212.60.170", network: "193.212.60.0/23", version: "IPv4", city: "Oslo", region: "Oslo County", region_code: "03", country: "NO", country_name: "Norway", country_code: "NO", country_code_iso3: "NOR", country_capital: "Oslo", country_tld: ".no", continent_code: "EU", in_eu: false, postal: "0026", latitude: 59.955, longitude: 10.859, timezone: "Europe/Oslo", utc_offset: "+0200", country_calling_code: "+47", currency: "NOK", currency_name: "Krone", languages: "no,nb,nn,se,fi", country_area: 324220, country_population: 5314336, asn: "AS2119", org: "Telenor Norge AS"}
```

我們會把這份資料加到 `messages` 陣列的新項目裡，同時
指定我們呼叫的 function 名稱。

```js
messages.push({
  role: "function",
  name: functionName,
  content: `The result of the last function was this: ${JSON.stringify(
    functionResponse
  )}
  `,
});
```

注意 `role` 設成 `"function"`。這告訴 OpenAI，
`content` 參數裡是 function call 的結果，
不是使用者的輸入。

這時候，我們需要用更新後的 `messages` 陣列對 OpenAI 送出新的請求。不過我們不想把新的 function
call 寫死，因為 agent 可能需要在自己和
GPT 之間來回好幾次，才能找到給使用者的最終答案。

這可以用好幾種方式解決，例如遞迴、while 迴圈或 for 迴圈。為了簡單，我們用傳統的 for 迴圈。

## 建立迴圈

在 `agent` function 的最上面，我們建立一個迴圈，讓整個流程最多執行五次。

如果 GPT 回傳 `finish_reason: "tool_calls"`，我們就把 function call 的結果
push 到 `messages` 陣列，然後跳到
迴圈的下一輪，觸發新的請求。

如果回傳 `finish_reason: "stop"`，表示 GPT 已經找到合適的
答案，我們就回傳結果並結束迴圈。

```js
for (let i = 0; i < 5; i++) {
  const response = await openai.chat.completions.create({
    model: "gpt-4",
    messages: messages,
    tools: tools,
  });
  const { finish_reason, message } = response.choices[0];

  if (finish_reason === "tool_calls" && message.tool_calls) {
    const functionName = message.tool_calls[0].function.name;
    const functionToCall = availableTools[functionName];
    const functionArgs = JSON.parse(message.tool_calls[0].function.arguments);
    const functionArgsArr = Object.values(functionArgs);
    const functionResponse = await functionToCall.apply(null, functionArgsArr);

    messages.push({
      role: "function",
      name: functionName,
      content: `
          The result of the last function was this: ${JSON.stringify(
            functionResponse
          )}
          `,
    });
  } else if (finish_reason === "stop") {
    messages.push(message);
    return message.content;
  }
}
return "The maximum number of iterations has been met without a suitable answer. Please try again with a more specific input.";
```

如果五輪之內都沒看到 `finish_reason: "stop"`，
就回傳一則訊息，說我們找不到合適的答案。

## 執行最終版 app

現在可以試試我們的 app 了！我會請 agent
根據我的位置和目前天氣推薦一些活動。

```js
const response = await agent(
  "Please suggest some activities based on my location and the current weather."
);
console.log(response);
```

以下是 console 裡看到的結果（已排版方便閱讀）：

```js
Based on your current location in Oslo, Norway and the weather (15°C and snowy),
here are some activity suggestions:

1. A visit to the Oslo Winter Park for skiing or snowboarding.
2. Enjoy a cosy day at a local café or restaurant.
3. Visit one of Oslo's many museums. The Fram Museum or Viking Ship Museum offer interesting insights into Norway’s seafaring history.
4. Take a stroll in the snowy streets and enjoy the beautiful winter landscape.
5. Enjoy a nice book by the fireplace in a local library.
6. Take a fjord sightseeing cruise to enjoy the snowy landscapes.

Always remember to bundle up and stay warm. Enjoy your day!
```

如果我們看一下內部，在迴圈每一輪都印出 `response.choices[0].message`，會看到 GPT 指示我們兩個 function 都要用，才給出答案。

首先，它要我們呼叫 `getLocation` function。接著要我們呼叫 `getCurrentWeather` function，並傳入
`"longitude": "10.859", "latitude": "59.955"` 當參數。這些資料是它從我們第一次 function call 的結果拿到的。

```js
{"role":"assistant","content":null,"tool_calls":[{"id":"call_Cn1KH8mtHQ2AMbyNwNJTweEP","type":"function","function":{"name":"getLocation","arguments":"{}"}}]}
{"role":"assistant","content":null,"tool_calls":[{"id":"call_uc1oozJfGTvYEfIzzcsfXfOl","type":"function","function":{"name":"getCurrentWeather","arguments":"{\n\"latitude\": \"10.859\",\n\"longitude\": \"59.955\"\n}"}}]}
```

你現在已經用 OpenAI functions 和 Node.js SDK 做出一個 AI agent 了！如果想要多一點挑戰，可以試著強化這個 app，例如加一個 function，取得使用者所在地最新的活動資訊。

寫得開心！

<details>
<summary>完整程式碼</summary>

```js
import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  dangerouslyAllowBrowser: true,
});

async function getLocation() {
  const response = await fetch("https://ipapi.co/json/");
  const locationData = await response.json();
  return locationData;
}

async function getCurrentWeather(latitude, longitude) {
  const url = `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&hourly=apparent_temperature`;
  const response = await fetch(url);
  const weatherData = await response.json();
  return weatherData;
}

const tools = [
  {
    type: "function",
    function: {
      name: "getCurrentWeather",
      description: "Get the current weather in a given location",
      parameters: {
        type: "object",
        properties: {
          latitude: {
            type: "string",
          },
          longitude: {
            type: "string",
          },
        },
        required: ["longitude", "latitude"],
      },
    }
  },
  {
    type: "function",
    function: {
      name: "getLocation",
      description: "Get the user's location based on their IP address",
      parameters: {
        type: "object",
        properties: {},
      },
    }
  },
];

const availableTools = {
  getCurrentWeather,
  getLocation,
};

const messages = [
  {
    role: "system",
    content: `You are a helpful assistant. Only use the functions you have been provided with.`,
  },
];

async function agent(userInput) {
  messages.push({
    role: "user",
    content: userInput,
  });

  for (let i = 0; i < 5; i++) {
    const response = await openai.chat.completions.create({
      model: "gpt-4",
      messages: messages,
      tools: tools,
    });

    const { finish_reason, message } = response.choices[0];

    if (finish_reason === "tool_calls" && message.tool_calls) {
      const functionName = message.tool_calls[0].function.name;
      const functionToCall = availableTools[functionName];
      const functionArgs = JSON.parse(message.tool_calls[0].function.arguments);
      const functionArgsArr = Object.values(functionArgs);
      const functionResponse = await functionToCall.apply(
        null,
        functionArgsArr
      );

      messages.push({
        role: "function",
        name: functionName,
        content: `
                The result of the last function was this: ${JSON.stringify(
                  functionResponse
                )}
                `,
      });
    } else if (finish_reason === "stop") {
      messages.push(message);
      return message.content;
    }
  }
  return "The maximum number of iterations has been met without a suitable answer. Please try again with a more specific input.";
}

const response = await agent(
  "Please suggest some activities based on my location and the weather."
);

console.log("response:", response);
```

</details>

## 重點整理
- OpenAI 不會幫你執行程式，它只告訴你該呼叫哪個 function，執行是你 app 的工作
- 用 `tools` 陣列描述 function 的 name、description、parameters，模型才知道什麼時候該用
- 把 function 放進 `availableTools` 物件，就能用模型回傳的字串名稱查到函式並呼叫
- 結果要用 `messages` 送回去，agent 才能接著推理，所以需要迴圈
- 迴圈以 `finish_reason` 判斷：`tool_calls` 繼續，`stop` 結束，並設上限避免無限跑

## 練習
1. 把迴圈上限從 5 改成 2，看看 agent 還能不能完成「根據位置和天氣推薦活動」的請求，以及失敗時的訊息。
2. 在 `tools` 和 `availableTools` 裡新增第三個 function（例如回傳目前時間），並修改輸入，讓 agent 把時間也納入推薦。
3. 把 `getCurrentWeather` 改成同時回傳濕度，並調整 system 訊息，要求 agent 在推薦時一定要提到濕度。
