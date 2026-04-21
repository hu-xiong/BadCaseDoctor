package controllers

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"badcasedoctor/backend-go/internal/models"

	"github.com/gin-gonic/gin"
)

func TestRegister(t *testing.T) {
	// 初始化数据库（使用内存数据库）
	if err := models.InitDB("root:password@tcp(127.0.0.1:3306)/testdb?charset=utf8mb4&parseTime=True&loc=Local"); err != nil {
		t.Fatalf("Failed to connect to database: %v", err)
	}

	// 自动迁移数据库模型
	if err := models.AutoMigrate(); err != nil {
		t.Fatalf("Failed to migrate database: %v", err)
	}

	// 创建Gin引擎
	r := gin.Default()

	// 注册路由
	r.POST("/api/auth/register", Register)

	// 测试数据
	testData := map[string]string{
		"name":     "testuser",
		"email":    "test@example.com",
		"password": "test123",
	}

	// 转换为JSON
	jsonData, err := json.Marshal(testData)
	if err != nil {
		t.Errorf("Failed to marshal test data: %v", err)
	}

	// 创建请求
	req, err := http.NewRequest("POST", "/api/auth/register", bytes.NewBuffer(jsonData))
	if err != nil {
		t.Errorf("Failed to create request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")

	// 执行请求
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// 检查响应状态码
	if w.Code != http.StatusCreated {
		t.Errorf("Expected status code %d, got %d", http.StatusCreated, w.Code)
	}

	// 检查响应内容
	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Errorf("Failed to unmarshal response: %v", err)
	}

	if response["message"] != "User registered successfully" {
		t.Errorf("Expected message 'User registered successfully', got %v", response["message"])
	}

	// 检查用户是否创建成功
	var user models.User
	if err := models.GetDB().Where("email = ?", testData["email"]).First(&user).Error; err != nil {
		t.Errorf("Failed to find created user: %v", err)
	}

	if user.Name != testData["name"] {
		t.Errorf("Expected name %s, got %s", testData["name"], user.Name)
	}

	if user.Email != testData["email"] {
		t.Errorf("Expected email %s, got %s", testData["email"], user.Email)
	}
}

func TestLogin(t *testing.T) {
	// 初始化数据库（使用内存数据库）
	if err := models.InitDB("root:password@tcp(127.0.0.1:3306)/testdb?charset=utf8mb4&parseTime=True&loc=Local"); err != nil {
		t.Fatalf("Failed to connect to database: %v", err)
	}

	// 自动迁移数据库模型
	if err := models.AutoMigrate(); err != nil {
		t.Fatalf("Failed to migrate database: %v", err)
	}

	// 创建测试用户
	user := models.User{
		Name:     "testuser",
		Email:    "test@example.com",
		Password: "test123", // 实际应该使用哈希密码
	}
	if err := models.GetDB().Create(&user).Error; err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// 创建Gin引擎
	r := gin.Default()

	// 注册路由
	r.POST("/api/auth/login", Login)

	// 测试数据
	testData := map[string]string{
		"email":    "test@example.com",
		"password": "test123",
	}

	// 转换为JSON
	jsonData, err := json.Marshal(testData)
	if err != nil {
		t.Errorf("Failed to marshal test data: %v", err)
	}

	// 创建请求
	req, err := http.NewRequest("POST", "/api/auth/login", bytes.NewBuffer(jsonData))
	if err != nil {
		t.Errorf("Failed to create request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")

	// 执行请求
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	// 检查响应状态码
	if w.Code != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, w.Code)
	}

	// 检查响应内容
	var response map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &response); err != nil {
		t.Errorf("Failed to unmarshal response: %v", err)
	}

	if response["message"] != "Login successful" {
		t.Errorf("Expected message 'Login successful', got %v", response["message"])
	}

	if response["token"] == nil {
		t.Error("Expected token in response")
	}
}