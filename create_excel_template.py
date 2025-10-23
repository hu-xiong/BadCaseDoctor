import pandas as pd

# 创建示例数据
sample_data = {
    'case_category': [
        '问题模糊不清',
        '问题缺少文档信息',
        '问题模型理解不清楚',
        '问题提示词不明确',
        '问题调用错了工具'
    ],
    'base_problem': [
        '用户询问"帮我写个程序"，但没有说明具体需求',
        '用户询问API使用方法，但相关文档缺失',
        '模型无法理解复杂的业务逻辑',
        '提示词过于简单，没有明确的指导方向',
        '系统调用了错误的工具来处理用户请求'
    ],
    'badcase_result': [
        '模型生成了通用的程序模板，不符合用户实际需求',
        '模型无法提供准确的API使用信息',
        '模型给出了错误的业务逻辑处理方案',
        '模型回答过于宽泛，没有针对性',
        '系统返回了不相关的工具结果'
    ],
    'correct_answer': [
        '应该询问用户具体的程序类型、功能需求、技术栈等详细信息',
        '应该提供基础的API概念，并建议用户查看官方文档',
        '应该要求用户提供更详细的业务场景描述',
        '应该使用更具体的提示词，明确回答范围和深度',
        '应该调用正确的工具或询问用户具体需求'
    ],
    'problem_reason': [
        '用户需求描述不够具体，缺乏关键信息',
        '系统缺少相关文档资源',
        '模型训练数据中缺少类似业务场景',
        '提示词设计不够精确',
        '工具选择逻辑存在缺陷'
    ],
    'needs_processing': [
        True,
        True,
        True,
        True,
        True
    ]
}

# 创建DataFrame
df = pd.DataFrame(sample_data)

# 保存为Excel文件
df.to_excel('badcase_template.xlsx', index=False)

print("Excel模板文件 'badcase_template.xlsx' 已创建成功！")
print("该文件包含了5个示例BadCase，可以作为导入模板使用。") 