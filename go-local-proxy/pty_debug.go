package main

import (
	"os"
	"strings"
)

// ptyDebugEnabled：设置环境变量 BADCASE_PTY_DEBUG=1 后打印 [pty-debug] 详细步骤。
func ptyDebugEnabled() bool {
	return strings.TrimSpace(os.Getenv("BADCASE_PTY_DEBUG")) == "1"
}
