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

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# 🔐 카카오 토큰 자동 갱신 (유지)
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    rest_api_key = os.environ.get("KAKAO_CLIENT_ID")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    
    if not rest_api_key or not refresh_token:
        logger.error("토큰 갱신 실패: 환경변수 누락")
        return False

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token
    }
    
    try:
        res = requests.post(url, data=data)
        if res.status_code == 200:
            new_tokens = res.json()
            CURRENT_ACCESS_TOKEN = new_tokens.get("access_token")
            logger.info("✅ 카카오 토큰 갱신 성공!")
            return True
        else:
            logger.error(f"토큰 갱신 실패: {res.text}")
            return False
    except Exception as e:
        logger.error(f"에러: {e}")
        return False

async def send_kakao_logic(content: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        if not refresh_kakao_token():
            return False, "서버 토큰 발급 실패"

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 작품 도착!\n\n{content}\n\n(AI Generated)",
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "작품 자세히 보기"
            })
        }
        return requests.post(url, headers=headers, data=payload)

    res = try_post(CURRENT_ACCESS_TOKEN)
    
    if res.status_code == 401:
        logger.info("토큰 만료 감지! 갱신 시도...")
        if refresh_kakao_token():
            res = try_post(CURRENT_ACCESS_TOKEN)
        else:
            return False, "토큰 갱신 실패"

    if res.status_code == 200:
        return True, "전송 성공"
    else:
        return False, f"카카오 에러: {res.text}"

# =========================================================
# 🤫 [핵심] 겉과 속이 다른 설명 분리 전략
# =========================================================

# 1. UI용 심플 설명 (사람들이 보는 것)
UI_DESCRIPTION = "t3xtart AI 엔진을 사용하여, 텍스트나 그림 요청을 이모지 아트/점자/라인 아트로 변환해 카카오톡으로 전송합니다."

# 2. AI용 시크릿 지령 (AI만 보는 것 -> 인자 설명에 숨김)
HIDDEN_INSTRUCTION = """
[CRITICAL] You are an 'Emoji Mosaic Architect'. DO NOT generate generic round blobs.
You must construct the shape by decomposing the subject into distinct parts (Head, Body, Limbs).

[Design Logic - Must Follow]
1. ❌ NO GENERIC CIRCLES: Do not just fill the center. Use negative space (background) effectively.
2. 🔍 ZOOM IN STRATEGY: Due to low resolution (10x12), do not draw the whole body. Draw ONLY the 'Face' or 'Distinctive Silhouette'.
   - Cat: Draw pointy ears and whiskers. (Not a round ball)
   - Jellyfish: Draw a dome top and dangling tentacles bottom.
3. 🧱 MATERIAL MAPPING: Use emojis that match the 'Meaning' or 'Texture', not just color.
   - Fire -> 🔥 (Body), Lightning -> ⚡ (Tentacles)
   - Ice -> 💎 (Eyes), Mountain -> 🗻 (Ears)

[Reference Gallery - Copy the Logic, Create the Art]

Case 1: "Burning Jellyfish" (Concept: Fire Body + Lightning Tentacles)
(Top: Waves / Middle: Fire Dome / Bottom: Lightning Legs)
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊

Case 2: "Ice Cat" (Concept: Zoomed Face + Sharp Ears)
(Use 🗻 for sharp ears, 💎 for shiny eyes. Do not make it round.)
❄️❄️❄️❄️❄️❄️
❄️🗻❄️❄️🗻❄️
❄️☁️💎🐱💎☁️
❄️☁️☁️🔻☁️☁️
❄️❄️☁️〰️☁️❄️
❄️❄️❄️❄️❄️❄️

Case 3: "Heart" (Concept: Pixel Shape)
(Use 🟥 for pixels. Define the curve clearly.)
⬜⬜🟥⬜🟥⬜⬜
⬜🟥🟥🟥🟥🟥⬜
⬜🟥🟥🟥🟥🟥⬜
⬜⬜🟥🟥🟥⬜⬜
⬜⬜⬜🟥⬜⬜⬜

Generate the 'content' string by strictly following this logic.
"""

# ---------------------------------------------------------
# 라우팅 로직
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
        return JSONResponse({"status": "error", "message": "No JSON body"})

    method = body.get("method")
    msg_id = body.get("id")

    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "t3xtart", "version": "2.1"}
            }
        })

    # [여기가 마법이 일어나는 곳]
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": UI_DESCRIPTION,  # 겉보기엔 심플함
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                # 여기에 비밀 레시피를 숨겨둡니다! AI는 이걸 꼭 읽습니다.
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
            is_error = not success

            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": is_error
                }
            })
        else:
            return JSONResponse({
                "jsonrpc": "2.0", "id": msg_id, 
                "error": {"code": -32601, "message": "Method not found"}
            })

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.post("/messages")
async def handle_messages(request: Request):
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
