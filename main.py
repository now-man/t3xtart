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
# 🎨 [핵심 수정] 도구 설명에 '강력한 지시사항'을 포함시켰습니다.
# ---------------------------------------------------------
TOOL_DESCRIPTION = """
이 도구는 단순한 텍스트 전송기가 아닙니다. 당신은 '이모지 그리드 아티스트'입니다.
사용자의 요청(예: "나뭇잎 원숭이")을 받으면, 반드시 다음 규칙을 따라 'content'를 생성하세요:

1. [캔버스] 10x10 ~ 12x12 크기의 이모지 그리드(Grid)를 마음속으로 그리세요.
2. [채우기] 빈 공간은 배경색 이모지(⬜, ⬛, ☁️, 🟦 등)로 꽉 채우세요.
3. [그리기] 주제(원숭이, 케이크 등)를 돋보이는 색상의 이모지로 중앙에 배치하세요.
4. [전송] 완성된 그리드 아트 문자열을 이 도구의 'content' 인자로 전달하세요.

(주의: 텍스트 설명보다 이모지 그림이 메인이 되어야 합니다.)
"""

@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="deliver_kakao_message",
            description=TOOL_DESCRIPTION, # 수정된 설명 적용
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "완성된 이모지 그리드 아트 및 메시지 내용"
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

    # 토큰 확인 (매 호출마다 환경변수 다시 확인)
    current_token = os.environ.get("KAKAO_TOKEN")
    if not current_token:
        return [types.TextContent(type="text", text="❌ 서버 오류: KAKAO_TOKEN 환경변수가 없습니다.")]

    message_content = arguments.get("content")
    
    # 메시지 전송 로직
    final_text = f"{message_content}\n\n🎨 t3xtart AI Generated"

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {current_token}"}
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": final_text,
            "link": {"web_url": "https://www.kakao.com", "mobile_web_url": "https://www.kakao.com"},
            "button_title": "자세히 보기"
        })
    }
    
    try:
        res = requests.post(url, headers=headers, data=payload)
        if res.status_code == 200:
            return [types.TextContent(type="text", text="✅ 전송 성공! 멋진 작품이네요.")]
        elif res.status_code == 401:
             return [types.TextContent(type="text", text="❌ 전송 실패: 카카오 토큰이 만료되었습니다. 개발자에게 토큰 갱신을 요청하세요.")]
        else:
            return [types.TextContent(type="text", text=f"❌ 카카오 에러 ({res.status_code}): {res.text}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 서버 내부 에러: {str(e)}")]

# ---------------------------------------------------------
# SSE 및 검증 핸들러
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
    try:
        body = await request.json()
    except:
        return JSONResponse(content={"status": "ok"})

    method = body.get("method")
    request_id = body.get("id")

    # 1. initialize
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
    
    # 2. tools/list (여기도 바뀐 설명이 나가도록 수정)
    if method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": "deliver_kakao_message",
                        "description": TOOL_DESCRIPTION, # 위에서 정의한 강력한 설명 사용
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string", "description": "완성된 이모지 그리드 아트"}
                            },
                            "required": ["content"]
                        }
                    }
                ]
            }
        })

    # 중요: tools/call 등 다른 요청은 여기서 처리하지 않고 패스해야 함 (빈값 리턴)
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
