import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # pyyaml
except Exception as exc:  # pragma: no cover
    print("缺少依赖 pyyaml，请先安装: pip install pyyaml", file=sys.stderr)
    raise


# 尝试延迟导入以便无需时不报错
def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        return sync_playwright
    except Exception as exc:  # pragma: no cover
        print(
            "缺少依赖 playwright，请先安装: pip install playwright\n安装浏览器: playwright install",
            file=sys.stderr,
        )
        raise


@dataclass
class CaptureRule:
    url_include_patterns: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE"])


@dataclass
class Overrides:
    url_base_replace_from: Optional[str] = None
    url_base_replace_to: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)
    body_overrides: Dict[str, Any] = field(default_factory=dict)  # 仅对 JSON body 生效


@dataclass
class ExecConfig:
    run: bool = False
    timeout: int = 30


@dataclass
class BrowserConfig:
    headless: bool = True
    user_agent: Optional[str] = None


@dataclass
class Config:
    start_url: str = "https://njjs-its-aitpm04.njjs.baidu.com:8690/web-saas/professional-qna/app?batchId=65147f13-577a-4ca0-8b77-e116c28b6457"
    wait_until: str = "networkidle"  # load | domcontentloaded | networkidle
    actions: List[Dict[str, Any]] = field(default_factory=list)  # 浏览器动作脚本
    capture: CaptureRule = field(default_factory=CaptureRule)
    overrides: Overrides = field(default_factory=Overrides)
    execute: ExecConfig = field(default_factory=ExecConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    output_dir: str = "captures"


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    capture = data.get("capture", {}) or {}
    overrides = data.get("overrides", {}) or {}
    execute = data.get("execute", {}) or {}
    browser = data.get("browser", {}) or {}

    return Config(
        start_url=data.get("start_url", "https://njjs-its-aitpm04.njjs.baidu.com:8690/web-saas/professional-qna/app?batchId=65147f13-577a-4ca0-8b77-e116c28b6457"),
        wait_until=data.get("wait_until", "networkidle"),
        actions=data.get("actions", []) or [],
        capture=CaptureRule(
            url_include_patterns=capture.get("url_include_patterns", []) or [],
            methods=[m.upper() for m in (capture.get("methods", []) or ["GET", "POST", "PUT", "PATCH", "DELETE"])],
        ),
        overrides=Overrides(
            url_base_replace_from=overrides.get("url_base_replace_from"),
            url_base_replace_to=overrides.get("url_base_replace_to"),
            headers=overrides.get("headers", {}) or {},
            query_params=overrides.get("query_params", {}) or {},
            body_overrides=overrides.get("body_overrides", {}) or {},
        ),
        execute=ExecConfig(
            run=bool(execute.get("run", False)),
            timeout=int(execute.get("timeout", 30)),
        ),
        browser=BrowserConfig(
            headless=bool(browser.get("headless", True)),
            user_agent=browser.get("user_agent"),
        ),
        output_dir=data.get("output_dir", "captures"),
    )


def match_url(url: str, patterns: List[str]) -> bool:
    if not patterns:
        return True
    for p in patterns:
        try:
            if re.search(p, url):
                return True
        except re.error:
            # 回退为简单包含
            if p in url:
                return True
    return False


def apply_overrides(
    method: str,
    url: str,
    headers: Dict[str, str],
    post_data: Optional[bytes],
    cfg: Config,
) -> Tuple[str, Dict[str, str], Optional[bytes]]:
    # URL 基础替换
    if cfg.overrides.url_base_replace_from and cfg.overrides.url_base_replace_to:
        url = url.replace(cfg.overrides.url_base_replace_from, cfg.overrides.url_base_replace_to)

    # 追加/覆盖 query 参数
    if cfg.overrides.query_params:
        from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

        parsed = urlparse(url)
        q = dict(parse_qsl(parsed.query, keep_blank_values=True))
        q.update(cfg.overrides.query_params)
        new_query = urlencode(q, doseq=True)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    # 头覆盖（如 Authorization）
    for k, v in (cfg.overrides.headers or {}).items():
        headers[k] = v

    # body 覆盖（仅 JSON）
    if post_data and cfg.overrides.body_overrides:
        ct = headers.get("Content-Type", headers.get("content-type", ""))
        if "application/json" in ct:
            try:
                body = json.loads(post_data.decode("utf-8")) if post_data else {}
                if isinstance(body, dict):
                    body.update(cfg.overrides.body_overrides)
                    post_data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            except Exception:
                pass

    return url, headers, post_data


def build_curl(method: str, url: str, headers: Dict[str, str], body: Optional[bytes]) -> str:
    parts = ["curl", "-X", method, shlex.quote(url)]
    for k, v in headers.items():
        parts += ["-H", shlex.quote(f"{k}: {v}")]
    if body:
        # 直接以二进制转文本输出（尽量假设utf-8），失败则跳过
        try:
            body_text = body.decode("utf-8")
        except Exception:
            body_text = body.decode("latin1", errors="ignore")
        parts += ["--data", shlex.quote(body_text)]
    return " ".join(parts)


def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def save_capture(output_dir: str, payload: Dict[str, Any]) -> str:
    ensure_dir(output_dir)
    fname = os.path.join(output_dir, "capture.json")
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return fname


def run_browser_and_capture(cfg: Config) -> Dict[str, Any]:
    sync_playwright = _load_playwright()
    captured: Dict[str, Any] = {}

    with sync_playwright()() as p:
        browser = p.chromium.launch(headless=cfg.browser.headless)
        context_args: Dict[str, Any] = {}
        if cfg.browser.user_agent:
            context_args["user_agent"] = cfg.browser.user_agent
        context = browser.new_context(**context_args)
        page = context.new_page()

        def on_request(req):
            nonlocal captured
            if captured:
                return  # 已抓取到一个，忽略后续
            method = req.method
            url = req.url
            if method.upper() not in cfg.capture.methods:
                return
            if not match_url(url, cfg.capture.url_include_patterns):
                return

            headers = dict(req.headers)
            post_data = None
            try:
                post_data = req.post_data_buffer
            except Exception:
                try:
                    txt = req.post_data or None
                    post_data = txt.encode("utf-8") if txt else None
                except Exception:
                    post_data = None

            # 应用覆盖
            new_url, new_headers, new_body = apply_overrides(method, url, headers, post_data, cfg)
            curl_cmd = build_curl(method, new_url, new_headers, new_body)

            captured = {
                "method": method,
                "original_url": url,
                "final_url": new_url,
                "headers": new_headers,
                "body": (new_body.decode("utf-8", errors="ignore") if new_body else None),
                "curl": curl_cmd,
            }

        page.on("request", on_request)

        page.goto(cfg.start_url, wait_until=cfg.wait_until)

        # 执行动作脚本（模拟点击/输入/等待/跳转等）
        def run_actions():
            for step in cfg.actions:
                if not isinstance(step, dict):
                    continue
                # 支持的动作：click, fill, wait_for_selector, wait, goto, press
                if "goto" in step:
                    page.goto(str(step["goto"]), wait_until=cfg.wait_until)
                elif "click" in step:
                    sel = str(step["click"])
                    page.locator(sel).click()
                elif "fill" in step:
                    sel = str(step.get("selector", ""))
                    val = str(step.get("value", ""))
                    if sel:
                        page.locator(sel).fill(val)
                elif "press" in step:
                    sel = str(step.get("selector", ""))
                    key = str(step.get("press", "Enter"))
                    if sel:
                        page.locator(sel).press(key)
                    else:
                        page.keyboard.press(key)
                elif "wait_for_selector" in step:
                    sel = str(step["wait_for_selector"])
                    page.wait_for_selector(sel)
                elif "wait" in step:
                    ms = int(step.get("wait", 500))
                    page.wait_for_timeout(ms)
                elif "download" in step:
                    # 下载文件到 output_dir，download 字段可为 selector 或 URL
                    target = step.get("download")
                    if isinstance(target, str) and target.startswith("http"):
                        # 直接通过 fetch 下载
                        import urllib.request

                        ensure_dir(cfg.output_dir)
                        fname = step.get("filename") or os.path.basename(target.split("?")[0]) or "download.bin"
                        out = os.path.join(cfg.output_dir, fname)
                        urllib.request.urlretrieve(target, out)
                    else:
                        # 通过点击触发浏览器下载
                        sel = str(target)
                        ensure_dir(cfg.output_dir)
                        with page.expect_download() as dl:
                            page.locator(sel).click()
                        download = dl.value
                        final_path = Path(cfg.output_dir) / (step.get("filename") or download.suggested_filename)
                        download.save_as(str(final_path))
                elif "screenshot" in step:
                    # 截图当前页面或指定元素
                    ensure_dir(cfg.output_dir)
                    out = Path(cfg.output_dir) / (step.get("filename") or "screenshot.png")
                    sel = step.get("selector")
                    if sel:
                        page.locator(str(sel)).screenshot(path=str(out))
                    else:
                        page.screenshot(path=str(out), full_page=bool(step.get("full_page", True)))

        run_actions()

        # 若仍未捕获，额外等待一小段时间以便请求产生
        if not captured:
            page.wait_for_timeout(3000)

        context.close()
        browser.close()

    return captured


def maybe_exec_curl(cmd: str, exec_cfg: ExecConfig) -> Tuple[int, str, str]:
    if not exec_cfg.run:
        return 0, "", ""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=exec_cfg.timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:  # pragma: no cover
        return 124, "", f"curl 超时: {e}"


def main():
    parser = argparse.ArgumentParser(description="使用浏览器拦截接口，按配置覆盖并生成/执行 curl")
    parser.add_argument("--config", default="config/permission_config.yaml", help="配置文件路径")
    parser.add_argument("--print-only", action="store_true", help="仅打印，不执行 curl")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cap = run_browser_and_capture(cfg)
    if not cap:
        print("未捕获到符合规则的请求，请调整 capture.url_include_patterns 或手动在页面触发接口。", file=sys.stderr)
        sys.exit(2)

    out_path = save_capture(cfg.output_dir, cap)
    print(f"已保存抓取数据: {out_path}")
    print("生成的 curl: \n" + cap["curl"])

    if args.print_only:
        return

    code, stdout, stderr = maybe_exec_curl(cap["curl"], cfg.execute)
    if cfg.execute.run:
        print(f"curl 返回码: {code}")
        if stdout:
            print("curl 标准输出:\n" + stdout)
        if stderr:
            print("curl 错误输出:\n" + stderr, file=sys.stderr)


if __name__ == "__main__":
    main()


