from __future__ import annotations

import pytest

from market_signal_system.appdb import (
    PostgresAuthRepository,
    PostgresConnectionFactory,
    PostgresSchemaManager,
    PostgresSignalPilotRepository,
)


def test_postgres_placeholder_connection_and_schema_raise_not_implemented() -> None:
    factory = PostgresConnectionFactory(dsn="postgresql://user:pass@localhost:5432/mss")
    with pytest.raises(NotImplementedError):
        factory.connect()
    with pytest.raises(NotImplementedError):
        PostgresSchemaManager(factory).ensure_schema()


def test_postgres_placeholder_repositories_raise_not_implemented() -> None:
    factory = PostgresConnectionFactory(dsn="postgresql://user:pass@localhost:5432/mss")
    auth_repo = PostgresAuthRepository(factory)
    signal_repo = PostgresSignalPilotRepository(factory)

    with pytest.raises(NotImplementedError):
        auth_repo.get_account_by_username("demo")
    with pytest.raises(NotImplementedError):
        signal_repo.count_alert_status(account_id="default")
