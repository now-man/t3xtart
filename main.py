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

# 2. 서버 초기화
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

# 3. 도구 정의 (SSE 연결용)
@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="deliver_kakao_message",
            description="완성된 텍스트 메시지나 이모지 아트를 입력받아 사용자의 카카오톡으로 전송합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "전송할 전체 메시지 내용"}
                },
                "required": ["content"]
            }
        )
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "deliver_kakao_message":
        raise ValueError(f"Unknown tool: {name}")

    if not KAKAO_TOKEN:
        return [types.TextContent(type="text", text="❌ 서버 오류: 카카오 토큰 설정 안됨")]

    message_content = arguments.get("content")
    final_text = f"🎨 [t3xtart] 작품 도착!\n\n{message_content}\n\n(t3xtart AI 생성)"

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {KAKAO_TOKEN}"}
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": final_text,
            "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
            "button_title": "앱 열기"
        })
    }
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code == 200:
            return [types.TextContent(type="text", text="✅ 전송 완료")]
        else:
            return [types.TextContent(type="text", text=f"❌ 실패: {res.text}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 에러: {str(e)}")]

# =================================================================
# 4. SSE 및 검증 로직 (여기가 중요합니다!)
# =================================================================
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
    try:
        body = await request.json()
        logger.info(f"POST /sse 요청 수신: {body}")
    except:
        return JSONResponse(content={"status": "ok"})

    method = body.get("method")
    request_id = body.get("id")

    # 1. 초기화 요청 (initialize)
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
    
    # 2. 도구 목록 요청 (tools/list) - 여기가 핵심 수정 사항입니다!
    if method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "deliver_kakao_message",
                        "description": "완성된 텍스트 메시지나 이모지 아트를 입력받아 사용자의 카카오톡으로 전송합니다.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "전송할 전체 메시지 내용"}
                            },
                            "required": ["content"]
                        }
                    }
                ]
            }
        })

    # 3. 기타 알림 (notifications/initialized 등)
    if method == "notifications/initialized":
        return JSONResponse(content={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # 4. 그 외 요청 (ping 등)
    return JSONResponse(content={
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {}
    })

@app.post("/messages")
async def handle_messages(request: Request):
    if sse_transport:
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
