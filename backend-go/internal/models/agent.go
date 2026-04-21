// agent.go - Agent相关模型

package models

import (
	"time"
)

// AgentTask Agent任务模型
type AgentTask struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	TaskType    string    `gorm:"size:50;not null" json:"task_type"` // bug_management, test_case, etc.
	Status      string    `gorm:"size:20;default:'pending'" json:"status"` // pending, running, completed, failed
	InputData   string    `gorm:"type:text" json:"input_data"` // JSON格式存储
	OutputData  string    `gorm:"type:text" json:"output_data"` // JSON格式存储
	Error       string    `gorm:"type:text" json:"error"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
	CompletedAt time.Time `json:"completed_at"`
}

// AgentTaskStep Agent任务步骤模型
type AgentTaskStep struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	TaskID      uint      `gorm:"not null" json:"task_id"`
	StepName    string    `gorm:"size:100;not null" json:"step_name"`
	Status      string    `gorm:"size:20;default:'pending'" json:"status"` // pending, running, completed, failed
	InputData   string    `gorm:"type:text" json:"input_data"` // JSON格式存储
	OutputData  string    `gorm:"type:text" json:"output_data"` // JSON格式存储
	Error       string    `gorm:"type:text" json:"error"`
	StartTime   time.Time `json:"start_time"`
	EndTime     time.Time `json:"end_time"`
}

// AgentConfig Agent配置模型
type AgentConfig struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	AgentType   string    `gorm:"size:50;not null" json:"agent_type"` // bug_management, test_case, etc.
	ConfigData  string    `gorm:"type:text;not null" json:"config_data"` // JSON格式存储
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}