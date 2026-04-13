with open(r'c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor\agents\intelligent_devops_agent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到第 187 行（索引 186）
for i, line in enumerate(lines):
    if '不推假的 reasoning 占位' in line:
        print(f'Found at line {i+1}: {repr(line[:50])}...')
        # 在这一行后面插入新代码
        insert_code = '''        # 立即发送占位思考内容，避免前端长时间无视觉反馈
        yield {
            'type': 'stream',
            'payload': {
                'lane': 'think',
                'delta': '正在思考...',
                'react_phase': 'think',
                'stream_channel': 'content',
            }
        }
'''
        # 检查下一行是否已经是我们插入的内容
        if i+1 < len(lines) and '立即发送占位思考内容' in lines[i+1]:
            print('Already inserted!')
        else:
            lines.insert(i+1, insert_code)
            with open(r'c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor\agents\intelligent_devops_agent.py', 'w', encoding='utf-8') as f:
                f.writelines(lines)
            print('Success!')
        break
