package config

import (
	"os"
	"strconv"
)

// Config 应用配置
type Config struct {
	Environment  string
	DatabaseURL  string
	JWTSecret    string
	ServerPort   string
	LogLevel     string
}

// LoadConfig 加载配置
func LoadConfig() *Config {
	cfg := &Config{
		Environment:  getEnv("ENVIRONMENT", "development"),
		DatabaseURL:  getEnv("DATABASE_URL", ""),
		JWTSecret:    getEnv("JWT_SECRET", ""),
		ServerPort:   getEnv("PORT", "8000"),
		LogLevel:     getEnv("LOG_LEVEL", "info"),
	}
	if cfg.Environment == "production" {
		if cfg.JWTSecret == "" || cfg.JWTSecret == "change-me" || cfg.JWTSecret == "your-secret-key-here" || cfg.JWTSecret == "your-jwt-secret-key-here" {
			panic("JWT_SECRET must be set to a strong value in production")
		}
		if cfg.DatabaseURL == "" {
			panic("DATABASE_URL must be set in production")
		}
	} else if cfg.JWTSecret == "" {
		// 仅开发兜底；生产已在上方拒绝
		cfg.JWTSecret = "dev-only-change-me"
	}
	return cfg
}

// getEnv 获取环境变量，如果不存在则返回默认值
func getEnv(key, defaultValue string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return defaultValue
}

// getEnvAsInt 获取环境变量并转换为整数
func getEnvAsInt(key string, defaultValue int) int {
	if value, exists := os.LookupEnv(key); exists {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

// getEnvAsBool 获取环境变量并转换为布尔值
func getEnvAsBool(key string, defaultValue bool) bool {
	if value, exists := os.LookupEnv(key); exists {
		if boolValue, err := strconv.ParseBool(value); err == nil {
			return boolValue
		}
	}
	return defaultValue
}