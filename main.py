import os
import json
import logging
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from mcp.server.sse import SseServerTransport

# 로그 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("t3xtart")

# 1. 환경 변수
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN")

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# 🎨 도구 설명 및 로직 분리
# ---------------------------------------------------------

TOOL_DESCRIPTION = """
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

# [핵심] 카카오 전송 로직을 별도 함수로 분리했습니다.
async def send_kakao_logic(content: str):
    token = os.environ.get("KAKAO_TOKEN")
    if not token:
        return False, "서버 토큰 설정 오류"

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {token}"}
    
    # 템플릿 구성
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": f"🎨 t3xtart 작품 도착!\n\n{content}\n\n(AI Generated)",
            "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
            "button_title": "자세히 보기"
        })
    }
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code == 200:
            return True, "전송 성공"
        elif res.status_code == 401:
            return False, "토큰 만료됨 (401)"
        else:
            return False, f"카카오 에러: {res.text}"
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------
# SSE (GET) - 연결 유지용
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
            # 여기서는 빈 루프만 돌려도 연결은 유지됩니다.
            # 실제 요청 처리는 POST에서 직접 하기 때문입니다.
            while True:
                await asyncio.sleep(1) 
    return StreamingResponse(stream(), media_type="text/event-stream")

# ---------------------------------------------------------
# POST 처리 (여기가 핵심입니다!)
# ---------------------------------------------------------
import asyncio

@app.post("/sse")
async def handle_sse_post(request: Request):
    """
    PlayMCP의 모든 요청(등록, 리스트, 도구 실행)을 직접 처리하는 라우터
    """
    try:
        body = await request.json()
        logger.info(f"요청 수신: {body}")
    except:
        return JSONResponse({"status": "error", "message": "No JSON body"})

    method = body.get("method")
    msg_id = body.get("id")

    # 1. 초기화 (initialize)
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

    # 2. 도구 목록 (tools/list)
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [{
                    "name": "deliver_kakao_message",
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "생성된 이모지 아트"}
                        },
                        "required": ["content"]
                    }
                }]
            }
        })

    # 3. 도구 실행 (tools/call) - 직접 실행!
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deliver_kakao_message":
            content = args.get("content", "")
            
            # 카카오 전송 실행
            success, msg = await send_kakao_logic(content)
            
            # 결과 구성
            result_text = "✅ 전송 성공!" if success else f"❌ 실패: {msg}"
            is_error = not success

            # JSON-RPC 응답 포맷
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": is_error
                }
            })
        else:
            # 모르는 도구일 때
            return JSONResponse({
                "jsonrpc": "2.0", 
                "id": msg_id, 
                "error": {"code": -32601, "message": "Method not found"}
            })

    # 4. 기타 (ping 등)
    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {}})

@app.post("/messages")
async def handle_messages(request: Request):
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
