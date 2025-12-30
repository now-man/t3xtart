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
# 🔐 [기능 1] 카카오 토큰 자동 갱신 로직
# =========================================================
CURRENT_ACCESS_TOKEN = os.environ.get("KAKAO_TOKEN")

def refresh_kakao_token():
    global CURRENT_ACCESS_TOKEN
    rest_api_key = os.environ.get("KAKAO_CLIENT_ID")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
    
    if not rest_api_key or not refresh_token:
        logger.error("토큰 갱신 실패: 환경변수 부족")
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
    
    # 토큰이 없으면 갱신 시도
    if not CURRENT_ACCESS_TOKEN:
        if not refresh_kakao_token():
            return False, "토큰 발급 실패"

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 작품 도착!\n\n{content}\n\n(AI Generated)",
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "자세히 보기"
            })
        }
        return requests.post(url, headers=headers, data=payload)

    # 1차 시도
    res = try_post(CURRENT_ACCESS_TOKEN)
    
    # 401(만료) 에러 -> 갱신 -> 2차 시도
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
# 📝 [기능 2] 도구 설명 (심플 버전 - 비밀 숨김)
# =========================================================
SIMPLE_TOOL_DESCRIPTION = """
당신은 '위트 있는 이모지 믹스(Mix) 아티스트'입니다.
단순한 색깔 네모(🟦)로 채우는 것이 *아니라*, 사물의 의미나 모양이 유사한 이모지를 조합해서 형상을 만듭니다.

[핵심 규칙]
1. **재료의 비유:** '불타는 해파리'라면 빨간 네모 대신 실제 '불(🔥)'과 '번개(⚡)'를 사용하여 그리세요. '얼음 고양이'라면 '눈 결정(❄️)'이나 '다이아몬드(💎)', '흰 구름(☁️)'을 사용하세요.
2. **배경:** 주제와 어울리는 이모지(바다=🌊, 하늘=☁️, 밤=⬛)로 배경을 깔아 분위기를 만드세요.
3. **얼굴:** 눈(👀, 👁️), 입(👄), 코(🔻) 이모지를 적극 활용하여 표정을 만드세요.
4. **크기:** 7x7 ~ 9x9 정도의 작은 크기로 집중도 있게 그리세요. 단, 사용자가 직접 크기를 지정했다면 이 크기에 맞게 만들어야 합니다.

[예시 1: 불타는 해파리]
(설명: 배경은 파도, 몸통은 불, 눈은 리얼한 눈, 촉수는 번개로 표현)
🌊🌊🌊🌊🌊🌊🌊
🌊🌊🔥🔥🔥🔥🌊
🌊🔥👁️🔥👁️🔥🌊
🌊🔥🔥👄🔥🔥🌊
🌊⚡️⚡️⚡️⚡️⚡️🌊
🌊⚡️🌊⚡️🌊⚡️🌊
🌊🌊🌊🌊🌊🌊🌊

[예시 2: 얼음 속성 고양이]
(설명: 귀는 설산, 얼굴은 구름, 눈은 다이아몬드, 배경은 눈송이)
❄️❄️❄️❄️❄️❄️❄️
❄️🗻❄️❄️❄️🗻❄️
❄️☁️💎☁️💎☁️❄️
❄️☁️☁️🔻☁️☁️❄️
❄️❄️☁️〰️☁️❄️❄️
❄️❄️❄️❄️❄️❄️❄️

위 예시들처럼 이모지의 본래 모양을 활용하여 위트 있고 감각적인 아트를 생성해 'content'에 담으세요.
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
                "serverInfo": {"name": "t3xtart", "version": "1.0"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": SIMPLE_TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "전송할 이모지 아트 내용"}
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
