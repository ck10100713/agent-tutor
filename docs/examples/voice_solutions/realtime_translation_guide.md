---
translated: true
source: examples/voice_solutions/realtime_translation_guide.mdx
---
# 用 gpt-realtime-translate 做即時翻譯應用

> 原文：[examples/voice_solutions/realtime_translation_guide.mdx](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/realtime_translation_guide.mdx)

這份 cookbook 教你用 Realtime Translation 做瀏覽器、電話和視訊通話的翻譯體驗。

## 這篇在做什麼

用 `gpt-realtime-translate` 這個即時語音對語音翻譯模型，在三種既有的音訊路徑上加入翻譯：瀏覽器分頁、Twilio 電話、LiveKit 視訊會議。最後還會講 production 的注意事項、模型限制和 eval 做法。

## 學完你會

- 用 WebRTC 加短效 client secret，做出把瀏覽器分頁音訊即時翻譯並顯示字幕的 app
- 用 Twilio Media Streams 加 WebSocket，把電話音訊橋接到翻譯 session，再把譯文語音送回對方
- 依「來源講者、目標語言」規劃 session 數量，在 LiveKit 視訊會議裡替每位遠端講者加翻譯 sidecar

## 開跑前

- OpenAI API key（要放在 server 端，瀏覽器只用短效 client secret）
- Node.js，跑瀏覽器和 Twilio demo 用
- Twilio 電話號碼，跑電話 demo 才需要
- LiveKit project 或自架的 LiveKit server，跑視訊 demo 才需要

`gpt-realtime-translate` 是即時語音對語音翻譯模型，適合做廣播、直播、通話和視訊對話的多語言音訊體驗。它接收語音輸入、自動偵測來源語言，回傳翻譯後的語音加文字逐字稿。開發者只要指定目標輸出語言。

這個模型有兩個新特色：

1. 跟通用的語音模型不同，`gpt-realtime-translate` 是**針對口譯優化**的。它用數千小時的專業口譯音訊訓練，所以只做翻譯，而且會等到有足夠的上下文才開口。對句子結構不同的語言來說，這點特別重要。
2. 它可以**一邊處理輸入音訊，一邊同時串流翻譯後的音訊回來**，所以連續說話時能做到真正的低延遲。

我們做 `gpt-realtime-translate`，是因為即時口譯的需求跟現有的 AI 語音互動不一樣。通用模型可以用 prompt 叫它翻譯，但它還是可能去回答問題或執行指令，而不是把那些話翻出來。它們也依賴輪流對話的方式，講者得停下來等模型生成翻譯語音，這對流暢的口譯行不通。

這些一直是自然即時口譯要做到高準確度、低延遲的主要障礙，也是 `gpt-realtime-translate` 要解決的事。

## 怎麼用 Realtime Translation 來建

這個模型的特別之處，在於它主要是**讓人類能說多種語言，而不是做 AI 語音 agent**。如果你要做語音 agent，請用新的 `gpt-realtime-2` 模型。

`gpt-realtime-translate` 主要有兩種用法。第一種是**廣播式翻譯**：直播、webinar、演講、財報電話會議、研討會 keynote，還有其他需要把單一主要來源翻成另一種語言給很多聽眾聽的情況。第二種是**對話式翻譯**，兩位以上的參與者跨語言互相交談：客服中心、視訊聊天，或其他電話類的 workflow。

這份 cookbook 就聚焦在這些模式：先講基礎，接著做一個能翻譯任何瀏覽器分頁音訊的**單向即時翻譯** web app，用 Twilio 把翻譯加進**電話通話**，再用 LiveKit 做一個**多語言群組視訊聊天**室。最後講 production 的最佳實務、模型限制和 evals。

## 你會做出什麼

你會做出三種在既有音訊路徑上加入即時翻譯的方式：

1. **瀏覽器分頁翻譯：**用 `getDisplayMedia()` 擷取分頁音訊，透過 WebRTC 送到 Realtime Translation，在瀏覽器播放譯文語音和字幕。
2. **電話通話翻譯：**用 Twilio Media Streams 透過 WebSocket 接收電話音訊，橋接到 Realtime Translation，再把譯文音訊送回給另一位通話者。
3. **視訊通話翻譯：**訂閱 LiveKit 遠端的麥克風 track，替聽者翻譯每位遠端講者，並在本機呈現譯文音訊和字幕。

完整的 demo app 放在對應的資料夾：

- [Browser tab translation](https://github.com/openai/openai-cookbook/tree/main/examples/voice_solutions/realtime_translation_guide/browser-translation-demo)
- [Twilio phone translation](https://github.com/openai/openai-cookbook/tree/main/examples/voice_solutions/realtime_translation_guide/twilio-translation-demo)
- [LiveKit video translation](https://github.com/openai/openai-cookbook/tree/main/examples/voice_solutions/realtime_translation_guide/livekit-translation-demo)

## 前置需求

你需要：

- 一組 OpenAI API key。
- Node.js，跑瀏覽器和 Twilio demo 用。
- 想跑電話 demo 的話，需要一個 Twilio 電話號碼。
- 想跑視訊會議 demo 的話，需要一個 LiveKit project 或自架的 LiveKit server。

OpenAI API key 要放在 server 上。瀏覽器的範例應該用短效的 client secret，不要把 API key 暴露給 client 端程式碼。

## API 與 Session 基礎

WebRTC 和 WebSocket session 的設定、client 與 server 事件、設定選項的完整說明，見 [Live Translation docs](https://developers.openai.com/api/docs/guides/realtime-translation)。

### 主要差異

Realtime Translation 的 session 是圍繞目標輸出語言來設定的。用 `session.audio.output.language` 設定目標語言。目前模型支援 70 種以上的輸入語言和 13 種輸出語言。這個模型目前不支援自訂 prompt 或選擇聲音的參數。

如果你想在譯文語音之外同時拿到來源語言的逐字稿，用 `gpt-realtime-whisper` 設定 input transcription。

Realtime Translation 用的是**動態聲音適應**。它不讓你挑固定的輸出聲音，譯文語音會跟著來源講者大致的語氣、音高和說話風格走。在多位講者的 session 裡，有新的講者音訊進來時，譯文的聲音也會跟著變。

### Session 生命週期

Session 的生命週期也跟一般的 Realtime 語音 session 不同：

- **專用 endpoint：**連到 `/v1/realtime/translations`。
- **持續的音訊輸入**：用 `session.input_audio_buffer.append` 串流 24 kHz PCM16 音訊，詞組之間的靜音也要送。
- **持續的翻譯輸出**：模型以 200 ms 的 PCM16 chunk 送出譯文音訊，外加目標語言的逐字稿 delta。
- **沒有 turn 生命週期**：翻譯是從進來的音訊串流本身開始。沒有 `response.create`、assistant turn、tool call，也沒有對話狀態要管。

### 通訊協定

瀏覽器 app 用 WebRTC。瀏覽器把麥克風、分頁或遠端參與者的音訊當成 media track 送出去，並把譯文語音當成遠端 audio track 收回來。用 `oai-events` data channel 處理 session 更新、逐字稿 delta 和錯誤。實作範例見 Browser Tab Translation 和 LiveKit 兩節。

後端的媒體 pipeline 用 WebSocket。如果你的 server 已經拿到原始音訊，例如 Twilio Media Streams、SIP、廣播 ingest 或 media worker，這就是適合的選擇。用 `session.input_audio_buffer.append` 送 base64 的 24 kHz PCM16 音訊，講話之間的靜音也要送。範例見 Phone Calls with Twilio 一節。

## 瀏覽器分頁翻譯

先從一個小的瀏覽器 app 開始，做單向即時翻譯。這個 app 擷取瀏覽器分頁的音訊，透過 WebRTC 開一個 Realtime Translation session，並在模型輸出時播放譯文語音加字幕。

這個模式適合原本的體驗就在瀏覽器裡發生的情況：公開會議、直播、研討會演講、線上課程，或沒有內建即時配音的影片。你不用重做播放器，也不用另外發布各語言的串流，app 只要放在頁面旁邊，就能即時給聽眾譯文語音和字幕。

![Browser tab translation architecture](https://github.com/openai/openai-cookbook/blob/main/images/realtime_translation_guide/browser-tab-translation.png?raw=true)

### 運作方式

1. 你的 server 建立一個短效的 translation client secret。
2. 瀏覽器用 `getDisplayMedia()` 擷取分頁音訊。
3. 瀏覽器建立 `RTCPeerConnection`，加入擷取到的 audio track，並開一個 `oai-events` data channel。
4. 瀏覽器帶著 client secret，把 SDP offer 送到 Realtime Translation 的 call endpoint。
5. 模型把譯文音訊從遠端 WebRTC audio track 送回來，並在 data channel 上送逐字稿 delta。

### 建立 translation client secret

在你的 server 上建立 client secret，這樣標準的 OpenAI API key 就不會到瀏覽器那邊。模型和輸出語言都寫在 client-secret 的請求裡。

```ts
const TRANSLATION_CLIENT_SECRET_URL =
  "https://api.openai.com/v1/realtime/translations/client_secrets";

app.post("/session", async (req, res) => {
  const language = req.body.targetLanguage ?? "es";

  const response = await fetch(TRANSLATION_CLIENT_SECRET_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session: {
        model: "gpt-realtime-translate",
        audio: {
          input: {
            transcription: { model: "gpt-realtime-whisper" },
            noise_reduction: { type: "near_field" },
          },
          output: { language },
        },
      },
    }),
  });

  res.status(response.status).json(await response.json());
});
```

完整的瀏覽器 demo 會在送 OpenAI 請求之前先驗證目標語言代碼，並且只把短效的 client secret 回傳給瀏覽器。

### 擷取分頁音訊

用 `getDisplayMedia()` 讓使用者明確選擇來源分頁。瀏覽器支援時，要加上 `suppressLocalAudioPlayback`，這樣聽者就不會同時聽到原音和譯音。

```ts
async function captureTabAudio() {
  const audio = {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
  };

  if (navigator.mediaDevices.getSupportedConstraints?.().suppressLocalAudioPlayback) {
    audio.suppressLocalAudioPlayback = true;
  }

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio,
  });

  if (!stream.getAudioTracks().length) {
    stream.getTracks().forEach((track) => track.stop());
    throw new Error("Choose a browser tab and enable tab audio.");
  }

  return stream;
}
```

### 開啟 WebRTC 翻譯 session

用短效 client secret，把瀏覽器的 SDP offer 送到 Realtime Translation 的 call endpoint。音訊輸出會以遠端 track 的形式到達。翻譯和輸入逐字稿的 delta 則在 data channel 上到達。

```ts
const sessionResponse = await fetch("/session", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ targetLanguage }),
});

const session = await sessionResponse.json();

const pc = new RTCPeerConnection();
const events = pc.createDataChannel("oai-events");

for (const track of sourceStream.getAudioTracks()) {
  pc.addTrack(track, sourceStream);
}

pc.ontrack = ({ streams }) => {
  translatedAudio.srcObject = streams[0];
};

events.onmessage = ({ data }) => {
  const event = JSON.parse(data);

  if (event.type === "session.output_transcript.delta") {
    translatedSubtitles.textContent += event.delta;
  }

  if (event.type === "session.input_transcript.delta") {
    sourceTranscript.textContent += event.delta;
  }
};

const offer = await pc.createOffer();
await pc.setLocalDescription(offer);

const sdpResponse = await fetch(
  "https://api.openai.com/v1/realtime/translations/calls",
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.client_secret}`,
      "Content-Type": "application/sdp",
    },
    body: offer.sdp,
  }
);

await pc.setRemoteDescription({
  type: "answer",
  sdp: await sdpResponse.text(),
});
```

跑完整的 demo：

```bash
cd examples/voice_solutions/realtime_translation_guide/browser-translation-demo
npm install
npm run dev
```

接著打開本機的 URL，選一個有聲音的分頁，挑目標語言，開始翻譯。

## 用 Twilio 打電話

接下來把 `gpt-realtime-translate` 放進 Twilio 的通話路徑。對話式翻譯在每位參與者都有獨立音訊串流時效果最好。Twilio Media Streams 給你的後端一條伺服器端的 WebSocket 來收電話音訊，格式轉換的邊界由你的 server 處理：接收通話者音訊、轉成 Realtime Translation 要的格式，再把譯文音訊轉回 Twilio 的 media 訊息。

![Twilio phone translation architecture](https://github.com/openai/openai-cookbook/blob/main/images/realtime_translation_guide/twilio-phone-translation.png?raw=true)

### 運作方式

1. 通話者加入，並說出他偏好的輸出語言。
2. Twilio 把該通話者的音訊串流到你的後端。
3. 你的後端把 Twilio 音訊轉成 Realtime Translation 預期的音訊格式。
4. 每個翻譯方向，你的後端都用聽者的目標語言開一個 Realtime Translation session。
5. 譯文音訊從 OpenAI 回來時，你的後端把它轉回 Twilio 的 media 訊息。
6. Twilio 把譯文音訊播放給另一位參與者。

兩個人的通話通常需要兩個翻譯 session：A 到 B 和 B 到 A。人數更多的通話，則依「誰要用哪種語言聽哪位來源講者」來建立翻譯 session，而不是把所有參與者混成一條共用的串流。

> **Production 提醒：**`gpt-realtime-translate` 對已經是聽者所選輸出語言的音訊，可能不會翻譯。這個 demo 沒有把 Twilio 的原始音訊直接轉給另一位參與者，所以同語言的發言可能變成一片靜音。Production 的電話橋接應該加上原音直通或混音。這個 demo 是一對一配對通話者，多出來的通話者要等另一位來電，再組成另一對。

### 設定 Twilio webhook

為你的 server 建一個公開的 endpoint，然後把 Twilio 電話號碼的 [Voice webhook](https://www.twilio.com/docs/usage/webhooks/voice-webhooks) 設成把來電導到你的應用程式。本機開發時，用 tunnel 把 server 暴露出去，或部署到 Twilio 能透過 443 port 連到的地方。同一個 host 必須同時提供 HTTP webhook 路由和 WebSocket Media Stream 路由。

### 詢問通話者的目標語言

通話者撥入時，回傳 [TwiML](https://www.twilio.com/docs/voice/twiml)，問他想要翻譯成哪種語言。

```xml
<Response>
  <Gather input="speech" timeout="10" speechTimeout="auto" action="/choose-language" method="POST">
    <Say>What language do you want to hear?</Say>
  </Gather>
  <Redirect method="POST">/choose-language</Redirect>
</Response>
```

### 啟動 Twilio Media Stream

通話者選好支援的語言之後，回傳一個雙向的 Media Stream。把選到的語言當成自訂參數傳進去，讓 WebSocket handler 能用通話者偏好的輸出語言註冊他。

```xml
<Response>
  <Say>You chose Spanish. Wait for the other caller, then begin speaking.</Say>
  <Connect>
    <Stream url="wss://YOUR_PUBLIC_HOST/media-stream">
      <Parameter name="callSid" value="CALL_SID" />
      <Parameter name="language" value="es" />
      <Parameter name="languageLabel" value="Spanish" />
    </Stream>
  </Connect>
</Response>
```

### 開啟伺服器端的翻譯 session

因為這個整合跑在你的後端，所以不需要瀏覽器的 client secret。直接從 server 用你的 OpenAI API key 開 Translation WebSocket，並在 URL 裡指定模型。
```ts
import WebSocket from "ws";

function openTranslationSession({ targetLanguage }) {
  const ws = new WebSocket(
    "wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate",
    {
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
      },
    }
  );

  ws.on("open", () => {
    ws.send(JSON.stringify({
      type: "session.update",
      session: {
        audio: {
          input: {
            transcription: { model: "gpt-realtime-whisper" },
            noise_reduction: { type: "near_field" },
          },
          output: { language: targetLanguage },
        },
      },
    }));
  });

  return ws;
}
```

### 把 Twilio 音訊橋接到 Realtime Translation

Twilio 送來的是 8 kHz 的 base64 `audio/x-mulaw`。Realtime Translation 預期的是 24 kHz、little-endian 的 base64 PCM16，所以橋接程式要解碼 u-law、重新取樣到 24 kHz，再 append 到音訊 buffer。要持續送音訊，包括靜音，因為翻譯 session 不是輪流制，也不會等 `response.create`。

```ts
function sendTwilioAudioToTranslation(realtimeWs, twilioMessage) {
  if (twilioMessage.event !== "media") return;

  const realtimeAudio = twilioMediaToRealtimeAudio(
    twilioMessage.media.payload
  );

  realtimeWs.send(JSON.stringify({
    type: "session.input_audio_buffer.append",
    audio: realtimeAudio,
  }));
}
```

### 把譯文音訊橋接回 Twilio

Realtime Translation 用 `session.output_audio.delta` 送出 base64 的 24 kHz PCM16 譯文音訊。送給 Twilio 之前，要先轉回 8 kHz u-law，再包成 Twilio 的 media 訊息。

```ts
function sendTranslationToTwilio(twilioWs, streamSid, realtimeEvent) {
  if (realtimeEvent.type !== "session.output_audio.delta") return;

  const twilioPayload = realtimeAudioToTwilioMedia(realtimeEvent.delta);

  twilioWs.send(JSON.stringify({
    event: "media",
    streamSid,
    media: {
      payload: twilioPayload,
    },
  }));
}
```

### 配對通話者，每個方向一個 session

兩位通話者都在等待時，就把他們配對並開兩個 Realtime Translation session。每個 session 的輸出語言是聽者選的語言，不是講者的。

```ts
function pairCallers(a, b) {
  const aToB = openTranslationSession({ targetLanguage: b.language });
  const bToA = openTranslationSession({ targetLanguage: a.language });

  a.onAudio = (message) => sendTwilioAudioToTranslation(aToB, message);
  b.onAudio = (message) => sendTwilioAudioToTranslation(bToA, message);

  aToB.on("message", (data) => {
    sendTranslationToTwilio(b.ws, b.streamSid, JSON.parse(data));
  });

  bToA.on("message", (data) => {
    sendTranslationToTwilio(a.ws, a.streamSid, JSON.parse(data));
  });
}
```

跑完整的 demo：

```bash
cd examples/voice_solutions/realtime_translation_guide/twilio-translation-demo
npm install
npm run dev
```

把你的 Twilio 電話號碼的 Voice webhook 設成呼叫 `POST https://YOUR_PUBLIC_HOST/incoming-call`。

## 用 LiveKit 做視訊聊天

最後，把 `gpt-realtime-translate` 整合進群組視訊會議。如果你已經有視訊房間，想在對話裡加上即時口譯，就用這個模式。[LiveKit](https://docs.livekit.io/) 負責房間、參與者、麥克風 track、鏡頭 track、裝置選擇和斷線重連。Realtime Translation 則扮演口譯層，掛在每位聽者收到的音訊 track 上。

![LiveKit video translation architecture](https://github.com/openai/openai-cookbook/blob/main/images/realtime_translation_guide/livekit-video-translation.png?raw=true)

### 運作方式

1. 參與者把麥克風和鏡頭 track 發布到 LiveKit 房間。
2. 聽者透過 LiveKit 訂閱遠端參與者的麥克風 track。
3. 聽者的瀏覽器把那條遠端的 `MediaStreamTrack` 交給 Realtime Translation sidecar。
4. Sidecar 用聽者選的輸出語言，開一個 WebRTC 的 Realtime Translation session。
5. Realtime Translation 把譯文音訊當成遠端 audio track 回傳，並透過 `oai-events` data channel 送逐字稿 delta。
6. 聽者的瀏覽器播放譯文音訊、顯示字幕，並在本機把 LiveKit 的原音壓低或混音。

這個 demo 裡，譯文音訊只留在聽者的瀏覽器，不會再發布回 LiveKit 房間。

### 把翻譯掛到遠端參與者的 track

聽者加入 LiveKit 房間後，找出每位遠端參與者的麥克風 track，把底層的 `MediaStreamTrack` 交給翻譯 helper。

```ts
function getParticipantAudioMediaStreamTrack(participant: Participant) {
  const publication = participant.getTrackPublication(Track.Source.Microphone);
  return publication?.audioTrack?.mediaStreamTrack ?? null;
}
```

### 每位遠端講者一個翻譯 sidecar

被翻譯的參與者 tile 可以保留原本的 LiveKit 媒體路徑，同時在旁邊加上翻譯輸出。Tile 還是會呈現參與者的影像和原音，但啟用翻譯時，也會替該參與者的麥克風 track 開一個 Realtime Translation sidecar。

```tsx
function TranslatedParticipantTile({
  participant,
  language,
  translationEnabled,
}: {
  participant: Participant;
  language: string;
  translationEnabled: boolean;
}) {
  const sourceTrack = getParticipantAudioMediaStreamTrack(participant);

  const translation = useRemoteTranslation({
    enabled: translationEnabled && Boolean(sourceTrack),
    sourceTrack,
    language,
  });

  return (
    <MeetingTile
      participant={participant}
      sourceVolume={translation.hasOutputAudio ? 0.15 : 1}
      translatedSubtitle={translation.translatedSubtitle}
      sourceSubtitle={translation.sourceSubtitle}
    />
  );
}
```

### 開啟翻譯 sidecar

這個 helper 會在你的 server 上建立短效的 Realtime Translation client secret，從瀏覽器開一個 WebRTC sidecar，把遠端 LiveKit 麥克風的 `MediaStreamTrack` 接到 `RTCPeerConnection` 上，並從回傳的遠端 track 播放譯文音訊。

```ts
async function startTranslationSidecar({ sourceTrack, clientSecret }) {
  const pc = new RTCPeerConnection();
  pc.addTrack(sourceTrack, new MediaStream([sourceTrack]));

  const translatedAudio = new Audio();
  translatedAudio.autoplay = true;
  pc.ontrack = ({ streams }) => {
    translatedAudio.srcObject = streams[0];
  };

  const events = pc.createDataChannel("oai-events");
  events.onmessage = ({ data }) => {
    const event = JSON.parse(data);
    if (event.type === "session.output_transcript.delta") {
      subtitles.textContent += event.delta;
    }
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const response = await fetch(
    "https://api.openai.com/v1/realtime/translations/calls",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${clientSecret}`,
        "Content-Type": "application/sdp",
      },
      body: offer.sdp,
    }
  );

  await pc.setRemoteDescription({
    type: "answer",
    sdp: await response.text(),
  });

  return pc;
}
```

### 依聽者語言規劃 session 的 fanout

兩個人的房間，每位參與者把對方的麥克風 track 翻成自己偏好的語言。群組房間裡，進行中的翻譯 session 數量取決於正在講話的遠端講者人數，以及聽者需要的不同目標語言數量。

瀏覽器端翻譯是最簡單的架構：每位聽者替自己想翻譯的遠端講者各建一個翻譯 sidecar。Production 裡房間比較大時，要把這些工作搬到 LiveKit worker 或伺服器端的參與者，由它訂閱房間音訊，每位來源講者每個目標語言只翻一次，再把譯文 track 發布回房間。

跑完整的 demo：

```bash
cd examples/voice_solutions/realtime_translation_guide/livekit-translation-demo
pnpm install
pnpm dev
```

在兩個瀏覽器視窗用同一個會議代碼，就會加入同一個 LiveKit 房間。在其中一個視窗開啟翻譯，選那位聽者想聽的語言，然後在另一個視窗說話。

## Production 準備度

上線 Realtime Translation 之前，要用你預期在 production 會遇到的音訊、語言、網路條件和使用者流程，完整測過整個體驗。翻譯品質只是體驗的一部分，延遲、講者路由、字幕、重連行為和音訊控制，都會影響 production 準備度。

### 依媒體路徑選擇架構

麥克風、分頁音訊或 LiveKit 參與者 track 這類 client 端的媒體，用瀏覽器 WebRTC。電話、廣播 ingest 或後端媒體 pipeline，則用伺服器端的 WebSocket。

多人通話要依來源講者和目標語言來路由翻譯。盡量讓講者的 track 保持分開，再把譯文輸出 fan out 給目標語言相同的聽者。把所有講者混進一條串流，字幕、講者身份和重疊的發言都會更難處理。

### 直接測試術語和人名

模型目前不支援自訂 prompt、詞彙表或發音指南。如果你的使用情境依賴特定詞彙、人名、法律或醫療術語等領域語言，要直接拿這些詞去測。模型翻譯時有時會把名字或實體換成錯的，所以這些案例要放進你的上線評估集。

### 考慮混語言的發言

Realtime Translation 會盡量不去翻譯已經是所選輸出語言的發言。例如輸出語言是西班牙文，講者切換成西班牙文時，模型可能就不會替那一段產生譯文音訊。

這對混語言的發言很重要。Spanglish（西英混用）翻成德文應該會正常，因為英文和西班牙文的部分都需要翻成德文。Spanglish 翻成英文就可能比較斷斷續續，因為模型可能翻西班牙文的部分，英文的部分則保持沉默。

這個行為通常有幫助，但如果你的 app 把原音完全靜音，就可能讓人困惑。預期講者會混用語言的話，要保留原音。好的做法是在播放譯文音訊時把原音壓低，而不是完全靜音。你也可以提供來源語言字幕，或是原音/譯音的混音控制。

### 支援的語言

Realtime Translation 目前支援 13 種目標輸出語言：Spanish、Portuguese、French、Japanese、Russian、Chinese、German、Korean、Hindi、Indonesian、Vietnamese、Italian 和 English。

模型目前支援 70 種以上的輸入語言。它可以動態偵測並翻譯這些語言：Arabic, Afrikaans, Azerbaijani, Belarusian, Bengali, Bosnian, Bulgarian, Catalan, Chinese, Croatian, Czech, Danish, Dutch, Dzongkha, English, Esperanto, Estonian, Basque, Persian / Farsi, Finnish, Filipino, French, Galician, German, Greek, Gujarati, Haitian Creole, Hawaiian, Hebrew, Hindi, Hungarian, Armenian, Indonesian, Italian, Japanese, Javanese, Georgian, Kazakh, Korean, Kurdish, Latin, Latvian, Lithuanian, Macedonian, Malay, Malayalam, Maori, Mongolian, Burmese / Myanmar, Nepali, Norwegian, Nynorsk, Polish, Portuguese, Punjabi, Romanian, Russian, Serbian, Shona, Slovak, Slovenian, Albanian, Spanish, Swahili, Swedish, Tagalog, Telugu, Thai, Turkish, Ukrainian, Uzbek, Vietnamese, Welsh 和 Yoruba。

### 分開評估語意和延遲

做評估時，每次執行都要把來源音訊、生成的譯文音訊、生成的逐字稿和參考文本放在一起。你之後要能回答三個問題：

- 模型聽到了什麼？
- 它說了什麼？
- 它應該說什麼？

用你能拿到的最好的人工參考，例如人工編輯的字幕、專業口譯員的逐字稿、雙語人士審過的通話逐字稿，或來源素材的人工配音。自動字幕和逐字稿適合做快速的 smoke test，但拿來當 source of truth 就比較弱。

參考文本有時間戳的話就用上。有時間對齊的字幕或逐字稿，不只能評翻譯品質，還能評譯文音訊和字幕什麼時候到。

翻譯要依語意打分，不是看字面。好的翻譯可能用不同的字，所以要評估重要的事實、細微語氣、實體、數字和語調有沒有保留。要追蹤失誤的完整分布，而不是只看平均分數，因為在即時翻譯裡，少數嚴重的錯誤影響可能很大。

BLEU 這類傳統文字指標可以幫忙做快速比較，但拿來代表語音對語音的品質並不好，因為它抓不到語意相似度。

延遲要跟品質分開量。追蹤「來源語音到譯文音訊」和「來源語音到字幕顯示」兩段時間。計算延遲時只用翻譯有明確對齊的片段，否則配錯的片段會讓時間資料誤導人。

最後，手動檢視低分的例子。把原始來源、生成的譯文和參考片段並排聽。這是抓出聚合分數看不出來的問題的地方，特別是人名、數字、只翻一半、語調，以及模型跳過或延遲內容的情況。

Realtime 評估的更深入說明，見 [Realtime eval guide](https://developers.openai.com/cookbook/examples/realtime_eval_guide)。

## 結論

Realtime Translation 改變了為多語言使用者建 app 的意義。它讓即時口譯成為產品體驗的原生一部分，多語言的對話就比較不像在用翻譯工具，而更像是在即時地互相理解。有了專用的翻譯 session，音訊就能在瀏覽器、電話和視訊房間之間流動，成為體驗本身的一部分。

當語言的隔閡變小，這些應用就能幫更多人參與、協作和連結。


## 重點整理

- `gpt-realtime-translate` 是專門做口譯的模型，只翻譯、不回答，而且邊收音邊輸出，沒有 turn 的概念。想做語音 agent 要用 `gpt-realtime-2`。
- 協定看媒體路徑選：client 端媒體用 WebRTC 加短效 client secret，後端 pipeline（Twilio、SIP、廣播）用 WebSocket。API key 永遠留在 server。
- 輸出語言由聽者決定，所以 session 要依「來源講者、目標語言」來規劃，兩人通話就是兩個 session。
- 模型不會翻已經是目標語言的語音，也不支援自訂 prompt 或詞彙表，所以要保留原音（壓低而不是靜音），並直接測人名和術語。
- 評估要分開看語意和延遲，用人工參考，並手動檢視低分例子。

## 練習

1. 在瀏覽器 demo 的 client-secret 請求裡，把目標語言從原本的設定改成 `ja`，確認字幕和譯文語音都變成日文。
2. 在 Twilio 配對的程式裡，想想兩位通話者選同一種語言時會發生什麼事，並試著加一個判斷，同語言時略過翻譯 session，改成直接把原音轉給對方。
3. 把 LiveKit 範例中原音的處理從完全靜音改成「播放譯音時壓低音量」，並加一個滑桿控制原音/譯音的比例。
