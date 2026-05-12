# -*- coding: utf-8 -*-
"""一次性补丁：grep_tool 支持 target=plan（Plan 表检索）+ raw_target。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "agents" / "tools" / "grep_tool.py"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    old_print = (
        '        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target}, status={status}, plan_id={plan_id})")'
    )
    new_print = """        raw_target = (target or "all").strip().lower() if isinstance(target, str) else "all"
        if raw_target not in ("all", "bug", "badcase", "testcase", "card", "plan"):
            raw_target = "all"
        print(
            f"[GREP] 🔍 开始定位 (keywords={keywords}, target={raw_target}, status={status}, plan_id={plan_id})"
        )"""
    if old_print not in text:
        raise SystemExit("already patched or print line mismatch")
    text = text.replace(old_print, new_print, 1)

    old_imp = """from agents.locale_prompts import (
    normalize_locale,
    grep_tool_progress,"""
    new_imp = """from agents.locale_prompts import (
    normalize_locale,
    is_english_locale,
    grep_tool_progress,"""
    if old_imp not in text:
        raise SystemExit("import mismatch")
    text = text.replace(old_imp, new_imp, 1)

    anchor_ready = '                    _progress(grep_tool_progress("phase1_plan_ready", loc))\n'
    idx_ready = text.index(anchor_ready) + len(anchor_ready)

    tail_assoc = '\n                elif mode == "associate":'
    hi = text.index("                    # 人类阅读模式：如果指定了 plan_id")
    ei = text.index(tail_assoc)

    legacy = text[hi:ei]
    # else 分支：整块相对原来的 locate 体多缩进一级（4 空格）
    indented = "\n".join(("    " + ln if ln.strip() else ln) for ln in legacy.splitlines())
    if not indented.endswith("\n"):
        indented += "\n"

    plan_if = """                    if raw_target == "plan":
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
                    else:
"""

    seg_after = indented.replace(" if target in ", " if raw_target in ").replace(
        " if target in(", " if raw_target in("
    )
    seg_after = seg_after.replace(
        "grep_tool: grep_target={target!r}", "grep_tool: grep_target={raw_target!r}"
    )
    seg_after = re.sub(
        r"(plan_tree,\s*\n\s+)target(,)",
        r"\1raw_target\2",
        seg_after,
        count=1,
    )

    text = text[:idx_ready] + "\n" + plan_if + seg_after + text[ei:]

    method_chunk = '''

    def _get_plan_entity_list(
        self,
        project_id: Any,
        keywords: Optional[str],
        scope_plan_id: Any = None,
    ) -> List[Dict[str, Any]]:
        """检索迭代计划 Plan 表；scope_plan_id 有值时仅 root 及其子孙计划。"""
        from app import db, Plan

        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            return []
        rows = db.session.query(Plan).filter(Plan.project_id == pid).all()
        candidates = list(rows)
        if scope_plan_id not in (None, "", "0"):
            try:
                root = int(scope_plan_id)
            except (TypeError, ValueError):
                root = None
            else:
                children_map: Dict[Any, List[int]] = {}
                for p in rows:
                    children_map.setdefault(p.parent_id, []).append(p.id)
                allowed = {root}
                stack = [root]
                while stack:
                    cur = stack.pop()
                    for cid in children_map.get(cur, []):
                        if cid not in allowed:
                            allowed.add(cid)
                            stack.append(cid)
                candidates = [p for p in rows if p.id in allowed]

        kw_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_all = not kw_list and (
            not keywords or str(keywords).strip() in ("", "*")
        )
        if not is_all and kw_list:
            filtered = []
            for p in candidates:
                hay = f"{p.name or ''} {(p.description or '')}"
                if self._text_matches_normalized_keywords(hay, keywords):
                    filtered.append(p)
            candidates = filtered
        elif not is_all and keywords and str(keywords).strip():
            k = str(keywords).strip().lower()
            candidates = [
                p
                for p in candidates
                if (p.name and k in (p.name or "").lower())
                or (p.description and k in (p.description or "").lower())
            ]

        candidates.sort(
            key=lambda x: (x.updated_at or x.created_at or x.id),
            reverse=True,
        )
        out: List[Dict[str, Any]] = []
        for p in candidates[:80]:
            out.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "title": p.name,
                    "description": (p.description or "")[:800],
                    "status": p.status,
                    "priority": p.priority,
                    "project_id": p.project_id,
                    "parent_id": p.parent_id,
                    "plan_id": p.id,
                    "is_default": getattr(p, "is_default", False),
                }
            )
        return out
'''

    insert_at = text.index("    async def _build_plan_records_tree(")
    text = text[:insert_at] + method_chunk + text[insert_at:]

    desc_old = (
        '"target(bug/badcase/testcase/card/all；card=仅查卡片层 Card 表标题与描述；all=四类均检索)，status，plan_id(当前迭代计划ID)，card_id(可选)。"'
    )
    desc_new = (
        '"target(bug/badcase/testcase/card/plan/all；card=仅查 Card；plan=仅查迭代计划 Plan；all=多类)，status，plan_id(当前迭代)，card_id(可选)。"'
    )
    if desc_old in text:
        text = text.replace(desc_old, desc_new, 1)

    PATH.write_text(text, encoding="utf-8")
    print("grep_tool.py patched OK")


if __name__ == "__main__":
    main()
