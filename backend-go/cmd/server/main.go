package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"badcasedoctor/backend-go/internal/api/routes"
	"badcasedoctor/backend-go/internal/config"
	"badcasedoctor/backend-go/internal/models"
	"badcasedoctor/backend-go/internal/utils"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
)

func main() {
	// 加载环境变量
	if err := godotenv.Load(); err != nil {
		log.Println("Warning: .env file not found")
	}

	// 初始化配置
	cfg := config.LoadConfig()

	// 初始化数据库
	if err := models.InitDB(cfg.DatabaseURL); err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	// 自动迁移数据库模型
	if err := models.AutoMigrate(); err != nil {
		log.Fatalf("Failed to migrate database: %v", err)
	}

	// 初始化Redis
	redisClient := utils.NewRedisClient()
	defer redisClient.Close()

	// 设置Gin模式
	if cfg.Environment == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	// 创建Gin引擎
	r := gin.Default()

	// 配置CORS
	r.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
	}))

	// 注册路由
	routes.SetupRoutes(r)

	// 获取端口
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	// 启动服务器
	serverAddr := fmt.Sprintf(":%s", port)
	srv := &http.Server{
		Addr:    serverAddr,
		Handler: r,
	}

	// 启动服务器（非阻塞）
	go func() {
		log.Printf("Server starting on %s", serverAddr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// 等待中断信号以优雅地关闭服务器
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	// 设置5秒的超时时间
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// 关闭服务器
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited gracefully")
}