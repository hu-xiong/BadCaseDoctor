package com.badcase.sdk;

import java.time.Duration;
import java.time.Instant;
import java.util.function.Supplier;

/**
 * LLM 调用观测：显式 start/stop 或 observe(callable)
 */
public final class LlmObservation {

    private final BadCaseCollector collector;
    private final String provider;
    private final String endpoint;
    private final String model;
    private final boolean streaming;
    private final Instant start;
    private String result = "success";
    private Long inputTokens;
    private Long outputTokens;

    private LlmObservation(BadCaseCollector collector, String provider, String endpoint, String model, boolean streaming) {
        this.collector = collector;
        this.provider = provider;
        this.endpoint = endpoint;
        this.model = model;
        this.streaming = streaming;
        this.start = Instant.now();
    }

    public static LlmObservation start(BadCaseCollector collector, String provider, String endpoint, String model, boolean streaming) {
        LlmContext ctx = LlmContext.create();
        LlmContext.setCurrent(ctx);
        return new LlmObservation(collector, provider, endpoint, model, streaming);
    }

    public static <T> T observe(BadCaseCollector collector, String provider, String endpoint, String model, boolean streaming, Supplier<T> callable) {
        LlmObservation obs = start(collector, provider, endpoint, model, streaming);
        try {
            T r = callable.get();
            obs.stop("success", null, null);
            return r;
        } catch (Exception e) {
            obs.stop("fail", null, null);
            collector.recordError(provider, endpoint, model, "other", "");
            throw e;
        }
    }

    public LlmObservation withInputTokens(long n) {
        this.inputTokens = n;
        return this;
    }

    public LlmObservation withOutputTokens(long n) {
        this.outputTokens = n;
        return this;
    }

    public void stop(String result, Long inputTokens, Long outputTokens) {
        stop(result, inputTokens, outputTokens, "none");
    }

    public void stop(String result, Long inputTokens, Long outputTokens, String badcaseType) {
        if (inputTokens != null) this.inputTokens = inputTokens;
        if (outputTokens != null) this.outputTokens = outputTokens;
        this.result = result;
        String bt = (badcaseType != null && !badcaseType.isBlank()) ? badcaseType : "none";

        Duration dur = Duration.between(start, Instant.now());
        collector.recordRequest(provider, endpoint, model, streaming, result);
        collector.recordDuration(provider, endpoint, model, streaming, result, dur);
        if (this.inputTokens != null) {
            collector.recordTokens(provider, endpoint, model, "input", this.inputTokens);
        }
        if (this.outputTokens != null) {
            collector.recordTokens(provider, endpoint, model, "output", this.outputTokens);
        }
        if (this.inputTokens != null && this.outputTokens != null) {
            collector.recordTokens(provider, endpoint, model, "total", this.inputTokens + this.outputTokens);
        }
        collector.recordBadcase(provider, endpoint, model, streaming, bt);

        LlmContext.setCurrent(null);
    }

    /** 便捷方法：成功结束并标注 badcase 类型 */
    public void stop(String badcaseType) {
        stop("success", null, null, badcaseType);
    }
}
