"""清理 diff_review_state 中 target_id 对应的实体已不存在的孤立记录。"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['FLASK_ENV'] = 'development'

# 必须先设置环境变量再导入 app，否则可能读到默认 .env
from app import app, db, DiffReviewState, BadCase, Bug, TestCase

with app.app_context():
    rows = DiffReviewState.query.filter(DiffReviewState.status == 'pending').all()
    total = len(rows)
    orphaned = []
    for r in rows:
        if r.target == 'badcase':
            exists = BadCase.query.get(r.target_id) is not None
        elif r.target == 'bug':
            exists = Bug.query.get(r.target_id) is not None
        elif r.target == 'testcase':
            exists = TestCase.query.get(r.target_id) is not None
        else:
            exists = True  # 未知类型不处理
        if not exists:
            orphaned.append(r)

    print(f'pending 总数: {total}')
    print(f'孤立记录数: {len(orphaned)}')

    if orphaned:
        print('\n孤立记录:')
        for r in orphaned:
            print(f'  id={r.id} target={r.target} target_id={r.target_id} project_id={r.project_id}')
        confirm = input(f'\n是否将以上 {len(orphaned)} 条孤立记录标记为 rejected? (y/N): ')
        if confirm.strip().lower() == 'y':
            now = datetime.utcnow()
            for r in orphaned:
                r.status = 'rejected'
                r.rejected_at = now
            db.session.commit()
            print(f'已标记 {len(orphaned)} 条记录为 rejected')
        else:
            print('已取消')
    else:
        print('没有孤立记录需要清理')
