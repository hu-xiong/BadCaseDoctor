"""大 JSON 响应 gzip。"""
from __future__ import annotations

import gzip
import json

def _gzip_large_json_response(resp):
    try:
        if not resp:
            return resp
        from flask import request as _req
        ae = (_req.headers.get('Accept-Encoding') or '').lower()
        if 'gzip' not in ae:
            return resp
        # 仅压缩 JSON；避免对图片/流式等产生副作用
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if 'application/json' not in ctype:
            return resp
        if resp.headers.get('Content-Encoding'):
            return resp
        # 保险：某些响应可能 direct_passthrough=True，get_data 为空/抛异常
        try:
            resp.direct_passthrough = False
        except Exception:
            pass
        data = resp.get_data(as_text=False)
        if not data or len(data) < 2048:
            return resp
        import gzip
        gz = gzip.compress(data, compresslevel=6)
        resp.set_data(gz)
        resp.headers['Content-Encoding'] = 'gzip'
        resp.headers['Content-Length'] = str(len(gz))
        resp.headers['Vary'] = 'Accept-Encoding'
        return resp
    except Exception:
        return resp
