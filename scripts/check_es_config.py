import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Config


def main():
    url = (Config.ES_URL or f"http://{Config.ES_HOST}:{Config.ES_PORT}").rstrip("/")
    print(f"ES endpoint: {url}")
    print(f"ES auth: {'api_key' if Config.ES_API_KEY else 'basic' if (Config.ES_USERNAME or Config.ES_PASSWORD) else 'none'}")
    print(f"ES verify certs: {Config.ES_VERIFY_CERTS}")
    print(f"Work item alias: {Config.GREP_WORK_ITEM_ALIAS}")
    print(f"Long memory index: {Config.ES_LONG_MEMORY_INDEX}")

    headers = {}
    if Config.ES_API_KEY:
        headers["Authorization"] = "ApiKey " + Config.ES_API_KEY
    elif Config.ES_USERNAME or Config.ES_PASSWORD:
        token = base64.b64encode(f"{Config.ES_USERNAME}:{Config.ES_PASSWORD}".encode()).decode()
        headers["Authorization"] = "Basic " + token

    context = None
    if url.startswith("https://") and not Config.ES_VERIFY_CERTS:
        context = ssl._create_unverified_context()

    for path in ["/", "/_cluster/health", f"/_alias/{Config.GREP_WORK_ITEM_ALIAS}"]:
        req = urllib.request.Request(url + path, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5, context=context) as resp:
                raw = resp.read(2000).decode("utf-8", "replace")
                try:
                    parsed = json.loads(raw)
                    raw = json.dumps(parsed, ensure_ascii=False)[:1200]
                except Exception:
                    raw = raw[:1200]
                print(f"\n{path} -> HTTP {resp.status}")
                print(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read(800).decode("utf-8", "replace")
            print(f"\n{path} -> HTTPError {exc.code}: {body}")
        except Exception as exc:
            print(f"\n{path} -> {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
