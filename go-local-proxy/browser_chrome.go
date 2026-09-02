// 客户本机 Chrome：由 go-local-proxy 拉起（有头 + remote-debugging），供云端 Agent / 前端经本代理驱动内网页面。
//
// HTTP:
//   GET  /browser/status
//   POST /browser/start   JSON: {"headless":false,"url":"","cdp_port":0}
//   POST /browser/stop
//   任意 /browser/cdp/*   → 反代到本机 Chrome DevTools HTTP（同机 Playwright connect_over_cdp 可用）
//
// WebSocket /ws 增补:
//   {"op":"browser_start","id":"1","headless":false,"url":"...","cdp_port":0}
//   {"op":"browser_stop","id":"1"}
//   {"op":"browser_status","id":"1"}
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

type browserManager struct {
	mu       sync.Mutex
	cmd      *exec.Cmd
	port     int
	userData string
	started  time.Time
}

var globalBrowser = &browserManager{}

type browserStartReq struct {
	Headless bool   `json:"headless"`
	URL      string `json:"url"`
	CdpPort  int    `json:"cdp_port"`
}

type browserStatusResp struct {
	OK          bool   `json:"ok"`
	Running     bool   `json:"running"`
	CdpPort     int    `json:"cdp_port,omitempty"`
	CdpHTTP     string `json:"cdp_http,omitempty"`
	ProxyCDP    string `json:"proxy_cdp_base,omitempty"`
	UserDataDir string `json:"user_data_dir,omitempty"`
	StartedAt   string `json:"started_at,omitempty"`
	Message     string `json:"message,omitempty"`
}

func (b *browserManager) statusLocked() browserStatusResp {
	running := b.cmd != nil && b.cmd.Process != nil && b.port > 0
	if running && b.cmd.ProcessState != nil && b.cmd.ProcessState.Exited() {
		running = false
	}
	out := browserStatusResp{OK: true, Running: running}
	if running {
		out.CdpPort = b.port
		out.CdpHTTP = fmt.Sprintf("http://127.0.0.1:%d", b.port)
		out.ProxyCDP = "/browser/cdp"
		out.UserDataDir = b.userData
		if !b.started.IsZero() {
			out.StartedAt = b.started.Format(time.RFC3339)
		}
	}
	return out
}

func (b *browserManager) Status() browserStatusResp {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.statusLocked()
}

func (b *browserManager) Stop() error {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.stopLocked()
}

func (b *browserManager) stopLocked() error {
	if b.cmd == nil || b.cmd.Process == nil {
		b.cmd = nil
		b.port = 0
		return nil
	}
	_ = b.cmd.Process.Kill()
	_, _ = b.cmd.Process.Wait()
	b.cmd = nil
	b.port = 0
	return nil
}

func pickFreePort() (int, error) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port, nil
}

func findChromeExecutable() (string, error) {
	if p := strings.TrimSpace(os.Getenv("BADCASE_CHROME_PATH")); p != "" {
		if _, err := os.Stat(p); err == nil {
			return p, nil
		}
	}
	candidates := []string{}
	switch runtime.GOOS {
	case "windows":
		locals := []string{
			os.Getenv("PROGRAMFILES"),
			os.Getenv("PROGRAMFILES(X86)"),
			os.Getenv("LOCALAPPDATA"),
		}
		rel := []string{
			`Google\Chrome\Application\chrome.exe`,
			`Microsoft\Edge\Application\msedge.exe`,
			`Chromium\Application\chrome.exe`,
		}
		for _, root := range locals {
			if strings.TrimSpace(root) == "" {
				continue
			}
			for _, r := range rel {
				candidates = append(candidates, filepath.Join(root, r))
			}
		}
	case "darwin":
		candidates = append(candidates,
			"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
			"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
			"/Applications/Chromium.app/Contents/MacOS/Chromium",
		)
	default:
		candidates = append(candidates,
			"google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
		)
	}
	for _, c := range candidates {
		if c == "google-chrome" || c == "chromium" || c == "chromium-browser" || c == "google-chrome-stable" || c == "microsoft-edge" {
			if p, err := exec.LookPath(c); err == nil {
				return p, nil
			}
			continue
		}
		if _, err := os.Stat(c); err == nil {
			return c, nil
		}
	}
	return "", fmt.Errorf("未找到 Chrome/Edge/Chromium，可设环境变量 BADCASE_CHROME_PATH")
}

func (b *browserManager) Start(req browserStartReq) (browserStatusResp, error) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if b.cmd != nil && b.cmd.Process != nil && (b.cmd.ProcessState == nil || !b.cmd.ProcessState.Exited()) {
		st := b.statusLocked()
		st.Message = "already_running"
		return st, nil
	}

	chrome, err := findChromeExecutable()
	if err != nil {
		return browserStatusResp{OK: false, Message: err.Error()}, err
	}

	port := req.CdpPort
	if port <= 0 {
		port, err = pickFreePort()
		if err != nil {
			return browserStatusResp{OK: false, Message: err.Error()}, err
		}
	}

	userData := filepath.Join(os.TempDir(), "badcase-chrome-cdp-profile")
	_ = os.MkdirAll(userData, 0o755)

	args := []string{
		fmt.Sprintf("--remote-debugging-port=%d", port),
		"--remote-debugging-address=127.0.0.1",
		"--user-data-dir=" + userData,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-popup-blocking",
	}
	// 默认有头；仅显式 headless=true 时无头
	if req.Headless {
		args = append(args, "--headless=new", "--disable-gpu")
	}
	startURL := strings.TrimSpace(req.URL)
	if startURL == "" {
		startURL = "about:blank"
	}
	args = append(args, startURL)

	cmd := exec.Command(chrome, args...)
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		return browserStatusResp{OK: false, Message: err.Error()}, err
	}

	b.cmd = cmd
	b.port = port
	b.userData = userData
	b.started = time.Now()

	// 等 DevTools 就绪
	deadline := time.Now().Add(12 * time.Second)
	var lastErr error
	for time.Now().Before(deadline) {
		if ok, e := probeChromeCDP(port); ok {
			st := b.statusLocked()
			st.Message = "started"
			log.Printf("[browser] chrome started exe=%s cdp=%d headless=%v", chrome, port, req.Headless)
			return st, nil
		} else {
			lastErr = e
		}
		if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
			b.cmd = nil
			b.port = 0
			return browserStatusResp{OK: false, Message: "chrome exited early"}, fmt.Errorf("chrome exited early: %v", lastErr)
		}
		time.Sleep(200 * time.Millisecond)
	}
	_ = b.stopLocked()
	msg := "chrome cdp not ready"
	if lastErr != nil {
		msg = lastErr.Error()
	}
	return browserStatusResp{OK: false, Message: msg}, fmt.Errorf(msg)
}

func probeChromeCDP(port int) (bool, error) {
	u := fmt.Sprintf("http://127.0.0.1:%d/json/version", port)
	ctxClient := &http.Client{Timeout: 800 * time.Millisecond}
	resp, err := ctxClient.Get(u)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return false, fmt.Errorf("status %d", resp.StatusCode)
	}
	body, _ := io.ReadAll(resp.Body)
	return strings.Contains(string(body), "webSocketDebuggerUrl") || strings.Contains(string(body), "Browser"), nil
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func handleBrowserHTTP(w http.ResponseWriter, r *http.Request) {
	touchClientActivity()
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	path := strings.TrimPrefix(r.URL.Path, "/browser")
	if path == "" {
		path = "/"
	}

	switch {
	case path == "/status" && r.Method == http.MethodGet:
		writeJSON(w, http.StatusOK, globalBrowser.Status())
		return
	case path == "/stop" && r.Method == http.MethodPost:
		_ = globalBrowser.Stop()
		writeJSON(w, http.StatusOK, browserStatusResp{OK: true, Running: false, Message: "stopped"})
		return
	case path == "/start" && r.Method == http.MethodPost:
		var req browserStartReq
		_ = json.NewDecoder(r.Body).Decode(&req)
		st, err := globalBrowser.Start(req)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, st)
			return
		}
		writeJSON(w, http.StatusOK, st)
		return
	case strings.HasPrefix(path, "/cdp"):
		handleBrowserCDPProxy(w, r)
		return
	default:
		http.NotFound(w, r)
	}
}

func handleBrowserCDPProxy(w http.ResponseWriter, r *http.Request) {
	st := globalBrowser.Status()
	if !st.Running || st.CdpPort <= 0 {
		http.Error(w, "browser not running", http.StatusServiceUnavailable)
		return
	}
	target, err := url.Parse(fmt.Sprintf("http://127.0.0.1:%d", st.CdpPort))
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	proxy := httputil.NewSingleHostReverseProxy(target)
	origDirector := proxy.Director
	proxy.Director = func(req *http.Request) {
		origDirector(req)
		// /browser/cdp/json/version → /json/version
		p := strings.TrimPrefix(req.URL.Path, "/browser/cdp")
		if p == "" {
			p = "/"
		}
		req.URL.Path = p
		req.Host = target.Host
	}
	proxy.ServeHTTP(w, r)
}

// WS 扩展字段（复用 msgIn 的松散 JSON：额外字段用二次解析）
type browserWSIn struct {
	Op       string `json:"op"`
	ID       string `json:"id"`
	Headless bool   `json:"headless"`
	URL      string `json:"url"`
	CdpPort  int    `json:"cdp_port"`
}

func handleBrowserWSOp(raw []byte, write func(msgOut)) bool {
	var in browserWSIn
	if err := json.Unmarshal(raw, &in); err != nil {
		return false
	}
	op := strings.ToLower(strings.TrimSpace(in.Op))
	switch op {
	case "browser_start":
		st, err := globalBrowser.Start(browserStartReq{
			Headless: in.Headless,
			URL:      in.URL,
			CdpPort:  in.CdpPort,
		})
		if err != nil {
			write(msgOut{Op: "error", ID: in.ID, Message: st.Message})
			return true
		}
		payload, _ := json.Marshal(st)
		write(msgOut{Op: "browser_ok", ID: in.ID, Data: string(payload), Message: st.Message})
		return true
	case "browser_stop":
		_ = globalBrowser.Stop()
		write(msgOut{Op: "browser_ok", ID: in.ID, Message: "stopped"})
		return true
	case "browser_status":
		st := globalBrowser.Status()
		payload, _ := json.Marshal(st)
		write(msgOut{Op: "browser_status", ID: in.ID, Data: string(payload)})
		return true
	default:
		return false
	}
}
