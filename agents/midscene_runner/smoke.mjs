/**
 * BadCase Doctor — Midscene UI smoke runner.
 *
 * Input (env MIDSCENE_SMOKE_INPUT = path to JSON):
 *   { url, goal?, headless?, timeout_ms? }
 *
 * stdout: single JSON object (machine-readable)
 * stderr: human logs
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
import { PlaywrightAgent } from "@midscene/web/playwright";

const DEFAULT_GOAL = [
  "你是一名认真的手工测试同学。请像正常人一样先把这个 Web 系统的主要界面功能走一遍：",
  "0) 若出现隐私政策/用户协议/Cookie 弹窗，先点击「同意」/「接受」；若页面要求登录而无法登录，如实说明被登录阻塞，不要虚构已测内容；遇到登录页不要猜测或输入任何账号密码、不要注册，记录已测内容后尽快结束探索并报告被登录阻塞；",
  "1) 确认页面已打开且不是明显报错页；",
  "2) 浏览侧栏/主导航/Tab，了解有哪些入口；",
  "3) 若有空状态，尝试新建/添加主业务对象（卡片、计划、用例等）并尽量保存；",
  "4) 尝试搜索、筛选、打开详情等常见操作；",
  "5) 不要点击删除、注销、退出登录、清空数据等危险操作；",
  "6) 日期/下拉请用正常点选，不要乱填无意义字符串；",
  "完成后停留在结果页，便于汇总。",
].join("\n");

// 部分站点 WAF 对 HeadlessChrome UA 直接回 502，需用普通浏览器 UA
const CHROME_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";

// 隐私政策/协议弹窗的「同意」按钮（只点同意，不点「暂不使用」）
const CONSENT_TEXTS = [
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

// ---- 劫持 console.log 到 stderr，防止 Midscene/Playwright 内部日志污染 stdout 的纯 JSON ----
// stderr 是「一行一条」的流式协议（Python 端一点点读、按行消费）。
// Midscene 可能把整棵元素树/提示词打成一行超长内容（数百 KB），
// 这里统一「换行打印」：按片切分，每片一行；单条总量设上限，防止日志爆炸。
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
    console.error("[midscene:log]");
    return;
  }
  const limit = Math.min(text.length, LOG_MAX_CHARS);
  for (let i = 0; i < limit; i += LOG_CHUNK_CHARS) {
    const piece = text.slice(i, i + LOG_CHUNK_CHARS);
    const isLast = i + LOG_CHUNK_CHARS >= limit;
    const tail = isLast && text.length > limit ? `…[本条日志其余 ${text.length - limit} 字符省略]` : "";
    console.error(`[midscene:log]${i === 0 ? "" : "+"} ${piece}${tail}`);
  }
};

async function tryDismissConsent(page) {
  const clicked = [];
  for (let round = 0; round < 3; round++) {
    let hit = false;

    // ---- Method 1: role-based locator (standard buttons / links) ----
    for (const text of CONSENT_TEXTS) {
      for (const role of ["button", "link"]) {
        try {
          const loc = page.getByRole(role, { name: text, exact: true });
          const count = await loc.count();
          for (let i = 0; i < Math.min(count, 2); i++) {
            const el = loc.nth(i);
            try {
              if (await el.isVisible({ timeout: 200 })) {
                await el.click({ timeout: 1500 });
                clicked.push(`role:${role}:${text}`);
                await page.waitForTimeout(400);
                hit = true;
                break;
              }
            } catch {
              /* try next */
            }
          }
        } catch {
          /* try next */
        }
        if (hit) break;
      }
      if (hit) break;
    }
    if (hit) continue;

    // ---- Method 2: text-based locator (for custom elements not exposing ARIA role) ----
    for (const text of CONSENT_TEXTS) {
      try {
        const loc = page.getByText(text, { exact: true });
        const count = await loc.count();
        for (let i = 0; i < Math.min(count, 2); i++) {
          const el = loc.nth(i);
          try {
            if (await el.isVisible({ timeout: 200 })) {
              // Only click if it looks like a clickable element
              const tag = await el.evaluate((node) => node.tagName.toLowerCase()).catch(() => "");
              if (["button", "a", "span", "div", "label"].includes(tag)) {
                await el.click({ timeout: 1500 });
                clicked.push(`text:${text}`);
                await page.waitForTimeout(400);
                hit = true;
                break;
              }
            }
          } catch {
            /* try next */
          }
        }
      } catch {
        /* try next */
      }
      if (hit) break;
    }
    if (hit) continue;

    // ---- Method 3: CSS selector fallback — common consent modal patterns ----
    const cssSelectors = [
      'button:has-text("同意")',
      'button:has-text("接受")',
      'button:has-text("Agree")',
      'button:has-text("Accept")',
      'a:has-text("同意")',
      'a:has-text("接受")',
      '[class*="consent"] button',
      '[class*="privacy"] button',
      '[class*="cookie"] button',
      '[class*="policy"] button',
      '[class*="protocol"] button',
      '.el-dialog button:has-text("同意")',
      '.el-dialog__footer button:first-child',
      '.van-dialog__confirm',
    ];
    for (const css of cssSelectors) {
      try {
        const els = await page.locator(css).all();
        for (const el of els) {
          try {
            if (await el.isVisible({ timeout: 200 })) {
              await el.click({ timeout: 1500 });
              clicked.push(`css:${css}`);
              await page.waitForTimeout(400);
              hit = true;
              break;
            }
          } catch {
            /* try next */
          }
        }
      } catch {
        /* try next */
      }
      if (hit) break;
    }

    if (!hit) break;
  }
  return clicked;
}

function readInput() {
  const inputPath = (process.env.MIDSCENE_SMOKE_INPUT || "").trim();
  if (inputPath && fs.existsSync(inputPath)) {
    return JSON.parse(fs.readFileSync(inputPath, "utf8"));
  }
  const url = process.argv[2];
  if (!url) {
    throw new Error("缺少 url：请传 MIDSCENE_SMOKE_INPUT JSON 或 argv[2]");
  }
  return {
    url,
    goal: process.argv[3] || DEFAULT_GOAL,
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
      engine: "midscene",
      error: String(e?.message || e),
      fallback_legacy: false,
    });
    process.exit(2);
  }

  const url = String(input.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    emit({
      success: false,
      engine: "midscene",
      error: `非法 url: ${url}`,
      fallback_legacy: false,
    });
    process.exit(2);
  }

  const goal = String(input.goal || DEFAULT_GOAL);
  const headless = input.headless !== false;
  const cdpWs = String(input.cdp_ws_url || process.env.MIDSCENE_CDP_WS_URL || "").trim();

  let browser;
  let page;
  let agent;
  try {
    if (cdpWs) {
      browser = await chromium.connectOverCDP(cdpWs);

      // 查找是否已有打开目标 URL 的 tab，有则复用（避免重复开新 tab）
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
          } catch { /* page might be on about:blank */ }
        }
        if (reusedPage) break;
      }

      if (reusedPage) {
        page = reusedPage;
        console.error(`[midscene] reused existing tab for ${url}`);
      } else {
        // 没有匹配的 tab：新建一个独立 context（不影响已有会话）
        const ctx = await browser.newContext({
          userAgent: CHROME_UA,
          locale: "zh-CN",
          viewport: { width: 1440, height: 900 },
        });
        page = await ctx.newPage();
        console.error(`[midscene] created new tab for ${url}`);
      }
      console.error(`[midscene] connected over CDP: ${cdpWs}`);
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
      console.error(`[midscene] launched chromium headless=${headless}`);
    }

    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    const httpStatus = resp ? resp.status() : 0;
    if (httpStatus >= 400) {
      const pageTitle = await page.title().catch(() => "");
      console.error(`[midscene] target unreachable: HTTP ${httpStatus}`);
      emit({
        success: false,
        engine: "midscene",
        url,
        http_status: httpStatus,
        page_title: pageTitle,
        error: `目标页面返回 HTTP ${httpStatus}，无法开展界面巡检（请确认网络/地址或站点可用性）`,
        fallback_legacy: false,
        duration_ms: Date.now() - started,
      });
      return;
    }
    await page.waitForTimeout(1500);
    const consentDismissed = await tryDismissConsent(page);
    if (consentDismissed.length) {
      console.error(`[midscene] consent dismissed: ${consentDismissed.join(", ")}`);
    }

    agent = new PlaywrightAgent(page);

    // ---- 注册逐步骤进度监听：每执行一步就通过 stderr 推送给 Python 端实时显示 ----
    const executionSteps = [];
    const unsubProgress = agent.addProgressListener((event) => {
      // 剔除大字段（如 base64 截图）：仅上行结构化动作信息，避免数 MB 单行
      let data = event.data;
      if (data && typeof data === "object" && !Array.isArray(data)) {
        const { screenshot, screenshots, image, imageBase64, ...rest } = data;
        data = rest;
      }
      const step = {
        phase: event.phase,
        sequence: event.sequence,
        data,
      };
      executionSteps.push(step);
      // [step] 前缀供 Python 流式读取识别
      console.error('[step]' + JSON.stringify(step));
    });

    console.error("[midscene] aiAct start");
    await agent.aiAct(goal);
    unsubProgress();
    console.error("[midscene] aiAct done, querying report");

    // ---- Post-check: 再次尝试关闭隐私弹窗（AI 可能未成功），防止幻觉报告 ----
    const consentAfter = await tryDismissConsent(page);
    if (consentAfter.length) {
      console.error(`[midscene] consent re-dismissed after aiAct: ${consentAfter.join(", ")}`);
    }
    const hasConsentModalStill = (consentDismissed.length === 0 && consentAfter.length === 0)
      ? await (async () => {
          // 如果两次都没点过，检查弹窗是否还可见
          try {
            const modalTexts = ["隐私政策", "隐私协议", "用户协议", "Cookie", "同意", "接受"];
            for (const t of modalTexts) {
              const el = page.getByText(t, { exact: false });
              if (await el.first().isVisible({ timeout: 200 }).catch(() => false)) {
                return true;
              }
            }
          } catch { /* ignore */ }
          return false;
        })()
      : false;
    if (hasConsentModalStill) {
      console.error("[midscene] WARNING: consent modal still visible after aiAct — AI report may be hallucinated");
    }

    const report = await agent.aiQuery(
      `{
        tested_flows: string[],
        passed: string[],
        failed: { step: string, reason: string }[],
        summary: string,
        has_blocking_bug: boolean,
        page_title: string,
        empty_state_seen: boolean
      },
      根据刚才对页面的真实操作，给出中文结构化测试报告。
      tested_flows=实际尝试过的功能入口；
      passed=看起来正常的点；
      failed=失败或异常（含无法完成的关键操作）；
      has_blocking_bug=是否存在阻止主流程的问题；
      empty_state_seen=是否见到空列表/暂无数据。`,
    );

    let reportFile = "";
    try {
      // Midscene prints report path to console; also check default dir
      const reportDir = path.join(process.cwd(), "midscene_run", "report");
      if (fs.existsSync(reportDir)) {
        const files = fs
          .readdirSync(reportDir)
          .filter((f) => f.endsWith(".html"))
          .map((f) => ({
            f,
            m: fs.statSync(path.join(reportDir, f)).mtimeMs,
          }))
          .sort((a, b) => b.m - a.m);
        if (files[0]) {
          reportFile = path.join(reportDir, files[0].f);
        }
      }
    } catch {
      /* ignore */
    }

    const failed = Array.isArray(report?.failed) ? report.failed : [];
    const passed = Array.isArray(report?.passed) ? report.passed : [];
    const tested = Array.isArray(report?.tested_flows) ? report.tested_flows : [];
    const blocking = Boolean(report?.has_blocking_bug);
    // 巡检「有效完成」= 拿到结构化报告（有已测/通过/失败任一信号）且无阻塞性问题；
    // failed 列表是巡检产出（发现的失败点，含空状态等轻微项），不等于巡检失败
    const hasSignal = tested.length > 0 || passed.length > 0 || failed.length > 0;
    const reportMissing = !(report && typeof report === "object") || !hasSignal;

    emit({
      success: !reportMissing && !blocking,
      report_missing: reportMissing,
      engine: "midscene",
      url,
      page_title: report?.page_title || (await page.title().catch(() => "")),
      summary: String(report?.summary || "").trim(),
      tested_flows: tested,
      passed,
      failed,
      has_blocking_bug: blocking,
      empty_state_seen: Boolean(report?.empty_state_seen),
      consent_dismissed: consentDismissed,
      consent_post_check: {
        dismissed_after_ai: consentAfter,
        modal_still_visible: hasConsentModalStill,
      },
      execution_steps: executionSteps,
      report_file: reportFile,
      duration_ms: Date.now() - started,
    });
  } catch (e) {
    console.error(`[midscene] error: ${e?.stack || e}`);
    const msg = String(e?.message || e);
    const missingModel =
      /MIDSCENE_MODEL|API_KEY|api key|model/i.test(msg) ||
      /401|403|Unauthorized/i.test(msg);
    emit({
      success: false,
      engine: "midscene",
      error: msg.slice(0, 2000),
      fallback_legacy: missingModel || /Cannot find module|ERR_MODULE_NOT_FOUND/i.test(msg),
      duration_ms: Date.now() - started,
    });
    process.exitCode = 1;
  } finally {
    try {
      if (agent?.destroy) await agent.destroy();
    } catch {
      /* ignore */
    }
    try {
      if (browser && !cdpWs) await browser.close();
    } catch {
      /* ignore */
    }
    // 强制退出兜底：CDP 复用模式（cdpWs 非空）下不关闭共享浏览器连接，
    // 活跃的 WebSocket 会拖住 Node 事件循环，进程不退出 → stdout 不关闭，
    // Python 侧读流拿不到 EOF 会误判「超时」并丢弃已写出的成功结果。
    // 最终 JSON 已用 fs.writeSync 同步写入 stdout，强制退出不会丢数据。
    process.exit(process.exitCode || 0);
  }
}

main();
