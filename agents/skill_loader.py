"""
Skill 动态加载器
从配置文件加载和管理技能
"""

import os
import yaml
import json
import fnmatch
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from .skill import Skill, SkillTrigger


class SkillLoader:
    """Skill 动态加载器"""
    
    def __init__(self, skill_dir: str = ".qoder/skills"):
        """
        初始化技能加载器
        
        Args:
            skill_dir: 技能配置文件目录，支持绝对路径或相对路径
        """
        # 标准化路径
        if os.path.isabs(skill_dir):
            self.skill_dir = skill_dir
        else:
            self.skill_dir = os.path.join(os.getcwd(), skill_dir)
        
        self.skills: Dict[str, Skill] = {}
        self.skill_files: Dict[str, str] = {}  # skill_name -> file_path
        self.last_reload_time: Optional[datetime] = None
        print(f"[SKILL_LOADER] 技能目录: {self.skill_dir}")
    
    def load_all(self, force_reload: bool = False) -> Dict[str, Skill]:
        """
        加载所有技能配置文件
        
        Args:
            force_reload: 是否强制重新加载，即使没有文件变化
            
        Returns:
            技能字典 {skill_name: Skill}
        """
        if not self.skill_dir or not os.path.exists(self.skill_dir):
            print(f"[SKILL_LOADER] 技能目录不存在: {self.skill_dir}")
            return {}
        
        # 检查是否需要重新加载（按文件修改时间）
        if not force_reload and self.last_reload_time:
            latest_mtime = self._get_latest_modification_time()
            if latest_mtime <= self.last_reload_time:
                print(f"[SKILL_LOADER] 技能文件无变化，使用缓存")
                return self.skills
        
        print(f"[SKILL_LOADER] 扫描技能文件...")
        new_skills = {}
        new_skill_files = {}
        loaded_count = 0
        error_count = 0
        
        # 支持递归扫描子目录
        for root, dirs, files in os.walk(self.skill_dir):
            for file in files:
                if file.endswith(('.yaml', '.yml', '.json')):
                    file_path = os.path.join(root, file)
                    skill = self._load_skill_from_file(file_path)
                    if skill:
                        new_skills[skill.name] = skill
                        new_skill_files[skill.name] = file_path
                        loaded_count += 1
                        print(f"[SKILL_LOADER] 加载技能: {skill.name} ({file})")
                    else:
                        error_count += 1
                        print(f"[SKILL_LOADER] 加载失败: {file_path}")
        
        # 更新内部状态
        self.skills = new_skills
        self.skill_files = new_skill_files
        self.last_reload_time = datetime.now()
        
        print(f"[SKILL_LOADER] 加载完成: {loaded_count} 个技能，{error_count} 个失败")
        return self.skills
    
    def _load_skill_from_file(self, file_path: str) -> Optional[Skill]:
        """从单个文件加载技能"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if file_path.endswith('.json'):
                skill = Skill.from_json(content)
            else:
                # YAML文件
                skill = Skill.from_yaml(content)
            
            return skill
        except Exception as e:
            print(f"[SKILL_LOADER] 加载失败 {file_path}: {str(e)}")
            return None
    
    def _get_latest_modification_time(self) -> Optional[datetime]:
        """获取技能目录中最新的文件修改时间"""
        latest_time = None
        
        for root, dirs, files in os.walk(self.skill_dir):
            for file in files:
                if file.endswith(('.yaml', '.yml', '.json')):
                    file_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(file_path)
                        mtime_dt = datetime.fromtimestamp(mtime)
                        if not latest_time or mtime_dt > latest_time:
                            latest_time = mtime_dt
                    except:
                        continue
        
        return latest_time
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """获取指定名称的技能"""
        # 如果技能未加载，尝试加载
        if skill_name not in self.skills:
            self.load_all()
        
        return self.skills.get(skill_name)
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能"""
        if not self.skills:
            self.load_all()
        
        return [
            {
                'name': skill.name,
                'description': skill.description,
                'tools': skill.get_tool_names(),
                'trigger_intents': skill.trigger.intents,
                'trigger_entities': skill.trigger.entities
            }
            for skill in self.skills.values()
        ]

    def build_skills_catalog_for_prompt(
        self,
        *,
        max_skills: int = 20,
        desc_chars: int = 220,
    ) -> str:
        """供统一流 LLM 在 thinking 中自选 workflow；不做关键词硬匹配。"""
        if not self.skills:
            self.load_all()
        try:
            max_skills = max(1, min(int(max_skills), 32))
        except (TypeError, ValueError):
            max_skills = 20
        try:
            desc_chars = max(60, min(int(desc_chars), 400))
        except (TypeError, ValueError):
            desc_chars = 220

        rows: List[str] = []
        for skill in sorted(self.skills.values(), key=lambda s: str(s.name or "")):
            if len(rows) >= max_skills:
                break
            desc = " ".join(str(skill.description or "").split())
            if len(desc) > desc_chars:
                desc = desc[:desc_chars].rstrip() + "…"
            wf = sorted(getattr(skill, "workflow", None) or [], key=lambda s: getattr(s, "step", 0))
            wf_str = " → ".join(
                str(getattr(s, "tool", "") or "").strip()
                for s in wf
                if str(getattr(s, "tool", "") or "").strip()
            )
            tools = ", ".join(skill.get_tool_names())
            rows.append(
                f'  <skill name="{skill.name}" tools="{tools}">\n'
                f"    <description>{desc}</description>\n"
                f"    <workflow>{wf_str or '（见 description）'}</workflow>\n"
                f"  </skill>"
            )
        if not rows:
            return ""
        return "<available_skills>\n" + "\n".join(rows) + "\n</available_skills>"

    def match_skill(self, user_input: str, context: Dict[str, Any] = None) -> Tuple[Optional[Skill], float]:
        """
        根据用户输入匹配合适的技能
        
        Args:
            user_input: 用户输入文本
            context: 上下文信息
            
        Returns:
            (匹配的技能, 匹配分数)
        """
        if not self.skills:
            self.load_all()
        
        if context is None:
            context = {}
        
        user_input_lower = user_input.lower()
        
        # 提取意图和实体（简化版，后续可集成NLP模型）
        extracted_intents = self._extract_intents(user_input_lower)
        extracted_entities = self._extract_entities(user_input_lower)

        if context:
            _ui = context.get("ui_context")
            if isinstance(_ui, dict):
                _ut = str(_ui.get("target") or "").strip().lower()
                if _ut in ("bug", "badcase", "testcase", "card", "plan") and _ut not in extracted_entities:
                    extracted_entities.append(_ut)
        
        try:
            from .intent_guards import intent_bucket
        except ImportError:
            intent_bucket = lambda _u: "unclear"  # type: ignore

        bucket = intent_bucket(user_input)

        try:
            from .intent_guards import user_text_implies_plan_entity_type
        except ImportError:
            user_text_implies_plan_entity_type = lambda _u: False  # type: ignore

        _implies_plan = user_text_implies_plan_entity_type(user_input)
        _delete_intent = "删除" in extracted_intents

        # 计算每个技能的匹配分数；create_* 按意图桶软降权（不再整表过滤到空）
        skill_scores = []
        for skill in self.skills.values():
            score = skill.trigger.match(user_input_lower, extracted_intents, extracted_entities)
            if score > 0:
                sn = (skill.name or "").lower()
                if sn.startswith("create_"):
                    orig = score
                    if bucket == "modify":
                        score *= 0.38
                        print(
                            f"[SKILL_MATCHER] 软降权 create_*（明确修改意图）: {skill.name} "
                            f"{orig:.2f} → {score:.2f}"
                        )
                    elif bucket == "unclear":
                        score *= 0.84
                        print(
                            f"[SKILL_MATCHER] 软降权 create_*（意图模糊，可由 ReAct 仲裁）: {skill.name} "
                            f"{orig:.2f} → {score:.2f}"
                        )
                elif _implies_plan and _delete_intent:
                    if sn.startswith("delete_") and sn not in ("delete_plan",):
                        orig = score
                        score *= 0.12
                        print(
                            f"[SKILL_MATCHER] 软降权 delete_*（用户明确删迭代计划）: {skill.name} "
                            f"{orig:.2f} → {score:.2f}"
                        )
                    elif sn == "delete_plan":
                        orig = score
                        score = min(1.0, score * 1.15)
                        if score != orig:
                            print(
                                f"[SKILL_MATCHER] 加权 delete_plan（删迭代计划）: {skill.name} "
                                f"{orig:.2f} → {score:.2f}"
                            )
                skill_scores.append((skill, score))

        if not skill_scores:
            return None, 0.0

        # 按匹配分数排序
        skill_scores.sort(key=lambda x: x[1], reverse=True)

        best_skill, best_score = skill_scores[0]
        
        # 记录匹配详情
        print(f"[SKILL_MATCHER] 🎯 用户输入: '{user_input}'")
        print(f"[SKILL_MATCHER] 📊 匹配结果:")
        for skill, score in skill_scores[:3]:  # 显示前3名
            print(f"  - {skill.name}: {score:.2f}")
        
        if best_score >= 0.3:  # 阈值
            print(f"[SKILL_MATCHER] ✅ 选择技能: {best_skill.name} (分数: {best_score:.2f})")
            try:
                from llm.prompt_log import maybe_log_skill_workflow

                wf = best_skill.get_workflow_prompt() if hasattr(best_skill, "get_workflow_prompt") else ""
                if wf:
                    maybe_log_skill_workflow(
                        best_skill.name,
                        wf,
                        score=best_score,
                        user_input=user_input,
                    )
            except Exception as _sk_log_ex:
                print(f"[REACT_PROMPT] skill_workflow log skip: {_sk_log_ex}", flush=True)
            return best_skill, best_score
        else:
            print(f"[SKILL_MATCHER] ⚠️  无合适技能 (最高分: {best_score:.2f})")
            return None, best_score
    
    def _extract_intents(self, text: str) -> List[str]:
        """从文本中提取意图（简化版）"""
        intents = []
        
        # 意图关键词映射
        intent_keywords = {
            '修改': ['修改', '改', '更新', '调整', '更正', '修正', '变更', '设为', '改成'],
            '查询': ['查询', '搜索', '查找', '查看', '找', '列出', '显示', '有哪些', '什么'],
            '创建': ['创建', '新建', '添加', '增加', '新增', '新建一个', '创建新'],
            '删除': ['删除', '删掉', '移除', '去掉', '清除'],
            '分配': ['分配', '指派', '交给', '转给', '分配给'],
            '状态': ['状态', '进展', '进度', '现状', '怎么样'],
            '报告': ['报告', '生成报告', '导出', '统计数据']
        }
        
        for intent, keywords in intent_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    intents.append(intent)
                    break
        
        return intents
    
    def _extract_entities(self, text: str) -> List[str]:
        """从文本中提取实体（简化版）"""
        entities = []
        
        # 实体关键词
        entity_keywords = {
            'bug': ['bug', '缺陷', '问题', '错误', 'bug', '虫'],
            'badcase': ['badcase', 'bad case', 'bad-case', '问题用例', '错误用例'],
            'testcase': ['测试用例', 'testcase', 'test case', '用例'],
            'plan': ['迭代计划', '计划', '迭代', 'sprint', '版本'],
            '优先级': ['优先级', '优先', '紧急', '重要'],
            '状态': ['状态', '进展情况', '处理情况']
        }
        
        for entity, keywords in entity_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    entities.append(entity)
                    break
        
        # 检查是否有特定ID模式（如"bug 123"）
        import re
        id_patterns = [
            (r'(bug|缺陷|问题)\s*[#]?\s*(\d+)', 'bug_id'),
            (r'(badcase|用例)\s*[#]?\s*(\d+)', 'badcase_id'),
            (r'id[=:]\s*(\d+)', 'item_id')
        ]
        
        for pattern, entity_type in id_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                entities.append(entity_type)
        
        return entities
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """
        获取技能对应的提示词
        
        Args:
            skill_name: 技能名称
            
        Returns:
            提示词内容，如果技能不存在则返回空字符串
        """
        skill = self.get_skill(skill_name)
        if not skill:
            print(f"[SKILL_LOADER] 技能不存在: {skill_name}")
            return ""
        
        return skill.get_workflow_prompt()
    
    def save_skill(self, skill: Skill, file_name: str = None) -> str:
        """
        保存技能到文件
        
        Args:
            skill: 技能对象
            file_name: 文件名（可选，默认使用技能名称）
            
        Returns:
            保存的文件路径
        """
        if not file_name:
            file_name = f"{skill.name}.yaml"
        
        file_path = os.path.join(self.skill_dir, file_name)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        yaml_content = skill.to_yaml()
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        
        # 更新内部缓存
        self.skills[skill.name] = skill
        self.skill_files[skill.name] = file_path
        
        print(f"[SKILL_LOADER] 保存技能: {skill.name} -> {file_path}")
        return file_path
    
    def remove_skill(self, skill_name: str) -> bool:
        """
        删除技能文件
        
        Args:
            skill_name: 技能名称
            
        Returns:
            是否成功删除
        """
        file_path = self.skill_files.get(skill_name)
        if not file_path or not os.path.exists(file_path):
            print(f"[SKILL_LOADER] 技能文件不存在: {skill_name}")
            return False
        
        try:
            os.remove(file_path)
            del self.skills[skill_name]
            del self.skill_files[skill_name]
            print(f"[SKILL_LOADER] 删除技能: {skill_name}")
            return True
        except Exception as e:
            print(f"[SKILL_LOADER] 删除失败: {str(e)}")
            return False