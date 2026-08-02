import os
import platform
import subprocess
import sys


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _env_truthy(name: str, default: str = "") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in ("1", "true", "yes", "on")


def _run_waitress(host: str, port: int) -> int:
    try:
        from waitress import serve
    except Exception as e:
        print(
            "[WSGI] 未检测到 waitress，请先安装：pip install waitress\n"
            f"[WSGI] import waitress 失败: {e}",
            file=sys.stderr,
        )
        return 1

    from app import app as flask_app

    threads = max(8, min(int(os.getenv("WSGI_THREADS", "200")), 512))
    print(f"[WSGI] 使用 waitress 运行在 http://{host}:{port} (threads={threads})")
    serve(flask_app, host=host, port=port, threads=threads)
    return 0


def _run_gunicorn(host: str, port: int) -> int:
    workers = os.getenv("WEB_CONCURRENCY") or os.getenv("WSGI_WORKERS") or "2"
    threads = os.getenv("WSGI_THREADS") or "8"
    # Agent SSE 可能远超 2 分钟；与 nginx /api/agent/ 的 3600s 对齐
    timeout = os.getenv("WSGI_TIMEOUT") or "3600"
    graceful = os.getenv("WSGI_GRACEFUL_TIMEOUT") or "120"

    bind = f"{host}:{port}"
    cmd = [
        sys.executable,
        "-m",
        "gunicorn",
        "app:app",
        "--bind",
        bind,
        "--worker-class",
        "gthread",
        "--workers",
        str(workers),
        "--threads",
        str(threads),
        "--timeout",
        str(timeout),
        "--graceful-timeout",
        str(graceful),
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
    ]

    print(
        f"[WSGI] 使用 gunicorn 运行在 http://{bind} "
        f"(workers={workers}, threads={threads}, timeout={timeout}, graceful={graceful})"
    )
    try:
        return subprocess.call(cmd)
    except FileNotFoundError as e:
        print(
            "[WSGI] 未检测到 gunicorn，请先安装：pip install gunicorn\n"
            f"[WSGI] 启动 gunicorn 失败: {e}",
            file=sys.stderr,
        )
        return 1


def _run_flask_dev(host: str, port: int) -> int:
    """开发模式：Flask 自带热重载，修改代码自动重启"""
    from app import app as flask_app

    print(
        f"[WSGI] 开发模式 (FLASK_DEBUG=1)：Flask 开发服务器 "
        f"http://{host}:{port}，支持热重载"
    )
    flask_app.run(host=host, port=port, debug=True)
    return 0


def main() -> int:
    host = (
        os.getenv("WSGI_HOST")
        or os.getenv("FLASK_HOST")
        or ("0.0.0.0" if not _is_windows() else "127.0.0.1")
    ).strip() or "0.0.0.0"
    try:
        port = int(os.getenv("WSGI_PORT") or os.getenv("PORT") or "5000")
    except ValueError:
        port = 5000

    production = (os.getenv("FLASK_ENV") or "").strip().lower() == "production"
    debug = _env_truthy("FLASK_DEBUG") and not production
    if debug:
        return _run_flask_dev(host, port)

    # 显式指定服务：waitress | gunicorn | flask
    engine = (os.getenv("WSGI_SERVER") or "").strip().lower()
    if engine == "flask":
        return _run_flask_dev(host, port)
    if engine == "gunicorn":
        return _run_gunicorn(host, port)
    if engine == "waitress":
        return _run_waitress(host, port)

    if _is_windows():
        return _run_waitress(host, port)
    return _run_gunicorn(host, port)


if __name__ == "__main__":
    raise SystemExit(main())
