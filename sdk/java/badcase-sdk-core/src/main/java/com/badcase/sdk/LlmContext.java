package com.badcase.sdk;

import java.util.Optional;
import java.util.UUID;

/**
 * Trace 上下文：conversation_id、request_id、span_id
 */
public final class LlmContext {

    private final String conversationId;
    private final String requestId;
    private final String spanId;
    private final String parentSpanId;
    private final String workflowId;
    private final String workflowStep;

    private static final ThreadLocal<LlmContext> CURRENT = new ThreadLocal<>();

    public LlmContext(
            String conversationId,
            String requestId,
            String spanId,
            String parentSpanId,
            String workflowId,
            String workflowStep) {
        this.conversationId = conversationId;
        this.requestId = requestId != null ? requestId : shortUuid();
        this.spanId = spanId;
        this.parentSpanId = parentSpanId;
        this.workflowId = workflowId;
        this.workflowStep = workflowStep;
    }

    public static LlmContext create(String conversationId) {
        return new LlmContext(conversationId, shortUuid(), shortUuid(), null, null, null);
    }

    public static LlmContext create() {
        return new LlmContext(null, shortUuid(), shortUuid(), null, null, null);
    }

    public LlmContext childSpan() {
        return new LlmContext(
                conversationId,
                shortUuid(),
                shortUuid(),
                spanId != null ? spanId : requestId,
                workflowId,
                workflowStep);
    }

    public static void setCurrent(LlmContext ctx) {
        if (ctx != null) {
            CURRENT.set(ctx);
        } else {
            CURRENT.remove();
        }
    }

    public static Optional<LlmContext> getCurrent() {
        return Optional.ofNullable(CURRENT.get());
    }

    private static String shortUuid() {
        return UUID.randomUUID().toString().substring(0, 8);
    }

    public String getConversationId() { return conversationId; }
    public String getRequestId() { return requestId; }
    public String getSpanId() { return spanId; }
    public String getParentSpanId() { return parentSpanId; }
    public String getWorkflowId() { return workflowId; }
    public String getWorkflowStep() { return workflowStep; }
}
