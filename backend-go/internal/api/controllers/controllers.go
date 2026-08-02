package controllers

import (
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"

	"badcasedoctor/backend-go/internal/models"
	"badcasedoctor/backend-go/internal/utils"

	"github.com/gin-gonic/gin"
)

// HealthCheck 健康检查
func HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status": "ok",
		"message": "BadCaseDoctor backend service is running",
	})
}

// Register 用户注册
func Register(c *gin.Context) {
	var user models.User
	if err := c.ShouldBindJSON(&user); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 检查邮箱是否已存在
	var existingUser models.User
	if err := models.GetDB().Where("email = ?", user.Email).First(&existingUser).Error; err == nil {
		c.JSON(http.StatusConflict, gin.H{"error": "Email already exists"})
		return
	}

	// 对密码进行哈希处理
	hashedPassword, err := utils.HashPassword(user.Password)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to hash password"})
		return
	}
	user.Password = hashedPassword

	// 创建用户
	if err := models.GetDB().Create(&user).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create user"})
		return
	}

	// 生成JWT token
	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "JWT_SECRET not configured"})
		return
	}
	token, err := utils.GenerateToken(user.ID, user.Email, jwtSecret)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "User registered successfully",
		"user": user,
		"token": token,
	})
}

// Login 用户登录
func Login(c *gin.Context) {
	var loginData struct {
		Email    string `json:"email" binding:"required"`
		Password string `json:"password" binding:"required"`
	}

	if err := c.ShouldBindJSON(&loginData); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 查找用户
	var user models.User
	if err := models.GetDB().Where("email = ?", loginData.Email).First(&user).Error; err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// 验证密码
	if !utils.CheckPassword(loginData.Password, user.Password) {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// 生成JWT token
	jwtSecret := os.Getenv("JWT_SECRET")
	if jwtSecret == "" {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "JWT_SECRET not configured"})
		return
	}
	token, err := utils.GenerateToken(user.ID, user.Email, jwtSecret)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Login successful",
		"user": user,
		"token": token,
	})
}

// RefreshToken 刷新令牌
func RefreshToken(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"message": "Token refreshed successfully",
	})
}

// GetUserProfile 获取用户信息
func GetUserProfile(c *gin.Context) {
	// 从上下文获取用户ID
	userID := 1 // 简化处理，实际应该从JWT中获取

	var user models.User
	if err := models.GetDB().First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"user": user,
	})
}

// UpdateUserProfile 更新用户信息
func UpdateUserProfile(c *gin.Context) {
	// 从上下文获取用户ID
	userID := 1 // 简化处理，实际应该从JWT中获取

	var user models.User
	if err := models.GetDB().First(&user, userID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	if err := c.ShouldBindJSON(&user); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&user).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update user"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "User profile updated successfully",
		"user": user,
	})
}

// GetProjectList 获取项目列表
func GetProjectList(c *gin.Context) {
	var projects []models.Project
	if err := models.GetDB().Find(&projects).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get projects"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"projects": projects,
	})
}

// CreateProject 创建项目
func CreateProject(c *gin.Context) {
	var project models.Project
	if err := c.ShouldBindJSON(&project); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&project).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create project"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Project created successfully",
		"project": project,
	})
}

// GetProjectDetail 获取项目详情
func GetProjectDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid project ID"})
		return
	}

	var project models.Project
	if err := models.GetDB().First(&project, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Project not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"project": project,
	})
}

// UpdateProject 更新项目
func UpdateProject(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid project ID"})
		return
	}

	var project models.Project
	if err := models.GetDB().First(&project, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Project not found"})
		return
	}

	if err := c.ShouldBindJSON(&project); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&project).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update project"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Project updated successfully",
		"project": project,
	})
}

// DeleteProject 删除项目
func DeleteProject(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid project ID"})
		return
	}

	if err := models.GetDB().Delete(&models.Project{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete project"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Project deleted successfully",
	})
}

// GetPlanList 获取计划列表
func GetPlanList(c *gin.Context) {
	var plans []models.Plan
	if err := models.GetDB().Find(&plans).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get plans"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"plans": plans,
	})
}

// CreatePlan 创建计划
func CreatePlan(c *gin.Context) {
	var plan models.Plan
	if err := c.ShouldBindJSON(&plan); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&plan).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create plan"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Plan created successfully",
		"plan": plan,
	})
}

// GetPlanDetail 获取计划详情
func GetPlanDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid plan ID"})
		return
	}

	var plan models.Plan
	if err := models.GetDB().First(&plan, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Plan not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"plan": plan,
	})
}

// UpdatePlan 更新计划
func UpdatePlan(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid plan ID"})
		return
	}

	var plan models.Plan
	if err := models.GetDB().First(&plan, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Plan not found"})
		return
	}

	if err := c.ShouldBindJSON(&plan); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&plan).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update plan"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Plan updated successfully",
		"plan": plan,
	})
}

// DeletePlan 删除计划
func DeletePlan(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid plan ID"})
		return
	}

	if err := models.GetDB().Delete(&models.Plan{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete plan"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Plan deleted successfully",
	})
}

// GetCardList 获取卡片列表
func GetCardList(c *gin.Context) {
	var cards []models.Card
	if err := models.GetDB().Find(&cards).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get cards"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"cards": cards,
	})
}

// GetProjectCards 获取项目卡片列表
func GetProjectCards(c *gin.Context) {
	projectIDStr := c.Param("id")
	projectID, err := strconv.ParseUint(projectIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid project ID"})
		return
	}

	// 获取分页参数
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	perPage, _ := strconv.Atoi(c.DefaultQuery("per_page", "20"))
	if page < 1 {
		page = 1
	}
	if perPage < 1 || perPage > 100 {
		perPage = 20
	}
	offset := (page - 1) * perPage

	// 获取筛选参数
	planIDStr := c.Query("plan_id")

	var cards []models.Card
	var total int64

	query := models.GetDB().Model(&models.Card{}).Where("project_id = ?", projectID)

	// 按计划筛选
	if planIDStr != "" {
		planID, err := strconv.ParseUint(planIDStr, 10, 64)
		if err == nil {
			query = query.Where("plan_id = ?", planID)
		}
	}

	// 获取总数
	if err := query.Count(&total).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to count cards"})
		return
	}

	// 获取分页数据，按创建时间倒序
	if err := query.Order("created_at DESC").Offset(offset).Limit(perPage).Find(&cards).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get cards"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"success": true,
		"cards":   cards,
		"total":   total,
		"pagination": gin.H{
			"page":       page,
			"per_page":   perPage,
			"total":      total,
		},
	})
}

// CreateCard 创建卡片
func CreateCard(c *gin.Context) {
	var card models.Card
	if err := c.ShouldBindJSON(&card); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&card).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create card"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Card created successfully",
		"card": card,
	})
}

// GetCardDetail 获取卡片详情
func GetCardDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid card ID"})
		return
	}

	var card models.Card
	if err := models.GetDB().First(&card, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Card not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"card": card,
	})
}

// UpdateCard 更新卡片
func UpdateCard(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid card ID"})
		return
	}

	var card models.Card
	if err := models.GetDB().First(&card, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Card not found"})
		return
	}

	if err := c.ShouldBindJSON(&card); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&card).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update card"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Card updated successfully",
		"card": card,
	})
}

// DeleteCard 删除卡片
func DeleteCard(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid card ID"})
		return
	}

	if err := models.GetDB().Delete(&models.Card{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete card"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Card deleted successfully",
	})
}

// GetBadCaseList 获取BadCase列表
func GetBadCaseList(c *gin.Context) {
	var badcases []models.BadCase
	if err := models.GetDB().Find(&badcases).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get badcases"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"badcases": badcases,
	})
}

// CreateBadCase 创建BadCase
func CreateBadCase(c *gin.Context) {
	var badcase models.BadCase
	if err := c.ShouldBindJSON(&badcase); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&badcase).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create badcase"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "BadCase created successfully",
		"badcase": badcase,
	})
}

// GetBadCaseDetail 获取BadCase详情
func GetBadCaseDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid badcase ID"})
		return
	}

	var badcase models.BadCase
	if err := models.GetDB().First(&badcase, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "BadCase not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"badcase": badcase,
	})
}

// UpdateBadCase 更新BadCase
func UpdateBadCase(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid badcase ID"})
		return
	}

	var badcase models.BadCase
	if err := models.GetDB().First(&badcase, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "BadCase not found"})
		return
	}

	if err := c.ShouldBindJSON(&badcase); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&badcase).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update badcase"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "BadCase updated successfully",
		"badcase": badcase,
	})
}

// DeleteBadCase 删除BadCase
func DeleteBadCase(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid badcase ID"})
		return
	}

	if err := models.GetDB().Delete(&models.BadCase{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete badcase"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "BadCase deleted successfully",
	})
}

// GetBugList 获取Bug列表
func GetBugList(c *gin.Context) {
	var bugs []models.Bug
	if err := models.GetDB().Find(&bugs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get bugs"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"bugs": bugs,
	})
}

// CreateBug 创建Bug
func CreateBug(c *gin.Context) {
	var bug models.Bug
	if err := c.ShouldBindJSON(&bug); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&bug).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create bug"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Bug created successfully",
		"bug": bug,
	})
}

// GetBugDetail 获取Bug详情
func GetBugDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid bug ID"})
		return
	}

	var bug models.Bug
	if err := models.GetDB().First(&bug, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Bug not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"bug": bug,
	})
}

// UpdateBug 更新Bug
func UpdateBug(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid bug ID"})
		return
	}

	var bug models.Bug
	if err := models.GetDB().First(&bug, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Bug not found"})
		return
	}

	if err := c.ShouldBindJSON(&bug); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&bug).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update bug"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Bug updated successfully",
		"bug": bug,
	})
}

// DeleteBug 删除Bug
func DeleteBug(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid bug ID"})
		return
	}

	if err := models.GetDB().Delete(&models.Bug{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete bug"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Bug deleted successfully",
	})
}

// GetTestCaseList 获取TestCase列表
func GetTestCaseList(c *gin.Context) {
	var testcases []models.TestCase
	if err := models.GetDB().Find(&testcases).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get testcases"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"testcases": testcases,
	})
}

// CreateTestCase 创建TestCase
func CreateTestCase(c *gin.Context) {
	var testcase models.TestCase
	if err := c.ShouldBindJSON(&testcase); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&testcase).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create testcase"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "TestCase created successfully",
		"testcase": testcase,
	})
}

// GetTestCaseDetail 获取TestCase详情
func GetTestCaseDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid testcase ID"})
		return
	}

	var testcase models.TestCase
	if err := models.GetDB().First(&testcase, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "TestCase not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"testcase": testcase,
	})
}

// UpdateTestCase 更新TestCase
func UpdateTestCase(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid testcase ID"})
		return
	}

	var testcase models.TestCase
	if err := models.GetDB().First(&testcase, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "TestCase not found"})
		return
	}

	if err := c.ShouldBindJSON(&testcase); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&testcase).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update testcase"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "TestCase updated successfully",
		"testcase": testcase,
	})
}

// DeleteTestCase 删除TestCase
func DeleteTestCase(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid testcase ID"})
		return
	}

	if err := models.GetDB().Delete(&models.TestCase{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete testcase"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "TestCase deleted successfully",
	})
}

// GetTerminalSessionList 获取终端会话列表
func GetTerminalSessionList(c *gin.Context) {
	var sessions []models.TerminalSession
	if err := models.GetDB().Find(&sessions).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get terminal sessions"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
	})
}

// CreateTerminalSession 创建终端会话
func CreateTerminalSession(c *gin.Context) {
	var session models.TerminalSession
	if err := c.ShouldBindJSON(&session); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&session).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create terminal session"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Terminal session created successfully",
		"session": session,
	})
}

// UpdateTerminalSession 更新终端会话
func UpdateTerminalSession(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	var session models.TerminalSession
	if err := models.GetDB().First(&session, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Terminal session not found"})
		return
	}

	if err := c.ShouldBindJSON(&session); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&session).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update terminal session"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Terminal session updated successfully",
		"session": session,
	})
}

// DeleteTerminalSession 删除终端会话
func DeleteTerminalSession(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	if err := models.GetDB().Delete(&models.TerminalSession{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete terminal session"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Terminal session deleted successfully",
	})
}

// ExecuteTerminalCommand 执行终端命令
func ExecuteTerminalCommand(c *gin.Context) {
	var commandData struct {
		SessionID string `json:"session_id" binding:"required"`
		Command   string `json:"command" binding:"required"`
	}

	if err := c.ShouldBindJSON(&commandData); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 简化处理，实际应该执行命令
	command := models.TerminalCommand{
		SessionID: commandData.SessionID,
		Command:   commandData.Command,
		Status:    "completed",
		Output:    "Command executed successfully",
		ExitCode:  0,
	}

	if err := models.GetDB().Create(&command).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to execute command"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Command executed successfully",
		"command": command,
	})
}

// GetTerminalCommandList 获取终端命令列表
func GetTerminalCommandList(c *gin.Context) {
	sessionID := c.Query("session_id")
	var commands []models.TerminalCommand

	query := models.GetDB()
	if sessionID != "" {
		query = query.Where("session_id = ?", sessionID)
	}

	if err := query.Find(&commands).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get terminal commands"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"commands": commands,
	})
}

// GetQuickCommandList 获取快速命令列表
func GetQuickCommandList(c *gin.Context) {
	projectID := c.Query("project_id")
	var commands []models.QuickCommand

	query := models.GetDB()
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}

	if err := query.Find(&commands).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get quick commands"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"commands": commands,
	})
}

// CreateQuickCommand 创建快速命令
func CreateQuickCommand(c *gin.Context) {
	var command models.QuickCommand
	if err := c.ShouldBindJSON(&command); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&command).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create quick command"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Quick command created successfully",
		"command": command,
	})
}

// UpdateQuickCommand 更新快速命令
func UpdateQuickCommand(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid command ID"})
		return
	}

	var command models.QuickCommand
	if err := models.GetDB().First(&command, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Quick command not found"})
		return
	}

	if err := c.ShouldBindJSON(&command); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&command).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update quick command"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Quick command updated successfully",
		"command": command,
	})
}

// DeleteQuickCommand 删除快速命令
func DeleteQuickCommand(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid command ID"})
		return
	}

	if err := models.GetDB().Delete(&models.QuickCommand{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete quick command"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Quick command deleted successfully",
	})
}

// GetTerminalAuditList 获取终端审计日志列表
func GetTerminalAuditList(c *gin.Context) {
	projectID := c.Query("project_id")
	var audits []models.TerminalAudit

	query := models.GetDB()
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}

	if err := query.Order("created_at DESC").Find(&audits).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get terminal audit logs"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"audits": audits,
	})
}

// GetChatSessionList 获取聊天会话列表
func GetChatSessionList(c *gin.Context) {
	projectID := c.Query("project_id")
	var sessions []models.ChatSession

	query := models.GetDB()
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}

	if err := query.Order("updated_at DESC").Find(&sessions).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get chat sessions"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
	})
}

// CreateChatSession 创建聊天会话
func CreateChatSession(c *gin.Context) {
	var session models.ChatSession
	if err := c.ShouldBindJSON(&session); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&session).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create chat session"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Chat session created successfully",
		"session": session,
	})
}

// GetChatSessionDetail 获取聊天会话详情
func GetChatSessionDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	var session models.ChatSession
	if err := models.GetDB().First(&session, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Chat session not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session": session,
	})
}

// UpdateChatSession 更新聊天会话
func UpdateChatSession(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	var session models.ChatSession
	if err := models.GetDB().First(&session, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Chat session not found"})
		return
	}

	if err := c.ShouldBindJSON(&session); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&session).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update chat session"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Chat session updated successfully",
		"session": session,
	})
}

// DeleteChatSession 删除聊天会话
func DeleteChatSession(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	// 先删除相关的消息
	if err := models.GetDB().Where("session_id = ?", id).Delete(&models.ChatMessage{}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete chat messages"})
		return
	}

	// 再删除会话
	if err := models.GetDB().Delete(&models.ChatSession{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete chat session"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Chat session deleted successfully",
	})
}

// GetChatMessageList 获取聊天消息列表
func GetChatMessageList(c *gin.Context) {
	sessionID := c.Query("session_id")
	if sessionID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Session ID is required"})
		return
	}

	var messages []models.ChatMessage
	if err := models.GetDB().Where("session_id = ?", sessionID).Order("created_at ASC").Find(&messages).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get chat messages"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"messages": messages,
	})
}

// SendChatMessage 发送聊天消息
func SendChatMessage(c *gin.Context) {
	var message models.ChatMessage
	if err := c.ShouldBindJSON(&message); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&message).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to send message"})
		return
	}

	// 更新会话的更新时间
	if err := models.GetDB().Model(&models.ChatSession{}).Where("id = ?", message.SessionID).Update("updated_at", time.Now()).Error; err != nil {
		// 记录错误但不影响消息发送
		fmt.Printf("Failed to update session updated_at: %v\n", err)
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Message sent successfully",
		"message_data": message,
	})
}

// GetChatSessionSummary 获取聊天会话摘要
func GetChatSessionSummary(c *gin.Context) {
	sessionID, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid session ID"})
		return
	}

	var summary models.ChatSessionSummary
	if err := models.GetDB().Where("session_id = ?", sessionID).First(&summary).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session summary not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"summary": summary,
	})
}

// GenerateChatSessionSummary 生成聊天会话摘要
func GenerateChatSessionSummary(c *gin.Context) {
	var data struct {
		SessionID uint `json:"session_id" binding:"required"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 简化处理，实际应该调用AI生成摘要
	summary := models.ChatSessionSummary{
		SessionID: data.SessionID,
		Summary:   "This is a generated summary of the chat session",
		Keywords:  "chat, summary, generated",
	}

	// 检查是否已存在摘要
	var existingSummary models.ChatSessionSummary
	if err := models.GetDB().Where("session_id = ?", data.SessionID).First(&existingSummary).Error; err == nil {
		// 更新现有摘要
		summary.ID = existingSummary.ID
		if err := models.GetDB().Save(&summary).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update session summary"})
			return
		}
	} else {
		// 创建新摘要
		if err := models.GetDB().Create(&summary).Error; err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate session summary"})
			return
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Session summary generated successfully",
		"summary": summary,
	})
}

// GetAgentTaskList 获取Agent任务列表
func GetAgentTaskList(c *gin.Context) {
	projectID := c.Query("project_id")
	status := c.Query("status")
	var tasks []models.AgentTask

	query := models.GetDB()
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}
	if status != "" {
		query = query.Where("status = ?", status)
	}

	if err := query.Order("created_at DESC").Find(&tasks).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get agent tasks"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"tasks": tasks,
	})
}

// CreateAgentTask 创建Agent任务
func CreateAgentTask(c *gin.Context) {
	var task models.AgentTask
	if err := c.ShouldBindJSON(&task); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 设置初始状态
	task.Status = "pending"

	if err := models.GetDB().Create(&task).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create agent task"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Agent task created successfully",
		"task": task,
	})
}

// GetAgentTaskDetail 获取Agent任务详情
func GetAgentTaskDetail(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid task ID"})
		return
	}

	var task models.AgentTask
	if err := models.GetDB().First(&task, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Agent task not found"})
		return
	}

	// 获取任务步骤
	var steps []models.AgentTaskStep
	if err := models.GetDB().Where("task_id = ?", id).Order("id ASC").Find(&steps).Error; err != nil {
		// 记录错误但不影响任务详情获取
		fmt.Printf("Failed to get task steps: %v\n", err)
	}

	c.JSON(http.StatusOK, gin.H{
		"task": task,
		"steps": steps,
	})
}

// CancelAgentTask 取消Agent任务
func CancelAgentTask(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid task ID"})
		return
	}

	var task models.AgentTask
	if err := models.GetDB().First(&task, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Agent task not found"})
		return
	}

	// 更新任务状态
	task.Status = "cancelled"
	if err := models.GetDB().Save(&task).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to cancel agent task"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Agent task cancelled successfully",
		"task": task,
	})
}

// GetAgentTaskStepList 获取Agent任务步骤列表
func GetAgentTaskStepList(c *gin.Context) {
	taskID := c.Query("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Task ID is required"})
		return
	}

	var steps []models.AgentTaskStep
	if err := models.GetDB().Where("task_id = ?", taskID).Order("id ASC").Find(&steps).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get task steps"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"steps": steps,
	})
}

// GetAgentConfigList 获取Agent配置列表
func GetAgentConfigList(c *gin.Context) {
	projectID := c.Query("project_id")
	agentType := c.Query("agent_type")
	var configs []models.AgentConfig

	query := models.GetDB()
	if projectID != "" {
		query = query.Where("project_id = ?", projectID)
	}
	if agentType != "" {
		query = query.Where("agent_type = ?", agentType)
	}

	if err := query.Find(&configs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to get agent configs"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"configs": configs,
	})
}

// CreateAgentConfig 创建Agent配置
func CreateAgentConfig(c *gin.Context) {
	var config models.AgentConfig
	if err := c.ShouldBindJSON(&config); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Create(&config).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create agent config"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"message": "Agent config created successfully",
		"config": config,
	})
}

// UpdateAgentConfig 更新Agent配置
func UpdateAgentConfig(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid config ID"})
		return
	}

	var config models.AgentConfig
	if err := models.GetDB().First(&config, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Agent config not found"})
		return
	}

	if err := c.ShouldBindJSON(&config); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if err := models.GetDB().Save(&config).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to update agent config"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Agent config updated successfully",
		"config": config,
	})
}

// DeleteAgentConfig 删除Agent配置
func DeleteAgentConfig(c *gin.Context) {
	id, err := strconv.Atoi(c.Param("id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid config ID"})
		return
	}

	if err := models.GetDB().Delete(&models.AgentConfig{}, id).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to delete agent config"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Agent config deleted successfully",
	})
}

// CommunicateWithPythonAgent 与Python Agent通信
func CommunicateWithPythonAgent(c *gin.Context) {
	var requestData struct {
		AgentType string      `json:"agent_type" binding:"required"`
		Input     interface{} `json:"input" binding:"required"`
		TaskID    uint        `json:"task_id"`
	}

	if err := c.ShouldBindJSON(&requestData); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 简化处理，实际应该与Python Agent进行通信
	// 这里模拟返回结果
	responseData := map[string]interface{}{
		"success": true,
		"message": "Communication with Python Agent successful",
		"data": map[string]interface{}{
			"result": "Agent processing completed",
			"details": "Python Agent has processed the request",
		},
	}

	// 如果有任务ID，更新任务状态
	if requestData.TaskID > 0 {
		var task models.AgentTask
		if err := models.GetDB().First(&task, requestData.TaskID).Error; err == nil {
			task.Status = "completed"
			task.CompletedAt = time.Now()
			models.GetDB().Save(&task)
		}
	}

	c.JSON(http.StatusOK, responseData)
}

// SendPasswordResetEmail 发送密码重置邮件
func SendPasswordResetEmail(c *gin.Context) {
	var data struct {
		Email string `json:"email" binding:"required"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 检查用户是否存在
	var user models.User
	if err := models.GetDB().Where("email = ?", data.Email).First(&user).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	// 生成重置链接（简化处理，实际应该生成带token的链接）
	resetLink := fmt.Sprintf("http://localhost:3000/reset-password?user_id=%d", user.ID)

	// 发送邮件
	emailService := utils.NewEmailService()
	if err := emailService.SendPasswordResetEmail(data.Email, resetLink); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to send password reset email"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Password reset email sent successfully",
	})
}

// SendVerificationEmail 发送验证邮件
func SendVerificationEmail(c *gin.Context) {
	var data struct {
		Email string `json:"email" binding:"required"`
	}

	if err := c.ShouldBindJSON(&data); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// 检查用户是否存在
	var user models.User
	if err := models.GetDB().Where("email = ?", data.Email).First(&user).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "User not found"})
		return
	}

	// 生成验证链接（简化处理，实际应该生成带token的链接）
	verificationLink := fmt.Sprintf("http://localhost:3000/verify-email?user_id=%d", user.ID)

	// 发送邮件
	emailService := utils.NewEmailService()
	if err := emailService.SendVerificationEmail(data.Email, verificationLink); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to send verification email"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message": "Verification email sent successfully",
	})
}