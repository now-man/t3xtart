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
# 🕵️‍♂️ [디버깅] 서버 시작 시 '사용 가능한 모델' 확인
# =========================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

def log_available_models():
    """
    내 API 키로 사용할 수 있는 모델의 '정확한 이름'을 구글에 물어보고 로그에 남깁니다.
    """
    if not GOOGLE_API_KEY:
        logger.error("❌ GOOGLE_API_KEY가 없습니다.")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            models = res.json().get('models', [])
            logger.info("============== [Gemini 모델 리스트] ==============")
            for m in models:
                # 'generateContent' 기능을 지원하는 모델만 출력
                if "generateContent" in m.get('supportedGenerationMethods', []):
                    logger.info(f"✅ 사용 가능: {m['name']}") # 예: models/gemini-1.5-flash
            logger.info("==================================================")
        else:
            logger.error(f"❌ 모델 리스트 조회 실패: {res.text}")
    except Exception as e:
        logger.error(f"❌ 모델 리스트 조회 중 에러: {e}")

# 서버 시작할 때 한 번 실행 (로그 확인용)
log_available_models()

# =========================================================
# 🧠 [수정됨] Gemini 직접 호출 (이름 변경: flash-latest)
# =========================================================
def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: GOOGLE_API_KEY 없음"

    # 프롬프트 설정
    system_prompt = """
    You are a 'Pixel Emoji Artist'. convert the user's request into a 10x12 grid emoji art.
    RULES:
    1. DO NOT fill background with the subject emoji.
    2. Use COLORED BLOCKS (🟦,🟥,🟨,⬜,⬛) or Shapes to DRAW the subject.
    3. Output ONLY the emoji string.
    """

    # 1차 시도: 1.5 Flash (Latest 버전 명시)
    # models/ 접두사를 포함해야 안전합니다.
    target_model = "models/gemini-1.5-flash-latest" 
    
    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={GOOGLE_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        
        if response.status_code == 200:
            result = response.json()
            try:
                text_content = result['candidates'][0]['content']['parts'][0]['text']
                logger.info(f"✅ Gemini 생성 성공 ({target_model})")
                return text_content.strip()
            except:
                return "🎨 (생성 오류) 응답 형식이 올바르지 않습니다."
        else:
            logger.warning(f"⚠️ 1차 모델({target_model}) 실패: {response.status_code}. 2차 시도합니다.")
            # 2차 시도: 1.0 Pro (가장 안정적)
            return try_fallback_model(user_prompt, system_prompt)
            
    except Exception as e:
        logger.error(f"❌ 통신 에러: {e}")
        return try_fallback_model(user_prompt, system_prompt)

def try_fallback_model(user_prompt, system_prompt):
    """Flash 실패 시 Pro 모델로 재시도"""
    # models/gemini-pro (이건 1.0 버전이라 거의 100% 됩니다)
    target_model = "models/gemini-pro"
    url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={GOOGLE_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}]
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(payload))
        if res.status_code == 200:
            logger.info(f"✅ Gemini 생성 성공 ({target_model} - Fallback)")
            return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            logger.error(f"❌ 2차 모델({target_model}) 실패: {res.text}")
    except Exception as e:
        logger.error(f"❌ 2차 에러: {e}")
    
    return "🎨 (AI 생성 실패) 모든 모델이 응답하지 않습니다. Render 로그의 '모델 리스트'를 확인해주세요."

# =========================================================
# 🔐 카카오 토큰 관리 (기존 유지)
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
# 📝 도구 설명 (기존 유지)
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
                "serverInfo": {"name": "t3xtart", "version": "3.4"}
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
            art_content = generate_art_with_gemini(user_prompt)
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
