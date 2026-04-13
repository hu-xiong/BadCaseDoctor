//go:build windows

package main

import (
	"os"
	"path/filepath"
	"strings"
)

// 浏览器常不传 term_start.cwd；若进程 cwd 落在 System32 等无关目录，Shell 起始路径会错。
// 在「exe 不在系统临时目录」时切到可执行文件所在目录（排除 go run 的临时构建路径）。
func init() {
	exe, err := os.Executable()
	if err != nil {
		return
	}
	dir := filepath.Clean(filepath.Dir(exe))
	if dir == "" || dir == "." {
		return
	}
	tmp := filepath.Clean(os.TempDir())
	if tmp != "" && tmp != "." {
		if strings.HasPrefix(strings.ToLower(dir), strings.ToLower(tmp)) {
			return
		}
	}
	_ = os.Chdir(dir)
}
