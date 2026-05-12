"""Patch grep_tool: raw_target, plan entity search, wrap non-plan locate in if not skip_rest_of_locate."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "agents" / "tools" / "grep_tool.py"
lines = path.read_text(encoding="utf-8").splitlines()

# --- import ---
imp_i = None
for i, ln in enumerate(lines):
    if ln.strip() == "normalize_locale,":
        imp_i = i
        break
if imp_i is None:
    raise SystemExit("import anchor missing")
if "is_english_locale" not in "\n".join(lines[max(0, imp_i - 3) : imp_i + 5]):
    lines.insert(imp_i + 1, "    is_english_locale,")

# --- raw_target after keywords ---
anchor = '        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target}, status={status}, plan_id={plan_id})")'
new_lines_kw = [
    '        raw_target = (target or "all").strip().lower() if isinstance(target, str) else "all"',
    '        if raw_target not in ("all", "bug", "badcase", "testcase", "card", "plan"):',
    '            raw_target = "all"',
    '        print(',
    '            f"[GREP] 🔍 开始定位 (keywords={keywords}, target={raw_target}, status={status}, plan_id={plan_id})"',
    '        )',
]
try:
    ai = lines.index(anchor)
except ValueError:
    raise SystemExit("print anchor missing")
lines[ai : ai + 1] = new_lines_kw

# --- insert plan block after phase1_plan_ready ---
needle = '                    _progress(grep_tool_progress("phase1_plan_ready", loc))'
try:
    pi = lines.index(needle)
except ValueError:
    raise SystemExit("phase1_plan_ready missing")

plan_insert = [
    "",
    "                    skip_rest_of_locate = False",
    '                    if raw_target == "plan":',
    "                        plan_records_tree = None",
    "                        if plan_id:",
    '                            _progress(grep_tool_progress("plan_material_read", loc))',
    "                            plan_records_tree = await self._build_plan_records_tree(",
    "                                project_id=project_id,",
    "                                root_plan_id=plan_id,",
    "                                progress_callback=progress_callback,",
    "                                ui_locale=loc,",
    "                            )",
    '                            _progress(grep_tool_progress("plan_material_ready", loc))',
    "                        plan_location = self._get_plan_entity_list(project_id, keywords, plan_id)",
    "                        en = is_english_locale(loc)",
    "                        if not plan_location:",
    '                            summary_plan = ("📅 No matching iteration plans." if en else "📅 未找到匹配的迭代计划。")',
    "                        else:",
    '                            summary_plan = (',
    '                                f"📅 Found {len(plan_location)} iteration plan(s)."',
    "                                if en",
    '                                else f"📅 找到 {len(plan_location)} 个迭代计划（target=plan）。"',
    "                            )",
    "                        plan_attr = [",
    '                            {"id": x["id"], "name": x.get("name"), "plan_id": x["id"]}',
    "                            for x in plan_location",
    "                        ]",
    "                        navigation_list = self._build_grep_navigation_items(",
    "                            plan_tree,",
    '                            "plan",',
    "                            [],",
    "                            [],",
    "                            [],",
    "                            [],",
    "                            scope_plan_id=plan_id,",
    "                            plan_entity_list=plan_location,",
    "                        )",
    "                        navigation = (",
    '                            {"type": "multiple", "items": navigation_list}',
    "                            if navigation_list",
    "                            else None",
    "                        )",
    "                        if navigation_list:",
    '                            _progress(grep_tool_progress("nav_build", loc))',
    "                            print(",
    '                                f"[GREP] ✅ 计划实体检索: n={len(plan_location)} nav={len(navigation_list)}"',
    "                            )",
    '                        result["data"] = {',
    '                            "plan_tree": plan_tree,',
    '                            "plan_records_tree": plan_records_tree,',
    '                            "plan_location": plan_location,',
    '                            "badcase_analysis": [],',
    '                            "bug_location": [],',
    '                            "testcase_location": [],',
    '                            "card_location": [],',
    '                            "plan_attribution": plan_attr,',
    '                            "comparison_report": "",',
    '                            "summary": summary_plan,',
    '                            "navigation": navigation,',
    "                        }",
    "                        skip_rest_of_locate = True",
    "                    if not skip_rest_of_locate:",
]

lines[pi + 1 : pi + 1] = plan_insert

# --- indent non-plan block: from '# 人类阅读模式' through closing brace before blank line before elif associate ---
start_mark = "                    # 人类阅读模式：如果指定了 plan_id，则返回该计划及其子计划的树形结构，并挂载各计划下的记录（从上到下、从外到里）"
try:
    si = lines.index(start_mark)
except ValueError:
    raise SystemExit("human read comment missing")

# find end: line that is exactly '                    }' followed eventually by '                elif mode == "associate":'
ei = None
for j in range(si, len(lines) - 2):
    if lines[j].strip() == "}" and lines[j].startswith("                    ") and lines[j + 1].strip() == "":
        if j + 2 < len(lines) and 'elif mode == "associate"' in lines[j + 2]:
            ei = j
            break
if ei is None:
    raise SystemExit("end brace before associate not found")

for j in range(si, ei + 1):
    lines[j] = "    " + lines[j]

# --- target -> raw_target in indented segment ---
for j in range(si, ei + 1):
    lines[j] = lines[j].replace(" if target in ", " if raw_target in ")
    lines[j] = lines[j].replace(" if target in(", " if raw_target in(")
    lines[j] = lines[j].replace("target in ('all',", "raw_target in ('all',")
    lines[j] = lines[j].replace(
        "grep_tool: grep_target={target!r}", "grep_tool: grep_target={raw_target!r}"
    )
lines[lines.index(start_mark) - 1] = lines[lines.index(start_mark) - 1].replace(
    "                    if not skip_rest_of_locate:",
    "                    if not skip_rest_of_locate:",
)

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("OK patched", path, "lines", len(lines))
