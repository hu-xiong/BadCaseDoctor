import re

with open(r'c:\Users\h2629\PycharmProjects\PythonProject\BadCaseDoctor\electron-vue3\src\components\SimpleChatPanel.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# Find lines with Chinese question mark inside single-quoted strings
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    # Check for Chinese question mark
    if '\uff1f' in line:
        print(f'Line {i}: {line[:120]}')
