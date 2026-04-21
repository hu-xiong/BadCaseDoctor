package utils

import (
	"context"
	"time"

	"github.com/redis/go-redis/v9"
)

// RedisClient Redis客户端
type RedisClient struct {
	client *redis.Client
}

// NewRedisClient 创建Redis客户端实例
func NewRedisClient() *RedisClient {
	host := getEnv("REDIS_HOST", "localhost")
	port := getEnv("REDIS_PORT", "6379")
	password := getEnv("REDIS_PASSWORD", "")
	db := 0 // 默认使用0号数据库

	client := redis.NewClient(&redis.Options{
		Addr:     host + ":" + port,
		Password: password,
		DB:       db,
	})

	// 测试连接
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err := client.Ping(ctx).Result()
	if err != nil {
		// 连接失败，记录错误但不中断程序
		// 在生产环境中，应该使用更健壮的错误处理
		return &RedisClient{client: client}
	}

	return &RedisClient{client: client}
}

// Set 设置键值对，带过期时间
func (r *RedisClient) Set(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return r.client.Set(ctx, key, value, expiration).Err()
}

// Get 获取键值
func (r *RedisClient) Get(ctx context.Context, key string) (string, error) {
	return r.client.Get(ctx, key).Result()
}

// Delete 删除键
func (r *RedisClient) Delete(ctx context.Context, keys ...string) error {
	return r.client.Del(ctx, keys...).Err()
}

// Exists 检查键是否存在
func (r *RedisClient) Exists(ctx context.Context, key string) (bool, error) {
	result, err := r.client.Exists(ctx, key).Result()
	if err != nil {
		return false, err
	}
	return result > 0, nil
}

// SetWithExpiration 设置键值对，带过期时间
func (r *RedisClient) SetWithExpiration(ctx context.Context, key string, value interface{}, expiration time.Duration) error {
	return r.client.Set(ctx, key, value, expiration).Err()
}

// GetWithTimeout 获取键值，带超时
func (r *RedisClient) GetWithTimeout(ctx context.Context, key string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	return r.client.Get(ctx, key).Result()
}

// Close 关闭Redis连接
func (r *RedisClient) Close() error {
	return r.client.Close()
}