"""Execution lock contract without requiring a live PostgreSQL server."""
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.domain.services.trace_lock_service import trace_execution_lock


def test_sqlite_lock_is_global_and_survives_commits():
    engine = create_engine("sqlite://")
    try:
        with Session(engine) as first, Session(engine) as second:
            with trace_execution_lock(first, "first") as acquired:
                assert acquired
                first.execute(text("SELECT 1"))
                first.commit()
                with trace_execution_lock(second, "different-trace") as busy:
                    assert not busy
                # A busy caller must not release the first caller's lock.
                with trace_execution_lock(second, "first") as busy:
                    assert not busy
            with trace_execution_lock(second, "first") as acquired:
                assert acquired
    finally:
        engine.dispose()


def test_sqlite_lock_is_released_after_base_exception():
    engine = create_engine("sqlite://")
    try:
        with Session(engine) as db:
            with pytest.raises(BaseException, match="worker interrupted"):
                with trace_execution_lock(db, "trace") as acquired:
                    assert acquired
                    raise BaseException("worker interrupted")
            with trace_execution_lock(db, "trace") as acquired:
                assert acquired
    finally:
        engine.dispose()


@pytest.fixture
def postgres():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.scalar.return_value = True
    engine = Mock(dialect=SimpleNamespace(name="postgresql"))
    engine.connect.return_value = connection
    db = Mock(bind=engine)
    db.get_bind.side_effect = lambda: db.bind
    return db, engine, connection


def test_postgres_pins_connection_and_preserves_lock_key_through_commits(postgres):
    db, engine, connection = postgres
    with trace_execution_lock(db, "trace") as acquired:
        assert acquired
        assert db.bind is connection
        connection.commit.assert_called_once_with()
        # The caller's commits continue to use the pinned connection.
        db.bind.commit()
        db.bind.commit()
        assert connection.execute.call_count == 1
        connection.__exit__.assert_not_called()
    assert db.bind is engine
    engine.connect.assert_called_once_with()
    db.rollback.assert_called_once_with()
    calls = connection.execute.call_args_list
    assert [str(item.args[0]) for item in calls] == [
        "SELECT pg_try_advisory_lock(:key)", "SELECT pg_advisory_unlock(:key)",
    ]
    # SHA256("sampling:trace") first 8 bytes, signed big-endian; shared with existing workers.
    assert [item.args[1] for item in calls] == [{"key": -8968710287189242368}] * 2
    assert connection.commit.call_count == 4
    connection.invalidate.assert_not_called()
    connection.__exit__.assert_called_once_with(None, None, None)


def test_postgres_busy_rolls_back_without_unlocking(postgres):
    db, engine, connection = postgres
    connection.execute.return_value.scalar.return_value = False
    with trace_execution_lock(db, "trace") as acquired:
        assert not acquired
    assert db.bind is engine
    db.rollback.assert_called_once_with()
    assert connection.execute.call_count == 1
    connection.commit.assert_called_once_with()
    connection.invalidate.assert_not_called()
    connection.__exit__.assert_called_once_with(None, None, None)


def test_postgres_body_failure_still_unlocks_and_restores_bind(postgres):
    db, engine, connection = postgres
    with pytest.raises(BaseException, match="worker interrupted"):
        with trace_execution_lock(db, "trace") as acquired:
            assert acquired
            raise BaseException("worker interrupted")
    assert db.bind is engine
    db.rollback.assert_called_once_with()
    assert str(connection.execute.call_args.args[0]) == "SELECT pg_advisory_unlock(:key)"
    assert connection.commit.call_count == 2
    connection.invalidate.assert_not_called()
    assert connection.__exit__.call_args.args[0] is BaseException


@pytest.mark.parametrize("failure", ["acquire", "acquire_commit", "rollback", "unlock", "unlock_commit"])
def test_postgres_failure_cleanup_restores_bind_and_invalidates_if_needed(postgres, failure):
    db, engine, connection = postgres
    error = BaseException(failure)
    if failure == "acquire":
        connection.execute.side_effect = error
    elif failure == "acquire_commit":
        connection.commit.side_effect = [error, None]
    elif failure == "rollback":
        db.rollback.side_effect = error
    elif failure == "unlock":
        connection.execute.side_effect = [Mock(scalar=lambda: True), error]
    else:
        connection.commit.side_effect = [None, error]
    with pytest.raises(BaseException, match=failure):
        with trace_execution_lock(db, "trace"):
            pass
    assert db.bind is engine
    db.rollback.assert_called_once_with()
    assert connection.invalidate.call_args_list == ([] if failure in {"acquire", "acquire_commit"} else [call()])
    assert connection.__exit__.call_args.args[1] is error


def test_postgres_multi_lock_orders_deduplicates_and_releases_partial_set(postgres):
    import hashlib
    db, engine, connection = postgres
    connection.execute.side_effect = [Mock(scalar=lambda: True), Mock(scalar=lambda: False), Mock()]
    with trace_execution_lock(db, ["b", "a", "a"]) as acquired:
        assert not acquired
    keys = [int.from_bytes(hashlib.sha256(f"sampling:{item}".encode()).digest()[:8], "big", signed=True)
            for item in ["a", "b"]]
    assert [item.args[1]["key"] for item in connection.execute.call_args_list] == keys + keys[:1]
    assert str(connection.execute.call_args_list[-1].args[0]) == "SELECT pg_advisory_unlock(:key)"
    assert db.bind is engine
    engine.connect.assert_called_once_with()


def test_postgres_multi_lock_acquisition_error_unlocks_previous_key(postgres):
    db, engine, connection = postgres
    connection.execute.side_effect = [Mock(scalar=lambda: True), ValueError("failed"), Mock()]
    with pytest.raises(ValueError, match="failed"):
        with trace_execution_lock(db, ["a", "b"]):
            pytest.fail("incomplete acquisition yielded")
    assert str(connection.execute.call_args_list[-1].args[0]) == "SELECT pg_advisory_unlock(:key)"
    assert db.bind is engine
