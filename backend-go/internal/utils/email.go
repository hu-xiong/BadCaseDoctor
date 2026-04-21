package utils

import (
	"fmt"
)

// EmailService 邮件服务
type EmailService struct {
	SMTPHost     string
	SMTPPort     string
	SMTPUsername string
	SMTPPassword string
	FromEmail    string
}

// NewEmailService 创建邮件服务实例
func NewEmailService() *EmailService {
	return &EmailService{
		SMTPHost:     getEnv("SMTP_HOST", "smtp.gmail.com"),
		SMTPPort:     getEnv("SMTP_PORT", "587"),
		SMTPUsername: getEnv("SMTP_USERNAME", ""),
		SMTPPassword: getEnv("SMTP_PASSWORD", ""),
		FromEmail:    getEnv("FROM_EMAIL", ""),
	}
}

// SendEmail 发送邮件
func (s *EmailService) SendEmail(to, subject, body string) error {
	// 简化处理，实际应该使用SMTP发送邮件
	// 这里模拟发送邮件
	fmt.Printf("Sending email to: %s\n", to)
	fmt.Printf("Subject: %s\n", subject)
	fmt.Printf("Body: %s\n", body)
	fmt.Println("Email sent successfully (simulated)")

	return nil
}

// SendPasswordResetEmail 发送密码重置邮件
func (s *EmailService) SendPasswordResetEmail(to, resetLink string) error {
	subject := "Password Reset Request"
	body := fmt.Sprintf(`
	Hello,

	We received a request to reset your password. Please click the link below to reset your password:

	%s

	If you did not request a password reset, please ignore this email.

	Best regards,
	BadCaseDoctor Team
	`, resetLink)

	return s.SendEmail(to, subject, body)
}

// SendVerificationEmail 发送邮箱验证邮件
func (s *EmailService) SendVerificationEmail(to, verificationLink string) error {
	subject := "Email Verification"
	body := fmt.Sprintf(`
	Hello,

	Please click the link below to verify your email address:

	%s

	If you did not create an account, please ignore this email.

	Best regards,
	BadCaseDoctor Team
	`, verificationLink)

	return s.SendEmail(to, subject, body)
}