# -*- coding: utf-8 -*-
"""删除指定项目中 plan_id 为空且标题包含关键词的 Bug（及同源 Card）。用法：
   python scripts/delete_unplanned_bugs_by_title.py [project_id] [标题关键词]
   默认：project_id=1，关键词=归档计划
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app, db  # noqa: E402
from app import Bug, Card  # noqa: E402


def main() -> None:
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    substr = sys.argv[2] if len(sys.argv) > 2 else '归档计划'

    with app.app_context():
        bugs = (
            Bug.query.filter(
                Bug.project_id == project_id,
                Bug.plan_id.is_(None),
                Bug.title.like(f'%{substr}%'),
            )
            .all()
        )
        if not bugs:
            print(f'未找到 project_id={project_id}、plan_id IS NULL、标题含「{substr}」的 Bug')
            return
        for b in bugs:
            print(f'删除 Bug id={b.id} title={b.title!r}')
            cards = Card.query.filter(
                Card.source_type == 'bug',
                Card.source_id == b.id,
            ).all()
            for c in cards:
                print(f'  删除同源 Card id={c.id}')
                db.session.delete(c)
            db.session.delete(b)
        db.session.commit()
        print(f'完成，共删除 {len(bugs)} 条 Bug')


if __name__ == '__main__':
    main()
