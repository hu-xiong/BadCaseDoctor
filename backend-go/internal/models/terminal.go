// terminal.go - 终端相关模型

package models

import (
	"time"
)

// TerminalSession 终端会话模型
type TerminalSession struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	SessionID   string    `gorm:"size:100;not null;unique" json:"session_id"`
	Title       string    `gorm:"size:100" json:"title"`
	Status      string    `gorm:"size:20;default:'active'" json:"status"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// TerminalCommand 终端命令模型
type TerminalCommand struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	SessionID   string    `gorm:"size:100;not null" json:"session_id"`
	Command     string    `gorm:"type:text;not null" json:"command"`
	Output      string    `gorm:"type:text" json:"output"`
	Status      string    `gorm:"size:20;default:'pending'" json:"status"`
	ExitCode    int       `json:"exit_code"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// TerminalAudit 终端审计模型
type TerminalAudit struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	SessionID   string    `gorm:"size:100" json:"session_id"`
	Command     string    `gorm:"type:text" json:"command"`
	IPAddress   string    `gorm:"size:50" json:"ip_address"`
	UserAgent   string    `gorm:"size:255" json:"user_agent"`
	CreatedAt   time.Time `json:"created_at"`
}

// QuickCommand 快速命令模型
type QuickCommand struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	Name        string    `gorm:"size:100;not null" json:"name"`
	Command     string    `gorm:"type:text;not null" json:"command"`
	Description string    `gorm:"type:text" json:"description"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}