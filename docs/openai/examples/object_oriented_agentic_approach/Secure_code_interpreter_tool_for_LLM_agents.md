---
translated: true
source: examples/object_oriented_agentic_approach/Secure_code_interpreter_tool_for_LLM_agents.ipynb
---
# 自己做 Code Interpreter：用 o3-mini 動態產生並執行 tool

> 原文：[examples/object_oriented_agentic_approach/Secure_code_interpreter_tool_for_LLM_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/Secure_code_interpreter_tool_for_LLM_agents.ipynb)



## 這篇在做什麼

讓 LLM 在 runtime 自己寫 Python 程式當 tool，再丟進一個鎖住網路的 Docker container 執行，用來分析交通事故的 CSV 資料。你會做出兩個 agent，一個負責讀檔，一個負責寫碼跑碼，兩邊權限刻意分開。

## 學完你會

- 用 Docker 建一個沒有網路、非 root 的隔離 Python 執行環境
- 用 BaseAgent、ToolInterface 這幾個 class 組出兩個權限分離的 agent，並接上自製的 code interpreter tool
- 用 o3-mini 加 `reasoning_effort` 讓模型針對沒預先定義過的問題，自己寫出分析程式並安全執行

## 開跑前

- 本機要裝好 Docker 並且在跑
- 本機要有 Python
- 要有 OpenAI API key，放環境變數或根目錄的 `.env`
- 範例資料用 [Key Factors Traffic Accidents](https://www.kaggle.com/datasets/willianoliveiragibin/key-factors-traffic-accidents)（Kaggle）

## 自己做 Code Interpreter：動態產生 tool 並執行

LLM agent 要跟外界或其他 agent 互動，核心是 tool（或 function）calling：LLM 帶著參數去呼叫一段程式。通常這些 function 是開發者事先寫好的，輸入輸出都固定。這篇換個比較彈性的做法：讓 LLM（這裡用 **o3-mini**）在 runtime **動態產生 tool**，再用 code interpreter 來執行。

### 動態產生 tool 搭配 Code Interpreter
動態產生的 tool 是 LLM 根據使用者的 prompt，在 runtime 自己寫出來的 function 或程式碼。你不用在程式裡預先列出每一種情境，解題的空間因此大很多。

動態 tool calling 更進一步，讓 LLM 可以即時產生 tool 並執行程式碼。適合這些工作：

- 資料分析與視覺化
- 資料處理與轉換
- 產生並執行 machine learning 流程
- 流程自動化與腳本
- 還有更多，要靠實驗慢慢發掘

### 用 o3-mini 動態產生 tool

o3-mini 在 2025/1/31 發布，STEM 能力很強，尤其是科學、數學和寫程式，同時保有小模型的低成本和低延遲。這篇會示範 o3-mini 怎麼寫 Python 程式來解讀資料、找出洞見。

Reasoning 模型很適合動態產生分析資料的 tool，因為它們自己會推理，不需要明確的 chain-of-thought prompt。事實上，在 prompt 裡硬塞 chain of thought 的指示，可能干擾模型內部的推理，結果反而變差。更多 o3-mini 的資訊看[這裡](https://openai.com/index/openai-o3-mini/)。

### 為什麼要自己做 code interpreter

很多 API 提供者（像 OpenAI 的 Assistants API）都內建 code interpreter。內建的很強，但有些情況開發者需要自己做，例如：

1. **語言或套件支援**：內建的 interpreter 可能不支援你要的程式語言（像 C++、Java）或套件。
2. **任務相容性**：你的用途可能跟提供者的內建方案不相容。
3. **模型限制**：你可能需要一個 interpreter 不支援的語言模型。
4. **成本考量**：程式執行或模型使用的收費方式可能不符合預算。
5. **檔案大小**：輸入資料太大，或 interpreter 不支援。
6. **整合內部系統**：提供者的 interpreter 可能接不到你的內部系統。

### 你會學到什麼
跟著這篇做，你會學到：

- 用 Docker 架設隔離的 Python 程式執行環境
- 設定自己的 code interpreter tool 給 LLM agent 用
- 把 agent 的職責清楚切開，兼顧安全
- 用 **o3-mini** 動態產生資料分析的程式碼
- 編排多個 agent 來完成任務
- 設計一個能動態產生並執行程式碼的 agent 應用

最後你會從零做出自訂的 code interpreter tool，讓 LLM 寫出複雜的程式，並在隔離環境裡安全執行，讓 AI 應用更彈性、更強，成本也更好控制。

### 範例情境

我們用 [Key Factors Traffic Accidents](https://www.kaggle.com/datasets/willianoliveiragibin/key-factors-traffic-accidents) 這份資料來回答一組問題。這些問題不用預先定義，LLM 會自己寫程式來回答。

問題可以像這樣：
- 哪些因素對事故頻率影響最大？（Feature importance analysis）
- 哪些地區事故風險最高？（Classification/Clustering）
- 罰款金額怎麼影響事故數量？（Regression/Causal inference）
- 能不能找出降低事故率的最佳罰款金額？（Optimization models）
- 高罰款是否跟較低的平均車速或較少的事故相關？（Correlation/Regression）
- 以此類推……

傳統的**預先定義 tool calling** 做法，開發者得為每個問題先寫好 function，LLM 就回答不了清單以外的問題。**動態 tool calling** 則讓 LLM 自己寫程式，再用 Code Interpreter tool 執行，就沒有這個限制。

## 總覽
來看怎麼做出這個動態產生 tool 的 agent 應用，分成三個部分：

#### Step 1：建立隔離的程式執行 container 環境

我們需要一個安全的環境來執行 LLM 產生的 function call。不要直接在主機上跑 LLM 產生的程式碼，所以建一個資源存取受限（例如沒有網路）的 Docker container。Docker container 預設不能存取主機的檔案系統，LLM 產生的程式碼因此被關在裡面。

##### ⚠️ 提醒：LLM 產生的程式碼要有強力的 guardrails
LLM 可能產生有害的程式碼，造成意料之外的後果。最佳做法是隔離執行環境，只開放任務需要的資源。不要在你的主機或筆電上直接跑 LLM 產生的程式碼。

#### Step 2：定義並測試 Agent

「**什麼是 Agent？**」在這篇裡，Agent 包含：
1. 一組給 LLM 遵循的指令，也就是 developer prompt
2. 一個 LLM 模型，以及透過 API 呼叫它的能力
3. 可以呼叫某個 function 的 tool 權限，以及執行該 function 的能力

我們會定義兩個 agent：
1. FileAccessAgent：讀檔，把內容當 context 交給 PythonCodeExecAgent。
2. PythonCodeExecAgent：產生 Python 程式碼來回答使用者的問題，並在 Docker container 裡執行。

#### Step 3：建立 Agentic Orchestration 來跑整個應用 
編排 agent 的方式有很多種，看應用需求而定。這篇用最簡單的：使用者給一個任務，agent 依序被呼叫來完成。  

整體的編排如下圖：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/oo_aa_image_1_code_interpreter_agents.png)

## 開始動手


### 前置需求
開始前，請確認主機上已安裝並設定好：

1. Docker：安裝好並在本機執行。更多資訊和[安裝方式看這裡](https://www.docker.com/)。 
2. Python：安裝在本機。更多資訊和[安裝方式看這裡](https://www.python.org/downloads/)。 
3. OpenAI API key：設成本機環境變數，或放在根目錄的 .env 檔。更多資訊和[設定方式看這裡](https://platform.openai.com/docs/api-reference/introduction)。 


### Step 1：建立隔離的程式執行環境 

先定義一個 Docker 化的 container 環境來執行程式碼。我在 `resources/docker` 目錄下寫好了 **[dockerfile](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/docker/dockerfile)**，用它建出的 container 環境規格如下：
- 以 Python 3.10 為基底 
- 使用非 root 使用者 
- 預先安裝 requirements.txt 裡的套件  

建 docker image 時用的 requirements.txt，包含 LLM 產生的程式碼可能用到的所有套件。因為我們會禁止 container 連網，所以任務需要的套件都要預先裝好。基於安全考量，LLM 不能自己再安裝其他套件。 

你可以自己建 docker image，裝好需要的語言環境（像 Python 3.10）和套件，也可以做出針對其他語言（像 Java、C++）和套件的客製 docker image。

用下面的指令建 docker image。為了簡短，我把輸出導給 grep，只印成功訊息，建置失敗時才印失敗訊息。

```python
!docker build -t python_sandbox:latest ./resources/docker 2>&1 | grep -E "View build details|ERROR" || echo "Build failed."
```

??? note "輸出"

    ```text
    View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/kl8fo02q7rgbindi9b42pn1zr
    ```

接著用受限模式跑 container，它會在背景執行。這裡正是設定 container 安全策略的時機。好的做法是只開放任務必需的最少功能。container 內預設不能存取主機檔案系統，我們再限制它的網路，讓它連不到網際網路或其他網路資源。 

```python
# Run the container in restricted mode. The container will run in the background.
!docker run -d --name sandbox --network none --cap-drop all --pids-limit 64 --tmpfs /tmp:rw,size=64M   python_sandbox:latest sleep infinity
```

??? note "輸出"

    ```text
    8446d1e9a7972f2e00a5d1799451c1979d34a2962aa6b4c35a9868af8d321b0e
    ```

用 `docker ps` 確認 container 有在跑，應該會列出我們的 container。 

```python
!docker ps
```

??? note "輸出"

    ```text
    CONTAINER ID   IMAGE                   COMMAND            CREATED         STATUS         PORTS     NAMES
    8446d1e9a797   python_sandbox:latest   "sleep infinity"   2 seconds ago   Up 2 seconds             sandbox
    ```

### Step 2：定義並測試 Agent

我們定義兩個 agent。 
1.	**Agent 1：File Access Agent（用預先定義的 tool calling）**
- 有指令去理解檔案內容，並把內容當 context 提供給 Agent 2。
- 可以存取主機的檔案系統。 
- 可以讀主機上的檔案，並複製進 Docker container。
- 不能使用 code interpreter tool。
- 使用 gpt-4o 模型。

2.	**Agent 2：Python Code Generator and Executor（用動態產生的 tool calling 和程式執行）**
- 從 Agent 1 收到檔案內容的 context。
- 有指令產生 Python 腳本來回答使用者的問題。
- 可以使用 Docker container 內的 code interpreter 執行 Python 程式碼。 
- 只能存取 Docker container 裡的檔案系統（不能碰主機）。
- 不能存取主機檔案系統或網路。
- 使用我們最新、擅長寫程式的 **o3-mini** 模型。

把檔案存取（Agent 1）和程式碼產生與執行（Agent 2）這兩個職責分開，是避免 LLM 直接存取或修改主機的關鍵。 


**Agent 1 有主機檔案系統的存取權，所以只能用靜態 tool calling。**  


| Agent | Type of Tool Call | Access to Host File System | Access to Docker Container File System | Access to Code Interpreter |
|-------|-------------------|----------------------------|----------------------------------------|----------------------------|
| Agent 1: File Access | Pre-defined Tools | Yes | Yes | No |
| Agent 2: Python Code Generator and Executor | Dynamically Generated Tools | No | Yes | Yes |


為了讓 agent 和 tool 好管理，我們用物件導向的原則定義了一組**核心 class**，兩個 agent 都靠它們建出來，介面才會一致。

- **BaseAgent**：一個抽象基底 class，規定共同的方法簽名，例如 `task()`。基底 class 也提供 debug 用的 logger、語言模型介面，以及 `add_context()` 這類共用功能，用來給 agent 加 context。 
- **ChatMessages**：用來存對話歷史的 class，因為 ChatCompletions API 是 stateless 的。 
- **ToolManager**：管理 agent 可以呼叫哪些 tool 的 class。
- **ToolInterface**：任何 agent 可呼叫的 'tool' 的抽象 class，讓所有 tool 有一致的介面。

這些 class 定義在 [object_oriented_agents/core_classes](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/object_oriented_agents/core_classes) 目錄。 

#### 核心 Class 的 UML Class Diagram
下面的 class diagram 顯示核心 class 之間的關係。這張 UML（Unified Modeling Language）是用 [Mermaid](https://mermaid) 產生的。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/oo_aa_image_2_uml_diagram.png)

**定義 Agent 1：搭配 FileAccessTool 的 FileAccessAgent**

先定義繼承自 ToolInterface 的 FileAccessTool。**FileAccessTool** 定義在 `resources/registry/tools` 目錄的 [file_access_tool.py](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/registry/tools/file_access_tool.py)。

- FileAccessTool 實作 ToolInterface，確保所有 tool 有一致的介面。 
- 在 `get_definition` 方法裡綁定 OpenAI Function Calling API 用的 tool 定義，再加上 tool 的 `run` 方法，好維護、好擴充、可重複使用。 

接著定義 **FileAccessAgent**，它繼承 BaseAgent，並綁定 **FileAccessTool**。FileAccessAgent 定義在 `resources/registry/agents` 目錄的 [file_access_agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/registry/agents/file_access_agent.py)。FileAccessAgent：

- 是 BaseAgent 的具體實作。 
- 用 developer prompt、模型名稱、logger 和語言模型介面初始化，開發者需要時可以覆寫這些值。 
- 有 setup_tools 方法，把 FileAccessTool 註冊到 tool manager。 
- 有 `task` 方法，呼叫 FileAccessTool 讀檔，並把 context 提供給 PythonCodeExecAgent。 
- 用 `model_name='gpt-4o'`，推理和 tool calling 能力足夠應付這個任務。


**定義 Agent 2：搭配 PythonExecTool 的 PythonExecAgent**  

同樣地，PythonExecTool 繼承 ToolInterface，實作 get_definition 和 run 方法。get_definition 回傳 OpenAI Function Calling API 要的 tool 定義格式。run 方法在 Docker container 裡執行 Python 程式碼並回傳輸出。這個 tool 定義在 `resources/registry/tools` 目錄的 [python_code_interpreter_tool.py](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/registry/tools/python_code_interpreter_tool.py)。

PythonExecAgent 同樣是 BaseAgent 的具體實作，定義在 `resources/registry/agents` 目錄的 [python_code_exec_agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/object_oriented_agentic_approach/resources/registry/agents/python_code_exec_agent.py)。PythonExecAgent：

- 是 BaseAgent 的具體實作。 
- 用 developer prompt、模型名稱、logger 和語言模型介面初始化，開發者需要時可以覆寫這些值。 
- 有 setup_tools 方法，把 PythonExecTool 註冊到 tool manager。 
- 有 `task` 方法，呼叫 OpenAI API 執行使用者的任務，這裡就是產生 Python 腳本回答使用者的問題，並用 Code Interpreter tool 執行。 
- 用 `model_name='o3-mini'`，擅長寫程式這類 STEM 任務。
- 用 `reasoning_effort='high'`，因為任務複雜，讓模型想得更完整，代價是產生更多 token、回應更慢。預設是 medium，在速度和推理準確度之間取平衡。

更多 `reasoning_effort` 參數的資訊看[這裡](https://platform.openai.com/docs/guides/reasoning)。

### Step 3：建立 Agentic Orchestration 來跑整個應用 

agent 都定義好了，接著定義跑整個應用的 orchestration loop。這個 loop 會請使用者輸入問題或任務，然後呼叫 FileAccessAgent 讀檔並把 context 交給 PythonExecAgent。PythonExecAgent 產生 Python 程式碼回答使用者的問題，並在 Docker container 裡執行，執行輸出再顯示給使用者。

使用者輸入 'exit' 就會結束應用。我們的問題是：**哪些因素對事故頻率影響最大？** 注意我們沒有預先定義任何 function 來回答這個問題。



```python
# Import the agents from registry/agents

from resources.registry.agents.file_access_agent import FileAccessAgent
from resources.registry.agents.python_code_exec_agent import PythonExecAgent


prompt = """Use the file traffic_accidents.csv for your analysis. The column names are:
Variable	Description
accidents	Number of recorded accidents, as a positive integer.
traffic_fine_amount	Traffic fine amount, expressed in thousands of USD.
traffic_density	Traffic density index, scale from 0 (low) to 10 (high).
traffic_lights	Proportion of traffic lights in the area (0 to 1).
pavement_quality	Pavement quality, scale from 0 (very poor) to 5 (excellent).
urban_area	Urban area (1) or rural area (0), as an integer.
average_speed	Average speed of vehicles in km/h.
rain_intensity	Rain intensity, scale from 0 (no rain) to 3 (heavy rain).
vehicle_count	Estimated number of vehicles, in thousands, as an integer.
time_of_day	Time of day in 24-hour format (0 to 24).
accidents	traffic_fine_amount
"""


print("Setup: ")
print(prompt)

print("Setting up the agents... ")

# Instantiate the agents with the default constructor defined values
# Developer may override the default values - prompt, model, logger, and language model interface if needed

# This agent use gpt-4o by default
file_ingestion_agent = FileAccessAgent()

# Let's make sure agent uses o3-mini model and set the reasoning_effort to high
data_analysis_agent = PythonExecAgent(model_name='o3-mini', reasoning_effort='high')

print("Understanding the contents of the file...")
# Give a task to the file ingestion agent to read the file and provide the context to the data analysis agent 
file_ingestion_agent_output = file_ingestion_agent.task(prompt)

# Add the file content as context to the data analysis agent
# The context is added to the agent's tool manager so that the tool manager can use the context to generate the code 

data_analysis_agent.add_context(prompt)
data_analysis_agent.add_context(file_ingestion_agent_output)

while True:

    print("Type your question related to the data in the file. Type 'exit' to exit.")
    user_input = input("Type your question.")

    if user_input == "exit":
        print("Exiting the application.")
        break

    print(f"User question: {user_input}")

    print("Generating dynamic tools and using code interpreter...")
    data_analysis_agent_output = data_analysis_agent.task(user_input)

    print("Output...")
    print(data_analysis_agent_output)
```

??? note "輸出"

    ```text
    Setup: 
    Use the file traffic_accidents.csv for your analysis. The column names are:
    Variable	Description
    accidents	Number of recorded accidents, as a positive integer.
    traffic_fine_amount	Traffic fine amount, expressed in thousands of USD.
    traffic_density	Traffic density index, scale from 0 (low) to 10 (high).
    traffic_lights	Proportion of traffic lights in the area (0 to 1).
    pavement_quality	Pavement quality, scale from 0 (very poor) to 5 (excellent).
    urban_area	Urban area (1) or rural area (0), as an integer.
    average_speed	Average speed of vehicles in km/h.
    rain_intensity	Rain intensity, scale from 0 (no rain) to 3 (heavy rain).
    vehicle_count	Estimated number of vehicles, in thousands, as an integer.
    time_of_day	Time of day in 24-hour format (0 to 24).
    accidents	traffic_fine_amount

    Setting up the agents... 
    Understanding the contents of the file...
    ```

    ```text
    2025-02-03 13:03:54,066 - MyApp - INFO - Handling tool call: safe_file_access
    2025-02-03 13:03:54,067 - MyApp - INFO - Tool arguments: {'filename': './resources/data/traffic_accidents.csv'}
    2025-02-03 13:03:54,562 - MyApp - INFO - Tool 'safe_file_access' response: Copied ./resources/data/traffic_accidents.csv into sandbox:/home/sandboxuser/.
    The file content for the first 15 rows is:
        accidents  traffic_fine_amount  traffic_density  traffic_lights  pavement_quality  urban_area  average_speed  rain_intensity  vehicle_count  time_of_day
    0          20               4.3709           2.3049         753.000            0.7700           1        321.592          1.1944       290.8570     160.4320
    1          11               9.5564           3.2757           5.452            4.0540           1        478.623          6.2960       931.8120       8.9108
    2          19               7.5879           2.0989           6.697          345.0000           0        364.476          2.8584       830.0860       5.5727
    3          23               6.3879           4.9188           9.412            4.7290           0         20.920          2.1065       813.1590     131.4520
    4          23               2.4042           1.9610           7.393            1.7111           1         37.378          1.7028         1.4663       6.9610
    5          31               2.4040           6.7137           5.411            5.9050           1        404.621          1.8936       689.0410       8.1801
    6          29               1.5228           5.2316           9.326            2.3785           1         16.292          2.5213       237.9710      12.6622
    7          18               8.7956           8.9864           4.784            1.9984           0        352.566          1.9072       968.0670       8.0602
    8          15               6.4100           1.6439           5.612            3.6090           1        217.198          3.4380       535.4440       8.2904
    9          22               7.3727           8.0411           5.961            4.7650           1        409.261          2.0919       569.0560     203.5910
    10         28               1.1853           7.9196           0.410            3.7678           1        147.689          1.6946       362.9180     224.1580
    11         17               9.7292           1.2718           8.385            8.9720           0         46.888          2.8990       541.3630     198.5740
    12         14               8.4920           3.9856           1.852            4.6776           0        287.393          2.2012        75.2240       2.3728
    13         21               2.9111           1.7015           5.548            1.9607           1        176.652          1.0320       566.3010       6.9538
    14         22               2.6364           2.5472           7.222            2.3709           0        209.686          4.0620        64.4850     170.7110
    ```

    ```text
    Type your question related to the data in the file. Type 'exit' to exit.
    User question: What factors contribute the most to accident frequency?
    Generating dynamic tools and using code interpreter...
    ```

    ```text
    2025-02-03 13:04:39,427 - MyApp - INFO - Handling tool call: execute_python_code
    2025-02-03 13:04:39,429 - MyApp - INFO - Tool arguments: {'python_code': "import pandas as pd\nimport numpy as np\nfrom sklearn.linear_model import LinearRegression\nfrom sklearn.preprocessing import StandardScaler\nimport matplotlib.pyplot as plt\nimport seaborn as sns\n\n# Load the dataset\nfile_path = '/home/sandboxuser/traffic_accidents.csv'\ndf = pd.read_csv(file_path)\n\n# Show basic information\nprint('Dataset shape:', df.shape)\nprint('First few rows:')\nprint(df.head(), '\\n')\nprint('Columns:', df.columns.tolist(), '\\n')\n\n# Correlation matrix analysis\ncorr_matrix = df.corr()\nprint('Correlation matrix:')\nprint(corr_matrix, '\\n')\n\n# Correlation of each feature with accidents\nacc_corr = corr_matrix['accidents'].drop('accidents').sort_values(key=lambda x: abs(x), ascending=False)\nprint('Correlation of other variables with accidents (sorted by absolute correlation):')\nprint(acc_corr, '\\n')\n\n# Visualize the correlation matrix\nplt.figure(figsize=(10, 8))\nsns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt='.2f')\nplt.title('Correlation Matrix')\nplt.tight_layout()\nplt.savefig('correlation_matrix.png')\nplt.close()\n\n# Prepare data for regression analysis\n# Exclude target variable 'accidents'\nfeatures = [col for col in df.columns if col != 'accidents']\nX = df[features]\ny = df['accidents']\n\n# Standardize the features to compare the regression coefficients on the same scale\nscaler = StandardScaler()\nX_scaled = scaler.fit_transform(X)\n\n# Fit a linear regression model\nmodel = LinearRegression()\nmodel.fit(X_scaled, y)\n\n# Gather coefficients along with feature names\ncoef = model.coef_\ncoef_df = pd.DataFrame({'Feature': features, 'Coefficient': coef})\ncoef_df['AbsCoefficient'] = coef_df['Coefficient'].abs()\ncoef_df = coef_df.sort_values(by='AbsCoefficient', ascending=False)\nprint('Linear Regression Coefficients (using standardized features):')\nprint(coef_df[['Feature', 'Coefficient']], '\\n')\n\n# Additionally, compute feature importances using a Random Forest regressor\nfrom sklearn.ensemble import RandomForestRegressor\nrf = RandomForestRegressor(random_state=42)\nrf.fit(X, y)\nrf_importance = rf.feature_importances_\nrf_df = pd.DataFrame({'Feature': features, 'Importance': rf_importance})\nrf_df = rf_df.sort_values(by='Importance', ascending=False)\nprint('Random Forest Feature Importances:')\nprint(rf_df, '\\n')\n\n# The printed outputs will help in understanding which factors contribute most to accident frequency.\n\n# For clarity, save the coefficients and importances to CSV files (optional)\ncoef_df.to_csv('linear_regression_coefficients.csv', index=False)\nrf_df.to_csv('random_forest_importances.csv', index=False)\n\n# End of analysis\n"}
    2025-02-03 13:04:43,123 - MyApp - INFO - Tool 'execute_python_code' response: Dataset shape: (8756, 10)
    First few rows:
       accidents  traffic_fine_amount  ...  vehicle_count  time_of_day
    0         20               4.3709  ...       290.8570     160.4320
    1         11               9.5564  ...       931.8120       8.9108
    2         19               7.5879  ...       830.0860       5.5727
    3         23               6.3879  ...       813.1590     131.4520
    4         23               2.4042  ...         1.4663       6.9610

    [5 rows x 10 columns] 

    Columns: ['accidents', 'traffic_fine_amount', 'traffic_density', 'traffic_lights', 'pavement_quality', 'urban_area', 'average_speed', 'rain_intensity', 'vehicle_count', 'time_of_day'] 

    Correlation matrix:
                         accidents  traffic_fine_amount  ...  vehicle_count  time_of_day
    accidents             1.000000            -0.745161  ...       0.068399     0.101995
    traffic_fine_amount  -0.745161             1.000000  ...      -0.016610    -0.006236
    traffic_density      -0.059265            -0.004365  ...      -0.014244     0.002806
    traffic_lights       -0.026642             0.009056  ...       0.001373    -0.001971
    pavement_quality      0.064694            -0.021229  ...       0.007840     0.000055
    urban_area            0.145092            -0.005136  ...      -0.006053    -0.006320
    average_speed         0.093923             0.009151  ...       0.000777    -0.005338
    rain_intensity       -0.091673            -0.015302  ...      -0.025933    -0.013446
    vehicle_count         0.068399            -0.016610  ...       1.000000    -0.009303
    time_of_day           0.101995            -0.006236  ...      -0.009303     1.000000

    [10 rows x 10 columns] 

    Correlation of other variables with accidents (sorted by absolute correlation):
    traffic_fine_amount   -0.745161
    urban_area             0.145092
    time_of_day            0.101995
    average_speed          0.093923
    rain_intensity        -0.091673
    vehicle_count          0.068399
    pavement_quality       0.064694
    traffic_density       -0.059265
    traffic_lights        -0.026642
    ... (省略 25 行)
    ```

    ```text
    Output...
    The analysis shows that one variable stands out by far:

    • Both the simple correlation analysis and regression results indicate that traffic_fine_amount is the dominant factor—its correlation with accidents is strong (about –0.75), and in the standardized linear regression its coefficient is the largest in magnitude (around –3.89). The negative sign suggests that, in this data, higher fine amounts are associated with fewer accidents (which might reflect more stringent enforcement or deterrence).

    Other findings include:

    • The Random Forest model also ranks traffic_fine_amount as most important (importance ≈ 0.58), with the next most influential factor being traffic_density (importance ≈ 0.17). Although its simple correlation with accidents is lower, traffic_density may contribute non‐linearly.

    • Additional factors like urban_area, average_speed, rain_intensity, and time_of_day have moderate associations (with linear model coefficients ranging between about ±0.5 to +0.74). These suggest that accidents tend to be somewhat higher in urban areas and vary with time of day and weather conditions, but their overall impact is much less than that of traffic fine amounts.

    In summary, the data analysis indicates that traffic_fine_amount contributes the most to accident frequency—with higher fines linked to fewer recorded accidents—while factors such as traffic density, urban area status, vehicle speed, rain intensity, and time of day also play secondary roles.
    Type your question related to the data in the file. Type 'exit' to exit.
    Exiting the application.
    ```

在這個例子裡，**o3-mini** 根據使用者的問題動態產生了 tool（一支 Python 腳本）來分析資料。可以看到 **o3-mini** 用了好幾種方法檢視問題，像是 correlation analysis、linear regression 和 random forest 模型。這顯示了：

**reasoning_effort**：模型推理的深度，例如這裡嘗試的方法數量，通常會隨著參數從 low、medium 調到 high 而增加。你可以試試不同等級，看差異。

**動態產生 tool calling**：分析資料的 tool（Python 腳本）不是開發者手寫或事先決定的，而是 o3-mini 在 runtime 產生了資料探索和相關性分析的程式碼。

**隔離的程式執行**：為了安全，避免在主機上跑不可信的程式碼，這支 Python 腳本是透過 `execute_python_code` tool 在 Docker container 裡執行的。container 的資源存取受限（例如沒有網路、檔案系統存取有限），把執行任意程式碼的風險降到最低。


### 結論

這篇示範如何針對特定應用需求，開發**自訂的 code interpreter**，解決廠商方案常見的限制，像是語言限制、成本考量，以及想搭配不同 LLM 或模型的彈性需求。

**管理 Agent 和 Tool 的方式**：我們也定義了一組核心 class 來管理 agent 和 tool，讓它們有一致的介面，可以跨應用重複使用。你可以建一個像 [registry](https://github.com/openai/openai-cookbook/tree/main/examples/object_oriented_agentic_approach/resources/registry) 資料夾這樣的倉庫來管理 agent 和 tool。

**o3-mini 模型**：我們展示了 o3-mini 能根據使用者很簡短的 prompt，在 runtime 產生複雜的程式碼來分析資料，之後還能針對分析結果推理，向使用者解釋。

最後回顧一下，建立動態 tool calling 的 agent 應用有三步：
1. 建立隔離的程式執行 container 環境
2. 定義並測試 Agent
3. 建立 Agentic Orchestration 來跑整個應用

我們談了隔離程式執行環境的重要性，這樣才能確保安全，不在主機上跑不可信的程式碼。以 CSV 檔為例，我們示範了動態產生 tool（一支 Python 腳本）來分析資料、回答使用者的問題，也示範了在 Docker container 裡執行程式碼，再把結果回傳給使用者。

## 重點整理

- 動態 tool calling 讓 LLM 在 runtime 自己寫 tool，不必為每個問題預先寫 function。
- LLM 產生的程式碼一定要關進隔離環境，這篇的做法是 Docker、非 root、不開網路、套件預先裝好。
- 把有主機檔案存取權的 agent（只用靜態 tool）和能跑動態程式碼的 agent 分開，這是安全設計的核心。
- 用 BaseAgent、ToolManager、ToolInterface 這類 class 統一介面，agent 和 tool 才好重複使用。
- Reasoning 模型不需要 chain-of-thought prompt，`reasoning_effort` 越高，通常會嘗試越多分析方法。

## 練習

1. 把 PythonExecAgent 的 `reasoning_effort` 從 `high` 改成 `low`，用同一個問題再跑一次，比較模型嘗試了幾種分析方法。
2. 把問題改成「罰款金額跟事故數量有沒有相關？」，看 o3-mini 這次產生什麼樣的程式，不用改任何 tool。
3. 在跑 container 的指令裡拿掉網路限制，讓 container 能連網，想想這會多出哪些風險，再恢復原狀。
