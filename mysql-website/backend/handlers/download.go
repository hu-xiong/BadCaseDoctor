package handlers

import (
	"net/http"
	"strconv"

	"mysql-website-backend/middleware"
	"mysql-website-backend/models"

	"github.com/gin-gonic/gin"
)

// DownloadHandler 下载处理器
type DownloadHandler struct{}

// List 获取下载列表
func (h *DownloadHandler) List(c *gin.Context) {
	var downloads []models.Download
	
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

	edition := c.Query("edition")
	osName := c.Query("os")

	query := models.DB.Model(&models.Download{})
	if edition != "" {
		query = query.Where("edition = ?", edition)
	}
	if osName != "" {
		query = query.Where("os = ?", osName)
	}

	// 查询总数
	var total int64
	query.Count(&total)

	// 查询列表
	if err := query.Order("created_at DESC").Offset(offset).Limit(pageSize).Find(&downloads).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch downloads",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"list":      downloads,
			"total":     total,
			"page":      page,
			"page_size": pageSize,
		},
	})
}

// Detail 获取下载详情
func (h *DownloadHandler) Detail(c *gin.Context) {
	id := c.Param("id")
	
	var download models.Download
	if err := models.DB.First(&download, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Download not found",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    download,
	})
}

// Record 记录下载
func (h *DownloadHandler) Record(c *gin.Context) {
	id := c.Param("id")
	userID := middleware.GetCurrentUserID(c)

	// 检查下载是否存在
	var download models.Download
	if err := models.DB.First(&download, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Download not found",
		})
		return
	}

	// 记录下载历史
	history := models.DownloadHistory{
		UserID:     userID,
		DownloadID: download.ID,
	}

	if err := models.DB.Create(&history).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to record download",
		})
		return
	}

	// 增加下载计数
	models.DB.Model(&download).Update("download_count", download.DownloadCount+1)

	c.JSON(http.StatusCreated, gin.H{
		"code":    201,
		"message": "Download recorded successfully",
	})
}

// GetByEdition 按版本获取下载列表
func (h *DownloadHandler) GetByEdition(c *gin.Context) {
	edition := c.Param("edition")
	
	var downloads []models.Download
	if err := models.DB.Where("edition = ?", edition).Order("version DESC").Find(&downloads).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch downloads",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    downloads,
	})
}

// GetByOS 按操作系统获取下载列表
func (h *DownloadHandler) GetByOS(c *gin.Context) {
	os := c.Param("os")
	
	var downloads []models.Download
	if err := models.DB.Where("os = ?", os).Order("version DESC").Find(&downloads).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch downloads",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    downloads,
	})
}
