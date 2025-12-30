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

# ✅ Gemini 라이브러리 추가
import google.generativeai as genai

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
# 🧠 [기능 1] Gemini에게 그림 시키기 (아트 엔진)
# =========================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

def generate_art_with_gemini(user_prompt: str):
    """
    사용자의 요청(예: '라면 그려줘')을 받아 Gemini가 고퀄리티 이모지 아트를 생성합니다.
    """
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: GOOGLE_API_KEY가 없습니다. 기본 모드로 전환합니다."

    # Gemini에게 주는 '진짜' 작업 지시서
    system_prompt = """
    You are a 'Pixel Emoji Artist'. convert the user's request into a 10x12 grid emoji art.
    
    [CRITICAL RULES]
    1. DO NOT fill the background with the subject emoji. (e.g., Do not fill the square with 🍜).
    2. USE COLORED BLOCKS (🟦, 🟥, 🟨, ⬜, ⬛) or specific shapes to DRAW the subject.
    3. Use Negative Space (Background) effectively.
    
    [Examples]
    User: "Ramen"
    Output:
    ⬛⬛⬛⬛⬛⬛⬛⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛ (Bowl rim)
    ⬛🍜🟨〰️〰️🟨🍜⬛ (Noodles)
    ⬛🍜🍥🥚🍖🥚🍜⬛ (Toppings)
    ⬛🍜🟨🟨🟨🟨🍜⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛⬛⬛⬛⬛⬛⬛⬛

    User: "Star"
    Output:
    ⬛⬛⬛🟨⬛⬛⬛
    ⬛⬛🟨🟨🟨⬛⬛
    ⬛🟨🟨🟨🟨🟨⬛
    ⬛⬛🟨🟨🟨⬛⬛
    ⬛🟨⬛⬛⬛🟨⬛
    
    User: "Water Jellyfish"
    Output:
    🌊🌊🌊🌊🌊🌊🌊
    🌊🌊🟦🟦🟦🌊🌊 (Head)
    🌊🟦👀🟦👀🟦🌊
    🌊🟦🟦👄🟦🟦🌊
    🌊⚡️⚡️⚡️⚡️⚡️🌊 (Legs)
    🌊⚡️🌊⚡️🌊⚡️🌊
    
    ONLY return the Emoji Art String. No explanation.
    """
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash") # 속도 빠르고 저렴한 모델
        response = model.generate_content(f"{system_prompt}\n\nUser Request: {user_prompt}")
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini 생성 실패: {e}")
        return f"🎨 (Gemini 오류로 기본 생성)\n\n{user_prompt}"

# =========================================================
# 🔐 [기능 2] 카카오 토큰 관리 (기존 유지)
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

async def send_kakao_logic(final_art: str, original_prompt: str):
    global CURRENT_ACCESS_TOKEN
    
    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    
    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": f"🎨 t3xtart 작품 도착!\n(주제: {original_prompt})\n\n{final_art}",
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
# 📝 [기능 3] 도구 설명 변경 (AI에게 '그리지 마'라고 지시)
# =========================================================
# 이제 PlayMCP는 그림을 그리는 게 아니라, "주문서(Prompt)"만 전달하면 됩니다.
TOOL_DESCRIPTION = "사용자가 원하는 그림의 주제(예: '라면 그려줘', '사랑해 점자')를 텍스트로 받아 t3xtart 엔진으로 전달합니다."
INPUT_DESCRIPTION = "사용자의 요청 내용 그대로 입력하세요. (AI가 직접 이모지 아트를 생성하지 마십시오. 단지 요청 텍스트만 전달하세요.)"

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
                "serverInfo": {"name": "t3xtart", "version": "3.0"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "generate_and_send_art", # 이름도 명확하게 변경
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": { # 인자 이름 변경: content -> prompt
                                "type": "string",
                                "description": INPUT_DESCRIPTION
                            }
                        },
                        "required": ["prompt"]
                    }
                }]
            }
        })

    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "generate_and_send_art":
            user_prompt = args.get("prompt", "")
            
            # 1. 서버에서 Gemini를 시켜서 그림 그리기
            art_content = generate_art_with_gemini(user_prompt)
            
            # 2. 카카오톡 전송
            success, msg = await send_kakao_logic(art_content, user_prompt)
            
            result_text = "✅ 작품 생성 및 전송 완료!" if success else f"❌ 실패: {msg}"
            
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
