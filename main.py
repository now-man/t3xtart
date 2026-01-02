import os
import json
import logging
import requests
import uvicorn
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from mcp.server.sse import SseServerTransport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("t3xtart")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# 🔐 Kakao
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ.get("KAKAO_CLIENT_ID"),
        "refresh_token": os.environ.get("KAKAO_REFRESH_TOKEN"),
        "client_secret": os.environ.get("KAKAO_CLIENT_SECRET"),
    }
    res = requests.post(url, data=data)
    if res.status_code == 200:
        CURRENT_ACCESS_TOKEN = res.json().get("access_token")
        return True
    return False

async def send_kakao(content: str):
    global CURRENT_ACCESS_TOKEN
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {CURRENT_ACCESS_TOKEN}"}
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": f"🎨 t3xtart 도착!\n\n{content}",
            "link": {"web_url": "https://playmcp.kakao.com"},
        })
    }

    res = requests.post(url, headers=headers, data=payload)
    if res.status_code == 401 and refresh_kakao_token():
        headers["Authorization"] = f"Bearer {CURRENT_ACCESS_TOKEN}"
        res = requests.post(url, headers=headers, data=payload)

    return res.status_code == 200

# =========================================================
# 🧠 PROMPTS
# =========================================================

INTERPRETER_PROMPT = """
You are a Visual Request Interpreter.

Analyze the user request and decide:
1. subject_type: object / creature / place / abstract
2. shape_hint:
   - circle
   - vertical (tall container, cup, bottle)
   - horizontal
   - asymmetric
   - scattered
3. recommended_aspect_ratio (e.g. 7x11, 9x6, 10x10)
4. mood keywords (max 3)

Return JSON only.
"""

PLANNING_PROMPT = """
You are an Art Director.

Using the interpretation:
- Respect the shape_hint strictly.
- Use negative space if possible.
- Avoid perfect symmetry unless requested.
- Choose a limited emoji palette.

Describe:
1. Canvas size
2. Emoji roles
3. Composition strategy
"""

DRAWING_PROMPT = """
You are a Pixel Artist.

Rules:
- Follow the planned aspect ratio.
- DO NOT default to circular blobs.
- If shape_hint is vertical, height MUST be greater than width.
- Use background space intentionally.
- Every row must have equal width.

Output ONLY the final grid.
"""

# =========================================================
# MCP
# =========================================================
sse_transport = None

@app.get("/sse")
async def sse(request: Request):
    global sse_transport
    sse_transport = SseServerTransport("/messages")

    async def stream():
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ):
            while True:
                await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def sse_post(request: Request):
    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "6.0-shape-aware"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "render_and_send",
                    "description": "Interpret request, plan shape-aware emoji art, render and send to Kakao",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "user_request": {
                                "type": "string",
                                "description": "Original user prompt"
                            },
                            "final_art_grid": {
                                "type": "string",
                                "description": "The final rendered emoji/ascii art grid"
                            }
                        },
                        "required": ["user_request", "final_art_grid"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        args = params.get("arguments", {})
    
        user_request = args.get("user_request", "")
        art = args.get("final_art_grid", "").strip()
    
        if not art:
            art = "❌ 아트를 생성하지 못했어요."
    
        logger.info(f"📝 Request: {user_request}")
        logger.info(f"🎨 Final Art:\n{art}")
    
        await send_kakao(art)
    
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": "✅ 전송 완료"}]
            }
        })

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.get("/")
async def health():
    return "t3xtart alive"
