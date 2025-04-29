import requests
import logging

def call_llm_api(model, prompt, api_key, base_url):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }
    try:
        resp = requests.post(base_url, json=data, headers=headers, timeout=180)
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logging.exception("LLM API 调用失败")
        return f"【大模型调用失败】{e}" 