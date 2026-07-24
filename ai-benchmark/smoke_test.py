"""One tiny request per model — verifies Vertex access/terms before the full sweep."""
import os
import anthropic

PROJECT_ID = os.environ.get("PROJECT_ID", "your-gcp-project")
REGION = os.environ.get("REGION", "global")

MODELS = [
    "claude-fable-5",
    "claude-opus-5",
    "claude-sonnet-5",
]

client = anthropic.AnthropicVertex(project_id=PROJECT_ID, region=REGION)
for model in MODELS:
    try:
        r = client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": "Say OK."}],
        )
        text = next((b.text for b in r.content if b.type == "text"), "")
        print(f"OK    {model}: served-as={r.model} out={r.usage.output_tokens} text={text[:20]!r}")
    except anthropic.APIStatusError as e:
        print(f"FAIL  {model}: HTTP {e.status_code} — {str(e.message)[:200]}")
    except Exception as e:
        print(f"FAIL  {model}: {type(e).__name__}: {str(e)[:200]}")
