package utils

import (
	"testing"
	"time"
)

func TestHashPassword(t *testing.T) {
	password := "test123"
	hashedPassword, err := HashPassword(password)
	if err != nil {
		t.Errorf("HashPassword failed: %v", err)
	}

	if hashedPassword == password {
		t.Error("Hashed password should not be the same as original")
	}

	if !CheckPassword(password, hashedPassword) {
		t.Error("CheckPassword should return true for correct password")
	}

	if CheckPassword("wrongpassword", hashedPassword) {
		t.Error("CheckPassword should return false for incorrect password")
	}
}

func TestGenerateToken(t *testing.T) {
	userID := uint(1)
	email := "test@example.com"
	secret := "test-secret"

	token, err := GenerateToken(userID, email, secret)
	if err != nil {
		t.Errorf("GenerateToken failed: %v", err)
	}

	if token == "" {
		t.Error("GenerateToken should return a non-empty token")
	}

	claims, err := ValidateToken(token, secret)
	if err != nil {
		t.Errorf("ValidateToken failed: %v", err)
	}

	if claims.UserID != userID {
		t.Errorf("Expected user ID %d, got %d", userID, claims.UserID)
	}

	if claims.Email != email {
		t.Errorf("Expected email %s, got %s", email, claims.Email)
	}

	if claims.ExpiresAt == nil {
		t.Error("ExpiresAt should not be nil")
	} else {
		if claims.ExpiresAt.Time.Before(time.Now()) {
			t.Error("Token should not be expired")
		}
	}
}

func TestValidateToken(t *testing.T) {
	userID := uint(1)
	email := "test@example.com"
	secret := "test-secret"

	token, err := GenerateToken(userID, email, secret)
	if err != nil {
		t.Errorf("GenerateToken failed: %v", err)
	}

	// 测试正确的token
	claims, err := ValidateToken(token, secret)
	if err != nil {
		t.Errorf("ValidateToken failed: %v", err)
	}

	if claims.UserID != userID {
		t.Errorf("Expected user ID %d, got %d", userID, claims.UserID)
	}

	// 测试错误的secret
	_, err = ValidateToken(token, "wrong-secret")
	if err == nil {
		t.Error("ValidateToken should return error for wrong secret")
	}

	// 测试无效的token
	_, err = ValidateToken("invalid-token", secret)
	if err == nil {
		t.Error("ValidateToken should return error for invalid token")
	}
}