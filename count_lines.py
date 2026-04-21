import os

total_lines = 0
file_count = 0

# 支持的文件扩展名
extensions = ['.py', '.vue', '.js', '.ts', '.jsx', '.tsx']

# 遍历目录
for root, dirs, files in os.walk('.'):
    # 跳过一些不需要统计的目录
    dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', 'venv', '__pycache__']]
    
    for file in files:
        if any(file.endswith(ext) for ext in extensions):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = len(f.readlines())
                    total_lines += lines
                    file_count += 1
                    print(f"{file_path}: {lines} lines")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

print(f"\nTotal files: {file_count}")
print(f"Total lines: {total_lines}")