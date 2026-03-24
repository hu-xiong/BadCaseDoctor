// Java SDK 使用示例
// 1. 添加 Maven 依赖:
//    <dependency>
//        <groupId>com.badcase</groupId>
//        <artifactId>badcase-sdk-spring-boot-starter</artifactId>
//        <version>0.1.0</version>
//    </dependency>
//
// 2. application.yml (可选):
//    badcase:
//      sdk:
//        enabled: true
//        app: my-llm-service
//        env: prod
//
// 3. 启用 Actuator Prometheus: management.endpoints.web.exposure.include=prometheus

package com.example;

import com.badcase.sdk.BadCaseCollector;
import com.badcase.sdk.LlmObservation;
import org.springframework.stereotype.Service;

@Service
public class ChatService {

    private final BadCaseCollector collector;

    public ChatService(BadCaseCollector collector) {
        this.collector = collector;
    }

    // 方式一：observe 包裹
    public String callLlm(String prompt) {
        return LlmObservation.observe(
                collector,
                "qwen",
                "chat",
                "qwen-plus",
                false,
                () -> doCallLlm(prompt)
        );
    }

    // 方式二：显式 start/stop
    public String callLlmExplicit(String prompt) {
        var obs = LlmObservation.start(collector, "qwen", "chat", "qwen-plus", false);
        try {
            String result = doCallLlm(prompt);
            obs.withInputTokens(100).withOutputTokens(50).stop("success", 100L, 50L);
            return result;
        } catch (Exception e) {
            obs.stop("fail", null, null);
            throw e;
        }
    }

    // 工具调用记录
    public void recordToolCall(String toolName, boolean success) {
        collector.recordToolCall("qwen", "chat", "qwen-plus", toolName, success ? "success" : "fail");
    }

    private String doCallLlm(String prompt) {
        // 实际 LLM 调用
        return "response";
    }
}
