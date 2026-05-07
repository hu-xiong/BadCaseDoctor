package handlers

import (
	"net/http"
	"strconv"

	"mysql-website-backend/models"

	"github.com/gin-gonic/gin"
)

// NewsHandler 新闻处理器
type NewsHandler struct{}

// List 获取新闻列表
func (h *NewsHandler) List(c *gin.Context) {
	var newsList []models.News
	
	// 分页参数
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "20"))
	if page < 1 {
		page = 1
	}
	if pageSize < 1 || pageSize > 100 {
		pageSize = 20
	}

	offset := (page - 1) * pageSize

	// 筛选条件
	status := c.DefaultQuery("status", "1")

	query := models.DB.Model(&models.News{})
	
	if status != "" {
		query = query.Where("status = ?", status)
	}

	// 查询总数
	var total int64
	query.Count(&total)

	// 查询列表
	if err := query.Order("created_at DESC").Offset(offset).Limit(pageSize).Find(&newsList).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch news",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"list":      newsList,
			"total":     total,
			"page":      page,
			"page_size": pageSize,
		},
	})
}

// Detail 获取新闻详情
func (h *NewsHandler) Detail(c *gin.Context) {
	id := c.Param("id")
	
	var news models.News
	if err := models.DB.First(&news, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "News not found",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    news,
	})
}

// Latest 获取最新新闻
func (h *NewsHandler) Latest(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	if limit < 1 || limit > 50 {
		limit = 10
	}
	
	var newsList []models.News
	if err := models.DB.Where("status = ?", 1).
		Order("created_at DESC").
		Limit(limit).
		Find(&newsList).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch news",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    newsList,
	})
}
