import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

msg = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=100,
    messages=[{"role": "user", "content": "안녕! 한 문장으로 인사해줘."}]
)

print(msg.content[0].text)
