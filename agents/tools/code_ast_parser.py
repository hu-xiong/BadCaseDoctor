# -*- coding: utf-8 -*-
"""
Python 源码 AST 浅层结构提取：用于代码分析/结构理解时优先于浅层正则全文匹配。
非 .py 或语法错误时返回 success=false，由调用方回退文本搜索。
"""

from __future__ import annotations

import ast
import os
import re
from typing import Any, Dict, List, Optional


def analyze_python_source(source: str, *, path: str = "") -> Dict[str, Any]:
    """解析 Python 源码，提取顶层类/函数/异步函数与 import 摘要。"""
    if not isinstance(source, str) or not source.strip():
        return {"success": False, "error": "empty_source", "path": path}
    try:
        tree = ast.parse(source, filename=path or "<string>")
    except SyntaxError as e:
        return {"success": False, "error": f"syntax_error: {e}", "path": path}

    classes: List[str] = []
    functions: List[str] = []
    async_functions: List[str] = []
    imports: List[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.AsyncFunctionDef):
            async_functions.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)

    return {
        "success": True,
        "path": path,
        "classes": classes[:200],
        "functions": functions[:200],
        "async_functions": async_functions[:200],
        "imports": imports[:300],
        "lineno": getattr(tree, "lineno", None),
    }


def analyze_python_file(
    file_path: str,
    *,
    max_bytes: int = 512_000,
) -> Dict[str, Any]:
    """读取本地文件并做 AST 分析（过大文件截断拒绝解析以免内存压力）。"""
    p = os.path.abspath(file_path)
    if not os.path.isfile(p):
        return {"success": False, "error": "not_a_file", "path": p}
    try:
        sz = os.path.getsize(p)
        if sz > max_bytes:
            return {"success": False, "error": f"file_too_large:{sz}", "path": p}
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError as e:
        return {"success": False, "error": str(e), "path": p}
    if not p.lower().endswith(".py"):
        return {"success": False, "error": "not_python_extension", "path": p}
    out = analyze_python_source(src, path=p)
    out["bytes"] = len(src.encode("utf-8", errors="replace"))
    return out


def analyze_code_paths(
    paths: Any,
    *,
    max_files: int = 20,
    max_bytes_per_file: int = 512_000,
) -> Dict[str, Any]:
    """
    批量分析路径列表（字符串或列表）。返回每文件结果与合并符号表。
    paths: str（逗号/换行分隔）或 list[str]
    """
    if paths is None:
        return {"success": False, "error": "no_paths", "files": []}
    if isinstance(paths, str):
        raw = [x.strip() for x in re_split_paths(paths) if x.strip()]
    elif isinstance(paths, (list, tuple)):
        raw = [str(x).strip() for x in paths if str(x).strip()]
    else:
        return {"success": False, "error": "invalid_paths_type", "files": []}

    raw = raw[: max(1, max_files)]
    files_out: List[Dict[str, Any]] = []
    all_classes: List[str] = []
    all_functions: List[str] = []

    for p in raw:
        one = analyze_python_file(p, max_bytes=max_bytes_per_file)
        files_out.append(one)
        if one.get("success"):
            all_classes.extend(one.get("classes") or [])
            all_functions.extend(one.get("functions") or [])
            all_functions.extend(one.get("async_functions") or [])

    any_ok = any(f.get("success") for f in files_out)
    return {
        "success": any_ok,
        "files": files_out,
        "merged_symbols": {
            "classes": all_classes[:500],
            "functions": all_functions[:500],
        },
    }


def re_split_paths(s: str) -> List[str]:
    return re.split(r"[\n,;]+", s)
