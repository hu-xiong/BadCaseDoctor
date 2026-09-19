//go:build windows

package main

import (
	"errors"
	"syscall"

	"golang.org/x/sys/windows"
)

// isAddrInUse：Windows 下 bind 冲突的错误码是 WSAEADDRINUSE（10048，经 errors.As 提取），
// 与 Go 为 POSIX 兼容发明的 syscall.EADDRINUSE 不相等，须按 WSA 码精确判断。
func isAddrInUse(err error) bool {
	var errno syscall.Errno
	if !errors.As(err, &errno) {
		return false
	}
	return errno == syscall.Errno(windows.WSAEADDRINUSE)
}
