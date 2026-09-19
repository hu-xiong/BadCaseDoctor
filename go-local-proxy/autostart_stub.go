//go:build !windows && !darwin && !linux

package main

// 其他平台（*BSD 等）：不支持开机自启注册，显式返回 supported=false，不影响主服务运行。

func autostartEnsure(exe string) (autostartInfo, error) {
	return autostartInfo{Supported: false, Mechanism: "unsupported", Detail: "platform not supported"}, nil
}

func autostartDescribe() (autostartInfo, error) {
	return autostartInfo{Supported: false, Mechanism: "unsupported", Detail: "platform not supported"}, nil
}

func autostartRemove() (autostartInfo, error) {
	return autostartInfo{Supported: false, Mechanism: "unsupported", Detail: "platform not supported"}, nil
}

func hideConsoleForAutostart() {}
