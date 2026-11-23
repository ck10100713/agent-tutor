---
translated: true
source: examples/o1/Using_reasoning_for_data_validation.ipynb
---

# 用 reasoning 做資料驗證

> 原文：[examples/o1/Using_reasoning_for_data_validation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/o1/Using_reasoning_for_data_validation.ipynb)



## 這篇在做什麼
用 o1 模型（這裡是 o1-preview）靠推理來驗證資料。拿一份合成的醫療資料集當例子，讓模型逐列找出資料裡的問題，再量測它抓得準不準。

## 學完你會
- 用模型產生一份刻意帶有不一致的合成醫療資料集
- 寫一個函式，把單列資料交給 reasoning 模型判斷是否有效並說明問題
- 用 gpt-4o 當 grader，算出抓問題的準確率，以及指出具體問題的準確率

## 開跑前
需要 OpenAI API key，而且要有 o1-preview 的使用權限。這類模型 rate limit 較低，要調整並行 worker 的數量。

這份指南會看怎麼用 o1 模型（具體是 o1-preview）靠推理做資料驗證。我們會用一個合成醫療資料集當實例，並示範怎麼評估模型找出資料問題的準確度。

## 總覽

資料驗證是確保資料集品質和可靠度的關鍵步驟，在醫療這類敏感領域尤其重要。傳統的驗證方法常依賴預先定義的規則和模式。不過像 o1 這種進階模型能理解 context 並對資料做推理，提供更靈活、更聰明的驗證方式。

這份教學要做的事：
- 產生一份含有不一致的合成醫療資料集。
- 定義一個函式，接收一列資料並驗證它是否正確
- 執行驗證流程並計算準確度指標。
- 分析並解讀結果。

```python
from openai import OpenAI
import json
from IPython.display import display, HTML
from sklearn.metrics import precision_score, recall_score, f1_score
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import pandas as pd

client = OpenAI()
MODEL = 'o1-preview'
```

## 合成資料產生

我們會用到 [Synthetic Data Generation](https://cookbook.openai.com/examples/sdg1) cookbook 裡的許多原則，來建立資料集的基礎。

我們會 prompt 模型，為我們的使用情境產生幾組醫療資料。我們給了模型詳細的指示：怎麼建立資料集、要遵循什麼格式、怎麼在裡面放入錯誤。也提供了幾列範例資料讓模型起步。

資料集每一列有這些欄位：
- Patient ID：隨機產生的病患 id
- Date of Birth：病患的出生日期
- Gender：M/F
- Medical History：過去的診斷
- Current Medications：病患目前服用的藥物
- Allergies：已確認的過敏
- Lab Results (Glucose mg/dL)
- Diagnoses：目前的診斷
- Treatment Plan：目前的治療計畫
- Is Valid：這列資料是否有效（True/False）
- Issue：如果這列資料無效，問題是什麼

資料裡可能出現的錯誤例子有：
- 開了病患會過敏的藥
- 目前用藥跟病史對不上
- 治療計畫跟診斷不符

````python
def generate_data():
    messages = [
        {
            "role": "user",
            "content": """
You are a helpful assistant designed to generate data. You will be given a format for the data to generate and some examples of the data.

When generating Patient IDs, use the format 'P' followed by a three-digit number (e.g., P006, P941, P319).

Intentionally make some mistakes in the data generation and document them in the appropriate columns ('Is Valid' and 'Issue') if the row of data is invalid.

The types of mistakes to include are:

- **Allergy Contradictions**: Prescribing a medication that the patient is allergic to (e.g., prescribing Penicillin to a patient allergic to Penicillin).
- **Medical History and Medication Mismatch**: A patient with a medical condition not receiving appropriate medication (e.g., a diabetic patient not prescribed any diabetes medication).
- **Lab Results and Diagnosis Mismatch**: Lab results that do not support the diagnosis (e.g., normal glucose levels but diagnosed with Diabetes Type 2).
- **Other Plausible Mistakes**: Any other realistic errors that could occur in medical records, such as incorrect gender entries, impossible dates of birth, or inconsistent treatment plans.

Ensure that when 'Is Valid' is 'False', the 'Issue' column clearly explains the problem.

Return 100 rows of data for the user. Your response should strictly be in the format of a valid CSV.

Generate Synthetic Medical Records Dataset with the following columns:
    - Patient ID: A randomly generated patient id
    - Date of Birth: Date of birth of the patient
    - Gender: M/F
    - Medical History: Past diagnoses
    - Current Medications: Medication the patient is taking
    - Allergies: Identified allergies
    - Lab Results (Glucose mg/dL)
    - Diagnoses: Current diagnosis
    - Treatment Plan: Current treatment plan
    - Is Valid: Whether or not the current row of data is valid (True/False)
    - Issue: If the row of data is not valid, what the issue is

Patient ID,Date of Birth,Gender,Medical History,Current Medications,Allergies,Lab Results (Glucose mg/dL),Diagnoses,Treatment Plan,Is Valid,Issue
P001,1980-05-14,M,Hypertension,Lisinopril,None,110,Hypertension,Continue Lisinopril,True,
P002,1975-11-30,F,Diabetes Type 2,Metformin,Penicillin,90,Diabetes Type 2,Continue Metformin,True,
P003,1990-07-22,F,Asthma,Albuterol,Aspirin,85,Asthma,Prescribe Albuterol,True,
P004,2000-03-10,M,None,Amoxicillin,Penicillin,95,Infection,Prescribe Amoxicillin,False,Prescribed Amoxicillin despite Penicillin allergy
P005,1985-09-18,F,Hyperlipidemia,Atorvastatin,None,200,Hyperlipidemia,Continue Atorvastatin,True,
P006,1978-12-05,M,Hypertension; Diabetes Type 2,Lisinopril; Insulin,None,55,Diabetes Type 2,Adjust insulin dosage,False,Low glucose level not properly addressed
            """
        }
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )

    return response.choices[0].message.content.replace('```csv', '').replace('```', '')
````

```python
# Generate data three times using the existing dataGeneration function
generated_data = []
data = generate_data()
generated_data.extend(data.strip().split('\n'))

# Append the generated data to the medicalData.csv file
with open('../data/medicalData.csv', 'a', newline='') as csvfile:
    csvwriter = csv.writer(csvfile)
    for row in generated_data:
        csvwriter.writerow(row.split(','))

print("Synthetic data generation and appending completed.")
```

??? note "輸出"

    ```text
    Synthetic data generation and appending completed.
    ```

## 資料驗證

資料集準備好之後，我們 prompt reasoning 模型檢視每一列資料，判斷它有沒有問題。我們會要求模型輸出資料有沒有問題，並說明問題是什麼。

模型列出它認為無效的資料後，我們把這些結果交給 model grader，評估兩個指標：
- 模型正確找出資料問題的準確度
- 在問題被正確找出的那部分資料裡，模型指出具體問題的準確度

因為這個任務窄很多，我們可以用比較快的 gpt-4o 模型來計算準確度。

提醒：這些模型還在 beta，rate limit 會低很多，請依此調整並行 worker 的數量。

````python
def validate_data(input_data):
    messages = [
        {
            "role": "user",
            "content": f"""
You are a helpful assistant designed to validate the quality of medical datasets. You will be given a single row of medical data, and your task is to determine whether the data is valid.

- Carefully analyze the data for any inconsistencies, contradictions, missing values, or implausible information.
- Consider the logical relationships between different fields (e.g., treatments should be appropriate for the diagnoses, medications should not conflict with allergies, lab results should be consistent with diagnoses, etc.).
- Use your general medical knowledge to assess the validity of the data.
- Focus solely on the information provided without making assumptions beyond the given data.

**Return only a JSON object** with the following two properties:

- `"is_valid"`: a boolean (`true` or `false`) indicating whether the data is valid.
- `"issue"`: if `"is_valid"` is `false`, provide a brief explanation of the issue; if `"is_valid"` is `true`, set `"issue"` to `null`.

Both JSON properties must always be present.

Do not include any additional text or explanations outside the JSON object.

MEDICAL DATA:
{input_data}
            """
        }
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )

    response_content = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
    
    try:
        if isinstance(response_content, dict):
            response_dict = response_content
        else:
            response_dict = json.loads(response_content)
        return response_dict
    except json.JSONDecodeError as e:
        print(f"Failed to decode JSON response: {response_content}")
        raise e
````

```python
# Read the CSV file and exclude the last two columns
input_data = []
with open('../data/medicalData.csv', 'r') as file:
    reader = csv.reader(file)
    headers = next(reader)
    for row in reader:
        input_data.append(row[:-2])  # Exclude "Is Valid" and "Issue" columns

# Initialize lists to store true labels
true_is_valid = []
true_issues = []

# Extract true labels from the CSV file
with open('../data/medicalData.csv', 'r') as file:
    reader = csv.reader(file)
    headers = next(reader)
    for row in reader:
        true_is_valid.append(row[-2] == 'True')
        true_issues.append(row[-1])

# Function to validate a single row of data
def validate_row(row):
    input_str = ','.join(row)
    result_json = validate_data(input_str)
    return result_json

# Validate data rows and collect results
pred_is_valid = [False] * len(input_data)
pred_issues = [''] * len(input_data)

with ThreadPoolExecutor() as executor:
    futures = {executor.submit(validate_row, row): i for i, row in enumerate(input_data)}
    
    for future in as_completed(futures):
        i = futures[future]  # Get the index of the current row
        result_json = future.result()
        pred_is_valid[i] = result_json['is_valid']
        pred_issues[i] = result_json['issue']
```

拿到模型的結果後，就可以跟 source of truth 比對，算出系統的準確度

```python
# Convert predicted and true 'is_valid' labels to boolean if they aren't already
pred_is_valid_bool = [bool(val) if isinstance(val, bool) else val == 'True' for val in pred_is_valid]
true_is_valid_bool = [bool(val) if isinstance(val, bool) else val == 'True' for val in true_is_valid]

# Calculate precision, recall, and f1 score for the 'is_valid' prediction
precision = precision_score(true_is_valid_bool, pred_is_valid_bool, pos_label=True)
recall = recall_score(true_is_valid_bool, pred_is_valid_bool, pos_label=True)
f1 = f1_score(true_is_valid_bool, pred_is_valid_bool, pos_label=True)

# Initialize issue_matches_full with False
issue_matches_full = [False] * len(true_is_valid)
```

```python
print(f"Precision: {precision:.2f}")
print(f"Recall: {recall:.2f}")
print(f"F1: {f1:.2f}")
```

??? note "輸出"

    ```text
    Precision: 0.82
    Recall: 0.87
    F1: 0.84
    ```

## 問題辨識

接下來看模型能不能準確分類資料裡的問題

```python
def validate_issue(model_generated_answer, correct_answer):
    messages = [
        {
            "role": "user",
            "content": f"""
You are a medical expert assistant designed to validate the quality of an LLM-generated answer.

The model was asked to review a medical dataset row to determine if the data is valid. If the data is not valid, it should provide a justification explaining why.

Your task:

    •	Compare the model-generated justification with the correct reason provided.
    •	Determine if they address the same underlying medical issue or concern, even if phrased differently.
    •	Focus on the intent, medical concepts, and implications rather than exact wording.

Instructions:

    •	If the justifications have the same intent or address the same medical issue, return True.
    •	If they address different issues or concerns, return False.
    •	Only respond with a single word: True or False.

Examples:

    1.	Example 1:
    •	Model Generated Response: “The patient is allergic to penicillin”
    •	Correct Response: “The patient was prescribed penicillin despite being allergic”
    •	Answer: True
    2.	Example 2:
    •	Model Generated Response: “The date of birth of the patient is incorrect”
    •	Correct Response: “The patient was prescribed penicillin despite being allergic”
    •	Answer: False


Model Generated Response: {model_generated_answer}
Correct Response:  {correct_answer}
            """
        }
    ]

    response = client.chat.completions.create(
        model="o1-preview",
        messages=messages
    )

    result = response.choices[0].message.content

    return result
```

```python
# Validate issues for rows where both true and predicted 'is_valid' are False
validation_results = []

with ThreadPoolExecutor() as executor:
    futures = {
        executor.submit(validate_issue, pred_issues[i], true_issues[i]): i
        for i in range(len(pred_is_valid_bool))
        if not pred_is_valid_bool[i] and not true_is_valid_bool[i]
    }
    
    for future in as_completed(futures):
        i = futures[future]  # Get the original index
        issue_match = future.result()
        issue_matches_full[i] = (issue_match == 'True')
        validation_results.append({
            "index": i,
            "predicted_issue": pred_issues[i],
            "true_issue": true_issues[i],
            "issue_match": issue_matches_full[i]
        })
    
    # Calculate issue accuracy
    issue_accuracy = sum([i['issue_match'] for i in validation_results]) / len(validation_results)
    
    # Store the results in the dictionary
    model_results = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "issue_accuracy": issue_accuracy
    }

# Create a DataFrame to store the results
df_results = pd.DataFrame([model_results])

# Create a DataFrame to store the validation results for each row
df_validation_results = pd.DataFrame(validation_results)
```

下面會顯示我們正確判斷出有問題的那些列。每一列都會顯示預測的問題和真實的問題，以及兩者是否吻合

```python
def display_formatted_dataframe(df):
    def format_text(text):
        return text.replace('\n', '<br>')

    df_formatted = df.copy()
    df_formatted['predicted_issue'] = df_formatted['predicted_issue'].apply(format_text)
    df_formatted['true_issue'] = df_formatted['true_issue'].apply(format_text)
    
    display(HTML(df_formatted.to_html(escape=False, justify='left')))
    
display_formatted_dataframe(pd.DataFrame(validation_results))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# Display the DataFrame
print(df_results)
```

??? note "輸出"

    ```text
       precision    recall       f1  issue_accuracy
    0   0.818182  0.870968  0.84375        0.615385
    ```

## 結論

從這裡的結果可以看到，模型在找出有問題的資料上可以達到高 precision/recall，在指出具體問題上也有不錯的準確度。

這應該能幫各種領域簡化 eval 資料集的資料驗證。

## 重點整理
- reasoning 模型能理解 context，所以能抓到固定規則寫不出來的不一致，例如藥物跟過敏衝突。
- 合成資料帶有標準答案（Is Valid 和 Issue），所以能直接量測驗證流程的好壞。
- 評估分兩層：有沒有抓到有問題的列，以及抓到的列有沒有說對問題。
- 評分任務比較窄，可以交給較快的模型（gpt-4o）當 grader。

## 練習
1. 在產生資料的 prompt 多加一種錯誤類型（例如劑量不合理），重新產生資料集。
2. 調整驗證時的並行 worker 數量，觀察 rate limit 錯誤是否減少。
3. 把 grader 的模型換成別的模型，比較算出的準確度有沒有差異。
