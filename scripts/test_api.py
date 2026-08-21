"""Test GLM-5.2 API with a real LiveMath question."""
import json
import requests

d = json.load(open("data/livemathematicianbench_split/val/items.json", encoding="utf-8"))
item = d[0]
choices_str = "\n".join(f"{c['label']}. {c['text']}" for c in item["choices"])

print(f"Question: {item['question'][:200]}")
print(f"Choices: {len(item['choices'])}")
print(f"Correct: {item['correct_choice']['label']}")
print()

r = requests.post(
    "http://113.46.219.251:8080/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-6Vi_7BS_IuofzkYt8t2B9w",
        "Content-Type": "application/json",
    },
    json={
        "model": "GLM-5.2",
        "messages": [
            {
                "role": "system",
                "content": "Answer the math question. Output ONLY the choice label inside <answer>X</answer>.",
            },
            {
                "role": "user",
                "content": f"Question: {item['question']}\n\nChoices:\n{choices_str}",
            },
        ],
        "max_tokens": 8000,
    },
    timeout=300,
)
resp = r.json()
msg = resp["choices"][0]["message"]

content = msg.get("content", "") or ""
reasoning = msg.get("reasoning_content", "") or ""

print(f"content_len: {len(content)}")
print(f"content: {repr(content[:500])}")
print()
print(f"reasoning_len: {len(reasoning)}")
print(f"reasoning[:300]: {repr(reasoning[:300])}")
print()
print(f"finish_reason: {resp['choices'][0].get('finish_reason')}")
print(f"usage: {resp.get('usage', {})}")
