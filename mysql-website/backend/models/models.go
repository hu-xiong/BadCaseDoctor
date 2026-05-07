package models

import (
	"time"
)

// User 用户模型
type User struct {
	ID           int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	Email        string    `gorm:"type:varchar(255);uniqueIndex;not null" json:"email"`
	PasswordHash string    `gorm:"type:varchar(255);not null" json:"-"`
	Username     string    `gorm:"type:varchar(100);not null" json:"username"`
	Avatar       string    `gorm:"type:varchar(500)" json:"avatar"`
	Status       int8      `gorm:"type:tinyint;default:1" json:"status"`
	CreatedAt    time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// TableName 指定表名
func (User) TableName() string {
	return "users"
}

// Download 下载模型
type Download struct {
	ID            int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	Name          string    `gorm:"type:varchar(255);not null" json:"name"`
	Version       string    `gorm:"type:varchar(50);not null" json:"version"`
	Edition       string    `gorm:"type:varchar(50);not null" json:"edition"`
	OS            string    `gorm:"type:varchar(50);not null" json:"os"`
	FilePath      string    `gorm:"type:varchar(500);not null" json:"file_path"`
	FileSize      int64     `gorm:"type:bigint" json:"file_size"`
	SHA256        string    `gorm:"type:varchar(64)" json:"sha256"`
	Description   string    `gorm:"type:text" json:"description"`
	DownloadCount int       `gorm:"type:int;default:0" json:"download_count"`
	CreatedAt     time.Time `gorm:"autoCreateTime" json:"created_at"`
}

// TableName 指定表名
func (Download) TableName() string {
	return "downloads"
}

// DownloadHistory 下载历史模型
type DownloadHistory struct {
	ID          int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	UserID      int64     `gorm:"index" json:"user_id"`
	DownloadID  int64     `gorm:"index" json:"download_id"`
	DownloadedAt time.Time `gorm:"autoCreateTime" json:"downloaded_at"`
	User        User      `gorm:"foreignKey:UserID" json:"user,omitempty"`
	Download    Download  `gorm:"foreignKey:DownloadID" json:"download,omitempty"`
}

// TableName 指定表名
func (DownloadHistory) TableName() string {
	return "download_history"
}

// DocCategory 文档分类模型
type DocCategory struct {
	ID        int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	Name      string    `gorm:"type:varchar(100);not null" json:"name"`
	ParentID  int64     `gorm:"index" json:"parent_id"`
	SortOrder int       `gorm:"type:int;default:0" json:"sort_order"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	Children  []DocCategory `gorm:"-" json:"children,omitempty"`
}

// TableName 指定表名
func (DocCategory) TableName() string {
	return "doc_categories"
}

// Doc 文档模型
type Doc struct {
	ID         int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	CategoryID int64     `gorm:"index" json:"category_id"`
	Title      string    `gorm:"type:varchar(255);not null" json:"title"`
	Content    string    `gorm:"type:text" json:"content"`
	Slug       string    `gorm:"type:varchar(255);uniqueIndex" json:"slug"`
	Status     int8      `gorm:"type:tinyint;default:1" json:"status"`
	CreatedAt  time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt  time.Time `gorm:"autoUpdateTime" json:"updated_at"`
	Category   DocCategory `gorm:"foreignKey:CategoryID" json:"category,omitempty"`
}

// TableName 指定表名
func (Doc) TableName() string {
	return "docs"
}

// Post 帖子模型
type Post struct {
	ID         int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	UserID     int64     `gorm:"index" json:"user_id"`
	Title      string    `gorm:"type:varchar(255);not null" json:"title"`
	Content    string    `gorm:"type:text" json:"content"`
	Category   string    `gorm:"type:varchar(50)" json:"category"`
	ViewCount  int       `gorm:"type:int;default:0" json:"view_count"`
	LikeCount  int       `gorm:"type:int;default:0" json:"like_count"`
	Status     int8      `gorm:"type:tinyint;default:1" json:"status"`
	CreatedAt  time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt  time.Time `gorm:"autoUpdateTime" json:"updated_at"`
	User       User      `gorm:"foreignKey:UserID" json:"user,omitempty"`
}

// TableName 指定表名
func (Post) TableName() string {
	return "posts"
}

// Comment 评论模型
type Comment struct {
	ID        int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	PostID    int64     `gorm:"index" json:"post_id"`
	UserID    int64     `gorm:"index" json:"user_id"`
	Content   string    `gorm:"type:text;not null" json:"content"`
	ParentID  int64     `gorm:"index" json:"parent_id"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	User      User      `gorm:"foreignKey:UserID" json:"user,omitempty"`
	Post      Post      `gorm:"foreignKey:PostID" json:"post,omitempty"`
	Children  []Comment `gorm:"-" json:"children,omitempty"`
}

// TableName 指定表名
func (Comment) TableName() string {
	return "comments"
}

// News 新闻模型
type News struct {
	ID        int64     `gorm:"primaryKey;autoIncrement" json:"id"`
	Title     string    `gorm:"type:varchar(255);not null" json:"title"`
	Content   string    `gorm:"type:text" json:"content"`
	Summary   string    `gorm:"type:varchar(500)" json:"summary"`
	ImageURL  string    `gorm:"type:varchar(500)" json:"image_url"`
	Status    int8      `gorm:"type:tinyint;default:1" json:"status"`
	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`
}

// TableName 指定表名
func (News) TableName() string {
	return "news"
}
