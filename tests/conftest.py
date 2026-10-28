"""Per-test isolated databases; no production databases are touched."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
import packages.database as database
import apps.api.main as api

@pytest.fixture
def client_from_api(tmp_path, monkeypatch):
    key={'X-PatchProof-Key': 'test-key'}
    monkeypatch.setenv('PATCHPROOF_API_KEY','test-key')
    monkeypatch.setattr(api, 'ROOT', tmp_path / 'repos')
    api.ROOT.mkdir()
    engine=create_engine(f'sqlite:///{tmp_path}/tests.db')
    old=database.Session.kw['bind']
    monkeypatch.setattr(database,'engine',engine)
    database.Session.configure(bind=engine)
    with TestClient(api.app) as client:
        yield client, api, key
    database.Session.configure(bind=old)
    engine.dispose()
