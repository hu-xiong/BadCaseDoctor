package utils

import (
	"testing"
)

func TestEmailService(t *testing.T) {
	// 创建邮件服务实例
	emailService := NewEmailService()

	// 测试发送密码重置邮件
	to := "test@example.com"
	resetLink := "http://localhost:3000/reset-password?token=test-token"

	err := emailService.SendPasswordResetEmail(to, resetLink)
	if err != nil {
		t.Errorf("SendPasswordResetEmail failed: %v", err)
	}

	// 测试发送验证邮件
	verificationLink := "http://localhost:3000/verify-email?token=test-token"

	err = emailService.SendVerificationEmail(to, verificationLink)
	if err != nil {
		t.Errorf("SendVerificationEmail failed: %v", err)
	}

	// 测试发送普通邮件
	subject := "Test Email"
	body := "This is a test email"

	err = emailService.SendEmail(to, subject, body)
	if err != nil {
		t.Errorf("SendEmail failed: %v", err)
	}
}