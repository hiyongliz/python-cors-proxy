import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # [1] 导入 CORS 中间件
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

logging.info("Starting CORS Proxy Server...")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # 允许所有来源 (生产环境建议改为 ["https://你的前端域名.com"])
    allow_origins=["*"],
    # 允许携带 Cookie / 身份验证信息
    allow_credentials=True,
    # 允许所有 HTTP 方法 (POST, GET, OPTIONS 等)
    allow_methods=["*"],
    # 允许所有请求头 (Content-Type, Authorization 等)
    allow_headers=["*"],
)

# 配置你的 API Key 和 上游地址
BASE_URL = os.getenv("BASE_URL", "")
UPSTREAM_URL = f"{BASE_URL}/v1/chat/completions"


@app.post("/v1/chat/completions")
async def generate_image_stream(req: Request):
    """
    接收 prompt 和 size，调用上游 Nano-Banana-Pro 模型，并流式返回结果
    """
    req_json = await req.json()
    req_json.setdefault("size", "16:9")

    # 2. 构造 Headers (伪装成浏览器，防止 Cloudflare 拦截)
    headers = {
        "Authorization": f"Bearer {req.headers.get('authorization', '').split(' ')[1]}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    }

    # httpx 的单位是秒
    timeout = httpx.Timeout(connect=60.0, read=3000.0, write=60.0, pool=60.0)

    # 4. 定义流式生成器
    async def upstream_generator():
        async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
            try:
                # 发起 POST 请求
                async with client.stream(
                    "POST", UPSTREAM_URL, json=req_json, headers=headers
                ) as response:
                    # 如果上游报错 (如 401, 400)，直接透传错误信息
                    if response.status_code != 200:
                        error_msg = await response.read()
                        yield f"Error {response.status_code}: {error_msg.decode()}".encode()
                        return

                    # 逐块读取并转发
                    async for chunk in response.aiter_bytes():
                        # 这里直接转发原始 bytes，保留 SSE 格式 (data: {...})
                        yield chunk

            except httpx.ReadTimeout:
                yield b'{"error": "Upstream timeout (drawing took too long)"}'
            except Exception as e:
                yield f'{{"error": "{str(e)}"}}'.encode()

    # 5. 返回流式响应
    return StreamingResponse(upstream_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    # 启动服务
    uvicorn.run(app, host="0.0.0.0", port=8000)
