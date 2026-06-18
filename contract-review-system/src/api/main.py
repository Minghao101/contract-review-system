"""
FastAPI应用入口
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from config.settings import get_settings

# 配置根日志 - 强制输出到控制台
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)

settings = get_settings()

logger.info("=" * 50)
logger.info("智能合同审查系统 API 启动中...")
logger.info(f"LLM Provider: {settings.LLM_PROVIDER}")
logger.info(f"LLM Model: {settings.LLM_MODEL}")
logger.info("=" * 50)

app = FastAPI(
    title="智能合同审查系统",
    description="基于多Agent协作的合同审查API",
    version="1.0.0",
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "智能合同审查系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
