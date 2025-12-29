import os
import json
import requests
import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# 1. 환경 변수에서 토큰 가져오기 (Render 설정에서 입력할 것임)
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN")

# 2. 서버 초기화
app = FastAPI()
mcp_server = Server("t3xtart-delivery-service")

# 3. 도구 정의
@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="deliver_kakao_message",
            description="완성된 텍스트 메시지나 이모지 아트를 입력받아 사용자의 카카오톡으로 전송합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "전송할 전체 메시지 내용"
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

    if not KAKAO_TOKEN:
        return [types.TextContent(type="text", text="❌ 서버 오류: 카카오 토큰이 설정되지 않았습니다.")]

    message_content = arguments.get("content")
    final_text = f"🎨 [t3xtart] 작품이 도착했습니다!\n\n{message_content}\n\n(t3xtart AI가 생성함)"

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
            return [types.TextContent(type="text", text="✅ 카카오톡 전송 완료")]
        else:
            return [types.TextContent(type="text", text=f"❌ 전송 실패: {res.text}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"❌ 전송 중 에러 발생: {str(e)}")]

# 4. SSE 엔드포인트 설정
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

@app.post("/messages")
async def handle_messages(request: Request):
    if sse_transport:
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return {"status": "ok"}

# 5. 실행 (Render가 실행할 때는 이 부분이 아니라 명령어로 실행됨)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
