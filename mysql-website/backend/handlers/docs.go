package handlers

import (
	"net/http"
	"strconv"

	"mysql-website-backend/models"

	"github.com/gin-gonic/gin"
)

// DocsHandler 文档处理器
type DocsHandler struct{}

// ListCategories 获取文档分类列表
func (h *DocsHandler) ListCategories(c *gin.Context) {
	var categories []models.DocCategory
	
	if err := models.DB.Order("sort_order ASC, id ASC").Find(&categories).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch categories",
		})
		return
	}

	// 构建树形结构
	tree := buildCategoryTree(categories)

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    tree,
	})
}

// buildCategoryTree 构建分类树形结构
func buildCategoryTree(categories []models.DocCategory) []models.DocCategory {
	categoryMap := make(map[int64]*models.DocCategory)
	var roots []models.DocCategory

	// 首先，将所有分类转换为指针并建立映射
	for i := range categories {
		categoryMap[categories[i].ID] = &categories[i]
	}

	// 然后，构建树形结构
	for i := range categories {
		cat := &categories[i]
		if cat.ParentID == 0 {
			roots = append(roots, *cat)
		} else {
			if parent, ok := categoryMap[cat.ParentID]; ok {
				parent.Children = append(parent.Children, *cat)
			}
		}
	}

	// 更新根节点中的Children
	for i := range roots {
		if children, ok := categoryMap[roots[i].ID]; ok {
			roots[i].Children = children.Children
		}
	}

	return roots
}

// ListPages 获取文档列表
func (h *DocsHandler) ListPages(c *gin.Context) {
	var docs []models.Doc
	
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
	categoryID := c.Query("category_id")
	status := c.DefaultQuery("status", "1")

	query := models.DB.Model(&models.Doc{})
	
	if categoryID != "" {
		query = query.Where("category_id = ?", categoryID)
	}
	
	if status != "" {
		query = query.Where("status = ?", status)
	}

	// 查询总数
	var total int64
	query.Count(&total)

	// 查询列表
	if err := query.Order("updated_at DESC").Preload("Category").Offset(offset).Limit(pageSize).Find(&docs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to fetch docs",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data": gin.H{
			"list":      docs,
			"total":     total,
			"page":      page,
			"page_size": pageSize,
		},
	})
}

// PageDetail 获取文档详情
func (h *DocsHandler) PageDetail(c *gin.Context) {
	id := c.Param("id")
	
	var doc models.Doc
	if err := models.DB.Preload("Category").First(&doc, id).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Document not found",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    doc,
	})
}

// PageBySlug 通过slug获取文档
func (h *DocsHandler) PageBySlug(c *gin.Context) {
	slug := c.Param("slug")
	
	var doc models.Doc
	if err := models.DB.Preload("Category").Where("slug = ?", slug).First(&doc).Error; err != nil {
		c.JSON(http.StatusNotFound, gin.H{
			"code":    404,
			"message": "Document not found",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    doc,
	})
}

// Search 搜索文档
func (h *DocsHandler) Search(c *gin.Context) {
	keyword := c.Query("keyword")
	
	if keyword == "" {
		c.JSON(http.StatusBadRequest, gin.H{
			"code":    400,
			"message": "Keyword is required",
		})
		return
	}

	var docs []models.Doc
	if err := models.DB.Where("title LIKE ? OR content LIKE ?", "%"+keyword+"%", "%"+keyword+"%").
		Order("updated_at DESC").
		Limit(50).
		Find(&docs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "Failed to search docs",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    200,
		"message": "Success",
		"data":    docs,
	})
}
