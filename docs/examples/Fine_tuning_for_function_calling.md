---
translated: true
source: examples/Fine_tuning_for_function_calling.ipynb
---
# Function calling 的 fine-tuning

> 原文：[examples/Fine_tuning_for_function_calling.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Fine_tuning_for_function_calling.ipynb)

## 這篇在做什麼

以一個無人機 copilot 為例，示範怎麼用 fine-tuning 提升 function calling 的準確度和穩定性。先量測 `gpt-3.5-turbo` 的基準表現，再只靠 function 清單用 `gpt-4o` 合成訓練資料，最後 fine-tune 並評估。

## 學完你會

- 設計測試 prompt，找出模型在「幾乎可行但其實做不到」的請求上會錯誤呼叫 function
- 從 function 定義自動列出所有可能的呼叫組合，並用 `gpt-4o` 產生對應的 prompt，組成合成訓練資料
- 啟動 fine-tuning job、查詢狀態與指標，並用 reject 的比例評估微調後的模型

## 開跑前

- 需要 OpenAI API key
- fine-tuning job 和 `gpt-4o` 產生資料都會產生費用

這份 notebook 說明怎麼用 fine-tuning 來提升 function calling 的準確度和可靠度。function calling 的更多資訊看[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)，fine-tuning 的更多資訊看[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_finetune_chat_models.ipynb)


補充背景，引用上面 function calling notebook 的說明：

> `tools` 是 Chat Completion API 的選用參數，可以用來提供 function 規格。目的是讓模型產生符合所提供規格的 function 參數。注意 API 不會真的執行任何 function call，要由開發者用模型的輸出自己執行 function call。


function calling 在按預期運作時非常強大。但我們發現，隨著 function 數量增加、任務變複雜，function calling 會變得比較不準（例如更多幻覺出來的呼叫、錯誤的呼叫）。

在為 function calling 做 fine-tuning 之前，最好先從這些做起：

- 改善 function 的定義：寫得更清楚，彼此更容易區分。
- 試試 prompt engineering：通常更詳細的 prompt 能幫模型呼叫對的 function。

_如果_上面這些步驟沒辦法把 function calling 改善到令人滿意的程度，才考慮為 function calling 做 fine-tuning。


### 概覽


這份 notebook 有三個部分

- **評估基準的 function calling 表現：** 評估現成的 `gpt-3.5-turbo` 模型在我們給定的 function 上的表現（假設因為延遲和成本，無人機 copilot 不能用 `gpt-4o`）
- **產生合成資料：** 用 `gpt-4o` 建立一組「黃金」的 prompt 和 function 呼叫，當成訓練資料
- **Fine-tuning：** 執行 fine-tuning job，並評估微調後的模型


注意：_這份 notebook 示範只靠一份 function 清單，怎麼建立 function calling fine-tuning 用的合成訓練資料。真實世界的正式環境測試 eval 比較好，但這個方法效果很不錯，也可以和真實世界的訓練資料搭配使用。_


# 取得 function calling 的基準表現


```python
#!pip install tenacity -q
#!pip install openai -q
#!pip install typing -q
# !pip install python-dotenv
```

```python
import numpy as np
import json
import os
from IPython.display import display
import pandas as pd
from openai import OpenAI
import itertools
import time
import base64
from tenacity import retry, wait_random_exponential, stop_after_attempt
from typing import Any, Dict, List, Generator
import ast

%load_ext dotenv
%dotenv

client = OpenAI(api_key=os.environ.get("OPENAI_BUILD_HOUR_KEY"))
```

??? note "輸出"

    ```text
    The dotenv extension is already loaded. To reload it, use:
      %reload_ext dotenv
    ```

### 工具函式


先定義呼叫 Chat Completions API 的工具函式，一個取得 completion，一個取得 function call。


```python
def get_chat_completion(
    messages: list[dict[str, str]],
    model: str = "gpt-3.5-turbo",
    max_tokens=500,
    temperature=0.0,
    stop=None,
    tools=None,
    seed=42,
    functions=None,
    tool_choice=None,
) -> str:
    params = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stop": stop,
        "tools": tools,
        "seed": seed,
        "tool_choice": tool_choice,
    }
    if functions:
        params["functions"] = functions

    completion = client.chat.completions.create(**params)
    return completion.choices[0].message, completion.usage


def eval(model: str, system_prompt: str, function_list, prompts_to_expected_tool_name):
    """
    Evaluate the performance of a model in selecting the correct function based on given prompts.

    Args:
        model (str): The name of the model to be evaluated.
        system_prompt (str): The system prompt to be used in the chat completion.
        function_list (list): A list of functions that the model can call.
        prompts_to_expected_tool_name (dict): A dictionary mapping prompts to their expected function names.

    Returns:
        None
    """

    prompts_to_actual = []
    latencies = []
    tokens_used = []

    for prompt, expected_function in prompts_to_expected_tool_name.items():
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        start_time = time.time()
        completion, usage = get_chat_completion(
            model=model,
            messages=messages,
            seed=42,
            tools=function_list,
            temperature=0.0,
            tool_choice="required",
        )
        end_time = time.time()

        latency = (end_time - start_time) * 1000  # convert to milliseconds
        latencies.append(latency)

        prompts_to_actual.append(
            {prompt: completion.tool_calls[0].function.name})

        # Calculate tokens used
        tokens_used.append(usage.total_tokens)

    total_prompts = len(prompts_to_expected_tool_name)

    # Calculate the number of matches
    matches = sum(
        1
        for result in prompts_to_actual
        if list(result.values())[0]
        == prompts_to_expected_tool_name[list(result.keys())[0]]
    )
    match_percentage = (matches / total_prompts) * 100

    # Calculate average latency
    avg_latency = sum(latencies) / total_prompts
    # Calculate average tokens used
    avg_tokens_used = sum(tokens_used) / total_prompts

    # Create a DataFrame to store the results
    results_df = pd.DataFrame(columns=["Prompt", "Expected", "Match"])

    results_list = []
    for result in prompts_to_actual:
        prompt = list(result.keys())[0]
        actual_function = list(result.values())[0]
        expected_function = prompts_to_expected_tool_name[prompt]
        match = actual_function == expected_function
        results_list.append(
            {
                "Prompt": prompt,
                "Actual": actual_function,
                "Expected": expected_function,
                "Match": "Yes" if match else "No",
            }
        )
    results_df = pd.DataFrame(results_list)

    def style_rows(row):
        match = row["Match"]
        background_color = "red" if match == "No" else "white"
        return ["background-color: {}; color: black".format(background_color)] * len(
            row
        )

    styled_results_df = results_df.style.apply(style_rows, axis=1)

    # Display the DataFrame as a table
    display(styled_results_df)

    print(
        f"Number of matches: {matches} out of {total_prompts} ({match_percentage:.2f}%)"
    )
    print(f"Average latency per request: {avg_latency:.2f} ms")
    print(f"Average tokens used per request: {avg_tokens_used:.2f}")
```

### 基準測試


我們來做一個智慧型無人機 copilot。我們希望能對 copilot 下指令，讓它呼叫該指令對應的 function，或是在指令不可行時拒絕這個請求。
先為 copilot 定義 system prompt。


```python
DRONE_SYSTEM_PROMPT = """You are an intelligent AI that controls a drone. Given a command or request from the user,
call one of your functions to complete the request. If the request cannot be completed by your available functions, call the reject_request function.
If the request is ambiguous or unclear, reject the request."""
```

接著定義 copilot 能執行的所有動作對應的 function。


```python
function_list = [
    {
        "type": "function",
        "function": {
            "name": "takeoff_drone",
            "description": "Initiate the drone's takeoff sequence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "altitude": {
                        "type": "integer",
                        "description": "Specifies the altitude in meters to which the drone should ascend.",
                    }
                },
                "required": ["altitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "land_drone",
            "description": "Land the drone at its current location or a specified landing point.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "enum": ["current", "home_base", "custom"],
                        "description": "Specifies the landing location for the drone.",
                    },
                    "coordinates": {
                        "type": "object",
                        "description": "GPS coordinates for custom landing location. Required if location is 'custom'.",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_drone_movement",
            "description": "Direct the drone's movement in a specific direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["forward", "backward", "left", "right", "up", "down"],
                        "description": "Direction in which the drone should move.",
                    },
                    "distance": {
                        "type": "integer",
                        "description": "Distance in meters the drone should travel in the specified direction.",
                    },
                },
                "required": ["direction", "distance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_drone_speed",
            "description": "Adjust the speed of the drone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "speed": {
                        "type": "integer",
                        "description": "Specifies the speed in km/h. Valid range is 0 to 100.",
                        "minimum": 0,
                    }
                },
                "required": ["speed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_camera",
            "description": "Control the drone's camera to capture images or videos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["photo", "video", "panorama"],
                        "description": "Camera mode to capture content.",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Duration in seconds for video capture. Required if mode is 'video'.",
                    },
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_gimbal",
            "description": "Adjust the drone's gimbal for camera stabilization and direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tilt": {
                        "type": "integer",
                        "description": "Tilt angle for the gimbal in degrees.",
                    },
                    "pan": {
                        "type": "integer",
                        "description": "Pan angle for the gimbal in degrees.",
                    },
                },
                "required": ["tilt", "pan"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_drone_lighting",
            "description": "Control the drone's lighting for visibility and signaling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["on", "off", "blink", "sos"],
                        "description": "Lighting mode for the drone.",
                    }
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "return_to_home",
            "description": "Command the drone to return to its home or launch location.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_battery_saver_mode",
            "description": "Toggle battery saver mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Toggle battery saver mode.",
                    }
                },
                "required": ["status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_obstacle_avoidance",
            "description": "Configure obstacle avoidance settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Toggle obstacle avoidance.",
                    }
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_follow_me_mode",
            "description": "Enable or disable 'follow me' mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Toggle 'follow me' mode.",
                    }
                },
                "required": ["status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calibrate_sensors",
            "description": "Initiate calibration sequence for drone's sensors.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_autopilot",
            "description": "Enable or disable autopilot mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["on", "off"],
                        "description": "Toggle autopilot mode.",
                    }
                },
                "required": ["status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "configure_led_display",
            "description": "Configure the drone's LED display pattern and colors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "enum": ["solid", "blink", "pulse", "rainbow"],
                        "description": "Pattern for the LED display.",
                    },
                    "color": {
                        "type": "string",
                        "enum": ["red", "blue", "green", "yellow", "white"],
                        "description": "Color for the LED display. Not required if pattern is 'rainbow'.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_home_location",
            "description": "Set or change the home location for the drone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "coordinates": {
                        "type": "object",
                        "description": "GPS coordinates for the home location.",
                    }
                },
                "required": ["coordinates"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reject_request",
            "description": "Use this function if the request is not possible.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
```

先看看 function calling 在一些直截了當的可行 prompt 上表現如何，再加幾個明顯不可能、應該呼叫 'reject_request' function 的請求。


```python
straightforward_prompts_to_expected = {
    "Land the drone at the home base": "land_drone",
    "Take off the drone to 50 meters": "takeoff_drone",
    "Change speed to 15 kilometers per hour": "set_drone_speed",
    "Turn into an elephant!": "reject_request",
    "Move the drone forward by 10 meters": "control_drone_movement",
    "I want the LED display to blink in red": "configure_led_display",
    "Can you take a photo?": "control_camera",
    "Can you detect obstacles?": "set_obstacle_avoidance",
    "Can you dance for me?": "reject_request",
    "Can you follow me?": "set_follow_me_mode",
}
```

```python
# Evaluate the model with the given prompts
eval(
    model="gpt-3.5-turbo",
    system_prompt=DRONE_SYSTEM_PROMPT,
    function_list=function_list,
    prompts_to_expected_tool_name=straightforward_prompts_to_expected,
)
```

??? note "輸出"

    ```text
    <pandas.io.formats.style.Styler at 0x13d068690>
    ```

    ```text
    Number of matches: 10 out of 10 (100.00%)
    Average latency per request: 826.81 ms
    Average tokens used per request: 796.20
    ```

不錯！模型對這些請求的表現相當好。現在試一些更難的請求：和無人機有關、_幾乎_可行，但無人機其實做不到，所以 pilot 應該拒絕的請求。


```python
challenging_prompts_to_expected = {
    "Play pre-recorded audio message": "reject_request",
    "Initiate following on social media": "reject_request",
    "Scan environment for heat signatures": "reject_request",
    "Bump into obstacles": "reject_request",
    "Change drone's paint job color": "reject_request",
    "Coordinate with nearby drones": "reject_request",
    "Change speed to negative 120 km/h": "reject_request",
    "Detect a person": "reject_request",
    "Please enable night vision": "reject_request",
    "Report on humidity levels around you": "reject_request",
}
```

```python
# Evaluate the model with the challenging prompts
eval(
    model="gpt-3.5-turbo",
    function_list=function_list,
    system_prompt=DRONE_SYSTEM_PROMPT,
    prompts_to_expected_tool_name=challenging_prompts_to_expected,
)
```

??? note "輸出"

    ```text
    <pandas.io.formats.style.Styler at 0x13c592190>
    ```

    ```text
    Number of matches: 6 out of 10 (60.00%)
    Average latency per request: 610.26 ms
    Average tokens used per request: 791.90
    ```

現在遇到問題了。
依照現有的 function，這些請求不可能、互相衝突或有歧義，模型應該全部拒絕，但它卻去呼叫跟請求有點關聯但不正確的 function。例如，被要求在社群媒體上開始追蹤時，模型卻設定了 follow_me_mode。

<br>
在這個簡單的例子裡，多做一些 prompt engineering 也許能解決部分問題，但這個範例的目的是示範怎麼用 fine-tuning 提升表現。另外，這個情況相對單純，隨著 function 的數量和複雜度增加，fine-tuning 的效果會越來越明顯。

再說一次，我們的目標是提升表現並用更少的 token，所以 fine-tuning 讓我們可以：

- 省略 function 和參數的說明：移除 function 和參數的 description 欄位
- 省略參數：移除 parameters 物件裡整個 properties 欄位
- 完全省略 function：從 functions 陣列移除整個 function 物件


# 產生合成資料


### 輔助函式


我們想產生每個 function 的每一種呼叫，這樣合成資料才能涵蓋所有可能的呼叫。接著，用 `gpt-4o` 想出能觸發每一種呼叫的 prompt，再把這組 prompt 和 function 呼叫的配對當成訓練資料。


為有固定 enum 的 function 產生所有呼叫比較簡單，但像 `control_gimbal` 這種 function，需要設定 `tilt` 和 `pan` 的整數值，所以產生這些合成呼叫時，我們先放一個佔位值，之後再用 `gpt-4o` 想出合理的數值。


```python
placeholder_int = "fill_in_int"
placeholder_string = "fill_in_string"
```

下面的函式會接收 function 清單裡的所有 function，並依每個 function 的參數，查看這些 function 所有可能的呼叫。
這些函式也會考慮 `required` 參數，確保所有呼叫都是實際可行的。


```python
def generate_permutations(
    params: Dict[str, Dict[str, Any]]
) -> Generator[Dict[str, Any], None, None]:
    """
    Generates all possible permutations for given parameters.

    :param params: Parameter dictionary containing required and optional fields.
    :return: A generator yielding each permutation.
    """

    # Extract the required fields from the parameters
    required_fields = params.get("required", [])

    # Generate permutations for required fields
    required_permutations = generate_required_permutations(params, required_fields)

    # Generate optional permutations based on each required permutation
    for required_perm in required_permutations:
        yield from generate_optional_permutations(params, required_perm)


def generate_required_permutations(
    params: Dict[str, Dict[str, Any]], required_fields: List[str]
) -> List[Dict[str, Any]]:
    """
    Generates permutations for the required fields.

    :param params: Parameter dictionary.
    :param required_fields: List of required fields.
    :return: A list of permutations for required fields.
    """

    # Get all possible values for each required field
    required_values = [get_possible_values(params, field) for field in required_fields]

    # Generate permutations from possible values
    return [
        dict(zip(required_fields, values))
        for values in itertools.product(*required_values)
    ]


def generate_optional_permutations(
    params: Dict[str, Dict[str, Any]], base_perm: Dict[str, Any]
) -> Generator[Dict[str, Any], None, None]:
    """
    Generates permutations for optional fields based on a base permutation.

    :param params: Parameter dictionary.
    :param base_perm: Base permutation dictionary.
    :return: A generator yielding each permutation for optional fields.
    """

    # Determine the fields that are optional by subtracting the base permutation's fields from all properties
    optional_fields = set(params["properties"]) - set(base_perm)

    # Iterate through all combinations of optional fields
    for field_subset in itertools.chain.from_iterable(
        itertools.combinations(optional_fields, r)
        for r in range(len(optional_fields) + 1)
    ):

        # Generate product of possible values for the current subset of fields
        for values in itertools.product(
            *(get_possible_values(params, field) for field in field_subset)
        ):

            # Create a new permutation by combining base permutation and current field values
            new_perm = {**base_perm, **dict(zip(field_subset, values))}

            yield new_perm


def get_possible_values(params: Dict[str, Dict[str, Any]], field: str) -> List[Any]:
    """
    Retrieves possible values for a given field.

    :param params: Parameter dictionary.
    :param field: The field for which to get possible values.
    :return: A list of possible values.
    """

    # Extract field information from the parameters
    field_info = params["properties"][field]

    # Based on the field's type or presence of 'enum', determine and return the possible values
    if "enum" in field_info:
        return field_info["enum"]
    elif field_info["type"] == "integer":
        return [placeholder_int]
    elif field_info["type"] == "string":
        return [placeholder_string]
    elif field_info["type"] == "boolean":
        return [True, False]
    elif field_info["type"] == "array" and "enum" in field_info["items"]:
        enum_values = field_info["items"]["enum"]
        all_combinations = [
            list(combo)
            for i in range(1, len(enum_values) + 1)
            for combo in itertools.combinations(enum_values, i)
        ]
        return all_combinations
    return []
```

### 先產生每個 function 的每一種呼叫


Prompts：


```python
INVOCATION_FILLER_PROMPT = """
1) Input reasonable values for 'fill_in_string' and 'fill_in_int' in the invocation here: {invocation}. Reasonable values are determined by the function definition. Use the
the entire function provided here :{function} to get context over what proper fill_in_string and fill_in_int values would be.
Example:

Input: invocation: {{
    "name": "control_camera",
    "arguments": {{
      "mode":"video",
      "duration":"fill_in_int"
    }}
}},
function:{function}

Output: invocation: {{
    "name": "control_camera",
    "arguments": {{
      "mode":"video",
      "duration": 30
    }}
}}


MAKE SURE output is just a dictionary with keys 'name' and 'arguments', no other text or response.

Input: {invocation}
Output:
"""


COMMAND_GENERATION_PROMPT = """
You are to output 2 commands, questions or statements that would generate the inputted function and parameters.
Please make the commands or questions natural, as a person would ask, and the command or questions should be varied and not repetitive.
It should not always mirror the exact technical terminology used in the function and parameters, rather reflect a conversational and intuitive request.
For instance, the prompt should not be 'turn on the dome light', as that is too technical, but rather 'turn on the inside lights'.
Another example, is the prompt should not be 'turn on the HVAC', but rather 'turn on the air conditioning'. Use language a normal driver would use, even if
it is technically incorrect but colloquially used.

RULES: ALWAYS put a backwards slash before an apostrophe or single quote '. For example, do not say don't but say don\'t.
Prompts MUST be in double quotes as well.

Example

Input: {{'name': 'calibrate_sensors','arguments': {{}}'' }}
Prompt: ["The sensors are out of whack, can you reset them", "The calibration of the drone is off, fix it please!"]

Input: {{'name': 'set_autopilot','arguments': {{'status': 'off'}}}}
Prompt: ["OK, I want to take back pilot control now","Turn off the automatic pilot I'm ready control it"]

Input: {invocation}
Prompt:
"""
```

下面這段程式會產生除了 `reject_request` function 以外，每個 function 的呼叫。

要做有效的 fine-tuning，我們需要標註正確的資料。我們可以手動想範例並標註資料，\
也可以靠 `gpt-4o` 產生合成資料 <br>

根據經驗，`gpt-4o` 需要多一點協助，才能產生會觸發 `reject_request` function 的真實 prompt 範例，所以接下來處理這部分...


```python
input_objects = []
all_but_reject = [f for f in function_list if f.get("name") != "reject_request"]

for function in all_but_reject:
    func_name = function["function"]["name"]
    params = function["function"]["parameters"]
    for arguments in generate_permutations(params):
        if any(val in arguments.values() for val in ["fill_in_int", "fill_in_str"]):
            input_object = {"name": func_name, "arguments": arguments}
            messages = [
                {
                    "role": "user",
                    "content": INVOCATION_FILLER_PROMPT.format(
                        invocation=str(input_object), function=function
                    ),
                }
            ]
            input_object, usage = get_chat_completion(
                model="gpt-4o", messages=messages, max_tokens=200, temperature=0.1
            ).content
        else:
            input_object = {"name": func_name, "arguments": arguments}

        input_objects.append(input_object)
```

現在有了所有的呼叫，我們用 `gpt-4o` 產生會觸發這些呼叫的 prompt


````python
def remove_sequences(input_string):
    # Replace the specific sequences with an empty string
    cleaned_string = input_string.replace("```json", "")  # Remove "```json" first
    cleaned_string = cleaned_string.replace("```", "")  # Then remove "```"
    return json.loads(cleaned_string)
````

```python
def create_commands(invocation_list):
    example_list = []
    for i, invocation in enumerate(invocation_list):
        if i < 100:
            print(
                f"\033[34m{np.round(100*i/len(invocation_list),1)}% complete\033[0m")
            if type(invocation) == str or "json" in invocation:
                invocation = remove_sequences(invocation)
            print(invocation)

        # Format the prompt with the invocation string
        request_prompt = COMMAND_GENERATION_PROMPT.format(
            invocation=invocation)

        messages = [{"role": "user", "content": f"{request_prompt}"}]
        completion, usage = get_chat_completion(messages, temperature=0.8)
        command_dict = {"Input": invocation, "Prompt": completion.content}
        example_list.append(command_dict)
    return example_list
```

```python
# Only printing the first 10 rows
training_examples_unformatted = create_commands(input_objects)
```

??? note "輸出"

    ```text
    0.0% complete
    {'name': 'takeoff_drone', 'arguments': {'altitude': 100}}
    1.8% complete
    {'name': 'land_drone', 'arguments': {'location': 'current'}}
    3.5% complete
    {'name': 'land_drone', 'arguments': {'location': 'home_base'}}
    5.3% complete
    {'name': 'land_drone', 'arguments': {'location': 'custom'}}
    7.0% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'forward', 'distance': 100}}
    8.8% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'backward', 'distance': 50}}
    10.5% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'left', 'distance': 10}}
    12.3% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'right', 'distance': 10}}
    14.0% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'up', 'distance': 10}}
    15.8% complete
    {'name': 'control_drone_movement', 'arguments': {'direction': 'down', 'distance': 10}}
    17.5% complete
    {'name': 'set_drone_speed', 'arguments': {'speed': 10}}
    19.3% complete
    {'name': 'control_camera', 'arguments': {'mode': 'photo'}}
    21.1% complete
    {'name': 'control_camera', 'arguments': {'mode': 'photo', 'duration': 10}}
    22.8% complete
    {'name': 'control_camera', 'arguments': {'mode': 'video'}}
    24.6% complete
    {'name': 'control_camera', 'arguments': {'mode': 'video', 'duration': 60}}
    26.3% complete
    {'name': 'control_camera', 'arguments': {'mode': 'panorama'}}
    28.1% complete
    {'name': 'control_camera', 'arguments': {'mode': 'panorama', 'duration': 60}}
    29.8% complete
    {'name': 'control_gimbal', 'arguments': {'tilt': 45, 'pan': 90}}
    31.6% complete
    {'name': 'set_drone_lighting', 'arguments': {'mode': 'on'}}
    33.3% complete
    {'name': 'set_drone_lighting', 'arguments': {'mode': 'off'}}
    ... (省略 74 行)
    ```

現在把訓練範例整理成正確的格式。關於 function calling fine-tuning 訓練資料格式的更多文件，看這裡：https://platform.openai.com/docs/guides/fine-tuning/fine-tuning-examples


```python
def remove_descriptions(function_list):
    for function in function_list:
        func = function["function"]
        if "description" in func:
            del func["description"]

        params = func["parameters"]
        if "properties" in params:
            for param in params["properties"].values():
                if "description" in param:
                    del param["description"]

    return function_list


modified_function_list = remove_descriptions(function_list)
```

```python
training_examples = []

for prompt in training_examples_unformatted:
    # adjust formatting for training data specs

    # if its not a dict, convert to dict
    if type(prompt["Input"]) != dict:
        prompt["Input"] = ast.literal_eval(prompt["Input"])
    prompt["Input"]["arguments"] = json.dumps(prompt["Input"]["arguments"])
    try:
        prompt["Prompt"] = json.loads(prompt["Prompt"])
    except:
        continue
    for p in prompt["Prompt"]:
        print(p)
        print(prompt["Input"])
        tool_calls = [
            {"id": "call_id", "type": "function", "function": prompt["Input"]}
        ]
        training_examples.append(
            {
                "messages": [
                    {"role": "system", "content": DRONE_SYSTEM_PROMPT},
                    {"role": "user", "content": p},
                    {"role": "assistant", "tool_calls": tool_calls},
                ],
                "parallel_tool_calls": False,
                "tools": modified_function_list,
            }
        )
```

??? note "輸出"

    ```text
    Let's get the drone in the air, how high should it go?
    {'name': 'takeoff_drone', 'arguments': '{"altitude": 100}'}
    Ready for takeoff, how high should the drone fly?
    {'name': 'takeoff_drone', 'arguments': '{"altitude": 100}'}
    Can you bring the drone down to where we are?
    {'name': 'land_drone', 'arguments': '{"location": "current"}'}
    Let's get the drone to land right here
    {'name': 'land_drone', 'arguments': '{"location": "current"}'}
    Bring the drone back to base for landing
    {'name': 'land_drone', 'arguments': '{"location": "home_base"}'}
    Can you safely land the drone at home base
    {'name': 'land_drone', 'arguments': '{"location": "home_base"}'}
    Can you make the drone move to the left by 10 units?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "left", "distance": 10}'}
    I need the drone to go left, could you move it 10 steps that way?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "left", "distance": 10}'}
    Can you move the drone to the right by 10 feet?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "right", "distance": 10}'}
    I need the drone to go 10 feet to the right, can you do that?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "right", "distance": 10}'}
    Can you make the drone go upwards by 10 units?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "up", "distance": 10}'}
    I need the drone to move up, can you do that for me?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "up", "distance": 10}'}
    Can you bring the drone lower by 10 feet please?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "down", "distance": 10}'}
    I need the drone to descend 10 units, can you make that happen?
    {'name': 'control_drone_movement', 'arguments': '{"direction": "down", "distance": 10}'}
    Can you make the drone go faster?
    {'name': 'set_drone_speed', 'arguments': '{"speed": 10}'}
    I think the drone should speed up a bit, don't you think?
    {'name': 'set_drone_speed', 'arguments': '{"speed": 10}'}
    I want to take a picture, can you switch the camera mode to photo
    {'name': 'control_camera', 'arguments': '{"mode": "photo"}'}
    Let's capture this moment, switch the camera to photo mode please
    {'name': 'control_camera', 'arguments': '{"mode": "photo"}'}
    Can you switch the camera to photo mode and take a picture for 10 seconds?
    {'name': 'control_camera', 'arguments': '{"mode": "photo", "duration": 10}'}
    I need to capture something, can you set the camera to take photos for 10 seconds?
    {'name': 'control_camera', 'arguments': '{"mode": "photo", "duration": 10}'}
    ... (省略 132 行)
    ```

回到拒絕的 function。我們來產生一些_幾乎_可行、但應該呼叫 `reject_request` function 的 prompt。做法是請 `gpt-4o` 產生跟給定 function 清單相關、但又不太可能完成的請求。


```python
reject_list = [
    "Translate broadcast message to another language",
    "Automatically capture photos when face is detected",
    "Detect nearby drones",
    "Measure wind resistance",
    "Capture slow motion video",
    "Move the drone forward and backward by same distance at the same time.",
    "Adjust drone's altitude to ground level changes",
    "Display custom message on LED display",
    "Sync drone's time with smartphone",
    "Alert when drone travels out of designated area",
    "Calibrate sensors and land simultaneously",
    "Detect moisture levels",
    "Automatically follow GPS tagged object",
    "Toggle night vision mode",
    "Maintain current altitude when battery is low",
    "Decide best landing spot using AI",
    "Program drone's route based on wind direction",
]
```

```python
reject_training_list = []
for prompt in reject_list:
    # Adjust formatting
    tool_calls = [
        {
            "id": "call_id",
            "type": "function",
            "function": {"name": "reject_request", "arguments": "{}"},
        }
    ]
    reject_training_list.append(
        {
            "messages": [
                {"role": "system", "content": DRONE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "tool_calls": tool_calls},
            ],
            "parallel_tool_calls": False,
            "tools": modified_function_list,
        }
    )
```

現在把所有訓練範例合併起來


```python
training_list_total = training_examples + reject_training_list
```

```python
training_file = "data/drone_training.jsonl"
with open(training_file, "w") as f:
    for item in training_list_total:
        json_str = json.dumps(item)
        f.write(f"{json_str}\n")
```

# Fine tuning


終於可以啟動 fine-tuning job 了


```python
# Upload the training file
file = client.files.create(
    file=open("data/drone_training.jsonl", "rb"),
    purpose="fine-tune",
)
file_id = file.id
print(f"FileID: {file_id}")

# Create a fine-tuning job

ft = client.fine_tuning.jobs.create(
    model="gpt-3.5-turbo",
    training_file=file_id,
    suffix="drone",
)

print(f"Fine-tuning job created: {ft}")
```

??? note "輸出"

    ```text
    FileID: file-blg0IytwIivZQzc9mbfnS8Pm
    Fine-tuning job created: FineTuningJob(id='ftjob-84PQg97hoIAKf21IPnhiNlU1', created_at=1718580285, error=Error(code=None, message=None, param=None), fine_tuned_model=None, finished_at=None, hyperparameters=Hyperparameters(n_epochs='auto', batch_size='auto', learning_rate_multiplier='auto'), model='gpt-3.5-turbo-0125', object='fine_tuning.job', organization_id='org-lb41cclBdkq5pm6BgDhx8DHP', result_files=[], seed=1513865891, status='validating_files', trained_tokens=None, training_file='file-blg0IytwIivZQzc9mbfnS8Pm', validation_file=None, estimated_finish=None, integrations=[], user_provided_suffix='drone')
    ```

除了建立 fine-tuning job，你也可以列出現有的 job、查詢 job 的狀態，或取消 job。


```python
ftjob_id = "ftjob-84PQg97hoIAKf21IPnhiNlU1"
# List 10 fine-tuning jobs
# client.fine_tuning.jobs.list(limit=10)

# Retrieve the state of a fine-tune
client.fine_tuning.jobs.retrieve(ftjob_id)

# Cancel a job
# client.fine_tuning.jobs.cancel("ftjob-abc123")

# List up to 10 events from a fine-tuning job
# client.fine_tuning.jobs.list_events(fine_tuning_job_id="ftjob-abc123", limit=10)

# Delete a fine-tuned model (must be an owner of the org the model was created in)
# client.models.delete("ft:gpt-3.5-turbo:abc:suffix:abc123")
```

??? note "輸出"

    ```text
    FineTuningJob(id='ftjob-84PQg97hoIAKf21IPnhiNlU1', created_at=1718580285, error=Error(code=None, message=None, param=None), fine_tuned_model='ft:gpt-3.5-turbo-0125:openai-gtm:drone:9atiPjeC', finished_at=1718581004, hyperparameters=Hyperparameters(n_epochs=3, batch_size=1, learning_rate_multiplier=2), model='gpt-3.5-turbo-0125', object='fine_tuning.job', organization_id='org-lb41cclBdkq5pm6BgDhx8DHP', result_files=['file-F6XPJFLVG9f3mR04KBmwUI9H'], seed=1513865891, status='succeeded', trained_tokens=145983, training_file='file-blg0IytwIivZQzc9mbfnS8Pm', validation_file=None, estimated_finish=None, integrations=[], user_provided_suffix='drone')
    ```

fine-tuning job 完成後，你還可以查詢 job、從 result_files 取出 file ID，再取得該檔案的內容，看訓練過程的指標。每個結果 CSV 檔有這些欄位：step、train_loss、train_accuracy、valid_loss 和 valid_mean_token_accuracy。指標有幫助，但直接評估微調後模型的輸出樣本，才最能看出模型品質。


```python
fine_tune_results = client.fine_tuning.jobs.retrieve(ftjob_id).result_files
result_file_id = client.files.retrieve(fine_tune_results[0]).id

# Retrieve the result file
result_file = client.files.content(file_id=result_file_id)
decoded_content = base64.b64decode(result_file.read()).decode("utf-8")
print(decoded_content)
```

??? note "輸出"

    ```text
    step,train_loss,train_accuracy,valid_loss,valid_mean_token_accuracy
    1,3.63265,0.5,,
    2,2.45992,0.80952,,
    3,2.77939,0.80952,,
    4,3.53073,0.65,,
    5,2.61654,0.8,,
    6,2.16,0.85714,,
    7,2.73706,0.8,,
    8,2.56944,0.625,,
    9,2.06096,0.78947,,
    10,1.69598,0.8,,
    11,1.94268,0.77778,,
    12,1.61752,0.86667,,
    13,1.2442,0.8,,
    14,0.73411,0.875,,
    15,0.34285,0.875,,
    16,0.22229,0.95238,,
    17,0.04635,0.95,,
    18,0.00626,1.0,,
    19,0.60888,0.90909,,
    20,0.00092,1.0,,
    21,0.8001,0.95,,
    22,0.04982,1.0,,
    23,0.35494,0.92857,,
    24,0.00023,1.0,,
    25,0.00034,1.0,,
    26,0.0029,1.0,,
    27,0.58017,0.875,,
    28,0.13018,0.9375,,
    29,0.00109,1.0,,
    30,6e-05,1.0,,
    31,0.61665,0.95,,
    32,3e-05,1.0,,
    33,0.23598,0.95,,
    34,3e-05,1.0,,
    35,0.03566,1.0,,
    36,1e-05,1.0,,
    37,1e-05,1.0,,
    38,2e-05,1.0,,
    39,2e-05,1.0,,
    ... (省略 270 行)
    ```

# 評估


太好了！我們訓練出了一個 function calling 的 fine-tuned 模型。來看看它在評估集上的表現，這些 prompt 是無人機助理應該自動拒絕的。


```python
ft_model = "ft:gpt-3.5-turbo-0125:openai-gtm:drone:9atiPjeC"
base_model = "gpt-3.5-turbo"

print(f"\nEvaluating fine-tuned model with challenging prompts: {ft_model}")
eval(
    model=ft_model,
    function_list=modified_function_list,
    system_prompt=DRONE_SYSTEM_PROMPT,
    prompts_to_expected_tool_name=challenging_prompts_to_expected,
)

print(f"\nEvaluating base model with challenging prompts: {base_model}")
eval(
    model="gpt-3.5-turbo",
    function_list=function_list,
    system_prompt=DRONE_SYSTEM_PROMPT,
    prompts_to_expected_tool_name=challenging_prompts_to_expected,
)
```

??? note "輸出"

    ```text

    Evaluating fine-tuned model with challenging prompts: ft:gpt-3.5-turbo-0125:openai-gtm:drone:9atiPjeC
    ```

    ```text
    <pandas.io.formats.style.Styler at 0x13c87a9d0>
    ```

    ```text
    Number of matches: 10 out of 10 (100.00%)
    Average latency per request: 3519.17 ms
    Average tokens used per request: 457.20

    Evaluating base model with challenging prompts: gpt-3.5-turbo
    ```

    ```text
    <pandas.io.formats.style.Styler at 0x13d3c7910>
    ```

    ```text
    Number of matches: 6 out of 10 (60.00%)
    Average latency per request: 647.58 ms
    Average tokens used per request: 791.90
    ```

太好了！原本的模型只拒絕了 60%，fine-tuned 模型則拒絕了 100% 的請求，而且用了更少的 token。


### 結論


恭喜！你現在可以為 function calling 做 fine-tuning 了。期待看到你做出什麼。


## 重點整理

- fine-tuning 之前先改 function 定義和 prompt，這兩招沒用才考慮 fine-tuning。
- function 越多、任務越複雜，模型越容易錯誤呼叫，特別是「幾乎可行」的請求。
- 只靠 function 清單就能合成訓練資料：列舉所有可能的呼叫，再讓強模型反推對應的 prompt。
- 需要拒絕的案例要另外特別產生，強模型不太會自己產生好的例子。
- fine-tuning 不只提升準確度，還能省略 description 之類的欄位，減少 token。

## 練習

1. 在基準測試的「難請求」清單裡多加兩個你自己想的幾乎可行但應該拒絕的 prompt，看 `gpt-3.5-turbo` 有沒有答錯。
2. 在 function 清單裡新增一個你自己的 function（例如控制燈光），重新跑所有呼叫的列舉，看合成資料的數量怎麼變。
3. 微調完成後，把評估集換成 notebook 沒用過的拒絕 prompt，比較原模型和 fine-tuned 模型的拒絕比例。
