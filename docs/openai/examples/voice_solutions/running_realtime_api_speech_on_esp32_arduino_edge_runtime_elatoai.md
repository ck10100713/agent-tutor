---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/voice_solutions/running_realtime_api_speech_on_esp32_arduino_edge_runtime_elatoai.md
---

# ElatoAI：在 Arduino 的 ESP32 上跑 Realtime 語音 AI Agent

> 原文：[examples/voice_solutions/running_realtime_api_speech_on_esp32_arduino_edge_runtime_elatoai.md](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/running_realtime_api_speech_on_esp32_arduino_edge_runtime_elatoai.md)



## 這篇在做什麼

用 ESP32 微控制器加一支麥克風和喇叭，做出一個可以直接跟 OpenAI Realtime API 對話的語音裝置。中間靠 Deno Edge Function 轉接 WebSocket，所以裝置本身不用處理複雜的 API 連線。整個專案包含 Next.js 前端、Supabase 後端、Deno 邊緣伺服器和 ESP32 韌體。

## 學完你會

- 看懂「ESP32 裝置、Deno Edge Server、OpenAI Realtime API」三層架構怎麼分工
- 在本機把 Supabase、Next.js 前端、Deno server 跑起來，並把裝置註冊到帳號底下
- 知道這個做法的限制（冷啟動、10 分鐘上限、無法偵測打斷），評估適不適合你的場景

## 開跑前

- 需要 `OPENAI_API_KEY` 和 `SUPABASE_ANON_KEY`
- 需要 ESP32-S3 開發板、I2S 麥克風和 I2S 喇叭放大器（或直接買組好的裝置）
- 本機、ESP32 要在同一個 Wifi 網路

![Elato Logo](https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/elato-alien.png)

## 👾 ElatoAI：用 Deno Edge Function 在 Arduino 的 ESP32 上跑 OpenAI Realtime 語音

這份指南教你做一個 AI 語音裝置，用 OpenAI Realtime API、ESP32、Secure WebSocket 和 Deno Edge Function 撐起超過 10 分鐘不中斷的全球對話。

這份 README 的最新版在 [ElatoAI](https://github.com/akdeb/ElatoAI)。

<div align="center">
    <a href="https://www.youtube.com/watch?v=o1eIAwVll5I" target="_blank">
    <img src="https://raw.githubusercontent.com/akdeb/ElatoAI/refs/heads/main/assets/thumbnail.png" alt="Elato AI Demo Video" width="100%" style="border-radius:10px" />
  </a>
</div>

## ⚡️ DIY 硬體設計

參考實作用 ESP32-S3 微控制器，只搭配少量零件：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/pcb-design.png" alt="Hardware Setup" width="100%">

**需要的零件：**
- ESP32-S3 開發板
- I2S 麥克風（例如 INMP441）
- I2S 放大器和喇叭（例如 MAX98357A）
- 開始/結束對話的按鈕
- 顯示狀態用的 RGB LED
- 選配：觸控感測器，當作另一種操控方式

**硬體選項：**
也可以直接買組好的 PCB 和裝置，在 [ElatoAI store](https://www.elatoai.com/products)。

## 📱 App 設計

用你自己的 webapp，從手機控制 ESP32 AI 裝置。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/mockups.png" alt="App Screenshots" width="100%">

| 從清單選 AI 角色 | 跟 AI 即時對話 | 建立個人化的 AI 角色 |
|:--:|:--:|:--:|

## ✨ 快速上手教學

<a href="https://www.youtube.com/watch?v=bXrNRpGOJWw">
  <img src="https://img.shields.io/badge/Quick%20start%20Tutorial-YouTube-yellow?style=for-the-badge&logo=youtube" alt="Watch Demo on YouTube">
</a>

1. **Clone repository**

到 [ElatoAI GitHub repository](https://github.com/akdeb/ElatoAI) 把專案 clone 下來。

```bash
git clone https://github.com/akdeb/ElatoAI.git
cd ElatoAI
```

2. **設定環境變數（OPENAI_API_KEY、SUPABASE_ANON_KEY）**

在 `frontend-nextjs` 目錄建立 `.env.local`，填入環境變數。

```bash
cd frontend-nextjs
cp .env.example .env.local

# NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>
# OPENAI_API_KEY=<your-openai-api-key>
```

在 `server-deno` 目錄建立 `.env`，填入環境變數。

```bash
cd server-deno
cp .env.example .env

# In .env, set your environment variables 
# SUPABASE_KEY=<your-supabase-anon-key>
# OPENAI_API_KEY=<your-openai-api-key>
```

2. **啟動 Supabase**

安裝 [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)，設好本機的 Supabase 後端。在根目錄執行：
```bash
brew install supabase/tap/supabase
supabase start # Starts your local Supabase server with the default migrations and seed data.
```

3. **設定 NextJS 前端**

（[看前端 README](https://github.com/akdeb/ElatoAI/tree/main/frontend-nextjs/README.md)）

在 `frontend-nextjs` 目錄執行下列指令。（**登入帳密：** Email: `admin@elatoai.com`，Password: `admin`）
```bash
cd frontend-nextjs
npm install

# Run the development server
npm run dev
```

4. **啟動 Deno server**

（[看 Deno server README](https://github.com/akdeb/ElatoAI/tree/main/server-deno/README.md)）
```bash
# Navigate to the server directory
cd server-deno

# Run the server at port 8000
deno run -A --env-file=.env main.ts
```

5. **設定 ESP32 裝置韌體**

（[看 ESP32 裝置 README](https://github.com/akdeb/ElatoAI/tree/main/firmware-arduino/README.md)）

在 `Config.cpp` 把 `ws_server` 和 `backend_server` 設成你本機的 IP。在 console 執行 `ifconfig`，找 `en0` -> `inet` -> `192.168.1.100`（你的 Wifi 可能不同）。這樣 ESP32 才會連到跑在你電腦上的 NextJS 前端和 Deno server。所有服務都要在同一個 Wifi 網路。

6. **設定 ESP32 裝置的 Wifi**

build 並把韌體燒進 ESP32。ESP32 會開一個 `ELATO-DEVICE` 的 captive portal 讓你連 Wifi。連上去後打開 `http://192.168.4.1` 設定裝置的 Wifi。

7. Wifi 帳密設好後，把裝置關掉再開，它就會連上你的 Wifi 和 server。

8. 現在可以跟你的 AI 角色講話了！

## 🚀 準備上線？

1. 把 ESP32 裝置的 MAC Address 和一組唯一的 user code 加到 Supabase 的 `devices` 資料表，完成裝置註冊。
> **小技巧：** 要找 ESP32-S3 的 MAC Address，用 PlatformIO build 並上傳 `test/print_mac_address_test.cpp`，再看 serial monitor。


2. 在前端的 [Settings 頁](http://localhost:3000/home/settings)，輸入那組 user code，裝置就會綁到你在 Supabase 的帳號。


3. 如果在本機測試，可以保持開啟 `firmware-arduino/Config.h` 裡的 `DEV_MODE` macro，以及 Deno server 的環境變數，這樣會用你的本機 IP 測試。


4. 重複上面的步驟，就能在帳號下註冊多個裝置。

## 專案架構

ElatoAI 有三個主要元件：

1. **前端 Client**（`Next.js`，部署在 Vercel）：用來建立 AI agent、跟它對話，並把它「送」到你的 ESP32 裝置
2. **Edge Server Functions**（`Deno`，跑在 Deno/Supabase Edge）：處理 ESP32 裝置的 websocket 連線，以及對 OpenAI API 的呼叫
3. **ESP32 IoT Client**（`PlatformIO/Arduino`）：接收 Edge Server Functions 的 websocket 連線，並透過 Deno edge server 把音訊送到 OpenAI API

## 🌟 主要功能

1. **Realtime Speech-to-Speech**：用 OpenAI Realtime API 即時轉換語音。
2. **建立自訂 AI Agent**：建立不同個性和聲音的 agent。
3. **可自訂聲音**：從多種聲音和個性中挑選。
4. **Secure WebSockets**：穩定、加密的 WebSocket 通訊。
5. **Server VAD 輪流偵測**：聰明處理對話節奏，讓互動順暢。
6. **Opus 音訊壓縮**：用很少的頻寬傳高品質音訊。
7. **全球 Edge 效能**：低延遲的 Deno Edge Function，讓全球對話都順。
8. **ESP32 Arduino Framework**：硬體整合好用又精簡。
9. **對話紀錄**：可以查看歷史對話。
10. **裝置管理與認證**：註冊並管理你的裝置。
11. **使用者認證**：安全的使用者認證與授權。
12. **WebRTC 與 Websocket 對話**：在 NextJS webapp 用 WebRTC 跟 AI 講話，在 ESP32 上用 websocket。
13. **音量控制**：從 NextJS webapp 控制 ESP32 喇叭的音量。
14. **即時逐字稿**：對話的即時逐字稿存在 Supabase DB。
15. **OTA 更新**：ESP32 韌體支援 Over the Air 更新。
16. **用 captive portal 管理 Wifi**：從 ESP32 裝置連你的 Wifi 網路。
17. **恢復原廠設定**：從 NextJS webapp 把 ESP32 裝置恢復原廠設定。
18. **按鈕與觸控支援**：用按鈕或觸控感測器控制 ESP32 裝置。
19. **不需要 PSRAM**：ESP32 跑 speech to speech AI 不需要 PSRAM。
20. **Web client 的 OAuth**：使用者用 OAuth 管理自己的 AI 角色和裝置。

## 🛠 技術堆疊

| Component       | Technology Used                          |
|-----------------|------------------------------------------|
| Frontend        | Next.js, Vercel            |
| Backend         | Supabase DB  |
| Edge Functions  | Edge Functions on Deno / Supabase Edge Runtime         |
| IoT Client      | PlatformIO, Arduino Framework, ESP32-S3  |
| Audio Codec     | Opus                                     |
| Communication   | Secure WebSockets                        |
| Libraries       | ArduinoJson, WebSockets, AsyncWebServer, ESP32_Button, Arduino Audio Tools, ArduinoLibOpus        |

## 📈 核心使用情境

我們有一份 [Usecases.md](https://github.com/akdeb/ElatoAI/tree/main/Usecases.md)，整理了 [Elato AI 裝置](https://www.elatoai.com/products) 或任何自製對話式 AI 裝置的核心使用情境。

## 🗺️ 整體流程

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/flowchart.png" alt="App Screenshots" width="100%">

## 專案結構

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/refs/heads/main/examples/voice_solutions/arduino_ai_speech_assets/structure.png" alt="App Screenshots" width="100%">

## ⚙️ PlatformIO 設定

```ini
[env:esp32-s3-devkitc-1]
platform = espressif32 @ 6.10.0
board = esp32-s3-devkitc-1
framework = arduino
monitor_speed = 115200

lib_deps =
    bblanchon/ArduinoJson@^7.1.0
    links2004/WebSockets@^2.4.1
    ESP32Async/ESPAsyncWebServer@^3.7.6
    https://github.com/esp-arduino-libs/ESP32_Button.git#v0.0.1
    https://github.com/pschatzmann/arduino-audio-tools.git#v1.0.1
    https://github.com/pschatzmann/arduino-libopus.git#a1.1.0
```

## 📊 重要數據

- ⚡️ **延遲**：全球來回 <2 秒
- 🎧 **音質**：Opus codec，bitrate 12kbps（清晰度高）
- ⏳ **不中斷對話**：最長連續對話 10 分鐘
- 🌎 **全球可用**：用 Deno 的 edge computing 優化

## 🛡 安全

- 用 Secure WebSockets (WSS) 加密傳輸資料
- 選配：用 256-bit AES 加密 API Key
- 用 Supabase DB 做安全認證
- 所有資料表都套用 Supabase RLS

## 🚫 限制
- 連到 edge server 時有 3 到 4 秒的冷啟動時間
- 不中斷對話最長 10 分鐘
- 超過 wall clock time 時 edge server 會停止
- ESP32 上沒有語音打斷偵測

## 授權

本專案採用 MIT License，詳見 [LICENSE](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/LICENSE)。

---

**這個範例是 [OpenAI Cookbook](https://github.com/openai/openai-cookbook) 的一部分。完整專案和最新更新請看 [ElatoAI](https://github.com/akdeb/ElatoAI)，覺得好用的話也給它一顆 ⭐️。**

## 重點整理

- 架構分三層：ESP32 只負責收音、播音，Deno Edge Function 轉接 WebSocket，OpenAI Realtime API 負責語音理解與生成。
- 把連線邏輯放在 edge server，裝置端韌體就能很輕，連 PSRAM 都不用。
- 音訊用 Opus 壓到 12kbps，在小頻寬下仍能維持清晰度。
- Edge function 有 wall clock 限制，所以單次對話最長約 10 分鐘，連線時也有幾秒冷啟動。
- 裝置靠 MAC Address 加 user code 綁定到 Supabase 帳號，RLS 控制資料存取。

## 練習

1. 把 PlatformIO 設定裡的 build flag 或 library 看一遍，找出哪個 library 負責 Opus 編碼，並說明它在音訊流程中的位置。
2. 在 Supabase 的 `devices` 資料表再註冊第二個裝置（用不同的 MAC Address 和 user code），到 Settings 頁綁定，確認兩台都出現在你的帳號。
3. 把 `Config.cpp` 的 `ws_server` 故意改成錯的 IP，觀察 ESP32 的 serial monitor 輸出，再改回來，理解裝置連線失敗時的表現。
