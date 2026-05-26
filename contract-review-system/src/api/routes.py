"""
API路由模块
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from .task_manager import TaskManager

router = APIRouter()

# 任务管理器实例
task_manager = TaskManager()


class ContractReviewRequest(BaseModel):
    """合同审查请求"""
    contract_text: str = Field(..., description="合同文本内容")
    contract_type: Optional[str] = Field(default="general", description="合同类型")
    review_focus: Optional[list] = Field(default=[], description="审查重点")
    callback_url: Optional[str] = Field(default=None, description="回调URL")


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/review", response_model=TaskResponse)
async def submit_review(request: ContractReviewRequest):
    """
    提交合同审查任务

    将合同发送到消息队列，异步处理
    """
    try:
        task_id = await task_manager.submit_task(
            contract_text=request.contract_text,
            contract_type=request.contract_type,
            review_focus=request.review_focus,
            callback_url=request.callback_url,
        )
        return TaskResponse(
            task_id=task_id,
            status="queued",
            message="任务已提交到队列"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review/sync", response_model=dict)
async def submit_review_sync(request: ContractReviewRequest):
    """
    同步合同审查（直接处理，不经过队列）

    适用于小文档或测试场景
    """
    try:
        result = await task_manager.process_sync(
            contract_text=request.contract_text,
            contract_type=request.contract_type,
            review_focus=request.review_focus,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """查询任务状态"""
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        result=task.get("result"),
        error=task.get("error"),
    )


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = 10):
    """列出任务"""
    tasks = await task_manager.list_tasks(status=status, limit=limit)
    return {"tasks": tasks}
