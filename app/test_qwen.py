import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:9000/v1"
MODEL = "Qwen/Qwen3.5-4B"  # 留空则自动读取 /v1/models 里的第一个模型
PROMPT = "你好，做个自我介绍"
TIMEOUT = 300


def http_json(method: str, url: str, payload=None):
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"连接失败: {e}") from e


def get_model_name() -> str:
    status, result = http_json("GET", f"{BASE_URL}/models")
    if status != 200:
        raise RuntimeError(f"/models 返回异常状态码: {status}")

    data = result.get("data", [])
    if not data:
        raise RuntimeError("没有读到任何模型，请先确认 transformers serve 还在运行。")

    if MODEL.strip():
        return MODEL.strip()

    first_model = data[0].get("id", "").strip()
    if not first_model:
        raise RuntimeError("读到了 models 列表，但拿不到模型 id。")
    return first_model


def chat(model_name: str, prompt: str):
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    status, result = http_json("POST", f"{BASE_URL}/chat/completions", payload)
    if status != 200:
        raise RuntimeError(f"/chat/completions 返回异常状态码: {status}")

    try:
        content = result["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"返回结果格式不对:\n{json.dumps(result, ensure_ascii=False, indent=2)}")

    return content, result


def main():
    prompt = PROMPT
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:]).strip()

    model_name = get_model_name()
    print(f"当前使用模型: {model_name}")
    print(f"提问内容: {prompt}")
    print("-" * 60)

    answer, raw = chat(model_name, prompt)
    print(answer)

    # 如果你想看完整 JSON 返回，把下面这行取消注释
    # print(json.dumps(raw, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()