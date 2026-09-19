//go:build windows

package main

import "golang.org/x/sys/windows"

var (
	modKernel32      = windows.NewLazySystemDLL("kernel32.dll")
	modUser32        = windows.NewLazySystemDLL("user32.dll")
	procAllocConsole = modKernel32.NewProc("AllocConsole")
	procGetConsoleW  = modKernel32.NewProc("GetConsoleWindow")
	procShowWindow   = modUser32.NewProc("ShowWindow")
)

const swHide = 0

func init() {
	// Windows GUI apps (like those started by Electron) don't have a console by default.
	// Allocate one so WriteConsoleInput can work for win32-input-mode support.
	procAllocConsole.Call()
}

// hideConsoleForAutostart：由注册表 Run 键在登录时拉起时，隐藏控制台窗口。
// 进程创建到 main 执行之间窗口可能短暂闪现（控制台子系统先建窗），执行后即隐藏。
func hideConsoleForAutostart() {
	hwnd, _, _ := procGetConsoleW.Call()
	if hwnd != 0 {
		procShowWindow.Call(hwnd, swHide)
	}
}
