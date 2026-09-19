// 首次安装/首次运行时的「开机自启」注册（幂等，均为当前用户级、无需管理员）：
//   - Windows：注册表 HKCU\Software\Microsoft\Windows\CurrentVersion\Run
//   - macOS  ：~/Library/LaunchAgents/<label>.plist（launchctl bootstrap；RunAtLoad，崩溃才由 launchd 拉起）
//   - Linux  ：~/.config/systemd/user/<unit>（systemctl --user enable）；无 user manager 时回退 XDG autostart .desktop
//
// 命令行：
//   --install-autostart    显式注册（首次安装的一键流程调用），随后照常启动服务
//   --uninstall-autostart  移除注册后退出（不杀已在运行的实例）
//   --autostart-status     打印 JSON 状态后退出
//   --autostart            由上述机制在登录时拉起本进程（Windows 下隐藏控制台、常驻）
//   --no-autostart         跳过自动注册；环境变量 BADCASE_LOCAL_PROXY_NO_AUTOSTART=1 等效
//                          （Flask 托管、仓库开发脚本等场景使用，避免劫持登录启动）
//
// 常规启动默认「确保已注册」：首次运行即写入；之后每次启动仅校验并修正路径（文件挪动后自愈）。
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	autostartEnvOptOut = "BADCASE_LOCAL_PROXY_NO_AUTOSTART"
	// autostartLabel 用于 macOS LaunchAgent 的 Label（也出现在日志里）。
	autostartLabel = "com.badcasedoctor.local-proxy"
)

type autostartMode int

const (
	autostartModeNone autostartMode = iota
	autostartModeInstall
	autostartModeUninstall
	autostartModeStatus
)

// autostartInfo 为各平台实现的统一返回值；--autostart-status 以 JSON 输出。
type autostartInfo struct {
	Supported  bool   `json:"supported"`
	Registered bool   `json:"registered"`
	Changed    bool   `json:"changed"`
	Mechanism  string `json:"mechanism"`
	Target     string `json:"target,omitempty"`
	Detail     string `json:"detail,omitempty"`
}

func parseAutostartArgs(args []string) (mode autostartMode, autostartRun bool, noAutostart bool) {
	for _, a := range args {
		switch strings.ToLower(strings.TrimSpace(a)) {
		case "--install-autostart":
			mode = autostartModeInstall
		case "--uninstall-autostart":
			mode = autostartModeUninstall
		case "--autostart-status":
			mode = autostartModeStatus
		case "--autostart":
			autostartRun = true
		case "--no-autostart":
			noAutostart = true
		}
	}
	return mode, autostartRun, noAutostart
}

func autostartOptOutByEnv() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(autostartEnvOptOut)))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

// autostartPathLooksTransient：go run（go-build 缓存）与系统临时目录中的二进制不注册——
// 重启后路径即失效，注册只会留下坏项。
func autostartPathLooksTransient(exe string) bool {
	low := strings.ToLower(filepath.Clean(exe))
	if low == "" || low == "." {
		return true
	}
	sep := string(os.PathSeparator)
	if t := strings.ToLower(filepath.Clean(os.TempDir())); t != "" && t != "." {
		if low == t || strings.HasPrefix(low, t+sep) {
			return true
		}
	}
	return strings.Contains(low, sep+"go-build") || strings.Contains(low, "/go-build")
}

// autostartListenAddr：写入注册项的 LISTEN，与当前进程一致（保证登录自启后端口/唤醒匹配）。
func autostartListenAddr() string {
	return getenv("LISTEN", "127.0.0.1:8794")
}

func printAutostartJSON(action string, info autostartInfo, err error) {
	out := map[string]any{
		"action":     action,
		"ok":         err == nil,
		"supported":  info.Supported,
		"registered": info.Registered,
		"changed":    info.Changed,
		"mechanism":  info.Mechanism,
		"target":     info.Target,
		"detail":     info.Detail,
	}
	if err != nil {
		out["error"] = err.Error()
	}
	b, _ := json.Marshal(out)
	fmt.Println(string(b))
}
