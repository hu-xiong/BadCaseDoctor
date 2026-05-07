package config

import (
	"os"
	"sync"

	"gopkg.in/yaml.v3"
)

// Config 应用配置
type Config struct {
	Server   ServerConfig   `yaml:"server"`
	Database DatabaseConfig `yaml:"database"`
	JWT      JWTConfig      `yaml:"jwt"`
	App      AppConfig      `yaml:"app"`
}

// ServerConfig 服务器配置
type ServerConfig struct {
	Port int    `yaml:"port"`
	Mode string `yaml:"mode"`
}

// DatabaseConfig 数据库配置
type DatabaseConfig struct {
	DSN            string `yaml:"dsn"`
	MaxIdleConns   int    `yaml:"max_idle_conns"`
	MaxOpenConns   int    `yaml:"max_open_conns"`
	ConnMaxLifetime int   `yaml:"conn_max_lifetime"`
}

// JWTConfig JWT配置
type JWTConfig struct {
	Secret      string `yaml:"secret"`
	ExpireHours int    `yaml:"expire_hours"`
}

// AppConfig 应用配置
type AppConfig struct {
	Name    string `yaml:"name"`
	Version string `yaml:"version"`
}

var (
	cfg  *Config
	once sync.Once
)

// Load 加载配置文件
func Load(path string) (*Config, error) {
	var err error
	once.Do(func() {
		var data []byte
		data, err = os.ReadFile(path)
		if err != nil {
			return
		}

		cfg = &Config{}
		err = yaml.Unmarshal(data, cfg)
	})

	return cfg, err
}

// Get 获取配置实例
func Get() *Config {
	return cfg
}
