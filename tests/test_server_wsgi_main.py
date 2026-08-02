# -*- coding: utf-8 -*-
import server_wsgi as wsgi


def test_main_uses_flask_dev_when_debug(monkeypatch):
    calls = []

    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.setenv("WSGI_HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "5000")
    monkeypatch.setattr(wsgi, "_run_flask_dev", lambda h, p: calls.append(("flask", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_waitress", lambda h, p: calls.append(("waitress", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_gunicorn", lambda h, p: calls.append(("gunicorn", h, p)) or 0)

    assert wsgi.main() == 0
    assert calls == [("flask", "127.0.0.1", 5000)]


def test_main_windows_defaults_to_waitress(monkeypatch):
    calls = []
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("WSGI_SERVER", raising=False)
    monkeypatch.setenv("WSGI_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "5000")
    monkeypatch.setattr(wsgi, "_is_windows", lambda: True)
    monkeypatch.setattr(wsgi, "_run_flask_dev", lambda h, p: calls.append(("flask", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_waitress", lambda h, p: calls.append(("waitress", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_gunicorn", lambda h, p: calls.append(("gunicorn", h, p)) or 0)

    assert wsgi.main() == 0
    assert calls == [("waitress", "0.0.0.0", 5000)]


def test_main_linux_defaults_to_gunicorn(monkeypatch):
    calls = []
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("WSGI_SERVER", raising=False)
    monkeypatch.setenv("WSGI_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "5000")
    monkeypatch.setattr(wsgi, "_is_windows", lambda: False)
    monkeypatch.setattr(wsgi, "_run_flask_dev", lambda h, p: calls.append(("flask", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_waitress", lambda h, p: calls.append(("waitress", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_gunicorn", lambda h, p: calls.append(("gunicorn", h, p)) or 0)

    assert wsgi.main() == 0
    assert calls == [("gunicorn", "0.0.0.0", 5000)]


def test_main_respects_wsgi_server_override(monkeypatch):
    calls = []
    monkeypatch.setenv("FLASK_DEBUG", "0")
    monkeypatch.setenv("WSGI_SERVER", "waitress")
    monkeypatch.setenv("WSGI_HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "5001")
    monkeypatch.setattr(wsgi, "_is_windows", lambda: False)
    monkeypatch.setattr(wsgi, "_run_flask_dev", lambda h, p: calls.append(("flask", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_waitress", lambda h, p: calls.append(("waitress", h, p)) or 0)
    monkeypatch.setattr(wsgi, "_run_gunicorn", lambda h, p: calls.append(("gunicorn", h, p)) or 0)

    assert wsgi.main() == 0
    assert calls == [("waitress", "127.0.0.1", 5001)]
