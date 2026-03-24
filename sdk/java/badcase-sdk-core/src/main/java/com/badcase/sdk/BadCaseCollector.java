package com.badcase.sdk;

import com.badcase.sdk.labels.LabelUtils;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * BadCase 指标采集器 - 与 Python SDK 指标命名对齐
 */
public class BadCaseCollector {

    private final String app;
    private final String env;
    private final MeterRegistry registry;

    private static final double[] DURATION_BUCKETS = {0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0};

    public BadCaseCollector(MeterRegistry registry, String app, String env) {
        this.registry = registry;
        this.app = app != null ? app : "unknown";
        this.env = env != null ? env : "dev";
    }

    public BadCaseCollector(MeterRegistry registry) {
        this(registry, "unknown", "dev");
    }

    public void recordRequest(String provider, String endpoint, String model, boolean streaming, String result) {
        Counter.builder("bdc_llm_requests_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("streaming", streaming ? "true" : "false")
                .tag("result", result)
                .register(registry)
                .increment();
    }

    public void recordError(String provider, String endpoint, String model, String errorType, String httpStatus) {
        Counter.builder("bdc_llm_errors_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("error_type", LabelUtils.normalizeErrorType(errorType))
                .tag("http_status", httpStatus != null ? httpStatus : "0")
                .register(registry)
                .increment();
    }

    public void recordDuration(String provider, String endpoint, String model, boolean streaming, String result, Duration duration) {
        Timer.builder("bdc_llm_duration_seconds")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("streaming", streaming ? "true" : "false")
                .tag("result", result)
                .publishPercentiles()
                .register(registry)
                .record(duration);
    }

    public void recordTokens(String provider, String endpoint, String model, String kind, long count) {
        Counter.builder("bdc_llm_tokens_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("kind", kind)
                .register(registry)
                .increment(count);
    }

    public void recordBadcase(String provider, String endpoint, String model, boolean streaming, String badcaseType) {
        Counter.builder("bdc_llm_badcase_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("streaming", streaming ? "true" : "false")
                .tag("badcase_type", LabelUtils.normalizeBadcaseType(badcaseType))
                .register(registry)
                .increment();
    }

    public void recordTimeToFirstToken(String provider, String endpoint, String model, String result, Duration duration) {
        Timer.builder("bdc_llm_time_to_first_token_seconds")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("result", result)
                .register(registry)
                .record(duration);
    }

    public void recordStreamDuration(String provider, String endpoint, String model, String result, Duration duration) {
        Timer.builder("bdc_llm_stream_duration_seconds")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("result", result)
                .register(registry)
                .record(duration);
    }

    public void recordStreamChunks(String provider, String endpoint, String model, long count) {
        Counter.builder("bdc_llm_stream_chunks_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .register(registry)
                .increment(count);
    }

    public void recordStreamBytes(String provider, String endpoint, String model, long count) {
        Counter.builder("bdc_llm_stream_bytes_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .register(registry)
                .increment(count);
    }

    public void recordStreamInterrupted(String provider, String endpoint, String model, String reason) {
        Counter.builder("bdc_llm_stream_interrupted_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("reason", LabelUtils.normalizeStreamReason(reason))
                .register(registry)
                .increment();
    }

    public void recordFinishReason(String provider, String endpoint, String model, String reason) {
        Counter.builder("bdc_llm_finish_reason_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("reason", LabelUtils.normalizeFinishReason(reason))
                .register(registry)
                .increment();
    }

    public void recordToolCall(String provider, String endpoint, String model, String toolName, String result) {
        String tn = toolName != null && toolName.length() > 32 ? toolName.substring(0, 32) : toolName;
        Counter.builder("bdc_llm_tool_calls_total")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("endpoint", endpoint)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("tool_name", tn)
                .tag("result", result)
                .register(registry)
                .increment();
    }

    public void recordRetrieval(String provider, String model, String result, Duration duration, Integer docsCount) {
        Timer.builder("bdc_llm_retrieval_duration_seconds")
                .tag("app", app)
                .tag("env", env)
                .tag("provider", provider)
                .tag("model", LabelUtils.normalizeModel(model))
                .tag("result", result)
                .register(registry)
                .record(duration);
        if (docsCount != null && docsCount > 0) {
            Counter.builder("bdc_llm_retrieval_docs_total")
                    .tag("app", app)
                    .tag("env", env)
                    .tag("provider", provider)
                    .tag("model", LabelUtils.normalizeModel(model))
                    .register(registry)
                    .increment(docsCount);
        }
    }

    public void recordWorkflowStep(String workflowId, String workflowStep, String stepType, String result, Duration duration) {
        String wf = workflowId != null && workflowId.length() > 32 ? workflowId.substring(0, 32) : workflowId;
        String ws = workflowStep != null && workflowStep.length() > 32 ? workflowStep.substring(0, 32) : workflowStep;
        String st = stepType != null && stepType.length() > 32 ? stepType.substring(0, 32) : stepType;
        Counter.builder("bdc_llm_workflow_steps_total")
                .tag("app", app)
                .tag("env", env)
                .tag("workflow_id", wf)
                .tag("workflow_step", ws)
                .tag("step_type", st)
                .tag("result", result)
                .register(registry)
                .increment();
        if (duration != null) {
            Timer.builder("bdc_llm_workflow_duration_seconds")
                    .tag("app", app)
                    .tag("env", env)
                    .tag("workflow_id", wf)
                    .tag("workflow_step", ws)
                    .tag("step_type", st)
                    .register(registry)
                    .record(duration);
        }
    }
}
