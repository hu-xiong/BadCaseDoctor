package main

import (
	"fmt"
	"log"

	"mysql-website-backend/config"
	"mysql-website-backend/models"
	"mysql-website-backend/routes"

	"github.com/gin-gonic/gin"
)

func main() {
	// 加载配置
	cfg, err := config.Load("config/config.yaml")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// 设置 Gin 模式
	gin.SetMode(cfg.Server.Mode)

	// 初始化数据库
	if err := models.InitDB(&cfg.Database); err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}

	// 自动迁移
	if err := models.AutoMigrate(); err != nil {
		log.Fatalf("Failed to auto migrate: %v", err)
	}

	// 初始化默认数据
	initDefaultData()

	// 创建 Gin 引擎
	router := gin.Default()

	// 设置路由
	routes.SetupRoutes(router)

	// 启动服务器
	addr := fmt.Sprintf(":%d", cfg.Server.Port)
	log.Printf("Starting server on %s", addr)
	if err := router.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}

// initDefaultData 初始化默认数据
func initDefaultData() {
	// 检查是否已有数据
	var count int64
	models.DB.Model(&models.Download{}).Count(&count)
	if count > 0 {
		return
	}

	// 初始化下载数据
	downloads := []models.Download{
		{
			Name:          "MySQL Community Server",
			Version:       "8.4.0",
			Edition:       "Community",
			OS:            "Linux",
			FilePath:      "/downloads/mysql-8.4.0-linux-glibc2.28-x86_64.tar.gz",
			FileSize:      156789456,
			SHA256:        "a1b2c3d4e5f6...",
			Description:   "MySQL Community Server is a freely downloadable version of the world's most popular open source database.",
			DownloadCount: 0,
		},
		{
			Name:          "MySQL Community Server",
			Version:       "8.4.0",
			Edition:       "Community",
			OS:            "Windows",
			FilePath:      "/downloads/mysql-installer-community-8.4.0.msi",
			FileSize:      245678912,
			SHA256:        "b2c3d4e5f6g7...",
			Description:   "MySQL Installer for Windows provides an easy to use, wizard-based installation experience for MySQL.",
			DownloadCount: 0,
		},
		{
			Name:          "MySQL Workbench",
			Version:       "8.0.36",
			Edition:       "Community",
			OS:            "Windows",
			FilePath:      "/downloads/mysql-workbench-community-8.0.36-winx64.msi",
			FileSize:      34567890,
			SHA256:        "c3d4e5f6g7h8...",
			Description:   "MySQL Workbench is a unified visual tool for database architects, developers, and DBAs.",
			DownloadCount: 0,
		},
		{
			Name:          "MySQL Shell",
			Version:       "8.4.0",
			Edition:       "Community",
			OS:            "Linux",
			FilePath:      "/downloads/mysql-shell-8.4.0-linux-glibc2.28-x86_64.tar.gz",
			FileSize:      56789012,
			SHA256:        "d4e5f6g7h8i9...",
			Description:   "MySQL Shell is an advanced MySQL client and code editor with Python and JavaScript modes.",
			DownloadCount: 0,
		},
		{
			Name:          "MySQL Router",
			Version:       "8.4.0",
			Edition:       "Community",
			OS:            "Linux",
			FilePath:      "/downloads/mysql-router-8.4.0-linux-glibc2.28-x86_64.tar.gz",
			FileSize:      12345678,
			SHA256:        "e5f6g7h8i9j0...",
			Description:   "MySQL Router is middleware that provides transparent routing between your application and MySQL servers.",
			DownloadCount: 0,
		},
	}

	for _, d := range downloads {
		models.DB.Create(&d)
	}

	// 初始化文档分类
	categories := []models.DocCategory{
		{Name: "Getting Started", SortOrder: 1},
		{Name: "Installation", SortOrder: 2},
		{Name: "Configuration", SortOrder: 3},
		{Name: "Tutorials", SortOrder: 4},
		{Name: "Reference", SortOrder: 5},
	}

	for _, cat := range categories {
		models.DB.Create(&cat)
	}

	// 初始化文档
	docs := []models.Doc{
		{
			CategoryID: 1,
			Title:      "What is MySQL?",
			Content:    "MySQL is the world's most popular open source database...",
			Slug:       "what-is-mysql",
			Status:     1,
		},
		{
			CategoryID: 2,
			Title:      "Installing MySQL on Linux",
			Content:    "This tutorial describes how to install MySQL on Linux...",
			Slug:       "installing-mysql-linux",
			Status:     1,
		},
		{
			CategoryID: 3,
			Title:      "MySQL Configuration File",
			Content:    "The MySQL configuration file my.cnf contains various settings...",
			Slug:       "mysql-configuration",
			Status:     1,
		},
	}

	for _, doc := range docs {
		models.DB.Create(&doc)
	}

	// 初始化新闻
	news := []models.News{
		{
			Title:     "MySQL 8.4 LTS Released",
			Summary:   "MySQL 8.4, the first Long Term Support release in the 8.x series, is now available.",
			Content:   "We are pleased to announce the release of MySQL 8.4, our first LTS release...",
			ImageURL:  "/images/news/mysql-8.4-release.png",
			Status:    1,
		},
		{
			Title:     "MySQL HeatWave Now Available on OCI",
			Summary:   "MySQL HeatWave is a fully managed database service for OLTP, OLAP, and ML.",
			Content:   "MySQL HeatWave is now available on Oracle Cloud Infrastructure...",
			ImageURL:  "/images/news/heatwave.png",
			Status:    1,
		},
		{
			Title:     "MySQL Community Server 8.0.37 Available",
			Summary:   "This is a maintenance release for MySQL Community Server 8.0.",
			Content:   "MySQL Community Server 8.0.37 is now available for download...",
			ImageURL:  "/images/news/mysql-8.0.37.png",
			Status:    1,
		},
	}

	for _, n := range news {
		models.DB.Create(&n)
	}

	log.Println("Default data initialized successfully")
}
