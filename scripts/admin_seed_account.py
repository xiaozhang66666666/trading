#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_signal_system.appdb import AuthService, SQLiteAuthRepository, SQLiteConnectionFactory, SQLiteSchemaManager


def main() -> int:
    parser = argparse.ArgumentParser(description="预置/更新 Web 登录账号")
    parser.add_argument("--account-id", required=True, help="账号唯一 ID")
    parser.add_argument("--username", required=True, help="登录用户名（全局唯一）")
    parser.add_argument("--password", required=True, help="登录密码")
    parser.add_argument("--display-name", default="", help="展示名")
    parser.add_argument("--db-path", default=None, help="SQLite 文件路径（默认 data/state/market_signal_system.db）")
    args = parser.parse_args()

    factory = SQLiteConnectionFactory(args.db_path)
    SQLiteSchemaManager(factory).ensure_schema()
    service = AuthService(SQLiteAuthRepository(factory))
    account = service.seed_account(
        account_id=args.account_id,
        username=args.username,
        password=args.password,
        display_name=args.display_name or args.username,
    )
    print(
        f"seeded account_id={account.account_id} username={account.username} display_name={account.display_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
