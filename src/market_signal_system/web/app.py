from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from market_signal_system.appdb import (
    AuthService,
    SignalPilotService,
    SQLiteAuthRepository,
    SQLiteConnectionFactory,
    SQLiteSchemaManager,
    SQLiteSignalPilotRepository,
)
from market_signal_system.storage import DEFAULT_ACCOUNT_ID, normalize_account_id
from market_signal_system.utils.paths import OUTPUT_DIR
from market_signal_system.web.security import LoginRateLimiter, generate_session_token

SESSION_COOKIE_NAME = "mss_session"
CSRF_COOKIE_NAME = "mss_csrf"


def _build_services(db_path: str | Path | None) -> tuple[AuthService, SignalPilotService]:
    factory = SQLiteConnectionFactory(db_path)
    SQLiteSchemaManager(factory).ensure_schema()
    auth_repo = SQLiteAuthRepository(factory)
    signal_repo = SQLiteSignalPilotRepository(factory)
    return AuthService(auth_repo), SignalPilotService(signal_repo)


def _parse_form_urlencoded(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in parsed.items()}


def create_app(
    *,
    db_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    cookie_secure: bool = False,
    session_ttl_seconds: int = 3600 * 12,
    login_rate_limit_max_attempts: int = 5,
    login_rate_limit_window_seconds: int = 300,
) -> FastAPI:
    auth_service, signal_service = _build_services(db_path)
    outputs = Path(output_dir) if output_dir is not None else OUTPUT_DIR
    app = FastAPI(title="Market Signal System Web")
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
    limiter: LoginRateLimiter | None = None
    if int(login_rate_limit_max_attempts) > 0:
        limiter = LoginRateLimiter(
            max_attempts=int(login_rate_limit_max_attempts),
            window_seconds=max(1, int(login_rate_limit_window_seconds)),
        )

    def get_current_account(request: Request):
        sid = request.cookies.get(SESSION_COOKIE_NAME)
        if not sid:
            return None
        return auth_service.get_account_by_session(sid, extend_ttl_seconds=session_ttl_seconds)

    def _issue_csrf_token(raw: str | None) -> str:
        token = str(raw or "").strip()
        if token:
            return token
        return generate_session_token()

    def _set_csrf_cookie(response, csrf_token: str) -> None:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=csrf_token,
            max_age=session_ttl_seconds,
            httponly=True,
            secure=bool(cookie_secure),
            samesite="lax",
            path="/",
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

    @app.get("/", response_class=HTMLResponse)
    def root(request: Request):
        account = get_current_account(request)
        if account is None:
            return RedirectResponse(url="/login", status_code=302)
        return RedirectResponse(url="/signal-pilot", status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, msg: str | None = None):
        if get_current_account(request) is not None:
            return RedirectResponse(url="/signal-pilot", status_code=302)
        csrf_token = _issue_csrf_token(request.cookies.get(CSRF_COOKIE_NAME))
        response = templates.TemplateResponse(
            request,
            "login.html",
            {"error": msg or "", "csrf_token": csrf_token},
        )
        _set_csrf_cookie(response, csrf_token)
        return response

    @app.post("/login")
    async def login_submit(request: Request):
        body = await request.body()
        form = _parse_form_urlencoded(body)
        csrf_cookie = _issue_csrf_token(request.cookies.get(CSRF_COOKIE_NAME))
        csrf_form = (form.get("csrf_token") or "").strip()
        if not csrf_form or csrf_form != csrf_cookie:
            response = templates.TemplateResponse(
                request,
                "login.html",
                {"error": "CSRF 校验失败，请刷新后重试", "csrf_token": csrf_cookie},
                status_code=400,
            )
            _set_csrf_cookie(response, csrf_cookie)
            return response
        username = (form.get("username") or "").strip().lower()
        password = form.get("password") or ""
        ip_addr = request.client.host if request.client else "unknown"
        limiter_key = f"{ip_addr}:{username}"

        if limiter is not None and not limiter.is_allowed(limiter_key):
            response = templates.TemplateResponse(
                request,
                "login.html",
                {"error": "登录失败次数过多，请稍后再试", "csrf_token": csrf_cookie},
                status_code=429,
            )
            _set_csrf_cookie(response, csrf_cookie)
            return response

        result = auth_service.login(
            username=username,
            password=password,
            ttl_seconds=session_ttl_seconds,
            user_agent=request.headers.get("user-agent"),
            ip_addr=ip_addr if ip_addr != "unknown" else None,
        )
        if result is None:
            if limiter is not None:
                limiter.register_failure(limiter_key)
            response = templates.TemplateResponse(
                request,
                "login.html",
                {"error": "用户名或密码错误", "csrf_token": csrf_cookie},
                status_code=401,
            )
            _set_csrf_cookie(response, csrf_cookie)
            return response
        if limiter is not None:
            limiter.clear(limiter_key)

        response = RedirectResponse(url="/signal-pilot", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=result.session_id,
            max_age=session_ttl_seconds,
            httponly=True,
            secure=bool(cookie_secure),
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/logout")
    async def logout(request: Request):
        body = await request.body()
        form = _parse_form_urlencoded(body)
        csrf_cookie = _issue_csrf_token(request.cookies.get(CSRF_COOKIE_NAME))
        csrf_form = (form.get("csrf_token") or "").strip()
        if not csrf_form or csrf_form != csrf_cookie:
            response = JSONResponse({"error": "csrf_invalid"}, status_code=400)
            _set_csrf_cookie(response, csrf_cookie)
            return response
        sid = request.cookies.get(SESSION_COOKIE_NAME)
        if sid:
            auth_service.logout(sid)
        response = RedirectResponse(url="/login", status_code=302)
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return response

    @app.get("/signal-pilot", response_class=HTMLResponse)
    def signal_pilot_dashboard(request: Request, status: str | None = None):
        account = get_current_account(request)
        if account is None:
            return RedirectResponse(url="/login", status_code=302)
        alerts = signal_service.list_recent_alerts(account_id=account.account_id, limit=200, status=status)
        status_counts = signal_service.count_alert_status(account_id=account.account_id)
        rows: list[dict[str, Any]] = []
        for alert in alerts:
            rows.append(
                {
                    "created_at": alert.created_at.isoformat() if alert.created_at else "",
                    "symbol": alert.symbol,
                    "strategy": alert.strategy,
                    "side": alert.side,
                    "status": alert.status,
                    "alert_price": "" if alert.alert_price is None else f"{alert.alert_price:.4f}",
                    "current_pnl_pct": "" if alert.current_pnl_pct is None else f"{alert.current_pnl_pct:.4%}",
                    "realized_pnl_pct": "" if alert.realized_pnl_pct is None else f"{alert.realized_pnl_pct:.4%}",
                    "reason": alert.alert_reason,
                }
            )

        csrf_token = _issue_csrf_token(request.cookies.get(CSRF_COOKIE_NAME))
        response = templates.TemplateResponse(
            request,
            "signal_pilot_dashboard.html",
            {
                "account_id": account.account_id,
                "display_name": account.display_name,
                "username": account.username,
                "csrf_token": csrf_token,
                "status_filter": status or "",
                "status_counts": status_counts,
                "alerts": rows,
            },
        )
        _set_csrf_cookie(response, csrf_token)
        return response

    @app.get("/api/me")
    def api_me(request: Request):
        account = get_current_account(request)
        if account is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return {
            "account_id": account.account_id,
            "username": account.username,
            "display_name": account.display_name,
        }

    @app.get("/api/signal-pilot/alerts")
    def api_signal_pilot(request: Request, status: str | None = None, limit: int = 100):
        account = get_current_account(request)
        if account is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        alerts = signal_service.list_recent_alerts(
            account_id=account.account_id,
            limit=max(1, min(int(limit), 500)),
            status=status,
        )
        return {
            "account_id": account.account_id,
            "status_counts": signal_service.count_alert_status(account_id=account.account_id),
            "alerts": [
                {
                    "alert_id": item.alert_id,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "symbol": item.symbol,
                    "strategy": item.strategy,
                    "side": item.side,
                    "status": item.status,
                    "alert_price": item.alert_price,
                    "current_pnl_pct": item.current_pnl_pct,
                    "realized_pnl_pct": item.realized_pnl_pct,
                    "alert_reason": item.alert_reason,
                }
                for item in alerts
            ],
        }

    @app.get("/api/baseline-summary/latest")
    def api_baseline_summary_latest(request: Request):
        account = get_current_account(request)
        if account is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        account_id = normalize_account_id(account.account_id)
        files = sorted(outputs.glob("baseline_daily_digest*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            payload_account = normalize_account_id(str(payload.get("account_id", DEFAULT_ACCOUNT_ID)))
            if payload_account != account_id:
                continue
            return {
                "account_id": account_id,
                "found": True,
                "source": path.name,
                "summary": {
                    key: value
                    for key, value in payload.items()
                    if key != "rows"
                },
            }
        return {"account_id": account_id, "found": False, "source": None, "summary": None}

    return app


app = create_app()
