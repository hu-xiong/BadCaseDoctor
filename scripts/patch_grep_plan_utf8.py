# -*- coding: utf-8 -*-
"""Apply grep_tool plan-entity + raw_target patch (run from repo root)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "agents" / "tools" / "grep_tool.py"
text = path.read_text(encoding="utf-8")

old_p = (
    '        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target}, status={status}, plan_id={plan_id})")'
)
new_p = """        raw_target = (target or "all").strip().lower() if isinstance(target, str) else "all"
        if raw_target not in ("all", "bug", "badcase", "testcase", "card", "plan"):
            raw_target = "all"
        print(
            f"[GREP] 🔍 开始定位 (keywords={keywords}, target={raw_target}, status={status}, plan_id={plan_id})"
        )"""
if old_p not in text:
    raise SystemExit("print block not found")
text = text.replace(old_p, new_p, 1)

old_i = """from agents.locale_prompts import (
    normalize_locale,
    grep_tool_progress,"""
new_i = """from agents.locale_prompts import (
    normalize_locale,
    is_english_locale,
    grep_tool_progress,"""
if old_i not in text:
    raise SystemExit("import block not found")
text = text.replace(old_i, new_i, 1)

tail_marker = '\n                elif mode == "associate":'
ei = text.index(tail_marker)
hi = text.index("                    # 人类阅读模式")
chunk = text[hi:ei]
ind_lines = []
for ln in chunk.splitlines():
    if ln.strip():
        ind_lines.append("    " + ln)
    else:
        ind_lines.append("")
indented = "\n".join(ind_lines) + "\n"

plan_blob = """                    _progress(grep_tool_progress("phase1_plan_ready", loc))

                    if raw_target == "plan":
                        plan_records_tree = None
                        if plan_id:
                            _progress(grep_tool_progress("plan_material_read", loc))
                            plan_records_tree = await self._build_plan_records_tree(
                                project_id=project_id,
                                root_plan_id=plan_id,
                                progress_callback=progress_callback,
                                ui_locale=loc,
                            )
                            _progress(grep_tool_progress("plan_material_ready", loc))
                        plan_location = self._get_plan_entity_list(project_id, keywords, plan_id)
                        en = is_english_locale(loc)
                        if not plan_location:
                            summary_plan = (
                                "📅 No matching iteration plans." if en else "📅 未找到匹配的迭代计划。"
                            )
                        else:
                            summary_plan = (
                                f"📅 Found {len(plan_location)} iteration plan(s)."
                                if en
                                else f"📅 找到 {len(plan_location)} 个迭代计划（target=plan）。"
                            )
                        plan_attr = [
                            {"id": x["id"], "name": x.get("name"), "plan_id": x["id"]}
                            for x in plan_location
                        ]
                        navigation_list = self._build_grep_navigation_items(
                            plan_tree,
                            "plan",
                            [],
                            [],
                            [],
                            [],
                            scope_plan_id=plan_id,
                            plan_entity_list=plan_location,
                        )
                        navigation = (
                            {"type": "multiple", "items": navigation_list}
                            if navigation_list
                            else None
                        )
                        if navigation_list:
                            _progress(grep_tool_progress("nav_build", loc))
                            print(
                                f"[GREP] ✅ 计划实体检索: n={len(plan_location)} nav={len(navigation_list)}"
                            )
                        result["data"] = {
                            "plan_tree": plan_tree,
                            "plan_records_tree": plan_records_tree,
                            "plan_location": plan_location,
                            "badcase_analysis": [],
                            "bug_location": [],
                            "testcase_location": [],
                            "card_location": [],
                            "plan_attribution": plan_attr,
                            "comparison_report": "",
                            "summary": summary_plan,
                            "navigation": navigation,
                        }
                    else:
"""

text = text[:hi] + plan_blob + indented + text[ei:]

# Only inside else-branch: target→raw_target for entity routing (narrow replace)
seg_start = text.index("                    else:\n") + len("                    else:\n")
seg_end = text.index(tail_marker)
segment = text[seg_start:seg_end]
segment = segment.replace(" if target in ", " if raw_target in ")
segment = segment.replace(" if target in(", " if raw_target in(")
segment = segment.replace(
    "grep_tool: grep_target={target!r}", "grep_tool: grep_target={raw_target!r}"
)
text = text[:seg_start] + segment + text[seg_end:]

path.write_text(text, encoding="utf-8")
print("patched", path)
