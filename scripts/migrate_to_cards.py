#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据迁移脚本 - 将Bug、BadCase、TestCase迁移到Card表

使用方法:
    python migrate_to_cards.py [--dry-run] [--project-id PROJECT_ID]

参数:
    --dry-run: 仅预览迁移结果，不执行实际迁移
    --project-id: 仅迁移指定项目的卡片

注意: 建议在运行前备份数据库！
"""

import sys
import argparse
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, '.')

from app import app, db
from app import BadCase, Bug, TestCase, Card, CardType, CardStatus, CardPlanRelation


def get_badcase_status_mapping():
    """BadCase状态映射到CardStatus"""
    return {
        'new': CardStatus.OPEN,
        'assigned': CardStatus.IN_PROGRESS,
        'in_progress': CardStatus.IN_PROGRESS,
        'resolved': CardStatus.RESOLVED,
        'closed': CardStatus.CLOSED,
        'reopened': CardStatus.REOPENED,
    }


def get_bug_status_mapping():
    """Bug状态映射"""
    return {
        'new': CardStatus.OPEN,
        'assigned': CardStatus.IN_PROGRESS,
        'in_progress': CardStatus.IN_PROGRESS,
        'resolved': CardStatus.RESOLVED,
        'closed': CardStatus.CLOSED,
        'reopened': CardStatus.REOPENED,
    }


def get_testcase_status_mapping():
    """TestCase状态映射"""
    return {
        'draft': CardStatus.DRAFT,
        'review': CardStatus.REVIEW,
        'published': CardStatus.PUBLISHED,
        'deprecated': CardStatus.DEPRECATED,
    }


def migrate_badcases(project_id=None, dry_run=True):
    """迁移BadCase数据到Card表"""
    print("\n" + "=" * 50)
    print("迁移 BadCase 数据...")
    print("=" * 50)
    
    query = BadCase.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    
    badcases = query.all()
    print(f"找到 {len(badcases)} 条 BadCase 记录")
    
    status_mapping = get_badcase_status_mapping()
    migrated_count = 0
    skipped_count = 0
    
    for bc in badcases:
        # 检查是否已存在对应卡片
        existing = Card.query.filter_by(
            source_type='bad_case',
            source_id=bc.id,
            project_id=bc.project_id
        ).first()
        
        if existing:
            print(f"  跳过: BadCase #{bc.id} - 已迁移")
            skipped_count += 1
            continue
        
        # 映射状态
        bc_status = bc.status.value if hasattr(bc.status, 'value') else bc.status
        card_status = status_mapping.get(bc_status, CardStatus.OPEN)
        
        # 查找负责人ID
        assignee_id = None
        if bc.assignee:
            from app import User
            user = User.query.filter_by(name=bc.assignee).first()
            if user:
                assignee_id = user.id
        
        card = Card(
            title=bc.title or bc.base_problem[:100] if bc.base_problem else f"BadCase-{bc.id}",
            type=CardType.BADCASE,
            status=card_status,
            priority=bc.priority,
            assignee_id=assignee_id,
            project_id=bc.project_id,
            creator_id=bc.creator_id,
            plan_id=bc.plan_id,
            description=bc.base_problem,
            
            # BadCase特有字段
            case_category=bc.case_category,
            base_problem=bc.base_problem,
            reproduction_steps=bc.reproduction_steps,
            badcase_result=bc.badcase_result,
            answer=bc.answer,
            correct_answer=bc.correct_answer,
            problem_reason=bc.problem_reason,
            solution=bc.solution,
            
            created_at=bc.created_at,
            updated_at=bc.updated_at
        )
        
        # 保存源表信息用于追溯
        card.source_type = 'bad_case'
        card.source_id = bc.id
        
        if not dry_run:
            db.session.add(card)
            db.session.flush()  # 获取card.id
            
            # 创建关联关系
            if bc.plan_id:
                relation = CardPlanRelation(
                    card_id=card.id,
                    plan_id=bc.plan_id,
                    relation_type='primary',
                    status_in_plan=bc_status
                )
                db.session.add(relation)
        
        print(f"  {'[预览]':<8} BadCase #{bc.id} -> Card(title={card.title[:30]}...)")
        migrated_count += 1
    
    if not dry_run:
        try:
            db.session.commit()
            print(f"\n✅ BadCase 迁移完成！成功迁移 {migrated_count} 条记录")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 迁移失败: {e}")
    else:
        print(f"\n[预览模式] 将迁移 {migrated_count} 条记录，跳过 {skipped_count} 条已迁移记录")
    
    return migrated_count, skipped_count


def migrate_bugs(project_id=None, dry_run=True):
    """迁移Bug数据到Card表"""
    print("\n" + "=" * 50)
    print("迁移 Bug 数据...")
    print("=" * 50)
    
    query = Bug.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    
    bugs = query.all()
    print(f"找到 {len(bugs)} 条 Bug 记录")
    
    status_mapping = get_bug_status_mapping()
    migrated_count = 0
    skipped_count = 0
    
    for bug in bugs:
        # 检查是否已存在对应卡片
        existing = Card.query.filter_by(
            source_type='bug',
            source_id=bug.id,
            project_id=bug.project_id
        ).first()
        
        if existing:
            print(f"  跳过: Bug #{bug.id} - 已迁移")
            skipped_count += 1
            continue
        
        # 映射状态
        bug_status = bug.status or 'new'
        card_status = status_mapping.get(bug_status, CardStatus.OPEN)
        
        card = Card(
            title=bug.title,
            type=CardType.BUG,
            status=card_status,
            priority=bug.priority,
            assignee_id=bug.assignee_id,
            project_id=bug.project_id,
            creator_id=bug.creator_id,
            plan_id=bug.plan_id,
            description=None,
            
            # Bug特有字段
            severity=bug.severity,
            steps_to_reproduce=bug.steps_to_reproduce,
            expected_result=bug.expected_result,
            actual_result=bug.actual_result,
            bug_type=bug.bug_type,
            environment=bug.environment,
            browser=bug.browser,
            os=bug.os,
            
            created_at=bug.created_at,
            updated_at=bug.updated_at
        )
        
        card.source_type = 'bug'
        card.source_id = bug.id
        
        if not dry_run:
            db.session.add(card)
            db.session.flush()
            
            # 创建关联关系
            if bug.plan_id:
                relation = CardPlanRelation(
                    card_id=card.id,
                    plan_id=bug.plan_id,
                    relation_type='primary',
                    status_in_plan=bug_status
                )
                db.session.add(relation)
        
        print(f"  {'[预览]':<8} Bug #{bug.id} -> Card(title={card.title[:30]}...)")
        migrated_count += 1
    
    if not dry_run:
        try:
            db.session.commit()
            print(f"\n✅ Bug 迁移完成！成功迁移 {migrated_count} 条记录")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 迁移失败: {e}")
    else:
        print(f"\n[预览模式] 将迁移 {migrated_count} 条记录，跳过 {skipped_count} 条已迁移记录")
    
    return migrated_count, skipped_count


def migrate_testcases(project_id=None, dry_run=True):
    """迁移TestCase数据到Card表"""
    print("\n" + "=" * 50)
    print("迁移 TestCase 数据...")
    print("=" * 50)
    
    query = TestCase.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    
    testcases = query.all()
    print(f"找到 {len(testcases)} 条 TestCase 记录")
    
    status_mapping = get_testcase_status_mapping()
    migrated_count = 0
    skipped_count = 0
    
    for tc in testcases:
        # 检查是否已存在对应卡片
        existing = Card.query.filter_by(
            source_type='test_case',
            source_id=tc.id,
            project_id=tc.project_id
        ).first()
        
        if existing:
            print(f"  跳过: TestCase #{tc.id} - 已迁移")
            skipped_count += 1
            continue
        
        # 映射状态
        tc_status = tc.status.value if hasattr(tc.status, 'value') else tc.status
        card_status = status_mapping.get(tc_status, CardStatus.DRAFT)
        
        card = Card(
            title=tc.title,
            type=CardType.TESTCASE,
            status=card_status,
            priority=tc.priority,
            assignee_id=tc.assignee_id,
            project_id=tc.project_id,
            creator_id=tc.creator_id,
            plan_id=tc.plan_id,
            
            # TestCase特有字段
            case_type_test=tc.case_type,
            test_type=tc.test_type,
            preconditions=tc.preconditions,
            steps=tc.steps,
            remark=tc.remark,
            requirement_id=tc.requirement_id,
            related_defects=tc.related_defects,
            last_executed=tc.last_executed,
            executed_by=tc.executed_by,
            execution_result=tc.execution_result,
            baseline=tc.baseline,
            estimated_time=tc.estimated_time,
            actual_time=tc.actual_time,
            remaining_time=tc.remaining_time,
            version=tc.version,
            
            created_at=tc.created_at,
            updated_at=tc.updated_at
        )
        
        card.source_type = 'test_case'
        card.source_id = tc.id
        
        if not dry_run:
            db.session.add(card)
            db.session.flush()
            
            # 创建关联关系
            if tc.plan_id:
                relation = CardPlanRelation(
                    card_id=card.id,
                    plan_id=tc.plan_id,
                    relation_type='primary',
                    status_in_plan=tc_status
                )
                db.session.add(relation)
        
        print(f"  {'[预览]':<8} TestCase #{tc.id} -> Card(title={card.title[:30]}...)")
        migrated_count += 1
    
    if not dry_run:
        try:
            db.session.commit()
            print(f"\n✅ TestCase 迁移完成！成功迁移 {migrated_count} 条记录")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 迁移失败: {e}")
    else:
        print(f"\n[预览模式] 将迁移 {migrated_count} 条记录，跳过 {skipped_count} 条已迁移记录")
    
    return migrated_count, skipped_count


def check_migration_status():
    """检查迁移状态"""
    print("\n" + "=" * 50)
    print("迁移状态检查")
    print("=" * 50)
    
    # 检查Card表中的记录数
    total_cards = Card.query.count()
    badcase_cards = Card.query.filter_by(type=CardType.BADCASE).count()
    bug_cards = Card.query.filter_by(type=CardType.BUG).count()
    testcase_cards = Card.query.filter_by(type=CardType.TESTCASE).count()
    
    print(f"Card 表统计:")
    print(f"  - 总记录数: {total_cards}")
    print(f"  - BadCase卡片: {badcase_cards}")
    print(f"  - Bug卡片: {bug_cards}")
    print(f"  - TestCase卡片: {testcase_cards}")
    
    # 源表统计
    print(f"\n源表统计 (原始数据):")
    print(f"  - BadCase: {BadCase.query.count()}")
    print(f"  - Bug: {Bug.query.count()}")
    print(f"  - TestCase: {TestCase.query.count()}")
    
    # 迁移进度
    total_source = BadCase.query.count() + Bug.query.count() + TestCase.query.count()
    total_migrated = badcase_cards + bug_cards + testcase_cards
    
    if total_source > 0:
        progress = (total_migrated / total_source) * 100
        print(f"\n迁移进度: {total_migrated}/{total_source} ({progress:.1f}%)")
    
    return total_cards


def rollback_migration(project_id=None, dry_run=True):
    """回滚迁移 - 删除已创建的Card记录"""
    print("\n" + "=" * 50)
    print("回滚迁移 (删除Card表中的迁移记录)")
    print("=" * 50)
    
    query = Card.query.filter(Card.source_type.isnot(None))
    if project_id:
        query = query.filter_by(project_id=project_id)
    
    cards = query.all()
    print(f"找到 {len(cards)} 条迁移的Card记录")
    
    deleted_count = 0
    for card in cards:
        # 先删除关联关系
        if not dry_run:
            CardPlanRelation.query.filter_by(card_id=card.id).delete()
            db.session.delete(card)
        print(f"  {'[预览]':<8} 删除 Card #{card.id} (source: {card.source_type}#{card.source_id})")
        deleted_count += 1
    
    if not dry_run:
        try:
            db.session.commit()
            print(f"\n✅ 回滚完成！删除 {deleted_count} 条记录")
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ 回滚失败: {e}")
    else:
        print(f"\n[预览模式] 将删除 {deleted_count} 条记录")
    
    return deleted_count


def main():
    parser = argparse.ArgumentParser(description='迁移数据到Card表')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不执行实际迁移')
    parser.add_argument('--project-id', type=int, help='仅迁移指定项目')
    parser.add_argument('--rollback', action='store_true', help='回滚迁移')
    parser.add_argument('--status', action='store_true', help='查看迁移状态')
    
    args = parser.parse_args()
    
    with app.app_context():
        if args.status:
            check_migration_status()
            return
        
        if args.rollback:
            rollback_migration(args.project_id, args.dry_run)
            return
        
        print("=" * 60)
        print("数据迁移脚本 - Bug/BadCase/TestCase -> Card")
        print("=" * 60)
        
        if args.dry_run:
            print("\n⚠️  [预览模式] 不会执行实际迁移")
        else:
            print("\n⚠️  [执行模式] 即将执行实际迁移操作")
        
        if args.project_id:
            print(f"📌 仅迁移项目 ID: {args.project_id}")
        
        # 执行迁移
        total_migrated = 0
        total_skipped = 0
        
        bc_migrated, bc_skipped = migrate_badcases(args.project_id, args.dry_run)
        total_migrated += bc_migrated
        total_skipped += bc_skipped
        
        bug_migrated, bug_skipped = migrate_bugs(args.project_id, args.dry_run)
        total_migrated += bug_migrated
        total_skipped += bug_skipped
        
        tc_migrated, tc_skipped = migrate_testcases(args.project_id, args.dry_run)
        total_migrated += tc_migrated
        total_skipped += tc_skipped
        
        print("\n" + "=" * 60)
        print("迁移汇总")
        print("=" * 60)
        print(f"新增迁移: {total_migrated} 条")
        print(f"跳过(已迁移): {total_skipped} 条")
        
        if not args.dry_run:
            check_migration_status()
            print("\n✅ 迁移完成！")
            print("\n提示: 如需回滚，请运行:")
            print(f"  python migrate_to_cards.py --rollback --project-id {args.project_id or 'ALL'}")
        else:
            print("\n如需执行迁移，请移除 --dry-run 参数")
            print(f"  python migrate_to_cards.py --project-id {args.project_id or ''}")


if __name__ == '__main__':
    main()
