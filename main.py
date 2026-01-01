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
# 🔐 카카오 토큰 관리 (완벽함 - 유지)
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    rest_api_key = os.environ.get("KAKAO_CLIENT_ID")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET") 
    
    if not rest_api_key or not refresh_token:
        return False

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token
    }
    
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
# 🧠 [뇌 개조] 강제 사고 유도 (CoT) 프롬프트
# =========================================================
PLAN_INSTRUCTION = """
Describe your visual strategy BEFORE drawing.
1. Identify the Subject Color (e.g., Frog=Green 🟩) and Background Color (e.g., Water=Blue 🟦).
2. Explain how you will draw the SILHOUETTE of the subject using blocks.
(Example: "I will use Green blocks to draw a frog shape in the center, and fill the rest with Blue blocks.")
"""

ART_INSTRUCTION = """
[THE CANVAS] 10 rows x 12 columns Grid.

[STRICT DRAWING RULES]
1. 🧱 **BLOCKS FIRST**: You MUST use colored blocks (⬛⬜🟥🟦🟩🟨🟧🟫) for the main shape.
2. 🎭 **CONTRAST**: The Subject and Background MUST be different colors.
   - ❌ BAD: Filling all with 🌸.
   - ✅ GOOD: 🌸 background, 🟩 Frog shape in middle.
3. 📐 **SHAPE**: Draw a recognizable shape (pixel art style).

[Examples]
User: "Flower Frog" (Green Frog + Pink Flower BG)
🌸🌸🌸🌸🌸🌸🌸🌸🌸🌸
🌸🌸🟩🟩🟩🟩🟩🌸🌸🌸
🌸🌸🟩⬜🟩⬜🟩🌸🌸🌸
🌸🌸🟩🟩🟩🟩🟩🌸🌸🌸
🌸🌸🟩🦵🏽🌸🦵🏽🟩🌸🌸🌸
🌸🌸🌸🌸🌸🌸🌸🌸🌸🌸

User: "Night Moon" (Yellow Moon + Black BG)
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛⬛⬛🟨🟨⬛⬛⬛⬛
⬛⬛⬛🟨🟨🟨🟨⬛⬛⬛
⬛⬛⬛🟨🟨🟨🟨⬛⬛⬛
⬛⬛⬛⬛🟨🟨⬛⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛

User: "Green Snake in Grass" (Subject: Green Blocks / Background: Leaf Emojis)
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

User: "Frozen Pork Belly" (Pink/Red layers + Ice)
❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️
❄️❄️🥩🟥⬜🟥⬜❄️❄️❄️
❄️❄️🟥⬜🟥⬜🟥❄️❄️❄️
❄️❄️⬜🟥⬜🟥⬜❄️❄️❄️
❄️❄️🟥⬜🟥⬜🟥❄️❄️❄️
❄️❄️❄️❄️❄️❄️❄️❄️❄️❄️

User: "Ramen" (Bowl + Noodles)
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛⬛
⬛🍜🟨〰️〰️〰️🟨🍜⬛⬛
⬛🍜🍥🥚🍖🥚🍥🍜⬛⬛
⬛🍜🟨🟨🟨🟨🟨🍜⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛

User: "Burning Jellyfish" (Fire Dome + Tentacles)
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊

Generate the final grid string here.
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
                "serverInfo": {"name": "t3xtart", "version": "3.0-brain-upgrade"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": "Visualize the user's request as a high-quality 10x12 Pixel Emoji Art and send it to KakaoTalk.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            # 1. 계획을 먼저 세우게 강제함 (중요!)
                            "design_plan": {
                                "type": "string",
                                "description": PLAN_INSTRUCTION
                            },
                            # 2. 계획된 대로 그리게 함
                            "final_art": {
                                "type": "string",
                                "description": ART_INSTRUCTION
                            }
                        },
                        "required": ["design_plan", "final_art"] # 둘 다 필수!
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deliver_kakao_message":
            # design_plan은 AI 생각 정리용이므로 로그에만 찍고 버림
            plan = args.get("design_plan", "")
            logger.info(f"🤖 AI 설계도: {plan}")
            
            # 실제 전송은 final_art만
            content = args.get("final_art", "")
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
