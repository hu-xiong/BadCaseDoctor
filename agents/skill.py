"""
Skill 数据模型定义
对应技能配置文件的字段
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml
import json


@dataclass
class ToolStep:
    """单个工具步骤定义"""
    name: str
    purpose: str
    params: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ToolStep':
        """从字典创建工具步骤"""
        return cls(
            name=data.get('name'),
            purpose=data.get('purpose', ''),
            params=data.get('params', {})
        )


@dataclass
class WorkflowStep:
    """工作流步骤定义"""
    step: int
    tool: str
    description: str
    depends_on: Optional[str] = None
    condition: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowStep':
        """从字典创建工作流步骤"""
        return cls(
            step=data.get('step', 1),
            tool=data.get('tool'),
            description=data.get('description', ''),
            depends_on=data.get('depends_on'),
            condition=data.get('condition')
        )


@dataclass
class SkillTrigger:
    """技能触发条件"""
    intents: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SkillTrigger':
        """从字典创建触发条件"""
        return cls(
            intents=data.get('intents', []),
            entities=data.get('entities', []),
            patterns=data.get('patterns', [])
        )
    
    def match(self, user_input: str, extracted_intents: List[str] = None, 
              extracted_entities: List[str] = None) -> float:
        """
        匹配用户输入与技能触发条件
        返回匹配分数（0-1）
        """
        user_input_lower = user_input.lower()
        score = 0.0
        
        # 检查意图匹配
        if extracted_intents:
            for intent in self.intents:
                if intent in extracted_intents:
                    score += 0.4  # 意图匹配权重
                    break
        
        # 检查实体匹配
        if extracted_entities:
            for entity in self.entities:
                if entity in extracted_entities:
                    score += 0.3  # 实体匹配权重
                    break
        
        # 检查关键词模式匹配
        if self.patterns:
            for pattern in self.patterns:
                if pattern in user_input_lower:
                    score += 0.3  # 模式匹配权重
                    break
        else:
            # 如果没有显式模式，使用意图和实体关键词
            for intent in self.intents:
                if intent in user_input_lower:
                    score += 0.2
            
            for entity in self.entities:
                if entity in user_input_lower:
                    score += 0.1
        
        return min(score, 1.0)


@dataclass
class Skill:
    """技能定义"""
    name: str
    description: str
    trigger: SkillTrigger
    tools: List[ToolStep] = field(default_factory=list)
    workflow: List[WorkflowStep] = field(default_factory=list)
    prompt_template: Optional[str] = None
    examples: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Skill':
        """从字典创建技能"""
        return cls(
            name=data.get('name', ''),
            description=data.get('description', ''),
            trigger=SkillTrigger.from_dict(data.get('trigger', {})),
            tools=[ToolStep.from_dict(tool) for tool in data.get('tools', [])],
            workflow=[WorkflowStep.from_dict(step) for step in data.get('workflow', [])],
            prompt_template=data.get('prompt_template'),
            examples=data.get('examples', []),
            metadata=data.get('metadata', {})
        )
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> 'Skill':
        """从YAML内容创建技能"""
        data = yaml.safe_load(yaml_content)
        return cls.from_dict(data)
    
    @classmethod
    def from_json(cls, json_content: str) -> 'Skill':
        """从JSON内容创建技能"""
        data = json.loads(json_content)
        return cls.from_dict(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'description': self.description,
            'trigger': {
                'intents': self.trigger.intents,
                'entities': self.trigger.entities,
                'patterns': self.trigger.patterns
            },
            'tools': [
                {
                    'name': tool.name,
                    'purpose': tool.purpose,
                    'params': tool.params
                }
                for tool in self.tools
            ],
            'workflow': [
                {
                    'step': step.step,
                    'tool': step.tool,
                    'description': step.description,
                    'depends_on': step.depends_on,
                    'condition': step.condition
                }
                for step in self.workflow
            ],
            'prompt_template': self.prompt_template,
            'examples': self.examples,
            'metadata': self.metadata
        }
    
    def to_yaml(self) -> str:
        """转换为YAML格式"""
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)
    
    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def get_tool_names(self) -> List[str]:
        """获取技能使用的工具名称列表"""
        return [tool.name for tool in self.tools]
    
    def get_workflow_prompt(self) -> str:
        """生成工作流提示词"""
        if self.prompt_template:
            return self.prompt_template
        
        # 如果未提供模板，生成默认提示词
        lines = [f"## 技能: {self.name}"]
        lines.append(f"### 描述: {self.description}")
        
        if self.examples:
            lines.append("### 示例:")
            for example in self.examples:
                lines.append(f"- {example}")
        
        lines.append("### 标准化工作流:")
        for step in self.workflow:
            step_desc = f"{step.step}. 使用 {step.tool} - {step.description}"
            if step.depends_on:
                step_desc += f" (依赖: 步骤{step.depends_on.split('_')[1]})"
            lines.append(step_desc)
        
        return '\n'.join(lines)