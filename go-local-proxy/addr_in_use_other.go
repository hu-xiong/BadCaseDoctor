//go:build !windows

package main

import (
	"errors"
	"syscall"
)

// isAddrInUse：POSIX 平台（darwin/linux 等）net 错误链中的 errno 即 EADDRINUSE，errors.Is 可精确匹配。
func isAddrInUse(err error) bool {
	return errors.Is(err, syscall.EADDRINUSE)
}
