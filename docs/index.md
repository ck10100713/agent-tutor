# OpenAI Cookbook 繁中教材

## 建議閱讀順序

### 1. 打基礎

- [Token 計算](examples/How_to_count_tokens_with_tiktoken.md)・3 篇
- [對話格式](examples/Summarizing_long_documents.md)・2 篇
- [文字生成（Completions）](examples/Fine-tuned_classification.md)・49 篇
- [Responses API](examples/skills_in_api.md)・11 篇
- [Prompt 技巧](examples/Prompt_migration_guide.md)・3 篇

### 2. 讓模型用工具、會推理

- [Function calling](examples/o-series/o3o4-mini_prompting_guide.md)・1 篇
- [推理模型](examples/reasoning_function_calls.md)・1 篇
- [GPT-5 系列](examples/gpt-5/prompt-optimization-cookbook.md)・8 篇

### 3. 接上自己的資料

- [Embedding 與向量搜尋](examples/Clustering.md)・83 篇
- [知識圖譜](examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents.md)・1 篇

### 4. 做 Agent

- [Agent 開發](examples/agents_api/apps/sev_bot/README.md)・8 篇
- [Agents SDK](examples/agents_sdk/session_memory.md)・14 篇
- [MCP](examples/mcp/mcp_tool_guide.md)・3 篇
- [Assistants API](examples/Assistants_API_overview_python.md)・2 篇
- [Deep Research API](examples/deep_research_api/introduction_to_deep_research_api.md)・2 篇

### 5. 上線前

- [評估（Evals）](examples/multimodal/image_evals.md)・18 篇
- [安全防護與內容審查](examples/How_to_use_guardrails.md)・4 篇
- [微調（Fine-tuning）](examples/fine-tuned_qa/reinforcement_finetuning_healthbench.md)・3 篇
- [批次處理](examples/batch_processing.md)・1 篇
- [延遲優化](examples/Prompt_Caching101.md)・1 篇
- [用量 API](examples/completions_usage_api.md)・1 篇

### 6. 多模態

- [語音與音訊](examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.md)・12 篇
- [即時語音（Realtime）](examples/Realtime_eval_guide.md)・6 篇
- [影像理解（Vision）](examples/How_to_combine_GPT4o_with_RAG_Outfit_Assistant.md)・4 篇
- [圖片生成](examples/multimodal/document_and_multimodal_understanding_tips.md)・9 篇
- [Sora 影片生成](examples/sora/sora2_prompting_guide.md)・1 篇

### 7. 用 AI 寫程式

- [Codex](examples/codex/secure_quality_gitlab.md)・10 篇
- [軟體開發流程](examples/third_party/Code_quality_and_security_scan_with_GitHub_Actions.md)・1 篇

### 8. 自己跑模型

- [開源模型（gpt-oss）](articles/gpt-oss/handle-raw-cot.md)・8 篇
- 要 GPU 的篇（Colab）・10 篇
    - [用 fine-tuning 讓 gpt-oss 的韓文表現更好](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/articles/gpt-oss/fine-tune-korean.ipynb)
    - [在 Google Colab 上跑 gpt-oss-20b](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/articles/gpt-oss/run-colab.ipynb)
    - [用 gpt-oss 和 Hugging Face Transformers 做 fine-tuning](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/articles/gpt-oss/fine-tune-transfomers.ipynb)
    - [用 Transformers 跑 gpt-oss](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/articles/gpt-oss/run-transformers.ipynb)
    - [用 vLLM 跑 gpt-oss](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/articles/gpt-oss/run-vllm.ipynb)
    - [客製化 embedding](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/examples/Customizing_embeddings.ipynb)
    - [交易資料的多類別分類](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/examples/Multiclass_classification_for_transactions.ipynb)
    - [用 DALL·E 和 Segment Anything 建立動態 mask](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/examples/dalle/How_to_create_dynamic_masks_with_DALL-E_and_Segment_Anything.ipynb)
    - [Fine-tuned Q&A：收集資料](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/examples/fine-tuned_qa/olympics-1-collect-data.ipynb)
    - [用 CLIP embedding 搭配 GPT-4 Vision 強化多模態 RAG](https://colab.research.google.com/github/ck10100713/agent-tutor/blob/main/notebooks/examples/custom_image_embedding_search.ipynb)

### 9. 平台整合範例

- [ChatGPT 應用](articles/chatgpt-agents-sales-meeting-prep.md)・9 篇
- [GPT Actions 串接範例](examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc.md)・26 篇
- [合作夥伴範例](examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.md)・9 篇
- [其他](articles/what_makes_documentation_good.md)・1 篇
