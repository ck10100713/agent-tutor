---
translated: true
source: articles/related_resources.md
---
# 網路上的相關資源

> 原文：[articles/related_resources.md](https://github.com/openai/openai-cookbook/blob/main/articles/related_resources.md)



## 這篇在做什麼

這是一份社群整理的資源清單，收了各種幫你改善 GPT 輸出的工具、指南、影片課程和論文。拿來當查資料的起點，不需要跑任何程式。

## 學完你會

- 知道有哪些 prompting 函式庫和 LLMOps 平台可以選（LangChain、LlamaIndex、OpenAI Evals 等）
- 找到入門 prompt engineering 的指南和影片課程
- 認得幾篇改善 reasoning 的經典論文（Chain-of-Thought、ReAct、Tree of Thoughts 等）


大家寫了很多很棒的工具和論文，用來改善 GPT 的輸出。下面是我們看到的一些不錯的資源：

## Prompting 函式庫和工具（依字母排序）

- [Arthur Shield](https://www.arthur.ai/get-started): A paid product for detecting toxicity, hallucination, prompt injection, etc.
- [Baserun](https://baserun.ai/): A paid product for testing, debugging, and monitoring LLM-based apps
- [Chainlit](https://docs.chainlit.io/overview): A Python library for making chatbot interfaces.
- [ElatoAI](https://github.com/akdeb/ElatoAI): A platform for running OpenAI Realtime API Speech on ESP32 on Arduino using Deno Edge Runtime and Supabase.
- [Embedchain](https://github.com/embedchain/embedchain): A Python library for managing and syncing unstructured data with LLMs.
- [FLAML (A Fast Library for Automated Machine Learning & Tuning)](https://microsoft.github.io/FLAML/docs/Getting-Started/): A Python library for automating selection of models, hyperparameters, and other tunable choices.
- [Guidance](https://github.com/microsoft/guidance): A handy looking Python library from Microsoft that uses Handlebars templating to interleave generation, prompting, and logical control.
- [Haystack](https://github.com/deepset-ai/haystack): Open-source LLM orchestration framework to build customizable, production-ready LLM applications in Python.
- [HoneyHive](https://honeyhive.ai): An enterprise platform to evaluate, debug, and monitor LLM apps.
- [LangChain](https://github.com/hwchase17/langchain): A popular Python/JavaScript library for chaining sequences of language model prompts.
- [LiteLLM](https://github.com/BerriAI/litellm): A minimal Python library for calling LLM APIs with a consistent format.
- [LlamaIndex](https://github.com/jerryjliu/llama_index): A Python library for augmenting LLM apps with data.
- [LLMOps Database](https://www.reddit.com/r/LocalLLaMA/comments/1h4u7au/a_nobs_database_of_how_companies_actually_deploy/): Database of how companies actually deploy LLMs in production.
- [LMQL](https://lmql.ai): A programming language for LLM interaction with support for typed prompting, control flow, constraints, and tools.
- [OpenAI Evals](https://github.com/openai/evals): An open-source library for evaluating task performance of language models and prompts.
- [Outlines](https://github.com/normal-computing/outlines): A Python library that provides a domain-specific language to simplify prompting and constrain generation.
- [Parea AI](https://www.parea.ai): A platform for debugging, testing, and monitoring LLM apps.
- [Portkey](https://portkey.ai/): A platform for observability, model management, evals, and security for LLM apps.
- [Promptify](https://github.com/promptslab/Promptify): A small Python library for using language models to perform NLP tasks.
- [PromptPerfect](https://promptperfect.jina.ai/prompts): A paid product for testing and improving prompts.
- [Prompttools](https://github.com/hegelai/prompttools): Open-source Python tools for testing and evaluating models, vector DBs, and prompts.
- [Scale Spellbook](https://scale.com/spellbook): A paid product for building, comparing, and shipping language model apps.
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel): A Python/C#/Java library from Microsoft that supports prompt templating, function chaining, vectorized memory, and intelligent planning.
- [Vellum](https://www.vellum.ai/): A paid AI product development platform to experiment with, evaluate, and deploy advanced LLM apps.
- [Weights & Biases](https://wandb.ai/site/solutions/llmops): A paid product for tracking model training and prompt engineering experiments.
- [YiVal](https://github.com/YiVal/YiVal): An open-source GenAI-Ops tool for tuning and evaluating prompts, retrieval configurations, and model parameters using customizable datasets, evaluation methods, and evolution strategies.

## Prompting 指南

- [Brex's Prompt Engineering Guide](https://github.com/brexhq/prompt-engineering): Brex's introduction to language models and prompt engineering.
- [learnprompting.org](https://learnprompting.org/): An introductory course to prompt engineering.
- [Lil'Log Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/): An OpenAI researcher's review of the prompt engineering literature (as of March 2023).
- [OpenAI Cookbook: Techniques to improve reliability](https://cookbook.openai.com/articles/techniques_to_improve_reliability): A slightly dated (Sep 2022) review of techniques for prompting language models.
- [promptingguide.ai](https://www.promptingguide.ai/): A prompt engineering guide that demonstrates many techniques.
- [Xavi Amatriain's Prompt Engineering 101 Introduction to Prompt Engineering](https://amatriain.net/blog/PromptEngineering) and [202 Advanced Prompt Engineering](https://amatriain.net/blog/prompt201): A basic but opinionated introduction to prompt engineering and a follow up collection with many advanced methods starting with CoT.

## 影片課程

- [Andrew Ng's DeepLearning.AI](https://www.deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/): A short course on prompt engineering for developers.
- [Andrej Karpathy's Let's build GPT](https://www.youtube.com/watch?v=kCc8FmEb1nY): A detailed dive into the machine learning underlying GPT.
- [Prompt Engineering by DAIR.AI](https://www.youtube.com/watch?v=dOxUroR57xs): A one-hour video on various prompt engineering techniques.
- [Scrimba course about Assistants API](https://scrimba.com/learn/openaiassistants): A 30-minute interactive course about the Assistants API.
- [LinkedIn course: Introduction to Prompt Engineering: How to talk to the AIs](https://www.linkedin.com/learning/prompt-engineering-how-to-talk-to-the-ais/talking-to-the-ais?u=0): Short video introduction to prompt engineering

## 改善 reasoning 的進階 prompting 論文

- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (2022)](https://arxiv.org/abs/2201.11903): 用 few-shot prompt 要求模型一步一步思考，可以改善它的 reasoning。PaLM 在數學應用題（GSM8K）的分數從 18% 升到 57%。
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models (2022)](https://arxiv.org/abs/2203.11171): 對多個輸出投票，準確度會再提高。對 40 個輸出投票，PaLM 在數學應用題的分數從 57% 再升到 74%，`code-davinci-002` 從 60% 升到 78%。
- [Tree of Thoughts: Deliberate Problem Solving with Large Language Models (2023)](https://arxiv.org/abs/2305.10601): 在一步一步推理的樹狀結構上搜尋，比對多條 chain of thought 投票更有幫助。它提升了 `GPT-4` 在創意寫作和填字遊戲上的分數。
- [Language Models are Zero-Shot Reasoners (2022)](https://arxiv.org/abs/2205.11916): 叫會遵循指令的模型一步一步思考，可以改善它的 reasoning。`text-davinci-002` 在數學應用題（GSM8K）的分數從 13% 升到 41%。
- [Large Language Models Are Human-Level Prompt Engineers (2023)](https://arxiv.org/abs/2211.01910): 自動在可能的 prompt 裡搜尋，找到一個能把數學應用題（GSM8K）分數提升到 43% 的 prompt，比 Language Models are Zero-Shot Reasoners 裡人寫的 prompt 高 2 個百分點。
- [Reprompting: Automated Chain-of-Thought Prompt Inference Through Gibbs Sampling (2023)](https://arxiv.org/abs/2305.09993): 自動搜尋可能的 chain-of-thought prompt，讓 ChatGPT 在幾個 benchmark 的分數提升 0 到 20 個百分點。
- [Faithful Reasoning Using Large Language Models (2022)](https://arxiv.org/abs/2208.14271): 結合下列幾項的系統可以改善 reasoning：由「選擇」和「推論」兩種 prompt 交替產生的 chain of thought、決定何時停止選擇推論迴圈的 halter 模型、用來在多條推理路徑上搜尋的 value function，以及幫助避免 hallucination 的句子標籤。
- [STaR: Bootstrapping Reasoning With Reasoning (2022)](https://arxiv.org/abs/2203.14465): chain of thought 推理可以透過 fine-tuning 內建進模型。對有標準答案的任務，範例的 chain of thought 可以由語言模型自己產生。
- [ReAct: Synergizing Reasoning and Acting in Language Models (2023)](https://arxiv.org/abs/2210.03629): 對有 tool 或環境的任務，如果有規則地交替進行 **Re**asoning（想接下來要做什麼）和 **Act**ing（從 tool 或環境取得資訊），chain of thought 效果更好。
- [Reflexion: an autonomous agent with dynamic memory and self-reflection (2023)](https://arxiv.org/abs/2303.11366): 帶著先前失敗的記憶重試任務，後續表現會變好。
- [Demonstrate-Search-Predict: Composing retrieval and language models for knowledge-intensive NLP (2023)](https://arxiv.org/abs/2212.14024): 用「retrieve-then-read」補充知識的模型，可以靠多跳（multi-hop）的搜尋鏈進一步改善。
- [Improving Factuality and Reasoning in Language Models through Multiagent Debate (2023)](https://arxiv.org/abs/2305.14325): 讓幾個 ChatGPT agent 進行幾輪辯論，可以提升各種 benchmark 的分數。數學應用題的分數從 77% 升到 85%。

## 重點整理

- 想改善 GPT 輸出，除了自己調 prompt，也有一整批函式庫（LangChain、LlamaIndex、Guidance 等）可以用。
- 要上線的話，eval 和 observability 平台（OpenAI Evals、Baserun、Portkey 等）能幫你測試、除錯、監控。
- 讓模型「一步一步想」是最基本的 reasoning 改善手法，再搭配投票（self-consistency）或搜尋（Tree of Thoughts）效果更好。
- 有 tool 的情境可以參考 ReAct，把思考和行動交替進行；失敗重試可以參考 Reflexion 的記憶機制。
- 這份清單有些內容日期較早（例如 2022、2023 年的論文和指南），用之前先確認是否還適用。

## 練習

1. 從清單挑一個你沒用過的函式庫（例如 LiteLLM），照它的 README 跑一個最小的 API 呼叫。
2. 拿一題數學應用題，分別用一般 prompt 和加上「think step by step」的 prompt 問同一個模型，比較答案。
3. 對同一題用較高 temperature 取樣 5 次，自己寫幾行程式做多數決，實作簡化版的 self-consistency。
