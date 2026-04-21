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
	return &Config{
		Environment:  getEnv("ENVIRONMENT", "development"),
		DatabaseURL:  getEnv("DATABASE_URL", "mysql://root:hx123456@117.72.33.38:33106/bad_case"),
		JWTSecret:    getEnv("JWT_SECRET", "your-secret-key-here"),
		ServerPort:   getEnv("PORT", "8000"),
		LogLevel:     getEnv("LOG_LEVEL", "info"),
	}
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