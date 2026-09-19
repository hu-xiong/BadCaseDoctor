//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// systemd 用户服务（无需 root）：登录时 default.target 拉起；Restart=on-failure 仅兜崩溃，
// 空闲正常退出（exit 0）不会被无限重拉。无 user manager（容器/精简发行版）时回退 XDG autostart。
const (
	autostartSystemdUnitName = "badcase-local-proxy.service"
	autostartDesktopName     = "badcase-local-proxy.desktop"
)

func autostartUnitPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "systemd", "user", autostartSystemdUnitName), nil
}

func autostartDesktopPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "autostart", autostartDesktopName), nil
}

// systemdUserAvailable：user manager 可达即认为可用（show-environment 失败通常是没有 user bus）。
func systemdUserAvailable() bool {
	if _, err := exec.LookPath("systemctl"); err != nil {
		return false
	}
	return exec.Command("systemctl", "--user", "show-environment").Run() == nil
}

// systemdQuoteExec：systemd ExecStart 的路径引用（% 需转义，含空白/引号/反斜杠时整体加引号）。
func systemdQuoteExec(p string) string {
	p = strings.ReplaceAll(p, "%", "%%")
	if strings.ContainsAny(p, " \t\"'\\") {
		p = `"` + strings.ReplaceAll(p, `\`, `\\`) + `"`
	}
	return p
}

func autostartUnitContent(exe, listen string) string {
	return fmt.Sprintf(`[Unit]
Description=BadCase Doctor local proxy (loopback shell/browser bridge)
After=default.target

[Service]
Type=simple
ExecStart=%s --autostart
Environment=LISTEN=%s
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
`, systemdQuoteExec(exe), listen)
}

// desktopExecQuote：.desktop Exec 字段引用（% 为字段码需转义；含空白时整体加引号）。
func desktopExecQuote(p string) string {
	p = strings.ReplaceAll(p, "%", "%%")
	if strings.ContainsAny(p, " \t") {
		p = `"` + strings.ReplaceAll(strings.ReplaceAll(p, `\`, `\\`), `"`, `\"`) + `"`
	}
	return p
}

func autostartDesktopContent(exe string) string {
	return fmt.Sprintf(`[Desktop Entry]
Type=Application
Name=BadCase Local Proxy
Comment=Loopback shell/browser bridge for BadCase Doctor
Exec=%s --autostart
Terminal=false
X-GNOME-Autostart-enabled=true
`, desktopExecQuote(exe))
}

func writeIfChanged(path, content string) (bool, error) {
	cur, _ := os.ReadFile(path)
	if string(cur) == content {
		return false, nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return false, err
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return false, err
	}
	return true, nil
}

func systemdUnitEnabled() bool {
	out, err := exec.Command("systemctl", "--user", "is-enabled", autostartSystemdUnitName).Output()
	return err == nil && strings.TrimSpace(string(out)) == "enabled"
}

func autostartDescribe() (autostartInfo, error) {
	info := autostartInfo{Supported: true}
	if unitPath, err := autostartUnitPath(); err == nil {
		if _, statErr := os.Stat(unitPath); statErr == nil && systemdUnitEnabled() {
			info.Registered = true
			info.Mechanism = "linux-systemd-user"
			info.Target = unitPath
			info.Detail = "enabled"
			return info, nil
		}
	}
	if desktopPath, err := autostartDesktopPath(); err == nil {
		if _, statErr := os.Stat(desktopPath); statErr == nil {
			info.Registered = true
			info.Mechanism = "linux-xdg-autostart"
			info.Target = desktopPath
			info.Detail = "desktop-file"
		}
	}
	return info, nil
}

func autostartEnsure(exe string) (autostartInfo, error) {
	info := autostartInfo{Supported: true}
	unitPath, err := autostartUnitPath()
	if err != nil {
		return info, err
	}
	desktopPath, _ := autostartDesktopPath()

	if systemdUserAvailable() {
		info.Mechanism = "linux-systemd-user"
		info.Target = unitPath
		changed, err := writeIfChanged(unitPath, autostartUnitContent(exe, autostartListenAddr()))
		if err != nil {
			return info, err
		}
		if changed {
			_ = exec.Command("systemctl", "--user", "daemon-reload").Run()
		}
		if !systemdUnitEnabled() {
			if out, err := exec.Command("systemctl", "--user", "enable", autostartSystemdUnitName).CombinedOutput(); err != nil {
				return info, fmt.Errorf("systemctl --user enable: %v (%s)", err, strings.TrimSpace(string(out)))
			}
			changed = true
		}
		// systemd 接管后清掉早前的 XDG 回退文件，避免双启
		if desktopPath != "" {
			if _, statErr := os.Stat(desktopPath); statErr == nil {
				if rmErr := os.Remove(desktopPath); rmErr == nil {
					changed = true
				}
			}
		}
		info.Registered = true
		info.Changed = changed
		if changed {
			info.Detail = "unit written & enabled"
		} else {
			info.Detail = "already-registered"
		}
		return info, nil
	}

	// 无 user manager：XDG autostart（仅桌面会话登录时启动，不提供崩溃重拉）
	info.Mechanism = "linux-xdg-autostart"
	info.Target = desktopPath
	changed, err := writeIfChanged(desktopPath, autostartDesktopContent(exe))
	if err != nil {
		return info, err
	}
	info.Registered = true
	info.Changed = changed
	if changed {
		info.Detail = "desktop-file written"
	} else {
		info.Detail = "already-registered"
	}
	return info, nil
}

func autostartRemove() (autostartInfo, error) {
	info := autostartInfo{Supported: true}
	removed := false
	if unitPath, err := autostartUnitPath(); err == nil {
		if _, statErr := os.Stat(unitPath); statErr == nil {
			info.Mechanism = "linux-systemd-user"
			info.Target = unitPath
			if systemdUserAvailable() {
				_ = exec.Command("systemctl", "--user", "disable", "--now", autostartSystemdUnitName).Run()
			}
			if err := os.Remove(unitPath); err == nil {
				removed = true
				if systemdUserAvailable() {
					_ = exec.Command("systemctl", "--user", "daemon-reload").Run()
				}
			}
		}
	}
	if desktopPath, err := autostartDesktopPath(); err == nil {
		if _, statErr := os.Stat(desktopPath); statErr == nil {
			if info.Mechanism == "" {
				info.Mechanism = "linux-xdg-autostart"
				info.Target = desktopPath
			}
			if err := os.Remove(desktopPath); err == nil {
				removed = true
			}
		}
	}
	info.Changed = removed
	if removed {
		info.Detail = "removed"
	} else {
		info.Detail = "not-registered"
	}
	return info, nil
}

// hideConsoleForAutostart：非 Windows 无控制台概念，留空实现以对齐 main 的跨平台调用。
func hideConsoleForAutostart() {}
