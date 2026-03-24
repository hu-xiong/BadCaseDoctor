package com.badcase.sdk.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * badcase.sdk 配置属性
 */
@ConfigurationProperties(prefix = "badcase.sdk")
public class BadCaseSdkProperties {

    private boolean enabled = true;
    private String app = "unknown";
    private String env = "dev";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getApp() {
        return app;
    }

    public void setApp(String app) {
        this.app = app;
    }

    public String getEnv() {
        return env;
    }

    public void setEnv(String env) {
        this.env = env;
    }
}
