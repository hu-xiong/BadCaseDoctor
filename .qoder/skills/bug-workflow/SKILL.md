---
name: bug-workflow
description: Bug/BadCase/测试用例的标准化操作流程。查询操作使用 grep 单步，修改操作使用 grep + modify 两步。
---

# Bug 操作标准化流程

简化工具流程，确保 AI 生成固定的任务步骤。

## 核心规则

### 查询操作（单步流程）

任何涉及 **查询/搜索** Bug/BadCase/测试用例 的操作，只需一步：

```
grep -> 搜索关键词
```

**适用场景**：
- 查询某类 Bug
- 搜索关键字相关的 Bug
- 查看某个状态的 Bug 列表
- 用户输入单个关键字（如"界面"、"登录"）

**示例**：

| 用户输入 | 生成的 Todo 列表 |
|---------|-----------------|
| 界面 | 使用 grep 工具搜索界面相关的Bug，keywords=界面，target=bug |
| 查询登录相关的Bug | 使用 grep 工具搜索登录相关的Bug，keywords=登录，target=bug |
| 搜索高优先级Bug | 使用 grep 工具搜索高优先级Bug，keywords=高优先级，target=bug |

### 修改操作（两步流程）

任何涉及 **修改** Bug/BadCase/测试用例 的操作，必须按以下顺序执行：

```
1. grep    -> 搜索定位目标对象
2. modify  -> 执行修改操作
```

**适用场景**：
- 修改 Bug 状态、优先级、严重程度
- 修改 Bug 标题、描述
- 批量修改多个 Bug

**示例**：

| 用户输入 | 生成的 Todo 列表 |
|---------|-----------------|
| 修改登录Bug的状态为关闭 | 1. 使用 grep 工具搜索定位登录Bug，keywords=登录，target=bug<br>2. 使用 modify 工具将Bug状态修改为closed |
| 把高优先级的Bug都改成P1 | 1. 使用 grep 工具搜索高优先级Bug，keywords=高优先级，target=bug<br>2. 使用 modify 工具批量修改优先级为P1 |

### 创建操作（单步流程）

创建操作只需一步：

```
create -> 创建新的 Bug/BadCase/测试用例
```

**示例**：

| 用户输入 | 生成的 Todo 列表 |
|---------|-----------------|
| 创建一个登录失败的Bug | 使用 create 工具创建Bug，标题=登录失败，优先级=高 |

## grep 工具参数规范

```json
{
  "keywords": "搜索关键词（必填）",
  "target": "bug | badcase | all（必填）",
  "project_id": "项目ID（可选）"
}
```

**target 参数说明**：
- `bug`: 只搜索 Bug
- `badcase`: 只搜索 BadCase
- `all`: 搜索所有类型

## modify 工具参数规范

```json
{
  "target": "bug | badcase | test_case",
  "target_id": "目标ID",
  "modifications": {
    "status": "新状态值",
    "priority": "新优先级"
  },
  "confirm": true
}
```

## 意图识别关键词

| 意图类型 | 关键词示例 | 流程 |
|---------|-----------|------|
| 查询意图 | 查询、搜索、查看、找、列出、显示、单个关键字 | grep（单步） |
| 修改意图 | 修改、改、更新、设为、改成、调整 | grep → modify（两步） |
| 创建意图 | 创建、新建、添加、增加 | create（单步） |

## 禁止事项

1. **禁止在查询操作中使用 modify**：查询就是查询，不能修改
2. **禁止修改操作跳过 grep**：必须先定位再修改
