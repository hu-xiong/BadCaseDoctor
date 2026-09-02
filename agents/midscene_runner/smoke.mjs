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
  "1) 确认页面已打开且不是明显报错页；",
  "2) 浏览侧栏/主导航/Tab，了解有哪些入口；",
  "3) 若有空状态，尝试新建/添加主业务对象（卡片、计划、用例等）并尽量保存；",
  "4) 尝试搜索、筛选、打开详情等常见操作；",
  "5) 不要点击删除、注销、退出登录、清空数据等危险操作；",
  "6) 日期/下拉请用正常点选，不要乱填无意义字符串；",
  "完成后停留在结果页，便于汇总。",
].join("\n");

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
  process.stdout.write(JSON.stringify(result));
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
      const ctx = browser.contexts()[0] || (await browser.newContext());
      page = ctx.pages()[0] || (await ctx.newPage());
      console.error(`[midscene] connected over CDP: ${cdpWs}`);
    } else {
      browser = await chromium.launch({
        headless,
        args: ["--no-sandbox", "--disable-setuid-sandbox"],
      });
      page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      console.error(`[midscene] launched chromium headless=${headless}`);
    }

    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1500);

    agent = new PlaywrightAgent(page);

    console.error("[midscene] aiAct start");
    await agent.aiAct(goal);
    console.error("[midscene] aiAct done, querying report");

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

    emit({
      success: !blocking && failed.length === 0,
      engine: "midscene",
      url,
      page_title: report?.page_title || (await page.title().catch(() => "")),
      summary: String(report?.summary || "").trim(),
      tested_flows: tested,
      passed,
      failed,
      has_blocking_bug: blocking,
      empty_state_seen: Boolean(report?.empty_state_seen),
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
  }
}

main();
