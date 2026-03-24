package com.badcase.sdk.labels;

import java.util.regex.Pattern;

/**
 * Label 基数控制：将数值映射为有限 bucket
 */
public final class LabelUtils {

    private static final Pattern DATE_SUFFIX = Pattern.compile("-\\d{4}-\\d{2}-\\d{2}$");

    private LabelUtils() {}

    public static String bucketTemperature(Double t) {
        if (t == null) return "t_unknown";
        if (t <= 0.0) return "t_0_0";
        if (t <= 0.2) return "t_0_0_0_2";
        if (t <= 0.7) return "t_0_2_0_7";
        if (t < 1.0) return "t_0_7_1_0";
        return "t_1_0plus";
    }

    public static String bucketTopP(Double p) {
        if (p == null) return "p_unknown";
        if (p <= 0.1) return "p_0_1";
        if (p <= 0.9) return "p_0_1_0_9";
        if (p < 1.0) return "p_0_9_1_0";
        return "p_1_0";
    }

    public static String bucketMaxTokens(Integer n) {
        if (n == null) return "mt_unknown";
        if (n <= 256) return "mt_256";
        if (n <= 512) return "mt_512";
        if (n <= 1024) return "mt_1024";
        if (n <= 4096) return "mt_4096";
        return "mt_4096plus";
    }

    public static String bucketInputTokens(Integer n) {
        if (n == null) return "in_unknown";
        if (n <= 512) return "in_0_512";
        if (n <= 2048) return "in_512_2k";
        if (n <= 8192) return "in_2k_8k";
        return "in_8kplus";
    }

    public static String bucketOutputTokens(Integer n) {
        if (n == null) return "out_unknown";
        if (n <= 256) return "out_0_256";
        if (n <= 1024) return "out_256_1k";
        return "out_1kplus";
    }

    public static String normalizeModel(String model) {
        if (model == null || model.isBlank()) return "unknown";
        String s = model.trim();
        s = DATE_SUFFIX.matcher(s).replaceAll("");
        return s.length() > 64 ? s.substring(0, 64) : (s.isEmpty() ? "unknown" : s);
    }

    public static String normalizeBadcaseType(String t) {
        if (t == null || t.isBlank()) return "none";
        String v = t.trim().toLowerCase();
        return switch (v) {
            case "none", "hallucination", "format_error", "refuse", "tool_error", "timeout", "parse_error" -> v;
            default -> "other";
        };
    }

    public static String normalizeErrorType(String t) {
        if (t == null || t.isBlank()) return "unknown";
        String v = t.trim().toLowerCase();
        return switch (v) {
            case "timeout", "http_429", "http_5xx", "http_4xx", "parse_error", "network_error" -> v;
            default -> "other";
        };
    }

    public static String normalizeStreamReason(String r) {
        if (r == null || r.isBlank()) return "unknown";
        String v = r.trim().toLowerCase();
        return switch (v) {
            case "client_cancel", "upstream_close", "timeout", "error" -> v;
            default -> "unknown";
        };
    }

    public static String normalizeFinishReason(String r) {
        if (r == null || r.isBlank()) return "unknown";
        String v = r.trim().toLowerCase();
        return switch (v) {
            case "stop", "length", "tool_calls", "content_filter", "error" -> v;
            default -> "unknown";
        };
    }
}
