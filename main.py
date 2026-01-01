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
# 🔐 카카오 토큰 관리 (유지)
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
# 🧠 [뇌 개조] 아트 디렉터 프롬프트 (설계 -> 시공)
# =========================================================

# 1. 기획 단계: 여기서 색깔과 구도를 미리 정하게 함
PLANNING_PROMPT = """
You are the 'Art Director'. Plan the pixel art before drawing.
1. **Canvas Size**: Recommend a grid size (e.g., 10x10, 8x8, 12x15) best for the subject.
2. **Palette Definition**: Assign emojis to roles.
   - Main Subject (Block): Must use SOLID colors (🟩, 🟥, 🟦, 🟨, 🟧, 🟫, ⬛, ⬜).
   - Details (Icon): Use specific emojis (👀, 🌟, 🔥) sparingly.
   - Background (Texture): Use atmospheric emojis (🌿, ☁️, 🌊, ⬛) or solid colors.
3. **Layering Strategy**: How will you separate the subject from the background? (Contrast).
"""

# 2. 시공 단계: 기획서대로 진짜 타일을 깔아버림
DRAWING_PROMPT = """
You are the 'Tile Constructor'. Execute the plan into a final grid string.

[CONSTRUCTION RULES - STRICT]
1. 🧱 **BLOCKS FIRST**: The Subject MUST be drawn primarily with COLORED SQUARES (e.g., 🟩 for Snake, 🟥 for Meat). Do NOT use the object's emoji (e.g., don't use 🐍 for the snake body, use 🟩).
2. 🍱 **CLEAR SHAPE**: The subject must have a recognizable silhouette.
3. 📐 **GRID ALIGNMENT**: Every row must have the SAME number of emojis/blocks. Use `\\n` for new lines.
4. ❌ **NO LAZY FILLING**: Do not fill the whole grid with one emoji. There must be a Subject and a Background.

[MASTERPIECE EXAMPLES - AIM FOR THIS QUALITY]

Case 1: "Green Snake" (Use 🟩 for Body, 🌿 for BG)
🌿🌿🌿🌿🌿🌿🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🌿🌿🌿🟩🌿🌿
🌿🌿🟩🟩🟩🟩🌿🌿
🌿🌿🟩🌿🌿🌿🌿🌿
🌿🌿🟩🟩👀👅🌿🌿
🌿🌿🌿🌿🌿🌿🌿🌿

Case 2: "Frozen Meat" (Use 🥩/🟥 for Meat, ❄️ for BG)
❄️❄️❄️❄️❄️❄️❄️
❄️🥩🟥⬜🟥⬜❄️
❄️🟥⬜🟥⬜🟥❄️
❄️⬜🟥⬜🟥⬜❄️
❄️🟥⬜🟥⬜🟥❄️
❄️❄️❄️❄️❄️❄️❄️

Case 3: "Ramen" (Bowl Shape + Noodle Lines)
⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛🍜🟨〰️〰️〰️🟨🍜⬛
⬛🍜🍥🥚🍖🥚🍥🍜⬛
⬛🍜🟨🟨🟨🟨🟨🍜⬛
⬛⬛🍜🍜🍜🍜🍜⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛

Case 4: "Burning Jellyfish" (Contrast: Fire vs Water)
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊

Case 5: "Earth" (Blue Circle + Green Continents)
⬛⬛⬛🟦🟦🟦⬛⬛⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛🟦🟦🟩🟩🟩🟩🟦⬛
⬛🟦🟦🟦🟩🟦🟦🟦⬛
⬛🟩🟦🟦🟩🟩🟦🟦⬛
⬛⬛🟦🟦🟩🟩🟦⬛⬛
⬛⬛⬛🟦🟦🟦⬛⬛⬛

Case 6: "Night Moon" (Yellow Moon + Black BG)
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛
⬛⬛⬛⬛🟨🟨⬛⬛⬛⬛
⬛⬛⬛🟨🟨🟨🟨⬛⬛⬛
⬛⬛⬛🟨🟨🟨🟨⬛⬛⬛
⬛⬛⬛⬛🟨🟨⬛⬛⬛⬛
⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛

Case 7: "67" (Random color numbers + Random color BG)
⬛⬛🟥⬛⬛🟥🟥🟥⬛
⬛🟥⬛🟥⬛🟥⬛🟥⬛
⬛🟥⬛⬛⬛⬛⬛🟥⬛
⬛🟥🟥🟥⬛⬛⬛🟥⬛
⬛🟥⬛🟥⬛⬛⬛🟥⬛
⬛⬛🟥⬛⬛⬛⬛🟥⬛

Output ONLY the final grid string.
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
                "serverInfo": {"name": "t3xtart", "version": "5.0-art-director"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": "Visualize user request into High-Quality Pixel Emoji Art. First plan the palette and grid, then draw.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "artistic_planning": {
                                "type": "string",
                                "description": PLANNING_PROMPT
                            },
                            "final_art_grid": {
                                "type": "string",
                                "description": DRAWING_PROMPT
                            }
                        },
                        "required": ["artistic_planning", "final_art_grid"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deliver_kakao_message":
            # AI의 기획 의도를 로그로 확인 (디버깅용)
            plan = args.get("artistic_planning", "")
            logger.info(f"🎨 Art Director's Plan:\n{plan}")
            
            content = args.get("final_art_grid", "")
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
