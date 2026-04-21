package models

import (
	"fmt"
	"time"

	"github.com/jinzhu/gorm"
	_ "github.com/jinzhu/gorm/dialects/mysql"
)

var db *gorm.DB

// InitDB 初始化数据库连接
func InitDB(databaseURL string) error {
	var err error
	db, err = gorm.Open("mysql", databaseURL)
	if err != nil {
		return fmt.Errorf("failed to connect to database: %w", err)
	}

	// 设置连接池
	db.DB().SetMaxIdleConns(10)
	db.DB().SetMaxOpenConns(100)
	db.DB().SetConnMaxLifetime(time.Hour)

	// 启用日志
	db.LogMode(true)

	return nil
}

// GetDB 获取数据库连接
func GetDB() *gorm.DB {
	return db
}

// AutoMigrate 自动迁移数据库模型
func AutoMigrate() error {
	return db.AutoMigrate(
		&User{},
		&Project{},
		&Plan{},
		&Card{},
		&BadCase{},
		&Bug{},
		&TestCase{},
		&TerminalSession{},
		&TerminalCommand{},
		&TerminalAudit{},
		&QuickCommand{},
		&ChatSession{},
		&ChatMessage{},
		&ChatSessionSummary{},
		&AgentTask{},
		&AgentTaskStep{},
		&AgentConfig{},
	).Error
}

// User 用户模型
type User struct {
	ID        uint      `gorm:"primary_key" json:"id"`
	Name      string    `gorm:"size:100;not null" json:"name"`
	Email     string    `gorm:"size:100;not null;unique" json:"email"`
	Password  string    `gorm:"size:100;not null" json:"-"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// Project 项目模型
type Project struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	Name        string    `gorm:"size:100;not null" json:"name"`
	Description string    `gorm:"type:text" json:"description"`
	Status      string    `gorm:"size:20;default:'published'" json:"status"`
	UserID      uint      `gorm:"not null" json:"user_id"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// Plan 计划模型
type Plan struct {
	ID          uint      `gorm:"primary_key" json:"id"`
	Name        string    `gorm:"size:100;not null" json:"name"`
	Description string    `gorm:"type:text" json:"description"`
	PlanType    string    `gorm:"size:20;not null" json:"plan_type"`
	StartDate   time.Time `json:"start_date"`
	EndDate     time.Time `json:"end_date"`
	Progress    float64   `gorm:"default:0.0" json:"progress"`
	ParentID    uint      `json:"parent_id"`
	ProjectID   uint      `gorm:"not null" json:"project_id"`
	CreatorID   uint      `gorm:"not null" json:"creator_id"`
	AssigneeID  uint      `json:"assignee_id"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// CardType 卡片类型
type CardType string

const (
	CardTypeBug      CardType = "bug"
	CardTypeBadCase  CardType = "badcase"
	CardTypeTestCase CardType = "testcase"
)

// CardStatus 卡片状态
type CardStatus string

const (
	CardStatusOpen      CardStatus = "open"
	CardStatusInProgress CardStatus = "in_progress"
	CardStatusClosed    CardStatus = "closed"
)

// Card 卡片模型
type Card struct {
	ID          uint        `gorm:"primary_key" json:"id"`
	Title       string      `gorm:"size:200;not null" json:"title"`
	Type        CardType    `gorm:"size:20;not null" json:"type"`
	Status      CardStatus  `gorm:"size:20;default:'open'" json:"status"`
	Priority    string      `gorm:"size:10;default:'p3'" json:"priority"`
	AssigneeID  uint        `json:"assignee_id"`
	ProjectID   uint        `gorm:"not null" json:"project_id"`
	CreatorID   uint        `gorm:"not null" json:"creator_id"`
	PlanID      uint        `json:"plan_id"`
	Description string      `gorm:"type:text" json:"description"`
	CreatedAt   time.Time   `json:"created_at"`
	UpdatedAt   time.Time   `json:"updated_at"`

	// Bug特有字段
	Severity         string `gorm:"size:20" json:"severity"`
	StepsToReproduce string `gorm:"type:text" json:"steps_to_reproduce"`
	ExpectedResult   string `gorm:"type:text" json:"expected_result"`
	ActualResult     string `gorm:"type:text" json:"actual_result"`

	// BadCase特有字段
	CaseCategory     string `gorm:"size:100" json:"case_category"`
	BaseProblem      string `gorm:"type:text" json:"base_problem"`
	ReproductionSteps string `gorm:"type:text" json:"reproduction_steps"`
	Solution         string `gorm:"type:text" json:"solution"`

	// TestCase特有字段
	Preconditions    string `gorm:"type:text" json:"preconditions"`
	Steps            string `gorm:"type:text" json:"steps"`
	Remark           string `gorm:"type:text" json:"remark"`
	ExecutionResult  string `gorm:"size:20" json:"execution_result"`
}

// BadCase BadCase模型
type BadCase struct {
	ID               uint      `gorm:"primary_key" json:"id"`
	ProjectID        uint      `gorm:"not null" json:"project_id"`
	PlanID           uint      `json:"plan_id"`
	CreatorID        uint      `gorm:"not null" json:"creator_id"`
	Title            string    `gorm:"size:200" json:"title"`
	CaseCategory     string    `gorm:"size:100;not null" json:"case_category"`
	BaseProblem      string    `gorm:"type:text;not null" json:"base_problem"`
	ReproductionSteps string    `gorm:"type:text" json:"reproduction_steps"`
	Solution         string    `gorm:"type:text" json:"solution"`
	Status           string    `gorm:"size:20;default:'new'" json:"status"`
	Priority         string    `gorm:"size:10;default:'p3'" json:"priority"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

// Bug Bug模型
type Bug struct {
	ID               uint      `gorm:"primary_key" json:"id"`
	Title            string    `gorm:"size:200;not null" json:"title"`
	Description      string    `gorm:"type:text" json:"description"`
	StepsToReproduce string    `gorm:"type:text" json:"steps_to_reproduce"`
	ExpectedResult   string    `gorm:"type:text" json:"expected_result"`
	ActualResult     string    `gorm:"type:text" json:"actual_result"`
	Severity         string    `gorm:"size:20;default:'medium'" json:"severity"`
	Priority         string    `gorm:"size:10;default:'p3'" json:"priority"`
	Status           string    `gorm:"size:20;default:'new'" json:"status"`
	BugType          string    `gorm:"size:50" json:"bug_type"`
	Environment      string    `gorm:"size:100" json:"environment"`
	Browser          string    `gorm:"size:50" json:"browser"`
	OS               string    `gorm:"size:50" json:"os"`
	PlanID           uint      `json:"plan_id"`
	ProjectID        uint      `gorm:"not null" json:"project_id"`
	CreatorID        uint      `gorm:"not null" json:"creator_id"`
	AssigneeID       uint      `json:"assignee_id"`
	Attachments      string    `gorm:"type:text" json:"attachments"`
	CreatedAt        time.Time `json:"created_at"`
	UpdatedAt        time.Time `json:"updated_at"`
}

// TestCase TestCase模型
type TestCase struct {
	ID              uint      `gorm:"primary_key" json:"id"`
	Title           string    `gorm:"size:200;not null" json:"title"`
	Status          string    `gorm:"size:20;default:'draft'" json:"status"`
	CaseType        string    `gorm:"size:50" json:"case_type"`
	Priority        string    `gorm:"size:10;default:'P3'" json:"priority"`
	TestType        string    `gorm:"size:50" json:"test_type"`
	Preconditions   string    `gorm:"type:text" json:"preconditions"`
	Steps           string    `gorm:"type:text" json:"steps"`
	Remark          string    `gorm:"type:text" json:"remark"`
	RequirementID   uint      `json:"requirement_id"`
	RelatedDefects  string    `gorm:"type:text" json:"related_defects"`
	LastExecuted    time.Time `json:"last_executed"`
	ExecutedBy      uint      `json:"executed_by"`
	ExecutionResult string    `gorm:"size:20" json:"execution_result"`
	Baseline        string    `gorm:"size:100" json:"baseline"`
	EstimatedTime   float64   `json:"estimated_time"`
	ActualTime      float64   `json:"actual_time"`
	RemainingTime   float64   `json:"remaining_time"`
	PlanID          uint      `json:"plan_id"`
	ProjectID       uint      `gorm:"not null" json:"project_id"`
	CreatorID       uint      `gorm:"not null" json:"creator_id"`
	AssigneeID      uint      `json:"assignee_id"`
	Version         string    `gorm:"size:50" json:"version"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}