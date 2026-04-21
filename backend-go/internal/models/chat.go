// chat.go - 聊天相关模型

package models

import (
	"time"
)

// ChatSession 聊天会话模型
type ChatSession struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	Title       string    `gorm:"size:100" json:"title"`
	Description string    `gorm:"type:text" json:"description"`
	Status      string    `gorm:"size:20;default:'active'" json:"status"`
	MemoryData  string    `gorm:"type:text" json:"memory_data"` // JSON格式存储
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// ChatMessage 聊天消息模型
type ChatMessage struct {
	ID         uint      `gorm:"primary_key" json:"id"`
	SessionID  uint      `gorm:"not null" json:"session_id"`
	UserID     uint      `gorm:"not null" json:"user_id"`
	Role       string    `gorm:"size:20;not null" json:"role"` // user, assistant
	Content    string    `gorm:"type:text;not null" json:"content"`
	MessageType string    `gorm:"size:20;default:'text'" json:"message_type"` // text, image, file
	Metadata   string    `gorm:"type:text" json:"metadata"` // JSON格式存储
	CreatedAt  time.Time `json:"created_at"`
}

// ChatSessionSummary 聊天会话摘要
type ChatSessionSummary struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	SessionID   uint      `gorm:"not null" json:"session_id"`
	Summary     string    `gorm:"type:text" json:"summary"`
	Keywords    string    `gorm:"type:text" json:"keywords"` // 逗号分隔的关键词
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}