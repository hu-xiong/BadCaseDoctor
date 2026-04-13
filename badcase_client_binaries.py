# -*- coding: utf-8 -*-
"""本地代理等可执行制品：文件名与目录约定（Flask 与 Agent 工具共用，避免重复配置）。"""
from __future__ import annotations

import os
from typing import Any, Dict, List

# 仓库根目录（本文件位于根目录）
_ROOT = os.path.dirname(os.path.abspath(__file__))


def client_binaries_dir() -> str:
    return os.environ.get("CLIENT_BINARIES_DIR", os.path.join(_ROOT, "client_binaries")).strip()


# 与 go-local-proxy 构建产物名一致；构建后放入 client_binaries/ 即可被下载
# arch：可选，缺省按 amd64；darwin 区分 Intel(amd64) 与 Apple Silicon(arm64)
LOCAL_PROXY_ARTIFACTS = (
    {"os": "win", "filename": "badcase-local-proxy.exe", "label": "Windows"},
    {"os": "linux", "arch": "amd64", "filename": "badcase-local-proxy-linux-amd64", "label": "Linux x64"},
    {"os": "darwin", "arch": "amd64", "filename": "badcase-local-proxy-darwin-amd64", "label": "macOS Intel"},
    {"os": "darwin", "arch": "arm64", "filename": "badcase-local-proxy-darwin-arm64", "label": "macOS Apple Silicon"},
)


def local_proxy_artifacts_for_api() -> List[Dict[str, Any]]:
    """供 SSE / manifest 使用：带 download_path、available。"""
    d = client_binaries_dir()
    out: List[Dict[str, Any]] = []
    for a in LOCAL_PROXY_ARTIFACTS:
        fn = a["filename"]
        path = os.path.join(d, fn)
        out.append(
            {
                **a,
                "download_path": f"/api/client-scripts/bin/{fn}",
                "available": os.path.isfile(path),
            }
        )
    return out
