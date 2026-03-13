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

    threads = int(os.getenv("WSGI_THREADS", "8"))
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


def main() -> int:
    host = os.getenv("WSGI_HOST", "127.0.0.1")
    port = int(os.getenv("WSGI_PORT", "5000"))

    if _is_windows():
        return _run_waitress(host, port)

    # 非 Windows 优先 gunicorn；如未安装可用 waitress 兜底
    try:
        import gunicorn  # noqa: F401

        return _run_gunicorn(host, port)
    except Exception:
        return _run_waitress(host, port)


if __name__ == "__main__":
    raise SystemExit(main())

