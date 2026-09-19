/**
 * BadCase Doctor — Gremlins.js monkey test runner.
 *
 * 在目标页面上执行猴子测试（随机点击、输入、滚动等），
 * 监测 console.error / pageerror / unhandledrejection，
 * 报告崩溃和异常。
 *
 * Input (env GREMLINS_INPUT = path to JSON):
 *   { url, duration_sec?, headless?, cdp_ws_url? }
 *
 * stdout: single JSON object (machine-readable)
 * stderr: human logs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const GREMLINS_DIST = path.join(
  __dirname,
  "node_modules",
  "gremlins.js",
  "dist",
  "gremlins.min.js",
);

const DEFAULT_DURATION_SEC = 60;
const MAX_DURATION_SEC = 300;

// 部分站点 WAF 对 HeadlessChrome UA 直接回 502，需用普通浏览器 UA
const CHROME_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";

// ---- 劫持 console.log 到 stderr，防止 Playwright 内部日志污染 stdout ----
// stderr 是「一行一条」的流式协议（Python 端一点点读、按行消费）。
// 超长内容统一「换行打印」：按片切分，每片一行；单条总量设上限，防止日志爆炸。
const LOG_CHUNK_CHARS = 800;
const LOG_MAX_CHARS = 8000;
const _origConsoleLog = console.log;
function _stringifyForLog(value) {
  if (typeof value === "string") return value;
  try {
    const text = JSON.stringify(value);
    return text === undefined ? String(value) : text;
  } catch {
    return String(value);
  }
}
console.log = function (...args) {
  const text = args.map(_stringifyForLog).join(" ");
  if (!text) {
    console.error("[gremlins:log]");
    return;
  }
  const limit = Math.min(text.length, LOG_MAX_CHARS);
  for (let i = 0; i < limit; i += LOG_CHUNK_CHARS) {
    const piece = text.slice(i, i + LOG_CHUNK_CHARS);
    const isLast = i + LOG_CHUNK_CHARS >= limit;
    const tail = isLast && text.length > limit ? `…[本条日志其余 ${text.length - limit} 字符省略]` : "";
    console.error(`[gremlins:log]${i === 0 ? "" : "+"} ${piece}${tail}`);
  }
};

// 隐私/协议弹窗「同意」按钮文本（与 smoke.mjs 同步）
const CONSENT_TEXTS_MONKEY = [
  "同意并继续",
  "同意并接受",
  "我同意",
  "同意",
  "接受并继续",
  "接受全部",
  "全部接受",
  "允许全部",
  "接受",
  "Agree",
  "Accept All",
  "Accept",
  "I Agree",
];

/** 猴子测试前尝试关闭隐私弹窗，减少导航导致执行上下文销毁的概率 */
async function _tryDismissConsentBeforeMonkey(page) {
  for (let round = 0; round < 2; round++) {
    let hit = false;
    // Method 1: role-based
    for (const text of CONSENT_TEXTS_MONKEY) {
      for (const role of ["button", "link"]) {
        try {
          const loc = page.getByRole(role, { name: text, exact: true });
          const count = await loc.count();
          for (let i = 0; i < Math.min(count, 2); i++) {
            if (await loc.nth(i).isVisible({ timeout: 200 }).catch(() => false)) {
              await loc.nth(i).click({ timeout: 1000 });
              hit = true;
              break;
            }
          }
        } catch { /* try next */ }
        if (hit) break;
      }
      if (hit) break;
    }
    if (hit) { await page.waitForTimeout(300); continue; }
    // Method 2: text-based
    for (const text of CONSENT_TEXTS_MONKEY) {
      try {
        const loc = page.getByText(text, { exact: true });
        const count = await loc.count();
        for (let i = 0; i < Math.min(count, 2); i++) {
          const el = loc.nth(i);
          if (await el.isVisible({ timeout: 200 }).catch(() => false)) {
            const tag = await el.evaluate((n) => n.tagName.toLowerCase()).catch(() => "");
            if (["button", "a", "span", "div", "label"].includes(tag)) {
              await el.click({ timeout: 1000 });
              hit = true;
              break;
            }
          }
        }
      } catch { /* try next */ }
      if (hit) break;
    }
    if (!hit) break;
    await page.waitForTimeout(300);
  }
}

function readInput() {
  const inputPath = (process.env.GREMLINS_INPUT || "").trim();
  if (inputPath && fs.existsSync(inputPath)) {
    return JSON.parse(fs.readFileSync(inputPath, "utf8"));
  }
  const url = process.argv[2];
  if (!url) {
    throw new Error("缺少 url：请传 GREMLINS_INPUT JSON 或 argv[2]");
  }
  return {
    url,
    duration_sec: parseInt(process.argv[3], 10) || DEFAULT_DURATION_SEC,
    headless: String(process.env.CDP_HEADLESS || "1") !== "0",
  };
}

function emit(result) {
  // 用 fs.writeSync 同步写 stdout，避免管道模式下异步缓冲导致 JSON 截断
  fs.writeSync(1, JSON.stringify(result) + "\n");
}

async function main() {
  const started = Date.now();
  let input;
  try {
    input = readInput();
  } catch (e) {
    emit({
      success: false,
      engine: "gremlins",
      error: String(e?.message || e),
    });
    process.exit(2);
  }

  const url = String(input.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    emit({
      success: false,
      engine: "gremlins",
      error: `非法 url: ${url}`,
    });
    process.exit(2);
  }

  const durationSec = Math.min(
    Math.max(parseInt(input.duration_sec, 10) || DEFAULT_DURATION_SEC, 10),
    MAX_DURATION_SEC,
  );
  const gremlins_duration_ms = durationSec * 1000;
  const headless = input.headless !== false;
  const cdpWs = String(input.cdp_ws_url || process.env.MIDSCENE_CDP_WS_URL || "").trim();

  if (!fs.existsSync(GREMLINS_DIST)) {
    emit({
      success: false,
      engine: "gremlins",
      error: `gremlins.min.js 未找到: ${GREMLINS_DIST}`,
    });
    process.exit(2);
  }

  let browser;
  let page;
  try {
    if (cdpWs) {
      browser = await chromium.connectOverCDP(cdpWs);

      // 查找是否已有打开目标 URL 的 tab，有则复用
      let reusedPage = null;
      const normUrl = url.replace(/\/$/, "");
      for (const ctx of browser.contexts()) {
        for (const pg of ctx.pages()) {
          try {
            const pgUrl = (await pg.url()).replace(/\/$/, "");
            if (pgUrl && pgUrl === normUrl) {
              reusedPage = pg;
              break;
            }
          } catch { /* skip */ }
        }
        if (reusedPage) break;
      }

      if (reusedPage) {
        page = reusedPage;
        console.error(`[gremlins] reused existing tab for ${url}`);
      } else {
        const ctx = await browser.newContext({
          userAgent: CHROME_UA,
          locale: "zh-CN",
          viewport: { width: 1440, height: 900 },
        });
        page = await ctx.newPage();
        console.error(`[gremlins] created new tab for ${url}`);
      }
      console.error(`[gremlins] connected over CDP: ${cdpWs}`);
    } else {
      browser = await chromium.launch({
        headless,
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });
      const ctx = await browser.newContext({
        userAgent: CHROME_UA,
        locale: "zh-CN",
        viewport: { width: 1440, height: 900 },
      });
      page = await ctx.newPage();
      console.error(`[gremlins] launched chromium headless=${headless}`);
    }

    // ----- 收集页面异常 -----
    const consoleErrors = [];
    const pageErrors = [];
    const unhandledRejections = [];
    const monitoredUrls = new Set();

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push({
          text: msg.text().slice(0, 500),
          location: msg.location()?.url || "",
        });
      }
    });
    page.on("pageerror", (err) => {
      pageErrors.push(String(err?.message || err).slice(0, 500));
    });
    // 监听请求失败
    page.on("requestfailed", (req) => {
      monitoredUrls.add({
        url: req.url().slice(0, 300),
        failure: req.failure()?.errorText || "unknown",
      });
    });

    // ----- 导航到目标 URL -----
    console.error(`[gremlins] navigating to ${url}`);
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    const httpStatus = resp ? resp.status() : 0;
    if (httpStatus >= 400) {
      const pageTitle = await page.title().catch(() => "");
      console.error(`[gremlins] target unreachable: HTTP ${httpStatus}`);
      emit({
        success: false,
        engine: "gremlins",
        url,
        http_status: httpStatus,
        page_title: pageTitle,
        error: `目标页面返回 HTTP ${httpStatus}，猴子测试未执行（请确认网络/地址或站点可用性）`,
        duration_ms: Date.now() - started,
      });
      return;
    }
    await page.waitForTimeout(2000);

    const pageTitle = await page.title().catch(() => "");
    console.error(`[gremlins] page loaded: ${pageTitle}`);

    // ----- 注入 gremlins.js -----
    // 注意：部分站点（如淘股吧）页面存在全局 define（AMD 加载器），gremlins.js 的 UMD
    // 会误判环境走 define(["exports"], ...) 分支，导致 window.gremlins 永不挂载。
    // 因此改为 evaluate 注入，并在求值前临时屏蔽 exports/module/define。
    console.error(`[gremlins] injecting gremlins.js`);
    const gremlinsSrc = fs.readFileSync(GREMLINS_DIST, "utf8");
    const gremlinsInjected = await page.evaluate((src) => {
      const had = {
        exports: "exports" in globalThis,
        module: "module" in globalThis,
        define: "define" in globalThis,
      };
      const saved = {
        exports: globalThis.exports,
        module: globalThis.module,
        define: globalThis.define,
      };
      try {
        globalThis.exports = undefined;
        globalThis.module = undefined;
        globalThis.define = undefined;
        (0, eval)(src);
      } finally {
        try {
          if (had.exports) globalThis.exports = saved.exports;
          else delete globalThis.exports;
          if (had.module) globalThis.module = saved.module;
          else delete globalThis.module;
          if (had.define) globalThis.define = saved.define;
          else delete globalThis.define;
        } catch (_) {
          /* ignore */
        }
      }
      return typeof window.gremlins;
    }, gremlinsSrc);

    if (gremlinsInjected !== "object") {
      console.error(`[gremlins] injection failed: window.gremlins=${gremlinsInjected}`);
      emit({
        success: false,
        engine: "gremlins",
        url,
        http_status: httpStatus,
        page_title: pageTitle,
        error: `gremlins.js 注入失败（window.gremlins=${gremlinsInjected}），猴子测试未执行`,
        duration_ms: Date.now() - started,
      });
      return;
    }

    // ----- 运行猴子测试（统计真实触发的交互事件数，而非按时间推算） -----
    console.error(`[gremlins] unleashing for ${durationSec}s`);

    // ---- 预处理：先尝试关闭隐私/Cookie 弹窗，避免猴子点弹窗触发导航 ----
    try {
      await _tryDismissConsentBeforeMonkey(page);
    } catch (_) { /* non-blocking */ }

    const monkeyStart = Date.now();
    const speciesCreated = await page.evaluate((durationMs) => {
      return new Promise((resolve) => {
        const start = Date.now();
        const counts = { click: 0, keydown: 0, input: 0, touchstart: 0, scroll: 0 };
        const bump = (key) => () => {
          counts[key] += 1;
        };
        const listeners = [
          ["click", bump("click")],
          ["keydown", bump("keydown")],
          ["input", bump("input")],
          ["touchstart", bump("touchstart")],
          ["scroll", bump("scroll")],
        ];
        listeners.forEach(([evt, fn]) => document.addEventListener(evt, fn, true));

        const horde = window.gremlins.createHorde({
          species: [
            window.gremlins.species.clicker(),
            window.gremlins.species.toucher(),
            window.gremlins.species.formFiller(),
            window.gremlins.species.scroller(),
            window.gremlins.species.typer(),
          ],
          mogwais: [],
        });

        horde.unleash();

        setTimeout(() => {
          try {
            horde.stop();
          } catch (_) {
            /* ignore */
          }
          listeners.forEach(([evt, fn]) => document.removeEventListener(evt, fn, true));
          const actionsCount = Object.values(counts).reduce((a, b) => a + b, 0);
          resolve({
            actions_count: actionsCount,
            action_counts: counts,
            elapsed_ms: Date.now() - start,
          });
        }, durationMs);
      });
    }, durationSec * 1000).catch(async (err) => {
      // ----- 执行上下文被销毁（导航导致）：采集已执行部分的统计信息 -----
      const msg = String(err?.message || err);
      console.error(`[gremlins] evaluate context destroyed (likely navigation): ${msg.slice(0, 200)}`);
      // 尝试从页面重新获取信息
      let partial = { actions_count: 0, action_counts: {}, elapsed_ms: Date.now() - monkeyStart };
      try {
        const errors = await page.evaluate(() => (window.__gremlinsErrors || []).length).catch(() => 0);
        if (errors > 0) pageErrors.push(`gremlins navigation caused ${errors} context errors`);
      } catch { /* ignore */ }
      return partial;
    });

    console.error(
      `[gremlins] done: ${speciesCreated?.actions_count || 0} actions in ${durationSec}s`,
    );

    // 再等一小会收集异步错误
    await page.waitForTimeout(1000);

    // ----- 汇总结果 -----
    const blockedRequests = [...monitoredUrls]
      .filter((r) => r.failure !== "OK")
      .slice(0, 20);
    const hasBlocking = pageErrors.length > 0 || consoleErrors.length > 5;
    const issues = [];

    for (const pe of pageErrors.slice(0, 10)) {
      issues.push({
        type: "gremlins_page_error",
        message: pe.slice(0, 500),
        severity: "high",
      });
    }
    for (const ce of consoleErrors.slice(0, 10)) {
      issues.push({
        type: "gremlins_console_error",
        message: `${ce.text}${ce.location ? ` @ ${ce.location}` : ""}`.slice(0, 500),
        severity: "medium",
      });
    }
    for (const br of blockedRequests.slice(0, 5)) {
      issues.push({
        type: "gremlins_request_failed",
        message: `${br.url} — ${br.failure}`.slice(0, 500),
        severity: "low",
      });
    }

    emit({
      success: !hasBlocking && (speciesCreated?.actions_count || 0) > 0,
      engine: "gremlins",
      url,
      page_title: pageTitle,
      http_status: httpStatus,
      summary: (speciesCreated?.actions_count || 0) > 0
        ? (
            `Gremlins 猴子测试完成: ` +
            `${speciesCreated?.actions_count || 0} 次随机操作（${durationSec}s），` +
            `页面错误 ${pageErrors.length} 个，` +
            `控制台错误 ${consoleErrors.length} 个，` +
            `请求失败 ${blockedRequests.length} 个。`
          )
        : "Gremlins 猴子测试未产生任何操作（页面可能未就绪或被弹窗遮挡），本次未形成有效覆盖。",
      error: (speciesCreated?.actions_count || 0) > 0
        ? undefined
        : "猴子测试未产生任何操作（页面可能未就绪或被弹窗遮挡）",
      console_errors: consoleErrors.length,
      page_errors: pageErrors.length,
      blocked_requests: blockedRequests.length,
      actions_count: speciesCreated?.actions_count || 0,
      action_counts: speciesCreated?.action_counts || {},
      duration_ms: durationSec * 1000,
      has_blocking_bug: hasBlocking,
      empty_state_seen: false,
      exploration_issues: issues,
      issues_found: issues.length,
      page: { url, title: pageTitle },
    });
  } catch (e) {
    console.error(`[gremlins] error: ${e?.stack || e}`);
    const msg = String(e?.message || e);
    emit({
      success: false,
      engine: "gremlins",
      error: msg.slice(0, 2000),
      duration_ms: Date.now() - started,
    });
    process.exitCode = 1;
  } finally {
    try {
      if (browser && !cdpWs) await browser.close();
    } catch {
      /* ignore */
    }
    // 强制退出兜底：CDP 复用模式下共享浏览器连接会拖住事件循环导致进程不退出，
    // stdout 不关闭会令 Python 侧误判「超时」；emit 已同步写入 stdout，退出不丢结果。
    process.exit(process.exitCode || 0);
  }
}

main();