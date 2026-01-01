import os
import json
import logging
import requests
import uvicorn
import asyncio
import time  # ⏳ 시간 지연을 위해 추가
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

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# =========================================================
# 🧠 [오뚝이 시스템] 재시도 & 백업 모델 로직
# =========================================================
def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: API 키 없음"

    # 프롬프트 (공통 사용)
    system_prompt = """
    Role: You are a master of 'Emoji Pixel Art'.
    Task: Convert the user's request into a **STRICT 10x12 GRID** art.

    [CRITICAL RULES - MUST FOLLOW]
    1. ⚠️ **MUST COMPLETE THE GRID**: You MUST generate the full 12 rows. Do NOT stop mid-way.
    2. 🧱 **Structure**: Use colored blocks (⬛⬜🟥🟦🟩🟨🟧🟫) to construct the main shape.
    3. 🎨 **Details**: Use specific emojis ONLY for crucial details.
    4. 🚫 **Clean Output**: Output ONLY the grid string. No introduction text.

    [Reference Examples]
        User: "Ramen"
    Output:
    ⬛⬛⬛⬛⬛⬛⬛⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛🍜🟨〰️〰️🟨🍜⬛
    ⬛🍜🍥🥚🍖🥚🍜⬛
    ⬛🍜🟨🟨🟨🟨🍜⬛
    ⬛⬛🍜🍜🍜🍜⬛⬛
    ⬛⬛⬛⬛⬛⬛⬛⬛

    User: "Winged Hat" (Conceptualize: Hat body + Wing emojis on sides)
    Output:
    ☁️☁️☁️☁️☁️☁️☁️☁️
    ☁️☁️⬜⬜⬜⬜☁️☁️
    ☁️🦅⬜🟥🟥⬜🦅☁️
    ☁️🦅🟥🟥🟥🟥🦅☁️
    ☁️☁️🟥🟥🟥🟥☁️☁️
    ☁️☁️☁️☁️☁️☁️☁️☁️

    User: "Blue Star"
    Output:
    ⬛⬛⬛🟦⬛⬛⬛
    ⬛⬛🟦🟦🟦⬛⬛
    ⬛🟦🟦🟦🟦🟦⬛
    ⬛⬛🟦🟦🟦⬛⬛
    ⬛🟦⬛⬛⬛🟦⬛

    User: "Burning Jellyfish"
    Output:
    🌊🌊🌊🌊🌊🌊🌊
    🌊🌊🔥🔥🔥🔥🌊
    🌊🔥👁️🔥👁️🔥🌊
    🌊🔥🔥👄🔥🔥🌊
    🌊⚡️⚡️⚡️⚡️⚡️🌊
    🌊⚡️🌊⚡️🌊⚡️🌊
    🌊🌊🌊🌊🌊🌊🌊

    User: "Frozen Pork Belly" (Pink/Red layers + Ice)
    Output:
    ❄️❄️❄️❄️❄️❄️❄️
    ❄️🥩🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️⬜🟥⬜🟥⬜❄️
    ❄️🟥⬜🟥⬜🟥❄️
    ❄️❄️❄️❄️❄️❄️❄️

    Now, generate art for:
    """

    # 🎯 전략:
    # 1. 2.5-Flash 시도
    # 2. (500 에러 시) 2초 쉬고 2.5-Flash 재시도
    # 3. (그래도 안 되면) 1.5-Flash (안정형)로 교체

    models_to_try = [
        ("models/gemini-2.5-flash", 5000),  # 1타: 최신형 (토큰 5000)
        ("models/gemini-2.5-flash", 5000),  # 2타: 재시도 (잠깐 쉬고)
        ("models/gemini-1.5-flash", 8192)   # 3타: 안정형 (토큰 넉넉함)
    ]

    for i, (model_name, max_tokens) in enumerate(models_to_try):

        # 재시도(2번째 시도)일 경우, 잠깐 쉼 (Back-off strategy)
        if i == 1:
            logger.info("⏳ 500 에러 발생. 2초 대기 후 재시도합니다...")
            time.sleep(2.0)

        # 백업 모델(3번째 시도)일 경우 로그
        if i == 2:
            logger.info("⚠️ 2.5 모델 불안정. 1.5 모델로 교체 투입!")

        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": max_tokens
            }
        }

        try:
            logger.info(f"🤖 [{i+1}차 시도] {model_name} 요청 중...")
            response = requests.post(url, headers=headers, data=json.dumps(payload))

            if response.status_code == 200:
                result = response.json()
                if 'candidates' in result and result['candidates']:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    logger.info(f"✅ 성공! (Used: {model_name})")
                    # 성공하면 바로 반환 (반복문 종료)
                    display_name = model_name.replace("models/", "").upper()
                    return text.strip(), display_name

            # 500(서버 에러) or 429(과부하) -> 다음 시도로 넘어감 (continue)
            logger.warning(f"⚠️ 실패 (Code: {response.status_code}) - {response.text[:100]}...")
            continue

        except Exception as e:
            logger.error(f"❌ 통신 에러: {e}")
            continue

    # 모든 시도가 실패했을 때
    return "🎨 (서버 과부하) 구글 AI 서버가 응답하지 않습니다. 잠시 후 천천히 다시 시도해주세요.", "System Error"

# =========================================================
# 🔐 카카오 토큰 관리
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

# =========================================================
# 📨 카카오 전송 로직
# =========================================================
async def send_kakao_logic(final_art: str, original_prompt: str, model_used: str):
    global CURRENT_ACCESS_TOKEN

    if not CURRENT_ACCESS_TOKEN:
        refresh_kakao_token()

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    final_message = f"🎨 t3xtart 작품 도착!\n(주제: {original_prompt})\n\n{final_art}\n\n(Artist: {model_used})"

    def try_post(token):
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": final_message,
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
# 📝 도구 설명
# =========================================================
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
                "serverInfo": {"name": "t3xtart", "version": "10.0-retry-system"}
            }
        })

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "tools": [{
                    "name": "generate_and_send_art",
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "prompt": {
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

            # 1. 오뚝이 시스템 가동
            art_content, model_used = generate_art_with_gemini(user_prompt)

            # 2. 카톡 전송
            success, msg = await send_kakao_logic(art_content, user_prompt, model_used)

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
