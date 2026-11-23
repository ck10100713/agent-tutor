---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/voice_solutions/one_way_translation_using_realtime_api.mdx
---
# 用 Realtime API 做多語言單向翻譯

> 原文：[examples/voice_solutions/one_way_translation_using_realtime_api.mdx](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/one_way_translation_using_realtime_api.mdx)

用 Realtime API 建立單向語音翻譯的 cookbook。

## 這篇在做什麼

做一個 speaker app 加 listener app：講者對著瀏覽器說話，音訊被分流到每種語言各一個 Realtime session，翻譯後的音訊再透過 WebSocket server 轉送給聽眾，聽眾選哪種語言就聽哪種。重點是示範「把同一段音訊 fork 出去做多種用途」的架構。

## 學完你會

- 為每種目標語言寫一組 prompt，並各開一個 Realtime session，用 few-shot 讓模型輸出翻譯而不是回答問題。
- 用 `RealtimeClient` 連 Realtime API，並用 `WavRecorder` 在瀏覽器擷取、串流 PCM16 音訊。
- 用 `Socket.IO` server 把翻譯後的音訊鏡像給 listener app，讓聽眾切換語言。

## 開跑前

需要 OpenAI API key，並下載[範例 repo](https://github.com/openai/openai-cookbook/tree/main/examples/voice_solutions/one_way_translation_using_realtime_api)在本機執行，用到 Realtime 模型會產生費用。

Realtime API 最令人興奮的地方之一，是說話的情緒、語調和節奏都會傳給模型做 inference。傳統的 cascaded 語音系統（STT 加 TTS）會多一個中間的轉錄步驟，靠 SSML 或 prompt 去近似語調，本質上會損失保真度，講者的表達方式在翻譯過程中就消失了。Realtime API 可以直接處理原始音訊，所以在 inference 過程中保留這些音訊特徵，降低延遲，回應也帶有語調和抑揚的線索。因此，Realtime API 讓 LLM 驅動的語音翻譯比以往更接近現場口譯員。

這份 cookbook 示範怎麼用 OpenAI 的 [Realtime API](https://platform.openai.com/docs/guides/realtime)，透過 WebSocket 建立多語言單向翻譯的工作流程。它用 [Realtime + WebSockets 整合](https://platform.openai.com/docs/guides/realtime-websocket)實作一個 speaker 應用，再加一個 WebSocket server，把翻譯後的音訊鏡像給 listener 應用。

這個 demo 的真實使用場景是多語言的對話式翻譯：講者對著 speaker app 說話，聽眾透過 listener app 聽到自己選的母語翻譯。想像一個會議室，講者用英文講話，戴耳機的參與者選擇聽 Tagalog 翻譯。因為目前音訊模型是 turn-based，講者必須短暫停頓，讓模型處理並翻譯語音。不過隨著模型變得更快、更有效率，這個延遲會大幅降低，翻譯也會更順暢。


來看看主要的功能和程式碼片段，了解這個 app 怎麼運作。如果想在本機執行，程式碼在[附帶的 repo](https://github.com/openai/openai-cookbook/tree/main/examples/voice_solutions/one_way_translation_using_realtime_api) 裡。

## 架構總覽

這個專案有兩個應用：speaker app 和 listener app。speaker app 從瀏覽器接收音訊，把音訊 fork 出去，為每種語言建立獨立的 Realtime session，並透過 WebSocket 送到 OpenAI Realtime API。翻譯後的音訊串流回來，再經由另一個 WebSocket server 鏡像給 listener app。listener app 會同時收到所有翻譯音訊串流，但只播放選定的語言。這個架構是為 POC 設計的，不適合 production。來看流程吧！

![Architecture](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/translation_images/Realtime_flow_diagram.png?raw=true)

## Step 1：語言與 Prompt 設定


每種語言都需要一個獨立的串流，也就是每種語言各自要有一組 prompt 和一個 Realtime API session。這些 prompt 定義在 `translation_prompts.js`。

Realtime API 由 [GPT-4o Realtime](https://platform.openai.com/docs/models/gpt-4o-realtime-preview) 或 [GPT-4o mini Realtime](https://platform.openai.com/docs/models/gpt-4o-mini-realtime-preview) 驅動，這些模型是 turn-based，專為對話式語音場景訓練。為了確保模型回傳翻譯後的音訊（也就是遇到問題時，我們要的是這個問題的直接翻譯，而不是回答），我們在 prompt 裡用問題的 few-shot 範例來引導模型。如果你的翻譯有特定目的或情境，或有專門詞彙能幫助模型理解翻譯的脈絡，也放進 prompt 裡。如果希望模型用特定口音說話，或以其他方式引導聲音，可以參考我們的 cookbook [Steering Text-to-Speech for more dynamic audio generation](https://cookbook.openai.com/examples/voice_solutions/steering_tts) 裡的技巧。

我們可以動態輸入任何語言的語音。

```js
// Define language codes and import their corresponding instructions from our prompt config file
const languageConfigs = [
  { code: 'fr', instructions: french_instructions },
  { code: 'es', instructions: spanish_instructions },
  { code: 'tl', instructions: tagalog_instructions },
  { code: 'en', instructions: english_instructions },
  { code: 'zh', instructions: mandarin_instructions },
];
```

## Step 2：設定 Speaker App

![SpeakerApp](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/translation_images/SpeakerApp.png?raw=true) 


需要處理連到 Realtime API 的 client instance 的設定和管理，讓應用能處理並串流不同語言的音訊。`clientRefs` 存放一個 `RealtimeClient` instance 的 map，每個 instance 對應一個語言代碼（例如 'fr' 是法文、'es' 是西班牙文），代表一條獨立的 Realtime API 連線。

```js
const clientRefs = useRef(
    languageConfigs.reduce((acc, { code }) => {
      acc[code] = new RealtimeClient({
        apiKey: OPENAI_API_KEY,
        dangerouslyAllowAPIKeyInBrowser: true,
      });
      return acc;
    }, {} as Record<string, RealtimeClient>)
  ).current;

  // Update languageConfigs to include client references
  const updatedLanguageConfigs = languageConfigs.map(config => ({
    ...config,
    clientRef: { current: clientRefs[config.code] }
  }));
  ```

注意：`dangerouslyAllowAPIKeyInBrowser` 設成 true，是因為這個 demo 在瀏覽器裡使用 OpenAI API key。在 production 應該改用透過 OpenAI REST API 產生的 [ephemeral API key](https://platform.openai.com/docs/api-reference/realtime-sessions)。

接著要真的連上 Realtime API，並把音訊資料送到 server。使用者在 speaker 頁面按下「Connect」時，就開始這個流程。
 
`connectConversation` 函式負責協調連線，確保所有必要元件都初始化完成、可以使用。

```js
const connectConversation = useCallback(async () => {
    try {
        setIsLoading(true);
        const wavRecorder = wavRecorderRef.current;
        await wavRecorder.begin();
        await connectAndSetupClients();
        setIsConnected(true);
    } catch (error) {
        console.error('Error connecting to conversation:', error);
    } finally {
        setIsLoading(false);
    }
}, []);
```

 `connectAndSetupClients` 確保我們用對模型和聲音。這個 demo 用的是 gpt-4o-realtime-preview-2024-12-17 和 coral。

```js
   // Function to connect and set up all clients
  const connectAndSetupClients = async () => {
    for (const { clientRef } of updatedLanguageConfigs) {
      const client = clientRef.current;
      await client.realtime.connect({ model: DEFAULT_REALTIME_MODEL });
      await client.updateSession({ voice: DEFAULT_REALTIME_VOICE });
    }
  };
```

## Step 3：音訊串流


用 WebSocket 送音訊，需要管理進出的 PCM16 音訊串流（[更多細節](https://platform.openai.com/docs/guides/realtime-model-capabilities#handling-audio-with-websockets)）。我們用 wavtools 把這些包起來，它是在瀏覽器錄音和串流音訊資料的函式庫。這裡用 `WavRecorder` 在瀏覽器擷取音訊。

這個 demo 支援[手動和語音活動偵測（VAD）](https://platform.openai.com/docs/guides/realtime-model-capabilities#voice-activity-detection-vad)兩種錄音模式，講者可以切換。為了讓音訊擷取比較乾淨，這裡建議用手動模式。

```js
const startRecording = async () => {
    setIsRecording(true);
    const wavRecorder = wavRecorderRef.current;

    await wavRecorder.record((data) => {
      // Send mic PCM to all clients
      updatedLanguageConfigs.forEach(({ clientRef }) => {
        clientRef.current.appendInputAudio(data.mono);
      });
    });
  };
  ```

## Step 4：顯示逐字稿


我們監聽 `response.audio_transcript.done` 事件來更新音訊的逐字稿。這些輸入逐字稿由 Whisper 模型產生，跟 GPT-4o Realtime 對原始音訊做翻譯的 inference 是平行進行的。

每一種可選語言都有一個 Realtime session 同時在跑，所以每種語言都會有逐字稿（不管聽眾端選了哪種語言）。切換「Show Transcripts」按鈕就能顯示它們。

## Step 5：設定 Listener App

聽眾可以從下拉選單選擇翻譯串流，連線後還能動態切換語言。這個 demo 應用用了法文、西班牙文、Tagalog、英文和中文，但 OpenAI 支援 57 種以上的語言。

這個 app 連到一個簡單的 `Socket.IO` server，它扮演音訊資料的 relay。當翻譯後的音訊從 Realtime API 串流回來，我們把這些音訊串流鏡像到 listener 頁面，讓使用者選擇語言並收聽翻譯串流。

關鍵函式是 `connectServer`，它負責連到 server 並設定音訊串流。

```js
  // Function to connect to the server and set up audio streaming
  const connectServer = useCallback(async () => {
    if (socketRef.current) return;
    try {
      const socket = io('http://localhost:3001');
      socketRef.current = socket;
      await wavStreamPlayerRef.current.connect();
      socket.on('connect', () => {
        console.log('Listener connected:', socket.id);
        setIsConnected(true);
      });
      socket.on('disconnect', () => {
        console.log('Listener disconnected');
        setIsConnected(false);
      });
    } catch (error) {
      console.error('Error connecting to server:', error);
    }
  }, []);
```

### 從 POC 到 Production

這是一個 demo，目的是提供靈感。這裡用 WebSocket 是為了方便本機開發。但在 production 環境，建議用 WebRTC（音訊品質和延遲都好得多），並用透過 OpenAI REST API 產生的 [ephemeral API key](https://platform.openai.com/docs/api-reference/realtime-sessions) 連到 Realtime API。

目前的 Realtime 模型是 turn-based，最適合對話式場景，而不是我們真正想要的、單向串流用途所需的聯合國式不間斷即時口譯。在這個 demo 裡，只要模型回傳翻譯音訊，我們就能立刻從 speaker app 擷取更多音訊（也就是在 listener app 播放翻譯音訊的同時繼續擷取輸入音訊），但一次能擷取的音訊長度有上限，所以講者需要停頓，讓翻譯跟上。

## 結論

總結來說，這個 POC 展示了 Realtime API 的單向翻譯用法，但「把音訊 fork 出去做多種用途」的想法不限於翻譯。其他工作流程還包括同步做情緒分析、即時 guardrail 或產生字幕。

## 重點整理

- Realtime API 直接處理原始音訊，所以語氣、情緒和節奏能保留下來，不像 STT 加 TTS 的 cascaded 系統會在轉錄時損失。
- 每種目標語言要有獨立的 prompt 和獨立的 Realtime session，用 few-shot 範例引導模型「翻譯而不是回答」。
- 音訊分流加 relay 的架構（speaker 端 fork、server 鏡像、listener 端選語言）可以擴充到情緒分析、guardrail、字幕等用途。
- Realtime 模型目前是 turn-based，講者需要停頓；production 建議改用 WebRTC 加 ephemeral API key。

## 練習

1. 在 `translation_prompts.js` 加一種新語言的 prompt，並在 listener 的下拉選單加上對應的選項。
2. 把 few-shot 範例裡的問題換成你自己的情境詞彙，觀察模型是不是更穩定地輸出翻譯。
3. 在 `connectAndSetupClients` 裡把聲音從 `coral` 換成別的 voice，再試著在 prompt 裡加口音指示，比較聽感。
