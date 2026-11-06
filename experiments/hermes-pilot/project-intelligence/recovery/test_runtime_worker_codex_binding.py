"""Codex's native thread binding must traverse the managed receipt contract."""
import pytest

from agent.runtime_session_store import RuntimeSessionStore, WorkerPersistenceError
from hermes_state import SessionDB
from hermes_state_runtime import (
    RuntimeStoreError, begin_runtime_epoch, mutate_worker_execution,
    register_worker_execution,
)


def test_codex_binding_survives_lost_ack_reopen_and_clear(tmp_path):
    path = tmp_path / 'state.db'
    db = SessionDB(path)
    db.create_session('owned', 'subagent', model_config={'_delegate_from': 'parent'})
    db.create_session('foreign', 'cli')
    epoch = begin_runtime_epoch(db, instance_id='fixture')
    scope = dict(epoch=epoch, execution_id='worker', session_id='owned', generation=0)
    register_worker_execution(db, **scope, kind='child', adoption_secret='test-secret')
    store = RuntimeSessionStore(lambda method, **p: mutate_worker_execution(db, **p), scope, tmp_path / 'outbox')
    try:
        store.patch_session_model_config('owned', {'codex_thread_id': 'synthetic-thread'})
        assert db.get_session_model_config_value('owned', 'codex_thread_id') == 'synthetic-thread'
        with pytest.raises(WorkerPersistenceError, match='permission_denied'):
            store.patch_session_model_config('foreign', {'codex_thread_id': 'stolen'})
        original = store.rpc
        def lost_ack(method, **params):
            original(method, **params)
            raise TimeoutError('lost-ack')
        store.rpc = lost_ack
        with pytest.raises(TimeoutError, match='lost-ack'):
            store.patch_session_model_config('owned', {'codex_thread_id': 'next-thread'})
        store.rpc = original
        assert len(store.retry_pending()) == 1
        assert not store.journal['pending']
        db.close()
        db = SessionDB(path)
        assert db.get_session_model_config_value('owned', 'codex_thread_id') == 'next-thread'
        assert db.get_session_model_config_value('owned', '_delegate_from') == 'parent'
        assert db.get_session_model_config_value('foreign', 'codex_thread_id') is None
        store.patch_session_model_config('owned', {'codex_thread_id': None})
        assert db.get_session_model_config_value('owned', 'codex_thread_id') is None
        begin_runtime_epoch(db, instance_id='restarted')
        with pytest.raises(RuntimeStoreError, match='stale_epoch'):
            mutate_worker_execution(db, **scope, sequence=store.journal['next_sequence'],
                                    operation='session.sidecars', payload={'patch': {'codex_thread_id': 'stale'}})
    finally:
        store.close()
        db.close()


@pytest.mark.parametrize('patch', [
    {'codex_thread_id': ''}, {'codex_thread_id': 'x' * 257},
    {'codex_thread_id': True}, {'codex_thread_id': 1}, {'codex_thread_id': []},
    {'codex_thread_id': {}}, {'codex_thread_id': 'ok', '_delegate_from': 'foreign'},
])
def test_invalid_codex_binding_is_atomic_and_keeps_schema_closed(tmp_path, patch):
    db = SessionDB(tmp_path / 'state.db')
    try:
        db.create_session('owned', 'subagent', model_config={'codex_thread_id': 'original'})
        epoch = begin_runtime_epoch(db, instance_id='fixture')
        scope = dict(epoch=epoch, execution_id='worker', session_id='owned', generation=0)
        register_worker_execution(db, **scope, kind='child', adoption_secret='test-secret')
        with pytest.raises(RuntimeStoreError, match='invalid_params'):
            mutate_worker_execution(db, **scope, sequence=1, operation='session.sidecars', payload={'patch': patch})
        assert db.get_session_model_config_value('owned', 'codex_thread_id') == 'original'
    finally:
        db.close()
