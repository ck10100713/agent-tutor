# OpenAI & Claude 開發教材

<div id="tutor-continue"></div>

## OpenAI Cookbook

### 1. 打基礎

- [Token 計算](openai/examples/How_to_count_tokens_with_tiktoken.md)・3 篇
- [對話格式](openai/examples/Summarizing_long_documents.md)・2 篇
- [文字生成（Completions）](openai/examples/Fine-tuned_classification.md)・49 篇
- [Responses API](openai/examples/skills_in_api.md)・11 篇
- [Prompt 技巧](openai/examples/Prompt_migration_guide.md)・3 篇

### 2. 讓模型用工具、會推理

- [Function calling](openai/examples/o-series/o3o4-mini_prompting_guide.md)・1 篇
- [推理模型](openai/examples/reasoning_function_calls.md)・1 篇
- [GPT-5 系列](openai/examples/gpt-5/prompt-optimization-cookbook.md)・8 篇

### 3. 接上自己的資料

- [Embedding 與向量搜尋](openai/examples/Clustering.md)・83 篇
- [知識圖譜](openai/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents.md)・1 篇

### 4. 做 Agent

- [Agent 開發](openai/examples/agents_api/apps/sev_bot/README.md)・8 篇
- [Agents SDK](openai/examples/agents_sdk/session_memory.md)・14 篇
- [MCP](openai/examples/mcp/mcp_tool_guide.md)・3 篇
- [Assistants API](openai/examples/Assistants_API_overview_python.md)・2 篇
- [Deep Research API](openai/examples/deep_research_api/introduction_to_deep_research_api.md)・2 篇

### 5. 上線前

- [評估（Evals）](openai/examples/multimodal/image_evals.md)・18 篇
- [安全防護與內容審查](openai/examples/How_to_use_guardrails.md)・4 篇
- [微調（Fine-tuning）](openai/examples/fine-tuned_qa/reinforcement_finetuning_healthbench.md)・3 篇
- [批次處理](openai/examples/batch_processing.md)・1 篇
- [延遲優化](openai/examples/Prompt_Caching101.md)・1 篇
- [用量 API](openai/examples/completions_usage_api.md)・1 篇

### 6. 多模態

- [語音與音訊](openai/examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.md)・12 篇
- [即時語音（Realtime）](openai/examples/Realtime_eval_guide.md)・6 篇
- [影像理解（Vision）](openai/examples/How_to_combine_GPT4o_with_RAG_Outfit_Assistant.md)・4 篇
- [圖片生成](openai/examples/multimodal/document_and_multimodal_understanding_tips.md)・9 篇
- [Sora 影片生成](openai/examples/sora/sora2_prompting_guide.md)・1 篇

### 7. 用 AI 寫程式

- [Codex](openai/examples/codex/secure_quality_gitlab.md)・10 篇
- [軟體開發流程](openai/examples/third_party/Code_quality_and_security_scan_with_GitHub_Actions.md)・1 篇

### 8. 自己跑模型

- [開源模型（gpt-oss）](openai/articles/gpt-oss/handle-raw-cot.md)・8 篇
- 要 GPU 的篇（Colab）・10 篇
    - [用 fine-tuning 讓 gpt-oss 的韓文表現更好](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/fine-tune-korean.ipynb)
    - [在 Google Colab 上跑 gpt-oss-20b](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/run-colab.ipynb)
    - [用 gpt-oss 和 Hugging Face Transformers 做 fine-tuning](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/fine-tune-transfomers.ipynb)
    - [用 Transformers 跑 gpt-oss](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/run-transformers.ipynb)
    - [用 vLLM 跑 gpt-oss](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/articles/gpt-oss/run-vllm.ipynb)
    - [客製化 embedding](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/Customizing_embeddings.ipynb)
    - [交易資料的多類別分類](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/Multiclass_classification_for_transactions.ipynb)
    - [用 DALL·E 和 Segment Anything 建立動態 mask](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/dalle/How_to_create_dynamic_masks_with_DALL-E_and_Segment_Anything.ipynb)
    - [Fine-tuned Q&A：收集資料](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/fine-tuned_qa/olympics-1-collect-data.ipynb)
    - [用 CLIP embedding 搭配 GPT-4 Vision 強化多模態 RAG](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/openai/examples/custom_image_embedding_search.ipynb)

### 9. 平台整合範例

- [ChatGPT 應用](openai/articles/chatgpt-agents-sales-meeting-prep.md)・9 篇
- [GPT Actions 串接範例](openai/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc.md)・26 篇
- [合作夥伴範例](openai/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.md)・9 篇
- [其他](openai/articles/what_makes_documentation_good.md)・1 篇

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
