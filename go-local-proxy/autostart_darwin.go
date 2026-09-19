//go:build darwin

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// LaunchAgent（用户级、无需 sudo）：登录时 RunAtLoad 拉起；KeepAlive 仅对异常退出生效，
// 因此空闲正常退出（exit 0）后不会立刻被 launchd 反复拉起，与 Windows/Linux 语义对齐。
func autostartPlistPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, "Library", "LaunchAgents", autostartLabel+".plist"), nil
}

func autostartLogPath() string {
	home, err := os.UserHomeDir()
	if err != nil || home == "" {
		return ""
	}
	return filepath.Join(home, "Library", "Logs", "badcase-local-proxy.log")
}

func xmlEscape(s string) string {
	return strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;").Replace(s)
}

func autostartPlistContent(exe, listen, logPath string) string {
	var b strings.Builder
	b.WriteString("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
	b.WriteString("<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n")
	b.WriteString("<plist version=\"1.0\">\n<dict>\n")
	fmt.Fprintf(&b, "\t<key>Label</key>\n\t<string>%s</string>\n", xmlEscape(autostartLabel))
	b.WriteString("\t<key>ProgramArguments</key>\n\t<array>\n")
	fmt.Fprintf(&b, "\t\t<string>%s</string>\n", xmlEscape(exe))
	b.WriteString("\t\t<string>--autostart</string>\n\t</array>\n")
	b.WriteString("\t<key>RunAtLoad</key>\n\t<true/>\n")
	b.WriteString("\t<key>KeepAlive</key>\n\t<dict>\n\t\t<key>SuccessfulExit</key>\n\t\t<false/>\n\t</dict>\n")
	b.WriteString("\t<key>EnvironmentVariables</key>\n\t<dict>\n")
	fmt.Fprintf(&b, "\t\t<key>LISTEN</key>\n\t\t<string>%s</string>\n", xmlEscape(listen))
	b.WriteString("\t</dict>\n")
	if dir := filepath.Dir(exe); dir != "" && dir != "." {
		fmt.Fprintf(&b, "\t<key>WorkingDirectory</key>\n\t<string>%s</string>\n", xmlEscape(dir))
	}
	if logPath != "" {
		fmt.Fprintf(&b, "\t<key>StandardOutPath</key>\n\t<string>%s</string>\n", xmlEscape(logPath))
		fmt.Fprintf(&b, "\t<key>StandardErrorPath</key>\n\t<string>%s</string>\n", xmlEscape(logPath))
	}
	b.WriteString("</dict>\n</plist>\n")
	return b.String()
}

func launchctlDomainTarget() string {
	return fmt.Sprintf("gui/%d", os.Getuid())
}

// launchctlLoaded：macOS 10.13+ 用 print 判定；老系统命令不存在时返回 false（走幂等重载路径）。
func launchctlLoaded() bool {
	return exec.Command("launchctl", "print", launchctlDomainTarget()+"/"+autostartLabel).Run() == nil
}

func autostartDescribe() (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "macos-launchagent"}
	p, err := autostartPlistPath()
	if err != nil {
		return info, err
	}
	info.Target = p
	if _, err := os.Stat(p); err == nil {
		info.Registered = true
		if launchctlLoaded() {
			info.Detail = "loaded"
		} else {
			info.Detail = "plist-exists-not-loaded"
		}
	}
	return info, nil
}

func autostartEnsure(exe string) (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "macos-launchagent"}
	p, err := autostartPlistPath()
	if err != nil {
		return info, err
	}
	info.Target = p
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return info, err
	}

	want := autostartPlistContent(exe, autostartListenAddr(), autostartLogPath())
	cur, _ := os.ReadFile(p)
	written := string(cur) != want
	if written {
		if err := os.WriteFile(p, []byte(want), 0o644); err != nil {
			return info, err
		}
	}

	loaded := launchctlLoaded()
	if written || !loaded {
		// 已加载时先 bootout，保证路径/内容更新生效；未加载时失败可忽略
		_ = exec.Command("launchctl", "bootout", launchctlDomainTarget(), p).Run()
		if out, err := exec.Command("launchctl", "bootstrap", launchctlDomainTarget(), p).CombinedOutput(); err != nil {
			// 老系统（<10.10 无 bootstrap）回退 load -w
			if out2, err2 := exec.Command("launchctl", "load", "-w", p).CombinedOutput(); err2 != nil {
				return info, fmt.Errorf(
					"launchctl bootstrap: %v (%s); load: %v (%s)",
					err, strings.TrimSpace(string(out)), err2, strings.TrimSpace(string(out2)),
				)
			}
		}
		info.Changed = true
		info.Detail = "plist written & loaded"
	} else {
		info.Detail = "already-registered"
	}
	info.Registered = true
	return info, nil
}

func autostartRemove() (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "macos-launchagent"}
	p, err := autostartPlistPath()
	if err != nil {
		return info, err
	}
	info.Target = p
	_ = exec.Command("launchctl", "bootout", launchctlDomainTarget(), p).Run()
	if err := os.Remove(p); err != nil {
		if os.IsNotExist(err) {
			info.Detail = "not-registered"
			return info, nil
		}
		return info, err
	}
	info.Changed = true
	info.Detail = "removed"
	return info, nil
}

// hideConsoleForAutostart：非 Windows 无控制台概念，留空实现以对齐 main 的跨平台调用。
func hideConsoleForAutostart() {}
