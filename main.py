import os
import json
import logging
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

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

mcp_server = Server("t3xtart-delivery-service")

# ---------------------------------------------------------
# 🎨 [AI 교육] 도구 설명에 '예시'를 넣어 퀄리티를 높입니다.
# ---------------------------------------------------------
TOOL_DESCRIPTION = """
당신은 '이모지 픽셀 아티스트'입니다. 사용자의 요청을 10x10 내외의 이모지 아트로 변환하여 전송합니다.

[중요 규칙]
1. 배경을 꽉 채우지 마세요. 필요한 부분만 이모지를 쓰고, 여백은 전각 공백(　)이나 흰색(⬜)을 사용하세요.
2. 모양을 단순화하세요. 복잡하면 깨집니다.
3. 요청에 맞는 '기본 예시'를 참고하여 변형하세요.

[예시: 다람쥐]
⬜⬜⬜🐿️🐿️⬜⬜
⬜⬜🐿️🟫🟫🐿️⬜
⬜🐿️🟫👀🟫🐿️⬜
⬜🐿️🟫🟫🟫🐿️⬜
⬜⬜🐿️🐿️🐿️⬜⬜
(갈색 네모와 다람쥐 이모지를 섞어서 표현)

[예시: 하트]
⬜⬜❤️⬜❤️⬜⬜
⬜❤️🟥❤️🟥❤️⬜
⬜❤️🟥🟥🟥❤️⬜
⬜⬜❤️🟥❤️⬜⬜
⬜⬜⬜❤️⬜⬜⬜

위와 같은 스타일로 창의적으로 생성하여 'content'에 담으세요.
"""

# ---------------------------------------------------------
# 🛡️ [안전장치] 전송 실패 시 보낼 기본 그림
# ---------------------------------------------------------
FALLBACK_ART = """
❓❓❓❓❓❓❓
❓❓🙄❓🙄❓❓
❓❓❓👄❓❓❓
❓❓❓❓❓❓❓
(오류가 발생하여 기본 이미지를 보냅니다)
"""

@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="deliver_kakao_message",
            description=TOOL_DESCRIPTION,
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "생성된 이모지 아트 문자열"
                    }
                },
                "required": ["content"]
            }
        )
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "deliver_kakao_message":
        raise ValueError(f"Unknown tool: {name}")

    current_token = os.environ.get("KAKAO_TOKEN")
    
    # 1. AI가 만든 콘텐츠 가져오기
    message_content = arguments.get("content", "")
    
    # 2. 카카오톡 전송 함수 (내부 함수)
    def send_to_kakao(text_to_send):
        if not current_token:
            return False, "토큰 없음"
            
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {current_token}"}
        # 메시지 템플릿 (텍스트가 너무 길면 잘릴 수 있음)
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 도착!\n\n{text_to_send}",
                "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
                "button_title": "자세히 보기"
            })
        }
        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code == 200:
                return True, "성공"
            return False, f"카카오 에러 {res.status_code}: {res.text}"
        except Exception as e:
            return False, str(e)

    # 3. 첫 번째 시도: AI가 만든 그림 전송
    success, msg = send_to_kakao(message_content)
    
    if success:
        return [types.TextContent(type="text", text="✅ 작품 전송 성공!")]
    
    # 4. 실패 시: 기본 그림(FALLBACK_ART)으로 재전송 시도
    logger.error(f"첫 번째 전송 실패: {msg}. 기본 이미지로 재시도합니다.")
    success_fallback, msg_fallback = send_to_kakao(FALLBACK_ART)
    
    if success_fallback:
        return [types.TextContent(type="text", text="⚠️ 생성된 아트 전송에 실패하여 '기본 이미지'를 대신 보냈습니다.")]
    else:
        return [types.TextContent(type="text", text=f"❌ 전송 완전 실패. 토큰을 확인하세요. ({msg})")]

# ---------------------------------------------------------
# SSE 및 라우팅 로직 (여기가 수정됨!)
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
            await mcp_server.run(
                streams[0], streams[1], mcp_server.create_initialization_options()
            )
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/sse")
async def handle_sse_validation(request: Request):
    """
    PlayMCP 요청 라우터
    1. 등록/검증 요청 -> 직접 JSON 응답
    2. 도구 실행 요청 -> 원래의 MCP Transport로 넘김 (중요!)
    """
    try:
        body = await request.json()
    except:
        return JSONResponse(content={"status": "ok"})

    method = body.get("method")
    request_id = body.get("id")

    # [케이스 1] 등록 및 정보 로드 요청 (우리가 직접 대답)
    if method == "initialize":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}, "resources": {}},
                "serverInfo": {"name": "t3xtart-delivery-service", "version": "1.0"}
            }
        })
    
    if method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "deliver_kakao_message",
                        "description": TOOL_DESCRIPTION, 
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "생성된 이모지 아트"}
                            },
                            "required": ["content"]
                        }
                    }
                ]
            }
        })

    # [케이스 2] 실제 도구 실행 요청 (tools/call)
    # -> 우리가 가로채면 안 됨! 원래 주인(sse_transport)에게 넘겨야 함
    if sse_transport:
        # Request 객체를 다시 만들 필요 없이, 들어온 요청을 그대로 처리하게 유도
        # 하지만 FastAPI 구조상 body를 이미 읽었으므로, transport에 직접 메시지를 주입해야 함
        # 여기서는 간단하게 /messages 로직을 재사용합니다.
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
        return {"status": "ok"} # 처리는 비동기로 됨

    return JSONResponse(content={"status": "error", "message": "Transport not ready"})

@app.post("/messages")
async def handle_messages(request: Request):
    if sse_transport:
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
