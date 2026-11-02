from openai import OpenAI

key = ""
for line in open(".env", encoding="utf-8"):
    if line.startswith("LLM_API_KEY="):
        key = line.split("=", 1)[1].strip()

client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
for m in sorted(client.models.list().data, key=lambda x: x.id):
    print(m.id)