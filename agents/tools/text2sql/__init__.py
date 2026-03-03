"""
Text2SQL 模块

提供完整的 Text2SQL 功能链:
1. Schema 管理 (schema_manager)
2. SQL 生成 (sql_generator)
3. SQL 校验 (sql_validator)
4. SQL 执行 (sql_executor)
5. 代码封装 (sql_code_wrapper) - 将 SQL 封装成 Python/Java 代码
6. 沙箱执行 (sandbox_executor) - 通过 OpenClaw 沙箱安全执行代码
"""

# Schema 管理
from .schema_manager import (
    SchemaManager,
    get_schema_manager
)

# SQL 生成
from .sql_generator import (
    SQLGenerator,
    get_sql_generator
)

# SQL 校验
from .sql_validator import (
    SQLValidator,
    ValidationResult,
    get_sql_validator
)

# SQL 执行
from .sql_executor import (
    SQLExecutor,
    SQLExecutorConfig,
    get_sql_executor
)

# 代码封装 - 将 SQL 封装成 Python/Java 代码
from .sql_code_wrapper import (
    SQLCodeWrapper,
    CodeWrapperConfig,
    CodeLanguage,
    get_sql_code_wrapper
)

# 沙箱执行 - Docker 沙箱（带资源限制和安全检查）
from .sandbox_executor import (
    SandboxExecutor,
    SandboxMode,
    SecurityConfig,
    SecurityChecker,
    get_sandbox_executor,
    get_security_config,
    create_sandbox_executor
)


__all__ = [
    # Schema
    'SchemaManager',
    'get_schema_manager',
    
    # Generator
    'SQLGenerator',
    'get_sql_generator',
    
    # Validator
    'SQLValidator',
    'ValidationResult',
    'get_sql_validator',
    
    # Executor
    'SQLExecutor',
    'SQLExecutorConfig',
    'get_sql_executor',
    
    # Code Wrapper
    'SQLCodeWrapper',
    'CodeWrapperConfig',
    'CodeLanguage',
    'get_sql_code_wrapper',
    
    # Sandbox
    'SandboxExecutor',
    'SandboxMode',
    'SecurityConfig',
    'SecurityChecker',
    'get_sandbox_executor',
    'get_security_config',
    'create_sandbox_executor',
]
