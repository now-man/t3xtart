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
                "button_title": "자세히 보기"
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
# 🧠 [뇌 개조] "추상화 및 아이콘화" (Abstraction & Iconography)
# =========================================================
# 특정 사물 예시를 외우는 게 아니라, '단순화하는 원리'를 가르칩니다.

LOGIC_INSTRUCTION = """
[TASK] Analyze the user's request and break it down into 'Geometric Primitives' for a 10x12 low-res grid.
You act as an 'Icon Designer'.

[ABSTRACTION LOGIC]
1. **Deconstruct**: Break the subject into max 2-3 parts. (e.g., Saturn = Circle + Line).
2. **Palette**: Pick ONE main color for the subject, ONE contrasting color for background.
3. **Geometry**:
   - Round Object -> Use a 'Plus (+)' or 'Diamond (◆)' shape block cluster.
   - Square/Can Object -> Use a Rectangle block cluster.
   - Numbers/Letters -> Use 1-block stroke width.

[OUTPUT FORMAT]
String describing: "Subject=[Shape]+[Color], Background=[Color], Key Feature=[Emoji]"
"""

ART_INSTRUCTION = """
[THE CANVAS] STRICT 10 rows x 12 columns Grid.

[ICONOGRAPHY RULES - HOW TO DRAW]
1. 🧱 **BLOCKS over EMOJIS**: Use colored squares (🟥🟦🟩🟨🟧🟫⬛⬜) to build the main shape.
   - Do NOT use a single emoji to represent the object. DRAW IT.
2. 🍱 **CENTERING**: Draw the subject in the middle (rows 2-8, cols 2-9). Leave margins.
3. ✂️ **NEGATIVE SPACE**: Do NOT fill the whole background if not necessary. Use ⬛ or ☁️ or ⬜ for empty space to make the subject pop.
4. 🖍️ **STROKES**: For thin objects (numbers, letters, limbs), use a single line of blocks.

[UNIVERSAL SHAPE LIBRARY]
- **Circle/Sphere** (Planet, Face, Ball):
  ⬛⬛🟨🟨⬛⬛
  ⬛🟨🟨🟨🟨⬛
  ⬛🟨🟨🟨🟨⬛
  ⬛⬛🟨🟨⬛⬛

- **Cylinder/Rectangle** (Can, Building, Cup):
  ⬛⬛🟦🟦🟦⬛⬛
  ⬛⬛🟦🟦🟦⬛⬛
  ⬛⬛🟦🟦🟦⬛⬛
  ⬛⬛🟦🟦🟦⬛⬛

- **Line/Cross** (Wings, Saturn Ring):
  ⬜⬜⬜⬜⬜⬜
  ⬜🟥🟥🟥🟥⬜ (Horizontal)
  ⬜⬜⬜⬜⬜⬜

Generate ONLY the grid string.
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
                "serverInfo": {"name": "t3xtart", "version": "4.0-abstraction"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": "Convert user request into a minimalist 10x12 Pixel Art Icon and send to KakaoTalk.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            # 1. 시각적 분해 논리 (AI가 스스로 모양을 정의하게 함)
                            "visual_logic": {
                                "type": "string",
                                "description": LOGIC_INSTRUCTION
                            },
                            # 2. 실제 그림
                            "final_art": {
                                "type": "string",
                                "description": ART_INSTRUCTION
                            }
                        },
                        "required": ["visual_logic", "final_art"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deliver_kakao_message":
            # AI의 생각 과정 로그 확인
            logic = args.get("visual_logic", "")
            logger.info(f"🤖 도안 설계: {logic}")
            
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
