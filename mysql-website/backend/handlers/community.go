package handlers

import (
	"net/http"
	"strconv"

	"mysql-website-backend/middleware"
	"mysql-website-backend/models"

	"github.com/gin-gonic/gin"
)

// CommunityHandler 社区处理器
type CommunityHandler struct{}

// ListPosts 获取帖子列表
func (h *CommunityHandler) ListPosts(c *gin.Context) {
	var posts []models.Post
	
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
	category := c.Query("category")
	status := c.DefaultQuery("status", "1")

	query := models.DB.Model(&models.Post{})
	
	if category != "" {
		query = query.Where("category = ?", category)
	}
	
	if status != "" {
		query = query.Where("status = ?", status)
	}

	// 查询总数
	var total int64
	query.Count(&total)

	// 查询列表
	if err := query.Order("created_at DESC").Preload("User").Offset(offset).Limit(pageSize).Find(&posts).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch posts",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"list":      posts,
			"total":     total,
			"page":      page,
			"page_size": pageSize,
		},
	})
}

// CreatePost 创建帖子
func (h *CommunityHandler) CreatePost(c *gin.Context) {
	userID := middleware.GetCurrentUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{
			"code":    401,
			"message": "Authentication required",
		})
		return
	}

	var req struct {
		Title     string `json:"title" binding:"required,min=1,max=255"`
		Content   string `json:"content" binding:"required"`
		Category  string `json:"category"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Invalid request: " + err.Error(),
		})
		return
	}

	post := models.Post{
		UserID:   userID,
		Title:    req.Title,
		Content:  req.Content,
		Category: req.Category,
		Status:   1,
	}

	if err := models.DB.Create(&post).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to create post",
		})
		return
	}

	// 预加载用户信息
	models.DB.Preload("User").First(&post, post.ID)

	c.JSON(http.StatusCreated, gin.H{
		"code":    201,
		"message": "Post created successfully",
		"data":    post,
	})
}

// PostDetail 获取帖子详情
func (h *CommunityHandler) PostDetail(c *gin.Context) {
	id := c.Param("id")
	
	var post models.Post
	if err := models.DB.Preload("User").First(&post, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Post not found",
		})
		return
	}

	// 增加浏览数
	models.DB.Model(&post).Update("view_count", post.ViewCount+1)

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    post,
	})
}

// UpdatePost 更新帖子
func (h *CommunityHandler) UpdatePost(c *gin.Context) {
	userID := middleware.GetCurrentUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{
			"code":    401,
			"message": "Authentication required",
		})
		return
	}

	id := c.Param("id")
	
	var post models.Post
	if err := models.DB.First(&post, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Post not found",
		})
		return
	}

	// 检查是否是帖子作者
	if post.UserID != userID {
		c.JSON(http.StatusForbidden, gin.H{
			"code":    403,
			"message": "You can only update your own posts",
		})
		return
	}

	var req struct {
		Title    string `json:"title"`
		Content  string `json:"content"`
		Category string `json:"category"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Invalid request: " + err.Error(),
		})
		return
	}

	// 更新字段
	updates := make(map[string]interface{})
	if req.Title != "" {
		updates["title"] = req.Title
	}
	if req.Content != "" {
		updates["content"] = req.Content
	}
	if req.Category != "" {
		updates["category"] = req.Category
	}

	if len(updates) > 0 {
		models.DB.Model(&post).Updates(updates)
	}

	models.DB.Preload("User").First(&post, post.ID)

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Post updated successfully",
		"data":    post,
	})
}

// DeletePost 删除帖子
func (h *CommunityHandler) DeletePost(c *gin.Context) {
	userID := middleware.GetCurrentUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{
			"code":    401,
			"message": "Authentication required",
		})
		return
	}

	id := c.Param("id")
	
	var post models.Post
	if err := models.DB.First(&post, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Post not found",
		})
		return
	}

	// 检查是否是帖子作者
	if post.UserID != userID {
		c.JSON(http.StatusForbidden, gin.H{
			"code":    403,
			"message": "You can only delete your own posts",
		})
		return
	}

	// 删除帖子（级联删除评论）
	models.DB.Delete(&post)
	models.DB.Where("post_id = ?", id).Delete(&models.Comment{})

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Post deleted successfully",
	})
}

// ListComments 获取评论列表
func (h *CommunityHandler) ListComments(c *gin.Context) {
	postID := c.Param("id")
	
	var comments []models.Comment
	if err := models.DB.Where("post_id = ? AND parent_id = 0", postID).
		Order("created_at DESC").
		Preload("User").
		Find(&comments).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch comments",
		})
		return
	}

	// 加载子评论
	for i := range comments {
		models.DB.Where("parent_id = ?", comments[i].ID).
			Order("created_at ASC").
			Preload("User").
			Find(&comments[i].Children)
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    comments,
	})
}

// CreateComment 创建评论
func (h *CommunityHandler) CreateComment(c *gin.Context) {
	userID := middleware.GetCurrentUserID(c)
	if userID == 0 {
		c.JSON(http.StatusUnauthorized, gin.H{
			"code":    401,
			"message": "Authentication required",
		})
		return
	}

	postID := c.Param("id")
	
	// 检查帖子是否存在
	var post models.Post
	if err := models.DB.First(&post, postID).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Post not found",
		})
		return
	}

	var req struct {
		Content  string `json:"content" binding:"required"`
		ParentID int64  `json:"parent_id"`
	}

	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Invalid request: " + err.Error(),
		})
		return
	}

	comment := models.Comment{
		PostID:   post.ID,
		UserID:   userID,
		Content:  req.Content,
		ParentID: req.ParentID,
	}

	if err := models.DB.Create(&comment).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to create comment",
		})
		return
	}

	models.DB.Preload("User").First(&comment, comment.ID)

	c.JSON(http.StatusCreated, gin.H{
		"code":    201,
		"message": "Comment created successfully",
		"data":    comment,
	})
}
