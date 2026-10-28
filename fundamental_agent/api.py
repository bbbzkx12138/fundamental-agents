"""最小 FastAPI 内部审批接口。"""

from __future__ import annotations

import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
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
    compliance: dict | None = None
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
    compliance: dict | None = None
    trace_path: str | None = None


class TraceResponse(BaseModel):
    thread_id: str
    events: list[dict]


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings.from_env()
    if settings.require_auth and not settings.auth_token:
        raise ValueError(
            "API_REQUIRE_AUTH=true 时必须设置 API_AUTH_TOKEN"
        )

    app = FastAPI(
        title="Fundamental Agent API",
        version="0.1.0",
        description="SEC 基本面简报、LangGraph 审批、Trace 和评测接口。",
    )
    service = RunService(settings)
    bearer_scheme = HTTPBearer(auto_error=False)
    api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_auth(
        bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        api_key: str | None = Depends(api_key_scheme),
    ) -> None:
        if not settings.require_auth:
            return
        provided = bearer.credentials if bearer else api_key
        if not provided:
            raise HTTPException(
                status_code=401,
                detail="需要 API 鉴权",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not secrets.compare_digest(provided, settings.auth_token):
            raise HTTPException(status_code=403, detail="API 鉴权失败")

    @app.exception_handler(RunNotFoundError)
    def handle_not_found(_, exc: RunNotFoundError):
        return _error(404, f"运行不存在：{exc.args[0]}")

    @app.exception_handler(ValueError)
    def handle_value_error(_, exc: ValueError):
        return _error(400, str(exc))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/runs",
        response_model=RunResponse,
        dependencies=[Depends(require_auth)],
    )
    def start_run(request: RunRequest) -> dict:
        return service.start_run(request.tickers, request.llm_mode)

    @app.get(
        "/runs/{thread_id}",
        response_model=RunResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_run(thread_id: str) -> dict:
        return service.get_run(thread_id)

    @app.post(
        "/runs/{thread_id}/approve",
        response_model=RunResponse,
        dependencies=[Depends(require_auth)],
    )
    def approve(
        thread_id: str,
        request: ApprovalRequest | None = None,
    ) -> dict:
        return service.approve(
            thread_id,
            request.comment if request else "API 审批通过",
        )

    @app.post(
        "/runs/{thread_id}/reject",
        response_model=RunResponse,
        dependencies=[Depends(require_auth)],
    )
    def reject(
        thread_id: str,
        request: ApprovalRequest | None = None,
    ) -> dict:
        return service.reject(
            thread_id,
            request.comment if request else "API 审批拒绝",
        )

    @app.get(
        "/runs/{thread_id}/report",
        response_model=ReportResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_report(thread_id: str) -> dict:
        return service.report(thread_id)

    @app.get(
        "/runs/{thread_id}/trace",
        response_model=TraceResponse,
        dependencies=[Depends(require_auth)],
    )
    def get_trace(thread_id: str) -> dict:
        return service.trace(thread_id)

    return app


def _error(status_code: int, detail: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": detail})


app = create_app()
