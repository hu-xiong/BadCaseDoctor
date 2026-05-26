import os
import platform
import subprocess
import sys


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


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
    print(f"[WSGI] Windows 环境：使用 waitress 运行在 http://{host}:{port} (threads={threads})")
    serve(flask_app, host=host, port=port, threads=threads)
    return 0


def _run_gunicorn(host: str, port: int) -> int:
    # gunicorn 通常以 CLI 形式运行；这里用 subprocess 拉起，方便统一入口
    workers = os.getenv("WEB_CONCURRENCY") or os.getenv("WSGI_WORKERS") or "2"
    threads = os.getenv("WSGI_THREADS") or "4"
    timeout = os.getenv("WSGI_TIMEOUT") or "120"

    bind = f"{host}:{port}"
    cmd = [
        sys.executable,
        "-m",
        "gunicorn",
        "app:app",
        "--bind",
        bind,
        "--workers",
        str(workers),
        "--threads",
        str(threads),
        "--timeout",
        str(timeout),
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
    ]

    print(f"[WSGI] Linux/Unix 环境：使用 gunicorn 运行在 http://{bind} (workers={workers}, threads={threads})")
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
    print(f"[WSGI] 开发模式 (FLASK_DEBUG=1)：使用 Flask 开发服务器 http://{host}:{port}，支持热重载")
    flask_app.run(host=host, port=port, debug=True)
    return 0


def main() -> int:
    host = os.getenv("WSGI_HOST", "127.0.0.1")
    port = int(os.getenv("WSGI_PORT", "5000"))

    # 强制使用开发模式，以便看到日志输出
    return _run_flask_dev(host, port)


if __name__ == "__main__":
    raise SystemExit(main())

