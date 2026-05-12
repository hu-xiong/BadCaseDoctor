# One-off: grep_tool plan entity search + raw_target (no broken else-indent)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "agents" / "tools" / "grep_tool.py"
text = path.read_text(encoding="utf-8")

old_kw = '''        if keywords is not None and not isinstance(keywords, str):
            if isinstance(keywords, (list, tuple)):
                keywords = " ".join(
                    str(x).strip() for x in keywords if x is not None and str(x).strip()
                )
            else:
                keywords = str(keywords).strip() or None
        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target}, status={status}, plan_id={plan_id})")
'''

new_kw = '''        if keywords is not None and not isinstance(keywords, str):
            if isinstance(keywords, (list, tuple)):
                keywords = " ".join(
                    str(x).strip() for x in keywords if x is not None and str(x).strip()
                )
            else:
                keywords = str(keywords).strip() or None
        raw_target = (target or "all").strip().lower() if isinstance(target, str) else "all"
        if raw_target not in ("all", "bug", "badcase", "testcase", "card", "plan"):
            raw_target = "all"
        print(
            f"[GREP] 🔍 开始定位 (keywords={keywords}, target={raw_target}, status={status}, plan_id={plan_id})"
        )
'''

if old_kw not in text:
    raise SystemExit("anchor keywords not found")
text = text.replace(old_kw, new_kw, 1)

locate_old = '''                if mode == "locate":
                    # 【阶段1】数据库查询（支持 plan_id 限定当前迭代，关键词拆分模糊匹配）
                    _progress(grep_tool_progress("phase1_plan_tree", loc))
                    plan_tree = await self._get_plan_tree(project_id)
                    _progress(grep_tool_progress("phase1_plan_ready", loc))

                    # 人类阅读模式：如果指定了 plan_id，则返回该计划及其子计划的树形结构，并挂载各计划下的记录（从上到下、从外到里）
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
                    
                    badcase_list = []
'''

locate_new = '''                if mode == "locate":
                    # 【阶段1】数据库查询（支持 plan_id 限定当前迭代，关键词拆分模糊匹配）
                    _progress(grep_tool_progress("phase1_plan_tree", loc))
                    plan_tree = await self._get_plan_tree(project_id)
                    _progress(grep_tool_progress("phase1_plan_ready", loc))

                    _grep_plan_entity_only = raw_target == "plan"
                    if _grep_plan_entity_only:
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
                                "📅 No matching iteration plans."
                                if en
                                else "📅 未找到匹配的迭代计划。"
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
                    if not _grep_plan_entity_only:
                    # 人类阅读模式：如果指定了 plan_id，则返回该计划及其子计划的树形结构，并挂载各计划下的记录（从上到下、从外到里）
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
                    
                    badcase_list = []
'''

if locate_old not in text:
    raise SystemExit("locate anchor not found")
text = text.replace(locate_old, locate_new, 1)

# Indent entire non-plan block under `if not _grep_plan_entity_only:` — must add 4 spaces to lines until result['data'] closes (exclusive)
lines = text.splitlines()
out = []
i = 0
while i < len(lines):
    line = lines[i]
    out.append(line)
    if line.strip() == "if not _grep_plan_entity_only:":
        i += 1
        while i < len(lines):
            ln = lines[i]
            # stop before result['data'] that belongs to non-plan branch — it's still inside if not plan
            if ln.strip().startswith("result['data'] = {") and i > 0 and "badcase_analysis" in lines[i + 1]:
                # indent this whole result assignment block until closing }; heuristic: until line that is `}` at col matching
                chunk = []
                depth = 0
                started = False
                while i < len(lines):
                    l2 = lines[i]
                    if "result['data']" in l2:
                        started = True
                    if started:
                        chunk.append("    " + l2)
                        if "{" in l2:
                            depth += l2.count("{") - l2.count("}")
                        elif "}" in l2:
                            depth -= l2.count("}") - l2.count("{")
                        i += 1
                        if started and l2.strip() == "}" and depth <= 0:
                            break
                    else:
                        i += 1
                out.extend(chunk)
                break
            # indent normal lines under if not _grep_plan_entity_only until we hit result['data']
            if ln.strip().startswith("result['data']"):
                break
            out.append("    " + ln)
            i += 1
        continue
    i += 1

text = "\n".join(out) + "\n"
