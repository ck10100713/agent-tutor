# OpenAI & Claude 開發教材

<div id="tutor-continue"></div>

## OpenAI Cookbook

### 1. 打基礎

- [Token 計算](openai/examples/How_to_count_tokens_with_tiktoken.md)・1 篇
- [文字生成（Completions）](openai/examples/book_translation/translate_latex_book.md)・9 篇
- [Responses API](openai/examples/skills_in_api.md)・2 篇

### 2. 讓模型用工具、會推理

- [GPT-5 系列](openai/examples/gpt-5/prompt-optimization-cookbook.md)・2 篇

### 3. 接上自己的資料

- [Embedding 與向量搜尋](openai/examples/Clustering.md)・17 篇
- [向量資料庫整合](openai/examples/vector_databases/analyticdb/Getting_started_with_AnalyticDB_and_OpenAI.md)・28 篇
- [知識圖譜](openai/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents.md)・1 篇

### 4. 做 Agent

- [Agent 開發](openai/examples/How_to_build_a_tool-using_agent_with_Langchain.md)・6 篇
- [Agents SDK](openai/examples/agents_sdk/session_memory.md)・9 篇

### 5. 上線前

- [評估（Evals）](openai/examples/multimodal/image_evals.md)・3 篇
- [微調（Fine-tuning）](openai/examples/Fine-tuned_classification.md)・3 篇
- [用量 API](openai/examples/completions_usage_api.md)・1 篇

### 6. 多模態

- [語音與音訊](openai/examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.md)・4 篇
- [即時語音（Realtime）](openai/examples/Realtime_eval_guide.md)・2 篇
- [圖片生成](openai/examples/multimodal/document_and_multimodal_understanding_tips.md)・3 篇

### 7. 用 AI 寫程式

- [Codex](openai/examples/codex/secure_quality_gitlab.md)・6 篇

### 8. 自己跑模型

- [開源模型（gpt-oss）](openai/articles/gpt-oss/handle-raw-cot.md)・6 篇
- 要 GPU 的篇（Colab）・5 篇
    - [用 gpt-oss 和 Hugging Face Transformers 做 fine-tuning](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/fine-tune-transfomers.ipynb)
    - [用 Transformers 跑 gpt-oss](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/run-transformers.ipynb)
    - [客製化 embedding](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/Customizing_embeddings.ipynb)
    - [交易資料的多類別分類](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/Multiclass_classification_for_transactions.ipynb)
    - [Fine-tuned Q&A：收集資料](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/fine-tuned_qa/olympics-1-collect-data.ipynb)

### 9. 平台整合範例

- [ChatGPT 應用](openai/articles/chatgpt-agents-sales-meeting-prep.md)・5 篇
- [合作夥伴範例](openai/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.md)・8 篇

## Claude Cookbook

### 1. 打基礎

- [Prompt 工程互動教學](prompt-tutorial/Anthropic_1P/00_Tutorial_How-To.md)・13 篇
- [Prompt 與回應技巧](claude/misc/building_moderation_filter.md)・11 篇
- [Extended Thinking](claude/extended_thinking/extended_thinking.md)・2 篇

### 2. 工具與資料

- [工具使用（Tool use）](claude/tool_use/calculator_tool.md)・11 篇
- [RAG 與檢索](claude/misc/pdf_upload_summarization.md)・9 篇
- [多模態](claude/multimodal/getting_started_with_vision.md)・6 篇

### 3. 做 Agent

- [Agent 設計模式](claude/multimodal/using_sub_agents.md)・10 篇
- [Claude Agent SDK](claude/claude_agent_sdk/00_The_one_liner_research_agent.md)・10 篇
- [Skills](claude/skills/notebooks/01_skills_introduction.md)・3 篇
- [Claude Managed Agents](claude/managed_agents/CMA_prompt_versioning_and_rollback.md)・18 篇

### 4. 上線前

- [評估（Evals）](claude/misc/building_evals.md)・4 篇
- [監控與管理](claude/observability/usage_cost_api.md)・3 篇
- [微調（Fine-tuning）](claude/finetuning/finetuning_on_bedrock.md)・1 篇

### 5. 整合範例

- [第三方整合](claude/third_party/Pinecone/rag_using_pinecone.md)・12 篇

## Claude Quickstarts

- [11 個可部署的完整專案範本](quickstarts/README.md)
