"""最小 FastAPI 内部审批接口。"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .service import ApiSettings, RunNotFoundError, RunService


class RunRequest(BaseModel):
    tickers: list[str] = Field(min_length=3, max_length=3)
    llm_mode: Literal["auto", "api", "template"] | None = None


class ApprovalRequest(BaseModel):
    comment: str = "API 审批通过"


class RunResponse(BaseModel):
    thread_id: str
    status: str
    summary_source: str | None = None
    llm_model: str | None = None
    budget: dict = Field(default_factory=dict)
    draft_preview: str | None = None
    trace_path: str | None = None


class ReportResponse(BaseModel):
    thread_id: str
    status: str
    markdown: str
    structured: dict
    summary_source: str | None = None
    llm_model: str | None = None
    budget: dict = Field(default_factory=dict)
    trace_path: str | None = None


class TraceResponse(BaseModel):
    thread_id: str
    events: list[dict]


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    app = FastAPI(
        title="Fundamental Agent API",
        version="0.1.0",
        description="SEC 基本面简报、LangGraph 审批、Trace 和评测接口。",
    )
    service = RunService(settings or ApiSettings.from_env())

    @app.exception_handler(RunNotFoundError)
    def handle_not_found(_, exc: RunNotFoundError):
        return _error(404, f"运行不存在：{exc.args[0]}")

    @app.exception_handler(ValueError)
    def handle_value_error(_, exc: ValueError):
        return _error(400, str(exc))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", response_model=RunResponse)
    def start_run(request: RunRequest) -> dict:
        return service.start_run(request.tickers, request.llm_mode)

    @app.get("/runs/{thread_id}", response_model=RunResponse)
    def get_run(thread_id: str) -> dict:
        return service.get_run(thread_id)

    @app.post("/runs/{thread_id}/approve", response_model=RunResponse)
    def approve(
        thread_id: str,
        request: ApprovalRequest | None = None,
    ) -> dict:
        return service.approve(
            thread_id,
            request.comment if request else "API 审批通过",
        )

    @app.post("/runs/{thread_id}/reject", response_model=RunResponse)
    def reject(
        thread_id: str,
        request: ApprovalRequest | None = None,
    ) -> dict:
        return service.reject(
            thread_id,
            request.comment if request else "API 审批拒绝",
        )

    @app.get("/runs/{thread_id}/report", response_model=ReportResponse)
    def get_report(thread_id: str) -> dict:
        return service.report(thread_id)

    @app.get("/runs/{thread_id}/trace", response_model=TraceResponse)
    def get_trace(thread_id: str) -> dict:
        return service.trace(thread_id)

    return app


def _error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": detail})


app = create_app()
