package routes

import (
	"mysql-website-backend/handlers"
	"mysql-website-backend/middleware"

	"github.com/gin-gonic/gin"
)

// SetupRoutes 配置所有路由
func SetupRoutes(router *gin.Engine) {
	// 应用全局中间件
	router.Use(middleware.LoggerMiddleware())
	router.Use(middleware.RecoveryMiddleware())
	router.Use(middleware.CORSMiddleware())

	// 初始化处理器
	authHandler := &handlers.AuthHandler{}
	downloadHandler := &handlers.DownloadHandler{}
	docsHandler := &handlers.DocsHandler{}
	communityHandler := &handlers.CommunityHandler{}
	newsHandler := &handlers.NewsHandler{}

	// API v1 路由组
	v1 := router.Group("/api/v1")
	{
		// 认证路由
		auth := v1.Group("/auth")
		{
			auth.POST("/register", authHandler.Register)
			auth.POST("/login", authHandler.Login)
			auth.POST("/logout", authHandler.Logout)
			auth.GET("/me", middleware.AuthMiddleware(), authHandler.Me)
		}

		// 下载路由
		downloads := v1.Group("/downloads")
		{
			downloads.GET("", downloadHandler.List)
			downloads.GET("/:id", downloadHandler.Detail)
			downloads.POST("/:id/record", middleware.AuthMiddleware(), downloadHandler.Record)
			downloads.GET("/edition/:edition", downloadHandler.GetByEdition)
			downloads.GET("/os/:os", downloadHandler.GetByOS)
		}

		// 文档路由
		docs := v1.Group("/docs")
		{
			docs.GET("/categories", docsHandler.ListCategories)
			docs.GET("/pages", docsHandler.ListPages)
			docs.GET("/pages/:id", docsHandler.PageDetail)
			docs.GET("/pages/slug/:slug", docsHandler.PageBySlug)
			docs.GET("/search", docsHandler.Search)
		}

		// 社区路由
		community := v1.Group("/community")
		{
			community.GET("/posts", communityHandler.ListPosts)
			community.POST("/posts", middleware.AuthMiddleware(), communityHandler.CreatePost)
			community.GET("/posts/:id", communityHandler.PostDetail)
			community.PUT("/posts/:id", middleware.AuthMiddleware(), communityHandler.UpdatePost)
			community.DELETE("/posts/:id", middleware.AuthMiddleware(), communityHandler.DeletePost)
			community.GET("/posts/:id/comments", communityHandler.ListComments)
			community.POST("/posts/:id/comments", middleware.AuthMiddleware(), communityHandler.CreateComment)
		}

		// 新闻路由
		news := v1.Group("/news")
		{
			news.GET("", newsHandler.List)
			news.GET("/latest", newsHandler.Latest)
			news.GET("/:id", newsHandler.Detail)
		}
	}

	// 健康检查
	router.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status": "ok",
		})
	})
}
