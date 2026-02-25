# utils/metrics.py
"""
Prometheus 性能指标收集模块
"""

from prometheus_client import Counter, Histogram, Gauge
import time

# ==================== Agent 执行指标 ====================

# Agent 执行计数器（按类型）
agent_execute_total = Counter(
    'agent_execute_total',
    'Agent 执行总数',
    ['agent_type', 'status']  # status: success, failure
)

# Agent 执行耗时（直方图）
agent_execute_duration_seconds = Histogram(
    'agent_execute_duration_seconds',
    'Agent 执行耗时（秒）',
    ['agent_type'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
)

# Agent 执行中的请求数
agent_execute_in_progress = Gauge(
    'agent_execute_in_progress',
    'Agent 执行中的请求数',
    ['agent_type']
)

# ==================== 测试执行指标 ====================

# 测试执行总数
test_execute_total = Counter(
    'test_execute_total',
    '测试执行总数',
    ['status']  # status: success, failure
)

# 测试执行耗时
test_execute_duration_seconds = Histogram(
    'test_execute_duration_seconds',
    '测试执行耗时（秒）',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
)

# 发现的 Bug 数
bugs_found_total = Counter(
    'bugs_found_total',
    '发现的 Bug 总数',
    ['severity']  # severity: critical, high, medium, low
)

# ==================== 意图识别指标 ====================

# 意图识别总数
intent_detection_total = Counter(
    'intent_detection_total',
    '意图识别总数',
    ['detected_intent', 'status']
)

# 意图识别耗时
intent_detection_duration_seconds = Histogram(
    'intent_detection_duration_seconds',
    '意图识别耗时（秒）',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)

# ==================== Bug 保存指标 ====================

# Bug 保存总数
bugs_saved_total = Counter(
    'bugs_saved_total',
    'Bug 保存总数',
    ['status']  # status: success, failure
)

# Bug 保存耗时
bugs_saved_duration_seconds = Histogram(
    'bugs_saved_duration_seconds',
    'Bug 保存耗时（秒）',
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0)
)

# 单个 Bug 保存耗时（分布）
bugs_saved_per_second = Gauge(
    'bugs_saved_per_second',
    '每秒保存的 Bug 数'
)

# ==================== API 调用指标 ====================

# API 调用总数
api_requests_total = Counter(
    'api_requests_total',
    'API 调用总数',
    ['method', 'endpoint', 'status_code']
)

# API 调用耗时
api_request_duration_seconds = Histogram(
    'api_request_duration_seconds',
    'API 调用耗时（秒）',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0)
)

# ==================== LLM 调用指标 ====================

# LLM 调用总数
llm_calls_total = Counter(
    'llm_calls_total',
    'LLM 调用总数',
    ['model', 'status']
)

# LLM 调用耗时
llm_call_duration_seconds = Histogram(
    'llm_call_duration_seconds',
    'LLM 调用耗时（秒）',
    ['model'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
)

# LLM token 使用
llm_tokens_used = Counter(
    'llm_tokens_used',
    'LLM token 使用数',
    ['model', 'token_type']  # token_type: prompt, completion, total
)


class MetricsRecorder:
    """指标记录器上下文管理器"""
    
    def __init__(self, metric_name, labels=None):
        """
        初始化指标记录器
        
        Args:
            metric_name: 指标名称
            labels: 标签字典
        """
        self.metric_name = metric_name
        self.labels = labels or {}
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        # 记录耗时指标
        if self.metric_name == 'agent_execute':
            agent_execute_duration_seconds.labels(
                agent_type=self.labels.get('agent_type', 'unknown')
            ).observe(duration)
        
        elif self.metric_name == 'test_execute':
            test_execute_duration_seconds.observe(duration)
        
        elif self.metric_name == 'intent_detection':
            intent_detection_duration_seconds.observe(duration)
        
        elif self.metric_name == 'bugs_saved':
            bugs_saved_duration_seconds.observe(duration)
        
        elif self.metric_name == 'api_request':
            api_request_duration_seconds.labels(
                method=self.labels.get('method', 'GET'),
                endpoint=self.labels.get('endpoint', 'unknown')
            ).observe(duration)
        
        elif self.metric_name == 'llm_call':
            llm_call_duration_seconds.labels(
                model=self.labels.get('model', 'unknown')
            ).observe(duration)


def record_agent_execute(agent_type, status='success'):
    """记录 Agent 执行指标"""
    agent_execute_total.labels(
        agent_type=agent_type,
        status=status
    ).inc()


def record_test_execute(status='success'):
    """记录测试执行指标"""
    test_execute_total.labels(status=status).inc()


def record_bug_found(severity='medium'):
    """记录发现的 Bug"""
    bugs_found_total.labels(severity=severity).inc()


def record_intent_detection(intent, status='success'):
    """记录意图识别"""
    intent_detection_total.labels(
        detected_intent=intent,
        status=status
    ).inc()


def record_bugs_saved(count, status='success'):
    """记录 Bug 保存"""
    bugs_saved_total.labels(status=status).inc()
    bugs_saved_per_second.set(count)


def record_api_request(method, endpoint, status_code):
    """记录 API 调用"""
    api_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_code
    ).inc()


def record_llm_call(model, status='success', tokens=0, token_type='total'):
    """记录 LLM 调用"""
    llm_calls_total.labels(
        model=model,
        status=status
    ).inc()
    
    if tokens > 0:
        llm_tokens_used.labels(
            model=model,
            token_type=token_type
        ).inc(tokens)
