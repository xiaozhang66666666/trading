#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> int:
    host_default = os.getenv("MSS_HOST", "0.0.0.0")
    port_default = int(os.getenv("MSS_PORT", "8080"))
    db_default = os.getenv("MSS_DB_PATH")
    ttl_default = int(os.getenv("MSS_SESSION_TTL_SECONDS", str(3600 * 12)))
    secure_default = os.getenv("MSS_COOKIE_SECURE", "0").strip() in {"1", "true", "yes", "on"}
    login_max_attempts_default = int(os.getenv("MSS_LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5"))
    login_window_default = int(os.getenv("MSS_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

    parser = argparse.ArgumentParser(description="启动 MSS Web 登录 MVP 服务")
    parser.add_argument("--host", default=host_default)
    parser.add_argument("--port", type=int, default=port_default)
    parser.add_argument("--db-path", default=db_default, help="SQLite 文件路径")
    parser.add_argument("--cookie-secure", action="store_true", default=secure_default, help="仅 HTTPS 下发送 session cookie")
    parser.add_argument("--session-ttl-seconds", type=int, default=ttl_default)
    parser.add_argument(
        "--login-rate-limit-max-attempts",
        type=int,
        default=login_max_attempts_default,
        help="登录失败限流阈值（<=0 关闭限流）",
    )
    parser.add_argument(
        "--login-rate-limit-window-seconds",
        type=int,
        default=login_window_default,
        help="登录失败限流窗口秒数",
    )
    args = parser.parse_args()

    from market_signal_system.web.app import create_app

    app = create_app(
        db_path=args.db_path,
        cookie_secure=args.cookie_secure,
        session_ttl_seconds=max(60, int(args.session_ttl_seconds)),
        login_rate_limit_max_attempts=int(args.login_rate_limit_max_attempts),
        login_rate_limit_window_seconds=max(1, int(args.login_rate_limit_window_seconds)),
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
