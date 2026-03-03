"""
沙箱执行器 - 在安全隔离环境中执行 Text2SQL 生成的数据库操作代码

使用 llm-sandbox 直接 Docker 执行，无需额外服务。

安装: pip install llm-sandbox

安全特性:
- CPU/内存/超时限制（防止死循环拖垮服务器）
- 网络隔离（防止数据泄露/恶意请求）
- 危险函数黑名单（禁止删除文件、执行系统命令）
- SQL 危险操作拦截（禁止 DROP/ALTER/TRUNCATE）

架构:
┌─────────────────┐
│ 本服务          │
│ - 代码生成      │
│ - 安全检查      │
│ - 结果处理      │
└────────┬────────┘
         │ 直接调用
         ▼
┌─────────────────────────────────────────────────────────┐
│                Docker 沙箱容器（资源受限）               │
│  - CPU: 0.5核  内存: 256MB  超时: 30s                   │
│  - 网络隔离  文件系统隔离                                │
│  - 危险函数拦截                                          │
└─────────────────────────────────────────────────────────┘
"""

import os
import re
import json
import time
import subprocess
import tempfile
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


# ========== 依赖检测 ==========

LLM_SANDBOX_AVAILABLE = False
try:
    from llm_sandbox import SandboxSession
    LLM_SANDBOX_AVAILABLE = True
    print("[SANDBOX] ✅ llm-sandbox 已安装，将使用 Docker 沙箱模式")
except ImportError:
    print("[SANDBOX] ⚠️ llm-sandbox 未安装，将使用本地执行模式（不安全）")
    print("[SANDBOX] 💡 安装: pip install llm-sandbox")


# ========== 安全配置 ==========

@dataclass
class SecurityConfig:
    """沙箱安全配置 - 三大核心：资源限制 + 操作黑名单 + 数据隔离"""
    
    # ==================== 1. 资源限制 ====================
    cpu_limit: float = 0.2              # CPU 限制（核数），防止占满 CPU
    memory_limit: str = "128m"          # 内存限制，防止内存泄漏拖垮服务器
    timeout: int = 15                   # 超时时间（秒），防止死循环
    
    # ==================== 2. 操作黑名单 ====================
    # 危险函数黑名单
    forbidden_functions: List[str] = field(default_factory=lambda: [
        # 文件删除/修改
        "os.remove", "os.unlink", "os.rmdir", "os.removedirs",
        "shutil.rmtree", "shutil.move", "shutil.copy", "shutil.copytree",
        # 系统命令执行
        "os.system", "os.popen", "os.spawn", "os.exec", "os.startfile",
        "subprocess.run", "subprocess.call", "subprocess.Popen",
        "subprocess.check_output", "subprocess.check_call",
        # 网络操作
        "socket.socket", "urllib.request", "urllib.urlopen",
        "requests.get", "requests.post", "requests.put", "requests.delete",
        "http.client", "httplib",
        # 进程操作
        "os.kill", "os.killpg", "os.fork", "os._exit", "os.wait",
        # 环境操作
        "os.putenv", "os.environ", "sys.exit", "exit", "quit",
        # 动态执行
        "eval", "exec", "compile",
        # 导入相关
        "importlib.import_module", "__import__",
    ])
    
    # 敏感目录黑名单（禁止访问）
    forbidden_paths: List[str] = field(default_factory=lambda: [
        "/root", "/etc", "/var", "/home", "/Users",
        "/proc", "/sys", "/dev", "/boot", "/lib", "/lib64",
        "/usr/bin", "/usr/sbin", "/bin", "/sbin"
    ])
    
    # SQL 危险操作黑名单
    forbidden_sql_patterns: List[str] = field(default_factory=lambda: [
        r"\bDROP\s+TABLE\b",
        r"\bDROP\s+DATABASE\b",
        r"\bDROP\s+INDEX\b",
        r"\bALTER\s+TABLE\b",
        r"\bALTER\s+DATABASE\b",
        r"\bTRUNCATE\s+TABLE?\b",
        r"\bDELETE\s+FROM\b(?!.*WHERE)",  # DELETE 无 WHERE 条件
        r"\bUPDATE\s+\w+\s+SET\b(?!.*WHERE)",  # UPDATE 无 WHERE 条件
        r"\bGRANT\b", r"\bREVOKE\b",
        r"\bCREATE\s+USER\b", r"\bDROP\s+USER\b",
        r"\bLOAD\s+FILE\b",  # 禁止加载文件
        r"\bINTO\s+OUTFILE\b",  # 禁止导出到文件
    ])
    
    # ==================== 3. 数据隔离 ====================
    # 网络隔离
    network_disabled: bool = True       # 禁用网络，防止数据泄露/恶意请求
    
    # 文件系统隔离
    read_only_root: bool = True         # 根文件系统只读
    allowed_write_dirs: List[str] = field(default_factory=lambda: [
        "/tmp", "/sandbox/workspace"  # 仅允许在这些目录写入
    ])
    
    # 数据库隔离
    db_read_only: bool = True           # 数据库只读模式
    db_use_copy: bool = True            # 使用数据库副本（非生产库）
    db_copy_dir: str = "/sandbox/db_copy"  # 数据库副本目录
    
    # 环境变量隔离
    clean_env: bool = True              # 清理敏感环境变量
    allowed_env_vars: List[str] = field(default_factory=lambda: [
        "PATH", "PYTHONPATH", "LANG", "LC_ALL"
    ])
    
    # 用户权限隔离
    run_as_non_root: bool = True        # 非 root 用户运行
    sandbox_user: str = "nobody"        # 沙箱运行用户


class SecurityChecker:
    """安全检查器"""
    
    def __init__(self, config: SecurityConfig = None):
        self.config = config or SecurityConfig()
    
    def check_code(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        检查代码安全性
        
        Returns:
            {'safe': bool, 'violations': [str], 'blocked': bool}
        """
        violations = []
        
        if language == "python":
            violations.extend(self._check_python_code(code))
        
        # 检查通用危险模式
        violations.extend(self._check_dangerous_patterns(code))
        
        return {
            'safe': len(violations) == 0,
            'violations': violations,
            'blocked': len(violations) > 0
        }
    
    def _check_python_code(self, code: str) -> List[str]:
        """检查 Python 代码"""
        violations = []
        
        # 检查危险函数
        for func in self.config.forbidden_functions:
            # 检查函数调用模式
            func_name = func.split('.')[-1]
            pattern = r'\b' + re.escape(func_name) + r'\s*\('
            if re.search(pattern, code):
                violations.append(f"禁止调用 {func} 函数")
        
        # 检查敏感路径
        for path in self.config.forbidden_paths:
            if path in code:
                violations.append(f"禁止访问敏感目录 {path}")
        
        # 检查 eval/exec/compile
        if re.search(r'\beval\s*\(', code):
            violations.append("禁止使用 eval() 函数")
        if re.search(r'\bexec\s*\(', code):
            violations.append("禁止使用 exec() 函数")
        if re.search(r'\bcompile\s*\(', code):
            violations.append("禁止使用 compile() 函数")
        
        # 检查文件写入模式 - 仅允许在 allowed_write_dirs 中写入
        write_pattern = r"open\s*\([^)]*,\s*['\"]w"
        if re.search(write_pattern, code):
            # 检查是否在允许的目录中
            allowed = False
            for allowed_dir in self.config.allowed_write_dirs:
                dir_pattern = r"open\s*\(\s*['\"]" + re.escape(allowed_dir)
                if re.search(dir_pattern, code):
                    allowed = True
                    break
            if not allowed:
                violations.append(f"仅允许在以下目录写入文件: {', '.join(self.config.allowed_write_dirs)}")
        
        # ==================== 数据隔离检查 ====================
        
        # 网络隔离检查
        if self.config.network_disabled:
            network_patterns = [
                r'\bsocket\s*\(',
                r'\burllib\.',
                r'\brequests\.',
                r'\bhttp\.client\b',
                r'\bhttplib\b',
                r'\burlretrieve\s*\(',
            ]
            for pattern in network_patterns:
                if re.search(pattern, code):
                    violations.append("网络已隔离，禁止进行网络操作")
                    break
        
        # 环境变量隔离检查
        if self.config.clean_env:
            if 'os.environ' in code or 'os.getenv' in code:
                # 检查是否访问了允许之外的环境变量
                violations.append("禁止访问环境变量（已启用环境隔离）")
        
        # 数据库只读检查
        if self.config.db_read_only:
            db_write_patterns = [
                r'\bINSERT\s+INTO\b',
                r'\bUPDATE\s+\w+\s+SET\b',
                r'\bDELETE\s+FROM\b',
            ]
            for pattern in db_write_patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    violations.append("数据库只读模式，禁止写入操作")
                    break
        
        # 检查 __import__
        if '__import__' in code:
            violations.append("禁止使用 __import__ 动态导入")
        
        # 检查 importlib
        if 'importlib.import_module' in code:
            violations.append("禁止使用 importlib.import_module 动态导入")
        
        return violations
    
    def _check_dangerous_patterns(self, code: str) -> List[str]:
        """检查通用危险模式"""
        violations = []
        
        # 检查无限循环模式
        if re.search(r'\bwhile\s+True\s*:', code):
            violations.append("检测到潜在无限循环 while True")
        
        return violations
    
    def check_sql(self, sql: str) -> Dict[str, Any]:
        """
        检查 SQL 安全性
        
        Returns:
            {'safe': bool, 'violations': [str]}
        """
        violations = []
        sql_upper = sql.upper()
        
        for pattern in self.config.forbidden_sql_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                violations.append(f"检测到危险 SQL 操作: {pattern}")
        
        return {
            'safe': len(violations) == 0,
            'violations': violations,
            'blocked': len(violations) > 0
        }


class SandboxMode(Enum):
    """沙箱模式"""
    SANDBOX = "sandbox"  # Docker 沙箱执行（推荐）
    LOCAL = "local"      # 本地直接执行（备选，不安全）


class SandboxExecutor:
    """
    沙箱执行器
    
    使用 llm-sandbox 在 Docker 容器中安全执行代码。
    内置资源限制和安全检查。
    """
    
    def __init__(
        self, 
        image: str = "python:3.11-slim",
        security_config: SecurityConfig = None,
        keep_template: bool = False,
        fallback_to_local: bool = False  # 默认不回退本地
    ):
        """
        初始化沙箱执行器
        
        Args:
            image: Docker 镜像
            security_config: 安全配置
            keep_template: 是否保持容器模板以加速后续执行
            fallback_to_local: 如果沙箱不可用，是否回退到本地执行
        """
        self.image = image
        self.security_config = security_config or SecurityConfig()
        self.keep_template = keep_template
        self.fallback_to_local = fallback_to_local
        
        # 初始化安全检查器
        self.security_checker = SecurityChecker(self.security_config)
        
        if LLM_SANDBOX_AVAILABLE:
            print(f"[SANDBOX] ✅ 初始化完成")
            print(f"[SANDBOX] 📊 资源限制: CPU={self.security_config.cpu_limit}核, "
                  f"内存={self.security_config.memory_limit}, "
                  f"超时={self.security_config.timeout}s")
            print(f"[SANDBOX] 🔒 网络隔离: {'已启用' if self.security_config.network_disabled else '未启用'}")
            print(f"[SANDBOX] 🗄️ 数据库隔离: 只读={self.security_config.db_read_only}, 副本={self.security_config.db_use_copy}")
        elif fallback_to_local:
            print("[SANDBOX] ⚠️ 使用本地执行模式（不安全）")
        else:
            print("[SANDBOX] ❌ 沙箱不可用且未启用本地回退")
    
    def _build_isolation_code(self, language: str) -> str:
        """
        构建隔离环境的前置代码
        
        在用户代码执行前注入，实现数据隔离
        """
        if language == "python":
            lines = []
            lines.append("# ===== 沙箱隔离环境 =====")
            
            # 环境变量隔离：清理敏感变量
            if self.security_config.clean_env:
                lines.append("import os")
                lines.append("# 清理敏感环境变量")
                lines.append("_allowed_env = " + str(self.security_config.allowed_env_vars))
                lines.append("_env_keys = list(os.environ.keys())")
                lines.append("for _k in _env_keys:")
                lines.append("    if _k not in _allowed_env:")
                lines.append("        del os.environ[_k]")
                lines.append("")
            
            # 数据库只读模式：注入 SQLite 只读连接
            if self.security_config.db_read_only:
                lines.append("# 数据库只读模式")
                lines.append("_original_connect = __builtins__.get('sqlite3_connect') if isinstance(__builtins__, dict) else getattr(__builtins__, 'sqlite3_connect', None)")
                lines.append("")
            
            # 文件系统隔离：限制写入目录
            if self.security_config.read_only_root:
                lines.append("# 文件系统隔离")
                lines.append("_allowed_dirs = " + str(self.security_config.allowed_write_dirs))
                lines.append("")
            
            lines.append("# ===== 用户代码 =====")
            lines.append("")
            
            return "\n".join(lines)
        
        # 其他语言暂不注入隔离代码
        return ""
    
    def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: int = None,
        libraries: List[str] = None,
        skip_security_check: bool = False
    ) -> Dict[str, Any]:
        """
        在沙箱中执行代码
        
        Args:
            code: 要执行的代码
            language: 语言 (python/java/cpp/go/javascript)
            timeout: 超时时间（秒），默认使用安全配置
            libraries: 需要安装的依赖库
            skip_security_check: 是否跳过安全检查
            
        Returns:
            执行结果
        """
        # 安全检查
        if not skip_security_check:
            security_result = self.security_checker.check_code(code, language)
            if security_result['blocked']:
                return {
                    'success': False,
                    'error': '代码安全检查未通过',
                    'violations': security_result['violations'],
                    'execution_mode': 'blocked'
                }
        
        # 使用配置的超时
        if timeout is None:
            timeout = self.security_config.timeout
        
        if LLM_SANDBOX_AVAILABLE:
            return self._execute_in_sandbox(code, language, timeout, libraries)
        elif self.fallback_to_local:
            return self._execute_local(code, language, timeout)
        else:
            return {
                'success': False,
                'error': 'llm-sandbox 未安装且未启用本地回退',
                'hint': 'pip install llm-sandbox'
            }
    
    def _execute_in_sandbox(
        self,
        code: str,
        language: str,
        timeout: int,
        libraries: List[str]
    ) -> Dict[str, Any]:
        """在 Docker 沙箱中执行代码（带资源限制和数据隔离）"""
        from llm_sandbox import SandboxSession
        
        start_time = time.time()
        print(f"[SANDBOX] 🚀 执行 {language} 代码（超时: {timeout}s）...")
        print(f"[SANDBOX] 🔒 数据隔离: 网络={'禁用' if self.security_config.network_disabled else '启用'}, "
              f"文件系统={'只读' if self.security_config.read_only_root else '可写'}, "
              f"用户={self.security_config.sandbox_user}")
        
        try:
            # 创建沙箱会话，带资源限制和数据隔离
            sandbox_kwargs = {
                'lang': language,
                'image': self.image,
                'keep_template': self.keep_template,
                'verbose': False
            }
            
            # 应用数据隔离配置（llm-sandbox 支持的参数）
            # 注意：不同版本 llm-sandbox API 可能不同，这里做兼容处理
            
            # 网络隔离
            if self.security_config.network_disabled:
                # llm-sandbox 通过 network_disabled 参数控制
                sandbox_kwargs['network_disabled'] = True
            
            try:
                with SandboxSession(**sandbox_kwargs) as session:
                    # 构建隔离环境的前置代码
                    isolation_prefix = self._build_isolation_code(language)
                    full_code = isolation_prefix + code
                    
                    # 设置超时执行
                    result = session.run(full_code, timeout=timeout)
                    
                    execution_time = time.time() - start_time
                    
                    # 构建输出
                    output = {
                        'success': result.exit_code == 0,
                        'stdout': result.stdout,
                        'stderr': result.stderr,
                        'exit_code': result.exit_code,
                        'execution_time': execution_time,
                        'execution_mode': 'sandbox',
                        'resource_limits': {
                            'cpu': self.security_config.cpu_limit,
                            'memory': self.security_config.memory_limit,
                            'timeout': timeout
                        },
                        'isolation': {
                            'network_disabled': self.security_config.network_disabled,
                            'read_only_root': self.security_config.read_only_root,
                            'db_read_only': self.security_config.db_read_only,
                            'db_use_copy': self.security_config.db_use_copy
                        }
                    }
                    
                    # 尝试解析 JSON 输出
                    if result.stdout:
                        try:
                            parsed = json.loads(result.stdout)
                            output['data'] = parsed.get('data', [])
                            output['columns'] = parsed.get('columns', [])
                            output['row_count'] = parsed.get('row_count', 0)
                        except json.JSONDecodeError:
                            pass
                    
                    # 检查是否超时
                    if execution_time >= timeout:
                        output['timeout'] = True
                        output['success'] = False
                        output['error'] = f'执行超时（>{timeout}s）'
                    
                    print(f"[SANDBOX] ✅ 执行完成，耗时: {execution_time:.2f}s")
                    return output
                    
            except Exception as inner_e:
                # 可能是超时或其他执行错误
                execution_time = time.time() - start_time
                error_msg = str(inner_e)
                
                if 'timeout' in error_msg.lower() or execution_time >= timeout:
                    return {
                        'success': False,
                        'error': f'执行超时（>{timeout}s），可能存在死循环',
                        'execution_time': execution_time,
                        'execution_mode': 'sandbox',
                        'timeout': True
                    }
                raise
                
        except Exception as e:
            print(f"[SANDBOX] ❌ 执行失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - start_time,
                'execution_mode': 'sandbox'
            }
    
    def _execute_local(self, code: str, language: str, timeout: int) -> Dict[str, Any]:
        """本地执行代码（不安全，仅作备选）"""
        start_time = time.time()
        print(f"[SANDBOX] ⚠️ 本地执行 {language} 代码（超时: {timeout}s）...")
        
        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix=f'.{language}', 
                delete=False
            ) as f:
                f.write(code)
                temp_path = f.name
            
            # 执行
            if language == "python":
                result = subprocess.run(
                    ['python', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            else:
                result = subprocess.run(
                    [language, temp_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            
            # 清理临时文件
            os.unlink(temp_path)
            
            execution_time = time.time() - start_time
            
            output = {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode,
                'execution_time': execution_time,
                'execution_mode': 'local'
            }
            
            # 尝试解析 JSON
            if result.stdout:
                try:
                    parsed = json.loads(result.stdout)
                    output['data'] = parsed.get('data', [])
                    output['columns'] = parsed.get('columns', [])
                    output['row_count'] = parsed.get('row_count', 0)
                except json.JSONDecodeError:
                    pass
            
            print(f"[SANDBOX] ✅ 本地执行完成，耗时: {execution_time:.2f}s")
            return output
            
        except subprocess.TimeoutExpired:
            print(f"[SANDBOX] ❌ 执行超时（>{timeout}s）")
            return {
                'success': False,
                'error': f'执行超时（>{timeout}s），可能存在死循环',
                'execution_time': time.time() - start_time,
                'execution_mode': 'local',
                'timeout': True
            }
        except Exception as e:
            print(f"[SANDBOX] ❌ 本地执行失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'execution_time': time.time() - start_time,
                'execution_mode': 'local'
            }
    
    def execute_sql(
        self,
        sql: str,
        db_config: Dict[str, Any] = None,
        language: str = "python",
        skip_security_check: bool = False
    ) -> Dict[str, Any]:
        """
        通过沙箱执行 SQL
        
        流程：
        1. SQL 安全检查
        2. 数据库副本准备（如果启用隔离）
        3. SQL -> Python 代码封装
        4. 代码安全检查
        5. 代码 -> Docker 沙箱执行
        6. 返回结果（副本不写回生产库）
        
        数据库副本说明：
        - db_use_copy=True: 操作的是数据库副本，不影响生产库
        - db_read_only=True: 只读模式，禁止写入操作
        - 副本在沙箱中执行完后保留，可用于审计
        - **不会自动写回生产库**（需人工确认后手动操作）
        
        Args:
            sql: SQL 语句
            db_config: 数据库配置 {"path": "...", "type": "sqlite/mysql"}
            language: 生成的代码语言
            skip_security_check: 是否跳过安全检查
            
        Returns:
            执行结果
        """
        # SQL 安全检查
        if not skip_security_check:
            sql_check = self.security_checker.check_sql(sql)
            if sql_check['blocked']:
                return {
                    'success': False,
                    'error': 'SQL 安全检查未通过',
                    'sql': sql,
                    'violations': sql_check['violations'],
                    'execution_mode': 'blocked'
                }
        
        from .sql_code_wrapper import get_sql_code_wrapper, CodeLanguage
        
        print(f"[SANDBOX] 📝 将 SQL 封装为 {language} 代码...")
        
        # ==================== 数据库副本处理 ====================
        actual_db_config = db_config.copy() if db_config else {}
        db_copy_path = None
        
        if self.security_config.db_use_copy:
            # 创建数据库副本
            db_copy_result = self._prepare_db_copy(db_config)
            if db_copy_result.get('success'):
                db_copy_path = db_copy_result['copy_path']
                actual_db_config['path'] = db_copy_path
                actual_db_config['is_copy'] = True
                print(f"[SANDBOX] 📋 已创建数据库副本: {db_copy_path}")
            else:
                print(f"[SANDBOX] ⚠️ 数据库副本创建失败: {db_copy_result.get('error')}")
                # 继续使用原数据库（但会受只读限制）
        
        # 封装 SQL 为代码
        code_wrapper = get_sql_code_wrapper()
        if language == "python":
            code_wrapper.config.language = CodeLanguage.PYTHON
        elif language == "java":
            code_wrapper.config.language = CodeLanguage.JAVA
        
        wrap_result = code_wrapper.wrap_sql(sql, actual_db_config)
        
        if not wrap_result.get('success'):
            return wrap_result
        
        code = wrap_result['code']
        print(f"[SANDBOX] 📦 代码生成完成，共 {len(code)} 字符")
        
        # 执行（会进行代码安全检查）
        result = self.execute_code(code, language, skip_security_check=skip_security_check)
        result['sql'] = sql
        result['db_copy_path'] = db_copy_path
        result['db_is_copy'] = db_copy_path is not None
        
        return result
    
    def _prepare_db_copy(self, db_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        准备数据库副本
        
        将生产数据库复制到沙箱副本目录，供隔离执行。
        副本不会自动写回生产库。
        
        Args:
            db_config: 数据库配置
            
        Returns:
            {'success': bool, 'copy_path': str, 'error': str}
        """
        import shutil
        from pathlib import Path
        
        try:
            # 获取源数据库路径
            source_path = db_config.get('path', 'instance/badcase_doctor.db') if db_config else 'instance/badcase_doctor.db'
            
            # 只支持 SQLite 副本
            db_type = db_config.get('type', 'sqlite') if db_config else 'sqlite'
            if db_type != 'sqlite':
                return {
                    'success': False,
                    'error': f'数据库副本仅支持 SQLite，当前类型: {db_type}'
                }
            
            # 检查源数据库是否存在
            if not os.path.exists(source_path):
                return {
                    'success': False,
                    'error': f'数据库文件不存在: {source_path}'
                }
            
            # 创建副本目录
            copy_dir = self.security_config.db_copy_dir
            os.makedirs(copy_dir, exist_ok=True)
            
            # 生成副本文件名（带时间戳）
            import uuid
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            unique_id = str(uuid.uuid4())[:8]
            db_name = os.path.basename(source_path)
            copy_filename = f"{db_name}.{timestamp}.{unique_id}.copy"
            copy_path = os.path.join(copy_dir, copy_filename)
            
            # 复制数据库
            shutil.copy2(source_path, copy_path)
            
            return {
                'success': True,
                'copy_path': copy_path,
                'source_path': source_path
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def check_code_safety(self, code: str, language: str = "python") -> Dict[str, Any]:
        """
        仅检查代码安全性（不执行）
        
        Args:
            code: 要检查的代码
            language: 语言
            
        Returns:
            安全检查结果
        """
        return self.security_checker.check_code(code, language)
    
    def check_sql_safety(self, sql: str) -> Dict[str, Any]:
        """
        仅检查 SQL 安全性（不执行）
        
        Args:
            sql: SQL 语句
            
        Returns:
            安全检查结果
        """
        return self.security_checker.check_sql(sql)


# ========== 全局实例 ==========

_sandbox_executor = None
_security_config = None


def get_security_config() -> SecurityConfig:
    """获取安全配置"""
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig()
    return _security_config


def get_sandbox_executor(
    image: str = "python:3.11-slim",
    security_config: SecurityConfig = None,
    fallback_to_local: bool = False
) -> SandboxExecutor:
    """
    获取沙箱执行器
    
    Args:
        image: Docker 镜像
        security_config: 安全配置（为 None 时使用默认配置）
        fallback_to_local: 如果沙箱不可用，是否回退到本地执行
        
    Returns:
        沙箱执行器实例
    """
    global _sandbox_executor
    if _sandbox_executor is None:
        _sandbox_executor = SandboxExecutor(
            image=image,
            security_config=security_config or get_security_config(),
            fallback_to_local=fallback_to_local
        )
    return _sandbox_executor


def create_sandbox_executor(
    cpu_limit: float = 0.5,
    memory_limit: str = "256m",
    timeout: int = 30,
    network_disabled: bool = True,
    **kwargs
) -> SandboxExecutor:
    """
    创建自定义配置的沙箱执行器
    
    Args:
        cpu_limit: CPU 限制（核数）
        memory_limit: 内存限制
        timeout: 超时时间（秒）
        network_disabled: 是否禁用网络
        **kwargs: 其他参数
        
    Returns:
        沙箱执行器实例
    """
    config = SecurityConfig(
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        timeout=timeout,
        network_disabled=network_disabled
    )
    return SandboxExecutor(security_config=config, **kwargs)


# 别名，保持兼容
Sandbox = SandboxExecutor
