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

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

# =========================================================
# 🕵️‍♂️ [디버깅] 브라우저에서 모델 확인 (/test)
# =========================================================
@app.get("/test")
async def test_gemini_connection():
    if not GOOGLE_API_KEY:
        return {"status": "error", "message": "GOOGLE_API_KEY가 없습니다."}

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url)
        if res.status_code == 200:
            models = res.json().get('models', [])
            # 생성 가능한 모델만 필터링
            available_models = [m['name'] for m in models if "generateContent" in m.get('supportedGenerationMethods', [])]
            return {
                "status": "ok", 
                "message": "Gemini 연결 성공!", 
                "available_models": available_models
            }
        else:
            return {"status": "error", "message": f"Gemini 연결 실패: {res.text}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# =========================================================
# 🧠 [수정됨] Gemini 호출 (리스트에 있는 모델로 교체)
# =========================================================
def generate_art_with_gemini(user_prompt: str):
    if not GOOGLE_API_KEY:
        return "❌ 서버 설정 오류: GOOGLE_API_KEY 없음"

    system_prompt = """
    You are a 'Pixel Emoji Artist'. convert the user's request into a 10x12 grid emoji art.
    RULES:
    1. DO NOT fill background with the subject emoji.
    2. Use COLORED BLOCKS (🟦,🟥,🟨,⬜,⬛) or Shapes to DRAW the subject.
    3. Output ONLY the emoji string.
    """

    # ✅ [변경] /test 리스트에 '확실히 있는' 모델명들
    # latest 별칭을 쓰면 알아서 최신(1.5 또는 2.0)으로 연결됩니다.
    candidate_models = [
        "models/gemini-flash-latest",    # 1순위: 최신 플래시
        "models/gemini-2.0-flash-exp",   # 2순위: 2.0 실험 버전
        "models/gemini-pro-latest",      # 3순위: 최신 프로
        "models/gemini-1.5-flash-latest" # 4순위: 1.5 최신
    ]

    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser Request: {user_prompt}"}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
        }
        
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            if response.status_code == 200:
                result = response.json()
                # 응답 구조 파싱 안전장치
                if 'candidates' in result and result['candidates']:
                    text = result['candidates'][0]['content']['parts'][0]['text']
                    logger.info(f"✅ Gemini 성공 ({model_name})")
                    return text.strip()
                else:
                    logger.warning(f"⚠️ 모델 응답 비어있음 ({model_name})")
                    continue
            else:
                logger.warning(f"⚠️ 모델 실패 ({model_name}): {response.status_code}")
                continue # 다음 모델 시도
        except Exception as e:
            logger.error(f"❌ 통신 에러 ({model_name}): {e}")
            continue
            
    return "🎨 (AI 생성 실패) Gemini 모델 연결에 실패했습니다. 잠시 후 다시 시도해주세요."

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
                "serverInfo": {"name": "t3xtart", "version": "3.6"}
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
