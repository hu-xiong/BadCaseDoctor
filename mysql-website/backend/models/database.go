package models

import (
	"fmt"
	"mysql-website-backend/config"
	"time"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

// InitDB 初始化数据库连接
func InitDB(cfg *config.DatabaseConfig) error {
	var err error
	
	// 配置 GORM Logger
	newLogger := logger.Default.LogMode(logger.Info)
	
	DB, err = gorm.Open(mysql.Open(cfg.DSN), &gorm.Config{
		Logger: newLogger,
	})
	if err != nil {
		return fmt.Errorf("failed to connect to database: %w", err)
	}

	// 获取底层 sql.DB
	sqlDB, err := DB.DB()
	if err != nil {
		return fmt.Errorf("failed to get database instance: %w", err)
	}

	// 设置连接池
	sqlDB.SetMaxIdleConns(cfg.MaxIdleConns)
	sqlDB.SetMaxOpenConns(cfg.MaxOpenConns)
	sqlDB.SetConnMaxLifetime(time.Duration(cfg.ConnMaxLifetime) * time.Second)

	return nil
}

// AutoMigrate 自动迁移数据库表
func AutoMigrate() error {
	return DB.AutoMigrate(
		&User{},
		&Download{},
		&DownloadHistory{},
		&DocCategory{},
		&Doc{},
		&Post{},
		&Comment{},
		&News{},
	)
}

// GetDB 获取数据库实例
func GetDB() *gorm.DB {
	return DB
}
