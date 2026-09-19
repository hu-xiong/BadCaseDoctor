//go:build windows

package main

import (
	"errors"
	"strings"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

// 当前用户 Run 键：登录时由 explorer 拉起，无需管理员；值指向本 exe + --autostart（隐藏控制台/常驻）。
const (
	autostartRunKeyPath   = `Software\Microsoft\Windows\CurrentVersion\Run`
	autostartRunValueName = "BadCaseLocalProxy"
)

func autostartDesiredCommand(exe string) string {
	return `"` + exe + `" --autostart`
}

func autostartDescribe() (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "windows-registry-run"}
	k, err := registry.OpenKey(registry.CURRENT_USER, autostartRunKeyPath, registry.QUERY_VALUE)
	if err != nil {
		return info, err
	}
	defer k.Close()
	v, _, err := k.GetStringValue(autostartRunValueName)
	if err != nil {
		if errors.Is(err, windows.ERROR_FILE_NOT_FOUND) {
			return info, nil
		}
		return info, err
	}
	info.Registered = strings.TrimSpace(v) != ""
	info.Target = v
	return info, nil
}

func autostartEnsure(exe string) (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "windows-registry-run"}
	want := autostartDesiredCommand(exe)
	info.Target = want

	k, _, err := registry.CreateKey(
		registry.CURRENT_USER,
		autostartRunKeyPath,
		registry.QUERY_VALUE|registry.SET_VALUE,
	)
	if err != nil {
		return info, err
	}
	defer k.Close()

	cur, _, err := k.GetStringValue(autostartRunValueName)
	if err == nil && cur == want {
		info.Registered = true
		info.Detail = "already-registered"
		return info, nil
	}
	if err := k.SetStringValue(autostartRunValueName, want); err != nil {
		return info, err
	}
	info.Registered = true
	info.Changed = true
	if strings.TrimSpace(cur) == "" {
		info.Detail = "registered"
	} else {
		info.Detail = "updated path: " + cur
	}
	return info, nil
}

func autostartRemove() (autostartInfo, error) {
	info := autostartInfo{Supported: true, Mechanism: "windows-registry-run"}
	k, err := registry.OpenKey(registry.CURRENT_USER, autostartRunKeyPath, registry.QUERY_VALUE|registry.SET_VALUE)
	if err != nil {
		return info, err
	}
	defer k.Close()
	if v, _, gerr := k.GetStringValue(autostartRunValueName); gerr == nil {
		info.Target = v
	}
	if err := k.DeleteValue(autostartRunValueName); err != nil {
		if errors.Is(err, windows.ERROR_FILE_NOT_FOUND) {
			info.Detail = "not-registered"
			return info, nil
		}
		return info, err
	}
	info.Changed = true
	info.Detail = "removed"
	return info, nil
}
