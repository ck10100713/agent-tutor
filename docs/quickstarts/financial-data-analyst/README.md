---
translated: true
source: financial-data-analyst/README.md
---

# Claude Financial Data Analyst

> 原文：[financial-data-analyst/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/financial-data-analyst/README.md)



## 這篇在做什麼

這是一個 Next.js 應用，把 Claude 的能力跟互動式資料視覺化結合，讓你用聊天的方式分析財務資料。上傳檔案後，Claude 會依內容產生折線圖、長條圖、圓餅圖等圖表。

## 學完你會

- 把這個應用 clone 下來、設好環境變數並跑起來。
- 了解它支援的檔案格式，以及 Claude 能產生的六種圖表。
- 知道它的技術堆疊，並把它改用在財務以外的資料分析情境。

## 開跑前

需要 Node.js 20+ 和 Claude API key，並在根目錄的 `.env.local` 設定 key。

![hero](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/financial-data-analyst/public/hero.png)

一個進階的 Next.js 應用，結合 Claude 的能力與互動式資料視覺化，透過聊天分析財務資料。

## 功能

- **智慧資料分析**：由 Claude 驅動（使用 Claude Haiku 4.5 與 Claude Sonnet 5.5）
- **支援多種檔案格式上傳**：
  - 文字/程式碼檔（.txt、.md、.html、.py、.csv 等）
  - PDF 文件（含文字的一般 PDF，不支援掃描文件）
  - 圖片
- **互動式資料視覺化**：依據情境與分析的資料，Claude 可以產生以下圖表：
  - 折線圖（時間序列資料與趨勢）
  - 長條圖（單一指標比較）
  - 多重長條圖（多個指標比較）
  - 面積圖（隨時間變化的量）
  - 堆疊面積圖（組成拆解）
  - 圓餅圖（分布分析）

## 開始使用

### 前置需求

- 已安裝 Node.js 20+（`@anthropic-ai/sdk` v1 需要）
- Claude API key（用於 Claude 整合）

### 安裝

1. Clone 專案：
```bash
git clone https://github.com/anthropics/anthropic-quickstarts.git
cd anthropic-quickstarts/financial-data-analyst
```

2. 安裝相依套件：
```bash
npm install
```

3. 在根目錄建立 `.env.local` 檔案：
```env
ANTHROPIC_API_KEY=your_api_key_here
```

4. 啟動開發伺服器：
```bash
npm run dev
```

用瀏覽器開啟 [http://localhost:3000](http://localhost:3000) 看結果。

## 技術堆疊

- **Frontend**：
  - Next.js 14
  - React
  - TailwindCSS
  - Shadcn/ui Components
  - Recharts（資料視覺化）
  - PDF.js（處理 PDF）

- **Backend**：
  - Next.js API Routes
  - Edge Runtime
  - Anthropic TypeScript SDK（`@anthropic-ai/sdk` v1.x）

## 使用範例

這個助理可以協助各種財務分析任務：

1. **資料擷取與分析**：
   - 上傳財務文件
   - 擷取關鍵指標
   - 分析趨勢與模式

2. **建立視覺化**：
   - 依資料產生圖表
   - 客製化視覺化
   - 比較多個指標

3. **互動式分析**：
   - 針對資料提問
   - 要求特定的視覺化
   - 取得詳細說明

## 有趣的使用情境

雖然主要是為財務分析設計，這個 AI 助理也能改用在各種有趣的應用：

1. **環境資料分析**：
   - 分析氣候變遷趨勢
   - 視覺化汙染程度隨時間的變化
   - 比較各地區再生能源的採用情況

2. **運動表現追蹤**：
   - 上傳運動員表現資料
   - 產生關鍵指標的視覺化
   - 分析球隊統計的趨勢與模式

3. **社群媒體分析**：
   - 處理各平台的互動資料
   - 建立顯示追蹤者成長與互動率的圖表
   - 分析使用者留言的情緒趨勢

4. **教育進度追蹤**：
   - 上傳學生成績資料
   - 視覺化學習進度隨時間的變化
   - 比較不同的教學方法或課程

5. **健康與健身監測**：
   - 處理穿戴裝置的個人健康資料
   - 為步數、心率、睡眠模式等指標建立圖表
   - 分析長期健康趨勢並提供洞察

你甚至可以用圖表和圖片做出有趣的結果，例如用圓餅圖看一張圖片裡最常出現的東西是什麼。

![Image Analysis](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/financial-data-analyst/public/image-analysis.png)

## 重點整理

- 這個應用的核心是讓 Claude 讀上傳的檔案，再依內容挑選合適的圖表類型輸出。
- 支援文字/程式碼檔、含文字的 PDF 和圖片，掃描的 PDF 不支援。
- 技術堆疊是 Next.js 加 Recharts 做視覺化，後端用 Edge Runtime 呼叫 Anthropic SDK。
- 同樣的架構可以搬到環境、運動、社群、教育、健康等任何有數據的領域。

## 練習

1. 照安裝步驟把專案跑起來，上傳一份 CSV，要求 Claude 畫折線圖。
2. 同一份資料改要求長條圖和圓餅圖，比較哪種圖最適合呈現。
3. 上傳一張圖片，請 Claude 用圓餅圖分析圖片中最常出現的物件，並看它是怎麼處理圖片輸入的。
