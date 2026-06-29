"""
API路由模块
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field
import logging

from .task_manager import get_task_manager
from .document_parser import DocumentParser

logger = logging.getLogger(__name__)
router = APIRouter()

# 获取全局任务管理器实例
task_manager = get_task_manager()


class ContractReviewRequest(BaseModel):
    """合同审查请求"""
    contract_text: str = Field(..., description="合同文本内容")
    contract_type: Optional[str] = Field(default="general", description="合同类型")
    review_focus: Optional[list] = Field(default=[], description="审查重点")
    callback_url: Optional[str] = Field(default=None, description="回调URL")
    contract_name: Optional[str] = Field(default="未命名合同", description="合同名称")
    session_id: Optional[str] = Field(default=None, description="会话ID（用于多轮对话）")


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


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    task_id: str
    status: str
    message: str
    filename: str
    file_type: str
    total_chars: int


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
            contract_name=request.contract_name,
            session_id=request.session_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review/stream")
async def review_stream(request: ContractReviewRequest):
    """
    流式合同审查

    处理完所有Agent后返回格式化结果，前端使用st.write_stream模拟流式显示
    """
    import traceback as _tb
    try:
        result = await task_manager.process_sync(
            contract_text=request.contract_text,
            contract_type=request.contract_type,
            review_focus=request.review_focus,
            contract_name=request.contract_name,
            session_id=request.session_id,
        )

        # 格式化结果
        formatted = _format_stream_result(result, request.review_focus)

        return Response(
            content=formatted,
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        logger.error(f"审查请求失败: {e}\n{_tb.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


def _format_stream_result(result: dict, review_focus: list = None) -> str:
    """将审查结果格式化为流式文本"""
    # 如果有 response（来自 _format_response），直接使用
    # 覆盖：追问、修改、单Agent分析等场景
    if result.get("response"):
        response = result["response"]
        if not isinstance(response, str):
            response = str(response)
        # intent type 存在 result["status"] 中（_flatten_agent_results 写入）
        intent_type = result.get("status", "")
        if intent_type in ("modify_contract", "question_answer", "greeting", "unknown"):
            return response
        # 非全量审查意图：也直接返回 response
        if intent_type and intent_type != "contract_review":
            return response

    lines = []
    focus = review_focus[0] if review_focus else "合同审查"
    lines.append(f"针对您的问题「{focus}」，以下是分析结果：\n")

    if result.get("document_info"):
        info = result["document_info"]
        if info.get("contract_type"):
            lines.append(f"**合同类型**: {info['contract_type']}")
        if info.get("basic_info"):
            bi = info["basic_info"]
            if bi.get("parties"):
                lines.append(f"**当事方**: {', '.join(str(p) for p in bi['parties'])}")
        lines.append("")

    if result.get("risks"):
        lines.append("### ⚠️ 风险评估")
        for r in result["risks"]:
            if isinstance(r, dict):
                level = r.get("level", r.get("severity", "medium"))
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")
                title = r.get("title", r.get("name", "风险"))
                desc = str(r.get("description", ""))[:150]
                lines.append(f"- {emoji} **{title}**: {desc}")
        lines.append("")

    if result.get("compliance_violations"):
        lines.append("### ✅ 合规问题")
        for v in result["compliance_violations"]:
            desc = v.get("description", v.get("issue", str(v))) if isinstance(v, dict) else str(v)
            lines.append(f"- ⚠️ {desc}")
        lines.append("")

    if result.get("missing_clauses"):
        lines.append("### 📋 缺失条款")
        for c in result["missing_clauses"]:
            lines.append(f"- ❌ {c}")
        lines.append("")

    if result.get("summary"):
        summary = result["summary"]
        lines.append("### 📊 综合摘要")
        if isinstance(summary, str):
            lines.append(summary)
        elif isinstance(summary, dict):
            text = summary.get("text") or summary.get("content") or ""
            if text:
                lines.append(text)
        lines.append("")

    if result.get("recommendations"):
        lines.append("### 💡 建议")
        for rec in result["recommendations"]:
            rec_dict = None
            if isinstance(rec, dict):
                rec_dict = rec
            elif isinstance(rec, str):
                try:
                    import json as _json
                    parsed = _json.loads(rec)
                    if isinstance(parsed, dict):
                        rec_dict = parsed
                except Exception:
                    pass

            if rec_dict:
                priority = rec_dict.get("priority", "medium")
                emoji = {"high": "🔴", "critical": "🔴", "medium": "🟡", "low": "🟢"}.get(priority, "⚪")
                category = rec_dict.get("category", "")
                suggestion = rec_dict.get("suggestion", rec_dict.get("description", ""))
                reason = rec_dict.get("reason", "")
                if category:
                    lines.append(f"- {emoji} **[{priority}] {category}**: {suggestion}")
                else:
                    lines.append(f"- {emoji} **[{priority}]**: {suggestion}")
                if reason:
                    lines.append(f"  原因: {reason}")
            else:
                lines.append(f"- {rec}")

    if len(lines) <= 1:
        lines.append("分析完成，但未找到相关信息。")

    return "\n".join(lines)


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


@router.get("/memory/recall")
async def recall_memory(
    query: str = "",
    memory_type: Optional[str] = None,
    top_k: int = 5,
):
    """查询历史记忆"""
    try:
        from src.memory.long_term_memory import get_long_term_memory
        memory = get_long_term_memory()
        results = memory.recall(
            query=query,
            memory_type=memory_type,
            top_k=top_k,
        )
        return {"memories": results, "total": len(results)}
    except Exception as e:
        return {"memories": [], "total": 0, "error": str(e)}


@router.get("/memory/history")
async def get_review_history(top_k: int = 10):
    """获取审查历史"""
    try:
        from src.memory.long_term_memory import get_long_term_memory
        memory = get_long_term_memory()
        results = memory.get_review_history(top_k=top_k)
        return {"memories": results, "total": len(results)}
    except Exception as e:
        return {"memories": [], "total": 0, "error": str(e)}


@router.post("/upload", response_model=FileUploadResponse)
async def upload_contract_file(
    file: UploadFile = File(..., description="合同文件（支持PDF、DOCX、TXT）"),
    contract_type: str = Form(default="general", description="合同类型"),
    review_focus: str = Form(default="", description="审查重点（逗号分隔）"),
):
    """
    上传合同文件进行审查

    支持格式：PDF、DOCX、TXT
    文件大小限制：50MB
    """
    # 检查文件格式
    filename = file.filename or "unknown.txt"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix not in {"pdf", "docx", "txt"}:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: .{suffix}，支持: pdf, docx, txt"
        )

    # 读取文件内容
    file_bytes = await file.read()

    # 检查文件大小（50MB限制）
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小超过50MB限制")

    # 解析文件
    parse_result = await DocumentParser.parse_file(file_bytes, filename)

    if "error" in parse_result:
        raise HTTPException(status_code=400, detail=parse_result["error"])

    contract_text = parse_result["full_text"]

    if not contract_text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 解析审查重点
    focus_list = [f.strip() for f in review_focus.split(",") if f.strip()] if review_focus else []

    # 提交审查任务
    task_id = await task_manager.submit_task(
        contract_text=contract_text,
        contract_type=contract_type,
        review_focus=focus_list,
    )

    return FileUploadResponse(
        task_id=task_id,
        status="queued",
        message="文件已上传并提交审查",
        filename=filename,
        file_type=suffix,
        total_chars=parse_result["total_chars"],
    )


@router.post("/upload/sync")
async def upload_contract_file_sync(
    file: UploadFile = File(..., description="合同文件（支持PDF、DOCX、TXT）"),
    contract_type: str = Form(default="general", description="合同类型"),
    review_focus: str = Form(default="", description="审查重点（逗号分隔）"),
):
    """
    上传合同文件并同步审查

    直接返回审查结果，适用于小文件
    """
    filename = file.filename or "unknown.txt"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if suffix not in {"pdf", "docx", "txt"}:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: .{suffix}，支持: pdf, docx, txt"
        )

    file_bytes = await file.read()

    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小超过50MB限制")

    parse_result = await DocumentParser.parse_file(file_bytes, filename)

    if "error" in parse_result:
        raise HTTPException(status_code=400, detail=parse_result["error"])

    contract_text = parse_result["full_text"]

    if not contract_text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    focus_list = [f.strip() for f in review_focus.split(",") if f.strip()] if review_focus else []

    result = await task_manager.process_sync(
        contract_text=contract_text,
        contract_type=contract_type,
        review_focus=focus_list,
    )

    result["file_info"] = {
        "filename": filename,
        "file_type": suffix,
        "total_chars": parse_result["total_chars"],
    }

    return result
