import os

# 要统计的文件类型
extensions = ['.py', '.vue', '.js', '.ts']
# 要排除的目录
exclude_dirs = ['venv', 'node_modules', '.git', '.venv']

total_lines = 0
file_count = 0

def count_lines_in_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f)
    except:
        return 0

def should_exclude(path):
    """检查路径是否应该被排除"""
    for exclude_dir in exclude_dirs:
        if exclude_dir in path.split(os.sep):
            return True
    return False

def traverse_directory(directory):
    global total_lines, file_count
    
    for root, dirs, files in os.walk(directory):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = os.path.join(root, file)
                # 再次检查路径是否包含排除目录
                if should_exclude(file_path):
                    continue
                lines = count_lines_in_file(file_path)
                total_lines += lines
                file_count += 1
                # 只打印前100个文件，避免输出过多
                if file_count <= 100:
                    print(f"{file_path}: {lines} lines")

# 从当前目录开始统计
traverse_directory('.')

print(f"\nTotal files: {file_count}")
print(f"Total lines: {total_lines}")