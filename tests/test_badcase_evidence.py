import ast
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from flask import Blueprint, Flask, jsonify, request
from flask_login import LoginManager, current_user, login_required
from sqlalchemy import and_

from agents.cdp import test_task
from db_extensions import db
from models.orm import BadCase, CdpTestRun, Project, ProjectPermission, User

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = '10000000-0000-4000-8000-000000000001'
OTHER_RUN_ID = '20000000-0000-4000-8000-000000000002'
CASE_ID = 9007199254740993


def _load_functions(path, names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)


def make_evidence_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='local-evidence-test', SQLALCHEMY_DATABASE_URI='sqlite://')
    db.init_app(app)
    login = LoginManager(app)

    @login.user_loader
    def load_user(uid):
        return db.session.get(User, int(uid))

    runtime = ModuleType('app')
    runtime.__dict__.update(
        db=db, BadCase=BadCase, Project=Project, ProjectPermission=ProjectPermission,
        and_=and_, time=time, os=os, _PROJECT_CTX_CACHE={},
    )
    _load_functions(ROOT / 'app.py', {
        '_model_for_user_collaborator_access', 'has_project_permission', '_cache_get', '_cache_set',
    }, runtime.__dict__)
    blueprint = Blueprint('agent_evidence_test', __name__, url_prefix='/api/agent')
    namespace = dict(
        agent_bp=blueprint, login_required=login_required, current_user=current_user,
        jsonify=jsonify, request=request, uuid=uuid, logger=logging.getLogger(__name__),
    )
    _load_functions(ROOT / 'routers/agent.py', {
        'api_badcase_evidence', 'api_list_cdp_test_runs',
    }, namespace)
    app.register_blueprint(blueprint)
    with app.app_context():
        for model in (User, Project, ProjectPermission, BadCase, CdpTestRun):
            model.__table__.create(db.engine)
        db.session.add_all([
            User(id=1, email='owner@example.test', name='Owner', password_hash='unused'),
            User(id=2, email='other@example.test', name='Other', password_hash='unused'),
            User(id=3, email='member@example.test', name='Member', password_hash='unused'),
            User(id=4, email='viewer@example.test', name='Viewer', password_hash='unused'),
            Project(id=1, name='Evidence test', user_id=1),
            Project(id=2, name='Other project', user_id=2),
            ProjectPermission(project_id=1, user_id=3, role='collaborator'),
            ProjectPermission(project_id=1, user_id=4, role='viewer'),
            BadCase(id=CASE_ID, project_id=1, creator_id=1, title='Evidence case',
                    case_category='功能缺陷', base_problem='', badcase_result='wrong', answer='answer'),
            CdpTestRun(id=RUN_ID, project_id=1, user_id=1, title='Recorded run', status='running',
                       steps_json=[], spec_json={}, react_request_id='request-one'),
            CdpTestRun(id=OTHER_RUN_ID, project_id=2, user_id=2, title='Private run', status='passed',
                       steps_json=[], spec_json={}, react_request_id='request-two'),
        ])
        db.session.commit()
    return app, runtime


@pytest.fixture
def evidence_app(monkeypatch, tmp_path):
    app, runtime = make_evidence_app()
    monkeypatch.setitem(sys.modules, 'app', runtime)
    monkeypatch.setenv('BADCASE_LLM_EXCHANGE_DIR', str(tmp_path))
    return app


def _client(app, uid=1):
    client = app.test_client()
    if uid is not None:
        with client.session_transaction() as session:
            session['_user_id'] = str(uid)
            session['_fresh'] = True
    return client


def _url(case_id=CASE_ID):
    return f'/api/agent/badcases/{case_id}/evidence'


def test_empty_evidence(evidence_app):
    response = _client(evidence_app).get(_url())
    assert response.status_code == 200
    assert response.json['evidence'] == {'run_ids': [], 'runs': [], 'unavailable_run_ids': []}


@pytest.mark.parametrize('uid,status', [(None, 401), (2, 403), (4, 403), (3, 200)])
def test_evidence_access(evidence_app, uid, status):
    assert _client(evidence_app, uid).get(_url()).status_code == status
    assert _client(evidence_app, uid).put(_url(), json={'run_ids': []}).status_code == status


def test_missing_badcase(evidence_app):
    assert _client(evidence_app).get(_url(999)).status_code == 404


def test_link_persist_reload_unlink_without_editing_form(evidence_app):
    client = _client(evidence_app)
    response = client.put(_url(), json={'run_ids': [RUN_ID, RUN_ID]})
    assert response.status_code == 200
    evidence = client.get(_url()).json['evidence']
    assert evidence['run_ids'] == [RUN_ID]
    assert evidence['runs'][0]['capture_status'] == 'not_captured'
    assert evidence['runs'][0]['snapshots'] == []
    assert client.put(_url(), json={'run_ids': []}).status_code == 200
    with evidence_app.app_context():
        row = db.session.get(BadCase, CASE_ID)
        assert row.title == 'Evidence case'
        assert row.answer == 'answer'
        assert row.cdp_run_ids == []
        assert db.session.get(CdpTestRun, RUN_ID) is not None


@pytest.mark.parametrize('payload', [None, [], {}, {'run_ids': 'x'}, {'run_ids': [1]},
                                     {'run_ids': ['../private']}, {'run_ids': [RUN_ID] * 11}])
def test_invalid_associations_rejected(evidence_app, payload):
    assert _client(evidence_app).put(_url(), json=payload).status_code == 400


def test_cross_project_association_is_atomic(evidence_app):
    client = _client(evidence_app)
    assert client.put(_url(), json={'run_ids': [RUN_ID]}).status_code == 200
    assert client.put(_url(), json={'run_ids': [RUN_ID, OTHER_RUN_ID]}).status_code == 400
    assert client.get(_url()).json['evidence']['run_ids'] == [RUN_ID]


def test_deleted_or_foreign_associations_not_exposed(evidence_app):
    missing = str(uuid.uuid4())
    with evidence_app.app_context():
        db.session.get(BadCase, CASE_ID).cdp_run_ids = [OTHER_RUN_ID, missing]
        db.session.commit()
    evidence = _client(evidence_app).get(_url()).json['evidence']
    assert evidence['runs'] == []
    assert evidence['unavailable_run_ids'] == [OTHER_RUN_ID, missing]


def test_run_candidates_project_permissions(evidence_app):
    client = _client(evidence_app)
    response = client.get('/api/agent/cdp-test-runs?project_id=1')
    assert response.status_code == 200
    assert [r['id'] for r in response.json['runs']] == [RUN_ID]
    assert 'spec_json' not in response.json['runs'][0]
    assert client.get('/api/agent/cdp-test-runs?project_id=2').status_code == 403
    assert client.get('/api/agent/cdp-test-runs?react_request_id=request-two').json['runs'] == []
    assert _client(evidence_app, 3).get('/api/agent/cdp-test-runs?project_id=1').status_code == 200


@pytest.mark.parametrize('query', ['', '?project_id=abc', '?project_id=1&limit=abc', '?chat_session_id=oops'])
def test_run_candidates_invalid_query(evidence_app, query):
    assert _client(evidence_app).get('/api/agent/cdp-test-runs' + query).status_code == 400


def test_automatic_run_creation_keyword_argument(evidence_app):
    with evidence_app.app_context():
        context = {}
        row = test_task.ensure_cdp_test_task(
            SimpleNamespace(db=db.session, user_id=1), project_id=1,
            user_input='先打开页面，然后点击按钮执行测试', tool_action='session', result_context=context,
        )
        assert row is not None
        assert context['cdp_test_run_id'] == row['id']
        assert db.session.get(CdpTestRun, row['id']).project_id == 1


def test_snapshot_persisted_bounded_without_field_values(evidence_app):
    with evidence_app.app_context():
        for index in range(7):
            test_task.append_cdp_test_step(db.session, RUN_ID, action='snapshot', params={}, observation={
                'session_id': f'session-{index % 2}', 'success': True, 'snapshot_id': f'snapshot-{index}',
                'url': 'https://name:secret@example.test/page?token=private#password', 'title': 'Page',
                'nodes': [{'ref': f'@e{i}', 'role': 'textbox', 'name': 'Label',
                           'value': 'private-input', 'selector_hint': '[value="private-input"]'} for i in range(205)],
            })
        db.session.expire_all()
        run = db.session.get(CdpTestRun, RUN_ID)
        snapshots = run.spec_json['snapshots']
        assert len(snapshots) == 5
        assert len(snapshots[-1]['nodes']) == 200
        assert snapshots[-1]['truncated'] is True
        assert snapshots[-1]['url'] == 'https://example.test/page'
        assert 'private-input' not in json.dumps(snapshots)
        assert run.spec_json['cdp_session_ids'] == ['session-0', 'session-1']
        assert run.pass_count == 7


def test_real_file_evidence_filters_run_project_and_session(evidence_app, tmp_path):
    from utils.observability import append_llm_exchange

    records = [
        {'session_id': 'shared', 'project_id': 1, 'cdp_run_id': RUN_ID, 'ts': '2026-09-23T01:00:00Z',
         'url': 'https://user:pass@example.test/api?key=secret', 'request': {'model': 'observed', 'params': {'temperature': 0}},
         'response': {'text': '<script>not executable</script>', 'usage': {'total_tokens': 0}}},
        {'session_id': 'shared', 'project_id': 2, 'cdp_run_id': RUN_ID, 'response': {'text': 'FOREIGN_PROJECT'}},
        {'session_id': 'shared', 'project_id': 1, 'cdp_run_id': OTHER_RUN_ID, 'response': {'text': 'OTHER_RUN'}},
        {'session_id': 'shared', 'project_id': None, 'cdp_run_id': None, 'response': {'text': 'LEGACY_UNSCOPED'}},
    ]
    for record in records:
        append_llm_exchange(record)
    with evidence_app.app_context():
        run = db.session.get(CdpTestRun, RUN_ID)
        run.cdp_session_id = 'shared'
        run.spec_json = {'cdp_session_ids': ['shared']}
        db.session.get(BadCase, CASE_ID).cdp_run_ids = [RUN_ID]
        db.session.commit()
    response = _client(evidence_app).get(_url())
    assert response.status_code == 200
    run = response.json['evidence']['runs'][0]
    assert run['capture_status'] == 'available'
    assert len(run['exchanges']) == 1
    assert run['exchanges'][0]['url'] == 'https://example.test/api'
    assert run['exchanges'][0]['request']['params']['temperature'] == 0
    assert 'FOREIGN_PROJECT' not in response.text
    assert 'OTHER_RUN' not in response.text
    assert 'LEGACY_UNSCOPED' not in response.text
