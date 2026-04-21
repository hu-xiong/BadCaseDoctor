package routes

import (
	"badcasedoctor/backend-go/internal/api/controllers"
	"badcasedoctor/backend-go/internal/api/middleware"

	"github.com/gin-gonic/gin"
)

// SetupRoutes 设置路由
func SetupRoutes(r *gin.Engine) {
	// 健康检查
	r.GET("/health", controllers.HealthCheck)

	// API 路由组
	api := r.Group("/api")
	{
		// 认证相关路由
		auth := api.Group("/auth")
		{
			auth.POST("/register", controllers.Register)
			auth.POST("/login", controllers.Login)
			auth.POST("/refresh", controllers.RefreshToken)
		}

		// 需要认证的路由
		authRequired := api.Group("/")
		authRequired.Use(middleware.JWTAuth())
		{
			// 用户相关
			user := authRequired.Group("/user")
			{
				user.GET("/profile", controllers.GetUserProfile)
				user.PUT("/profile", controllers.UpdateUserProfile)
			}

			// 项目相关
			project := authRequired.Group("/project")
			{
				project.GET("/list", controllers.GetProjectList)
				project.POST("/create", controllers.CreateProject)
				project.GET("/detail/:id", controllers.GetProjectDetail)
				project.PUT("/update/:id", controllers.UpdateProject)
				project.DELETE("/delete/:id", controllers.DeleteProject)
			}

			// 计划相关
			plan := authRequired.Group("/plan")
			{
				plan.GET("/list", controllers.GetPlanList)
				plan.POST("/create", controllers.CreatePlan)
				plan.GET("/detail/:id", controllers.GetPlanDetail)
				plan.PUT("/update/:id", controllers.UpdatePlan)
				plan.DELETE("/delete/:id", controllers.DeletePlan)
			}

			// 卡片相关
			card := authRequired.Group("/card")
			{
				card.GET("/list", controllers.GetCardList)
				card.POST("/create", controllers.CreateCard)
				card.GET("/detail/:id", controllers.GetCardDetail)
				card.PUT("/update/:id", controllers.UpdateCard)
				card.DELETE("/delete/:id", controllers.DeleteCard)
			}

			// 项目卡片相关
			projectCard := authRequired.Group("/project")
			{
				projectCard.GET("/:id/cards", controllers.GetProjectCards)
			}

			// BadCase相关
			badcase := authRequired.Group("/badcase")
			{
				badcase.GET("/list", controllers.GetBadCaseList)
				badcase.POST("/create", controllers.CreateBadCase)
				badcase.GET("/detail/:id", controllers.GetBadCaseDetail)
				badcase.PUT("/update/:id", controllers.UpdateBadCase)
				badcase.DELETE("/delete/:id", controllers.DeleteBadCase)
			}

			// Bug相关
			bug := authRequired.Group("/bug")
			{
				bug.GET("/list", controllers.GetBugList)
				bug.POST("/create", controllers.CreateBug)
				bug.GET("/detail/:id", controllers.GetBugDetail)
				bug.PUT("/update/:id", controllers.UpdateBug)
				bug.DELETE("/delete/:id", controllers.DeleteBug)
				}

				// TestCase相关
				testcase := authRequired.Group("/testcase")
				{
					testcase.GET("/list", controllers.GetTestCaseList)
					testcase.POST("/create", controllers.CreateTestCase)
					testcase.GET("/detail/:id", controllers.GetTestCaseDetail)
					testcase.PUT("/update/:id", controllers.UpdateTestCase)
					testcase.DELETE("/delete/:id", controllers.DeleteTestCase)
				}

				// 终端API相关
				terminal := authRequired.Group("/terminal")
				{
					// 会话管理
					terminal.GET("/session/list", controllers.GetTerminalSessionList)
					terminal.POST("/session/create", controllers.CreateTerminalSession)
					terminal.PUT("/session/update/:id", controllers.UpdateTerminalSession)
					terminal.DELETE("/session/delete/:id", controllers.DeleteTerminalSession)

					// 命令执行
					terminal.POST("/command/exec", controllers.ExecuteTerminalCommand)
					terminal.GET("/command/list", controllers.GetTerminalCommandList)

					// 快速命令
					terminal.GET("/quickcommand/list", controllers.GetQuickCommandList)
					terminal.POST("/quickcommand/create", controllers.CreateQuickCommand)
					terminal.PUT("/quickcommand/update/:id", controllers.UpdateQuickCommand)
					terminal.DELETE("/quickcommand/delete/:id", controllers.DeleteQuickCommand)

					// 审计日志
					terminal.GET("/audit/list", controllers.GetTerminalAuditList)
				}

				// 聊天模块
				chat := authRequired.Group("/chat")
				{
					// 会话管理
					chat.GET("/session/list", controllers.GetChatSessionList)
					chat.POST("/session/create", controllers.CreateChatSession)
					chat.GET("/session/detail/:id", controllers.GetChatSessionDetail)
					chat.PUT("/session/update/:id", controllers.UpdateChatSession)
					chat.DELETE("/session/delete/:id", controllers.DeleteChatSession)

					// 消息管理
					chat.GET("/message/list", controllers.GetChatMessageList)
					chat.POST("/message/send", controllers.SendChatMessage)

					// 会话摘要
					chat.GET("/session/summary/:id", controllers.GetChatSessionSummary)
					chat.POST("/session/summary/generate", controllers.GenerateChatSessionSummary)
				}

				// Agent模块
				agent := authRequired.Group("/agent")
				{
					// 任务管理
					agent.GET("/task/list", controllers.GetAgentTaskList)
					agent.POST("/task/create", controllers.CreateAgentTask)
					agent.GET("/task/detail/:id", controllers.GetAgentTaskDetail)
					agent.PUT("/task/cancel/:id", controllers.CancelAgentTask)

					// 任务步骤
					agent.GET("/task/step/list", controllers.GetAgentTaskStepList)

					// 配置管理
					agent.GET("/config/list", controllers.GetAgentConfigList)
					agent.POST("/config/create", controllers.CreateAgentConfig)
					agent.PUT("/config/update/:id", controllers.UpdateAgentConfig)
					agent.DELETE("/config/delete/:id", controllers.DeleteAgentConfig)

					// 与Python Agent通信
					agent.POST("/communicate", controllers.CommunicateWithPythonAgent)
				}

				// 邮件模块
				email := authRequired.Group("/email")
				{
					// 发送密码重置邮件
					email.POST("/reset-password", controllers.SendPasswordResetEmail)
					// 发送验证邮件
					email.POST("/verify", controllers.SendVerificationEmail)
				}
			}
		}
	}
}