package com.badcase.sdk.spring;

import com.badcase.sdk.BadCaseCollector;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

/**
 * BadCase SDK 自动配置 - Spring Boot Starter
 * 添加依赖后自动注册 BadCaseCollector，配合 Actuator 暴露 /actuator/prometheus
 */
@AutoConfiguration
@ConditionalOnClass(MeterRegistry.class)
@ConditionalOnProperty(prefix = "badcase.sdk", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(BadCaseSdkProperties.class)
public class BadCaseCollectorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BadCaseCollector.class)
    public BadCaseCollector badCaseCollector(MeterRegistry registry, BadCaseSdkProperties properties) {
        return new BadCaseCollector(registry, properties.getApp(), properties.getEnv());
    }
}
