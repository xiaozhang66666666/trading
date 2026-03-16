from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_admin_seed_account_script_creates_login_account(tmp_path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "accounts.db"
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "admin_seed_account.py"),
        "--account-id",
        "acct_ops",
        "--username",
        "ops",
        "--password",
        "ops123456",
        "--display-name",
        "Ops Team",
        "--db-path",
        str(db_path),
    ]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    run = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT account_id, username, display_name FROM accounts WHERE account_id = ?", ("acct_ops",)).fetchone()
    cred = conn.execute("SELECT account_id, password_hash FROM account_credentials WHERE account_id = ?", ("acct_ops",)).fetchone()
    conn.close()

    assert row == ("acct_ops", "ops", "Ops Team")
    assert cred is not None
    assert str(cred[1]).startswith("pbkdf2_sha256$")
