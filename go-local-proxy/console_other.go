//go:build !windows

package main

// 非 Windows 平台（darwin/linux）：无需为 win32-input-mode 分配控制台，保持空实现以对齐构建约束。
