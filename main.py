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

# 로그 설정
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
# 🔐 [복구 완료] 카카오 토큰 관리 (Client Secret 포함)
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    rest_api_key = os.environ.get("KAKAO_CLIENT_ID")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET") # 필수!

    if not rest_api_key or not refresh_token:
        return False

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token
    }
    
    # 비밀키가 있으면 반드시 포함 (사용자님 환경 필수)
    if client_secret:
        data["client_secret"] = client_secret
    
    try:
        res = requests.post(url, data=data)
        if res.status_code == 200:
            new_tokens = res.json()
            CURRENT_ACCESS_TOKEN = new_tokens.get("access_token")
            return True
        return False
    except:
        return False

async def send_kakao_logic(content: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 도착!\n\n{content}",
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "작품 보기"
            })
        }
        return requests.post(url, headers=headers, data=payload)

    res = try_post(CURRENT_ACCESS_TOKEN)
    if res.status_code == 401:
        if refresh_kakao_token():
            res = try_post(CURRENT_ACCESS_TOKEN)
        else:
            return False, "토큰 갱신 실패"

    if res.status_code == 200:
        return True, "전송 성공"
    else:
        return False, f"카카오 에러: {res.text}"

# =========================================================
# 🧠 [뇌 개조] "배경과 피사체 분리" 프롬프트
# =========================================================
# 뱀 그리기 실패를 교훈 삼아, '명암'과 '대비'를 강조했습니다.
HIDDEN_INSTRUCTION = """
[ROLE] You are a 'Pixel Emoji Artist'. 
Your goal is to visualize the user's request into a strict 10x12 grid art.

[CRITICAL DESIGN RULES - MUST FOLLOW]
1. 📐 **Grid Layout**: You MUST generate a 10-row by 12-column grid. Use `\\n` for line breaks.
2. 🎭 **CONTRAST RULE (Most Important)**: 
   - The **SUBJECT** (e.g., Snake) must use SOLID BLOCKS (🟩, 🟥, 🟦, 🟨).
   - The **BACKGROUND** (e.g., Grass) must use DIFFERENT emojis (🌿, ⬛, ☁️).
   - **NEVER** fill the entire grid with the same emoji.
3. 🧱 **Construction**: Draw the silhouette/shape of the subject first, then fill the background.
4. 🚫 **No Chatter**: The 'content' argument must contain ONLY the art string.

[Visual Logic Examples - MEMORIZE THIS PATTERN]

Case 1: "Green Snake in Grass" (Subject: Green Blocks / Background: Leaf Emojis)
(Notice how the snake is distinct from the grass)
🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🟩🟩🟩🟩🌿🌿🌿
🌿🌿🌿 🌿🌿🌿🟩🌿🌿🌿
🌿🌿🌿 🌿🌿🌿🟩🌿🌿🌿
🌿🌿🟩🟩🟩🟩🟩🌿🌿🌿
🌿🌿🟩🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🟩🟩👀👅🌿🌿🌿
🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿
🌿🌿🌿🌿🌿🌿🌿🌿🌿🌿 

Case 2: "Frozen Pork Belly" (Pink/Red layers + Ice)
❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️
❄️❄️🥩🟥⬜🟥⬜❄️❄️❄️
❄️❄️🟥⬜🟥⬜🟥❄️❄️❄️
❄️❄️⬜🟥⬜🟥⬜❄️❄️❄️
❄️❄️🟥⬜🟥⬜🟥❄️❄️❄️
❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️

Case 3: "Ramen" (Bowl + Noodles)
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛⬛
⬛🍜🟨〰️〰️〰️🟨🍜⬛⬛
⬛🍜🍥🥚🍖🥚🍥🍜⬛⬛
⬛🍜🟨🟨🟨🟨🟨🍜⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛

Case 4: "Burning Jellyfish" (Fire Dome + Tentacles)
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊



Generate the art following this high-contrast style.
"""

# ---------------------------------------------------------
# 라우팅
# ---------------------------------------------------------
sse_transport = None

@app.get("/sse")
async def handle_sse(request: Request):
    global sse_transport
    sse_transport = SseServerTransport("/messages")
    async def stream():
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            while True:
                await asyncio.sleep(1) 
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def handle_sse_post(request: Request):
    try:
        body = await request.json()
    except:
        return JSONResponse({"status": "error"})

    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "2.0-fixed"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": "Generate high-quality pixel emoji art based on user text and send it to KakaoTalk.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": HIDDEN_INSTRUCTION
                            }
                        },
                        "required": ["content"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deliver_kakao_message":
            content = args.get("content", "")
            success, msg = await send_kakao_logic(content)
            result_text = "✅ 전송 성공!" if success else f"❌ 실패: {msg}"
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": not success
                }
            })
        
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "No tool"}})

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.post("/messages")
async def handle_messages(request: Request):
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
