import os, json, re
from datetime import datetime
from openai import OpenAI
from modules import logger

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.1-8b-instant"

def _get_client():
    return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

def get_daily_ai_content():
    from modules.ai_ranker import get_top3_ranked
    try: ai_rankings = get_top3_ranked()
    except: ai_rankings = []
    if not GROQ_API_KEY:
        mock = _mock_content(); mock["ai_rankings"] = ai_rankings; return mock
    try:
        client = _get_client()
        today  = datetime.now().strftime("%B %d, %Y")
        r = client.chat.completions.create(model=GROQ_MODEL, max_tokens=1500, messages=[
            {"role":"system","content":"You are AIPulse. Respond only in valid JSON, no markdown."},
            {"role":"user","content":f'Today is {today}. Return JSON: {{"news_summary":"3-4 sentences of top AI news","top_tools":[{{"rank":1,"name":"","tagline":"","use_case":"","category":"","free_tier":true,"url":""}}]}} with exactly 3 tools.'}
        ])
        text = re.sub(r"```json|```","", r.choices[0].message.content).strip()
        parsed = json.loads(text); parsed["ai_rankings"] = ai_rankings; return parsed
    except Exception as e:
        logger.error("ai_content", f"Groq failed: {e}")
        mock = _mock_content(); mock["ai_rankings"] = ai_rankings; return mock

def chat_with_ai(conversation_history, user_message):
    if not GROQ_API_KEY: return "⚠️ GROQ_API_KEY not set in HF Space secrets."
    try:
        client = _get_client()
        messages = [{"role":"system","content":"You are AIPulse, an expert AI analyst. Be helpful and concise."}]
        for e in conversation_history:
            role = e.get("role","user")
            content = e.get("content","")
            if role in ("user","assistant"): messages.append({"role":role,"content":content})
        messages.append({"role":"user","content":user_message})
        r = client.chat.completions.create(model=GROQ_MODEL, messages=messages, max_tokens=1000)
        return r.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error: {e}"

def get_email_subject(content):
    return f"⚡ AIPulse Daily Briefing — {datetime.now().strftime('%b %d')}"

def _mock_content():
    return {
        "news_summary": "AI is advancing rapidly with new models from OpenAI, Google, and Anthropic pushing boundaries daily. Open source models from Meta continue to democratize AI access.",
        "top_tools": [
            {"rank":1,"name":"Cursor","tagline":"AI-first code editor","use_case":"Write and refactor code with natural language in your IDE.","category":"Coding","free_tier":True,"url":"https://cursor.so"},
            {"rank":2,"name":"Perplexity AI","tagline":"AI-powered search","use_case":"Get AI answers backed by real-time web sources.","category":"Research","free_tier":True,"url":"https://perplexity.ai"},
            {"rank":3,"name":"Runway","tagline":"AI video generation","use_case":"Create cinematic video from text prompts.","category":"Video","free_tier":True,"url":"https://runwayml.com"},
        ],
        "ai_rankings": [],
    }
