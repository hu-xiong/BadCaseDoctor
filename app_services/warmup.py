"""启动后台预热：避免启动后首个请求（常见为登录）承担 MySQL/Redis 冷连接开销。

- MySQL：连接池并发建连 N 条（TCP + 认证成本摊到启动阶段，登录/首屏直接复用热连接）
- Redis：建立客户端并 ping（登录路径上的缓存失效/读取不再现付建连）
- 由 server_wsgi（waitress）与 app.py __main__（waitress 分支）调用；失败静默不阻塞启动。
环境变量：
  BADCASE_PREWARM=0        关闭预热（默认 1 开启）
  BADCASE_PREWARM_CONNS=N  MySQL 预热连接数（默认 8，上限 200）
  BADCASE_POOL_CORE=N      核心保底连接数（默认 0 = 不启动维持器；N>0 时周期借还以保底 N 条空闲连接）
  BADCASE_POOL_KEEPALIVE_SEC=S  维持器间隔秒（默认 1800，最小 60）
"""
from __future__ import annotations

import os
import threading
import time


def _prewarm_enabled() -> bool:
    return (os.getenv("BADCASE_PREWARM") or "1").strip().lower() not in ("0", "false", "no", "off")


def _prewarm_conns() -> int:
    try:
        n = int((os.getenv("BADCASE_PREWARM_CONNS") or "8").strip())
    except ValueError:
        n = 8
    return max(1, min(n, 200))


def _core_conns() -> int:
    try:
        n = int((os.getenv("BADCASE_POOL_CORE") or "0").strip())
    except ValueError:
        n = 0
    return max(0, min(n, 200))


def _keepalive_sec() -> float:
    try:
        s = float((os.getenv("BADCASE_POOL_KEEPALIVE_SEC") or "1800").strip())
    except ValueError:
        s = 1800.0
    return max(60.0, s)


def _start_dirty_cleanup_worker(flask_app) -> None:
    """未计划脏数据清理 worker：常驻 BRPOP Redis 队列，二次校验后物理删除。

    独立于 BADCASE_PREWARM 开关，由 DIRTY_CLEANUP_ENABLED 控制（默认开）；
    run_cleanup_worker 自带防重入（多次调用只启一个）。
    """
    try:
        from agents.dirty_data_cleanup import run_cleanup_worker

        threading.Thread(
            target=run_cleanup_worker,
            args=(flask_app,),
            name="dirty-cleanup-worker",
            daemon=True,
        ).start()
    except Exception as e:
        print(f"[DIRTY-CLEANUP] worker 启动跳过: {e}", flush=True)


def prewarm_async(flask_app, app_module=None, *, delay_s: float = 0.2) -> None:
    """daemon 线程预热 DB/Redis。

    app_module：app 模块引用（用于取模块级 get_redis_client）；缺省时跳过 Redis 预热。
    注意：app.py 以 __main__ 运行时须传入 sys.modules[__name__]，避免 import app 二次加载模块。
    """
    # 未计划脏数据清理 worker（独立于预热开关，常驻消费 Redis 队列）
    _start_dirty_cleanup_worker(flask_app)

    if not _prewarm_enabled():
        return

    def _warm_db(app_module) -> None:
        try:
            from concurrent.futures import ThreadPoolExecutor

            from sqlalchemy import text as sa_text

            # 注意：项目里 app.py 的 db = SQLAlchemy(app) 才是注册实例；
            # db_extensions.db 是未 init_app 的独立实例（使用会报 not registered），统一从扩展取。
            sa_ext = flask_app.extensions.get("sqlalchemy")
            if sa_ext is None:
                print("[PREWARM] MySQL 预热跳过: 未找到 flask_sqlalchemy 扩展", flush=True)
                return

            n = _prewarm_conns()

            def _one(_i: int) -> bool:
                try:
                    with flask_app.app_context():
                        try:
                            sa_ext.session.execute(sa_text("SELECT 1"))
                        finally:
                            try:
                                sa_ext.session.remove()
                            except Exception:
                                pass
                    return True
                except Exception:
                    return False

            # 先触发 ORM mapper 配置（几十个模型的一次性成本）
            try:
                from sqlalchemy.orm import configure_mappers

                configure_mappers()
            except Exception:
                pass

            # 跑一次与登录同形的 ORM 查询：把 Query 构建/语句编译/session 首次绑定
            # 等一次性成本也从首请求（登录）挪到启动阶段
            try:
                User = getattr(app_module, "User", None) if app_module is not None else None
                if User is not None:
                    with flask_app.app_context():
                        try:
                            User.query.filter_by(email="__prewarm__@invalid.local").first()
                        finally:
                            try:
                                sa_ext.session.remove()
                            except Exception:
                                pass
            except Exception:
                pass

            with ThreadPoolExecutor(max_workers=n) as ex:
                ok = sum(1 for r in ex.map(_one, range(n)) if r)
            try:
                with flask_app.app_context():
                    pool = sa_ext.engine.pool
                    total = int(pool.checkedin()) + int(pool.checkedout())
            except Exception:
                total = -1
            print(
                f"[PREWARM] MySQL 连接池预热 x{n} 完成（成功 {ok}，池内总数 {total}）",
                flush=True,
            )
        except Exception as e:
            print(f"[PREWARM] MySQL 预热跳过: {e}", flush=True)

    def _warm_redis() -> None:
        try:
            if app_module is not None and hasattr(app_module, "get_redis_client"):
                rc = app_module.get_redis_client()
                if rc is not None:
                    rc.ping()
                    print("[PREWARM] Redis 连接预热完成", flush=True)
        except Exception as e:
            print(f"[PREWARM] Redis 预热跳过: {e}", flush=True)

    def _run() -> None:
        t0 = time.time()
        time.sleep(max(0.0, delay_s))
        th_db = threading.Thread(target=_warm_db, args=(app_module,), name="prewarm-db", daemon=True)
        th_redis = threading.Thread(target=_warm_redis, name="prewarm-redis", daemon=True)
        th_db.start()
        th_redis.start()
        th_db.join()
        th_redis.join()
        print(f"[PREWARM] 完成，用时 {time.time() - t0:.1f}s", flush=True)

    threading.Thread(target=_run, name="prewarm-launcher", daemon=True).start()


def maintain_pool_async(flask_app, *, initial_delay_s: float = 10.0) -> None:
    """"核心连接数"维持器（SQLAlchemy QueuePool 无 minIdle 语义，此处模拟之）。

    每 BADCASE_POOL_KEEPALIVE_SEC 秒并发借出后归还 core 条连接：
    - 池内不足 core 时自动建新连接（冷建连成本留在后台）
    - 借出会触发 pool_pre_ping 校验与 pool_recycle 超龄重建（同样在后台消化）
    - 归还后空闲连接保底 core 条，业务请求永远 checkout 热连接

    环境变量：
      BADCASE_POOL_CORE=N          核心保底连接数（默认 0 = 不启动）
      BADCASE_POOL_KEEPALIVE_SEC=S 维持间隔秒（默认 1800，最小 60）
    """
    core_n = _core_conns()
    if core_n <= 0:
        return
    interval_s = _keepalive_sec()

    def _maintain_once() -> None:
        from concurrent.futures import ThreadPoolExecutor

        # 与预热同一入口：从 flask_app 扩展取注册的 SQLAlchemy 实例
        sa_ext = flask_app.extensions.get("sqlalchemy")
        if sa_ext is None:
            print("[POOL] 维持跳过: 未找到 flask_sqlalchemy 扩展", flush=True)
            return

        t0 = time.time()
        with flask_app.app_context():
            engine = sa_ext.engine

            def _touch(_i: int) -> bool:
                try:
                    conn = engine.connect()
                except Exception:
                    return False
                try:
                    return True
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

            workers = max(1, min(16, core_n))
            with ThreadPoolExecutor(max_workers=workers) as ex:
                ok = sum(1 for r in ex.map(_touch, range(core_n)) if r)
            try:
                pool = engine.pool
                idle = int(pool.checkedin())
                total = idle + int(pool.checkedout())
            except Exception:
                idle, total = -1, -1
            print(
                f"[POOL] 维持 core={core_n}: 借还 {ok}/{core_n}，"
                f"用时 {time.time() - t0:.1f}s，空闲={idle} 总数={total}",
                flush=True,
            )

    def _loop() -> None:
        time.sleep(max(0.0, initial_delay_s))
        while True:
            try:
                _maintain_once()
            except Exception as e:
                print(f"[POOL] 维持跳过: {e}", flush=True)
            time.sleep(interval_s)

    threading.Thread(target=_loop, name="pool-maintainer", daemon=True).start()
