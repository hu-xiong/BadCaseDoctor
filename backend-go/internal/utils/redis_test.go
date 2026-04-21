package utils

import (
	"context"
	"testing"
	"time"
)

func TestRedisClient(t *testing.T) {
	// 创建Redis客户端
	client := NewRedisClient()
	defer client.Close()

	// 测试上下文
	ctx := context.Background()

	// 测试键值
	key := "test-key"
	value := "test-value"

	// 测试Set和Get
	err := client.Set(ctx, key, value, 10*time.Second)
	if err != nil {
		t.Errorf("Set failed: %v", err)
	}

	// 等待一小段时间确保数据已写入
	time.Sleep(100 * time.Millisecond)

	retrievedValue, err := client.Get(ctx, key)
	if err != nil {
		t.Errorf("Get failed: %v", err)
	}

	if retrievedValue != value {
		t.Errorf("Expected value %s, got %s", value, retrievedValue)
	}

	// 测试Exists
	exists, err := client.Exists(ctx, key)
	if err != nil {
		t.Errorf("Exists failed: %v", err)
	}

	if !exists {
		t.Error("Exists should return true for existing key")
	}

	// 测试Delete
	err = client.Delete(ctx, key)
	if err != nil {
		t.Errorf("Delete failed: %v", err)
	}

	// 测试键是否已删除
	exists, err = client.Exists(ctx, key)
	if err != nil {
		t.Errorf("Exists failed: %v", err)
	}

	if exists {
		t.Error("Exists should return false for deleted key")
	}

	// 测试GetWithTimeout
	err = client.Set(ctx, key, value, 10*time.Second)
	if err != nil {
		t.Errorf("Set failed: %v", err)
	}

	retrievedValue, err = client.GetWithTimeout(ctx, key, 1*time.Second)
	if err != nil {
		t.Errorf("GetWithTimeout failed: %v", err)
	}

	if retrievedValue != value {
		t.Errorf("Expected value %s, got %s", value, retrievedValue)
	}

	// 清理
	client.Delete(ctx, key)
}