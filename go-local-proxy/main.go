// 本地轻量服务：浏览器终端模块通过 WebSocket 连接本进程，下发命令、执行 shell、流式回传输出。
// 与云端 Flask（LLM/业务 API）分离：Flask 走 HTTPS；本服务仅本机 loopback，不暴露公网。
//
// 构建产物放到仓库 client_binaries/ 供 Web 下载（文件名见 ../badcase_client_binaries.py）：
//   GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o ../client_binaries/badcase-local-proxy.exe .
//   GOOS=linux   GOARCH=amd64 go build -ldflags="-s -w" -o ../client_binaries/badcase-local-proxy-linux-amd64 .
//   GOOS=darwin  GOARCH=amd64 go build -ldflags="-s -w" -o ../client_binaries/badcase-local-proxy-darwin-amd64 .
//   GOOS=darwin  GOARCH=arm64 go build -ldflags="-s -w" -o ../client_binaries/badcase-local-proxy-darwin-arm64 .
package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// 自定义 URL 协议（见 scripts/protocol/）：badcase-local-proxy://wakeup?... 由系统传给本进程。
// 若本机已有实例在监听，则直接退出 0，避免重复启动。
const urlSchemeMarker = "badcase-local-proxy://"

// 与浏览器约定：JSON 文本帧（UTF-8）。
//
// 客户端 → 服务端
//   {"op":"ping"}
//   {"op":"run","id":"1","cmd":"ls -la","cwd":"","timeout_sec":120,"env":{...},"confirmed":true}
//   整行仅为 cd（无 &&|;）：不启子进程，更新会话 cwd，chunk stdout 提示后 done exit 0
//   {"op":"cancel","id":"1"}
//   {"op":"session","action":"set_cwd","path":"/tmp"}
//   {"op":"session","action":"set_env","key":"K","value":"v"}
//
// 服务端 → 客户端
//   {"op":"pong"}
//   {"op":"chunk","id":"1","stream":"stdout","data":"..."}
//   {"op":"chunk","id":"1","stream":"stderr","data":"..."}
//   {"op":"done","id":"1","exit_code":0}
//   {"op":"cancelled","id":"1"}
//   {"op":"session_ok","id":"","message":"..."}
//   {"op":"confirm_required","id":"1","reason":"bash_max_subcommands","message":"..."}
//   {"op":"error","id":"1","message":"..."}

type msgIn struct {
	Op         string            `json:"op"`
	ID         string            `json:"id"`
	Cmd        string            `json:"cmd"`
	Cwd        string            `json:"cwd"`
	TimeoutSec int               `json:"timeout_sec"`
	Env        map[string]string `json:"env"`
	Confirmed  bool              `json:"confirmed"`
	Action     string            `json:"action"`
	Path       string            `json:"path"`
	Key        string            `json:"key"`
	Value      string            `json:"value"`
}

type msgOut struct {
	Op       string `json:"op"`
	ID       string `json:"id,omitempty"`
	Stream   string `json:"stream,omitempty"`
	Data     string `json:"data,omitempty"`
	ExitCode int    `json:"exit_code,omitempty"`
	Message  string `json:"message,omitempty"`
	Reason   string `json:"reason,omitempty"`
}

type connSession struct {
	mu  sync.Mutex
	cwd string
	env map[string]string
}

func (s *connSession) effectiveCwd(req string) string {
	req = strings.TrimSpace(req)
	if req != "" {
		return req
	}
	if s == nil {
		return ""
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.cwd
}

func (s *connSession) mergedEnv(override map[string]string) []string {
	base := os.Environ()
	if s == nil {
		for k, v := range override {
			base = append(base, k+"="+v)
		}
		return base
	}
	s.mu.Lock()
	for k, v := range s.env {
		base = append(base, k+"="+v)
	}
	s.mu.Unlock()
	for k, v := range override {
		base = append(base, k+"="+v)
	}
	return base
}

// runID -> cancel func（与 run 的 id 对齐，供 cancel op 终止）
var runCancels sync.Map

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	CheckOrigin:     checkOriginLocalhost,
}

func checkOriginLocalhost(r *http.Request) bool {
	o := r.Header.Get("Origin")
	if o == "" {
		return true
	}
	lo := strings.ToLower(o)
	return strings.HasPrefix(lo, "http://localhost:") ||
		strings.HasPrefix(lo, "http://127.0.0.1:") ||
		strings.HasPrefix(lo, "https://localhost:") ||
		strings.HasPrefix(lo, "https://127.0.0.1:") ||
		strings.HasPrefix(lo, "file://")
}

func hasWakeupSchemeArg(args []string) bool {
	for _, a := range args {
		if strings.Contains(strings.ToLower(a), strings.ToLower(urlSchemeMarker)) {
			return true
		}
	}
	return false
}

func healthURLFromListenAddr(addr string) string {
	addr = strings.TrimSpace(addr)
	if addr == "" {
		addr = "127.0.0.1:8794"
	}
	return "http://" + addr + "/health"
}

func probeHealthOK(healthURL string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 900*time.Millisecond)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, healthURL, nil)
	if err != nil {
		return false
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return false
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false
	}
	return strings.TrimSpace(string(body)) == "ok"
}

func main() {
	addr := getenv("LISTEN", "127.0.0.1:8794")
	pathWS := getenv("WS_PATH", "/ws")

	if len(os.Args) > 1 && hasWakeupSchemeArg(os.Args[1:]) {
		u := healthURLFromListenAddr(addr)
		if probeHealthOK(u) {
			log.Printf("[go-local-proxy] wakeup: already up (%s)", u)
			os.Exit(0)
		}
		log.Printf("[go-local-proxy] wakeup: starting (health %s not ok)", u)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/pty", handlePtyTerminal)
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		// 允许浏览器从 http://localhost:5173 等页面 fetch 健康检查（与 Web 终端页探测联动）
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		_, _ = w.Write([]byte("ok"))
	})
	mux.HandleFunc(pathWS, handleWebSocket)

	log.Printf("[go-local-proxy] listen %s  http=/health  ws_run=%s  ws_pty=/pty", addr, pathWS)
	if ptyDebugEnabled() {
		log.Printf("[go-local-proxy] BADCASE_PTY_DEBUG=1: verbose PTY logs enabled")
	}
	srv := &http.Server{Addr: addr, Handler: mux}
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

func getenv(k, def string) string {
	v := strings.TrimSpace(os.Getenv(k))
	if v == "" {
		return def
	}
	return v
}

func handleWebSocket(w http.ResponseWriter, r *http.Request) {
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil && !isLoopbackHost(host) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}

	c, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("upgrade: %v", err)
		return
	}
	defer c.Close()

	sess := &connSession{env: make(map[string]string)}
	var wmu sync.Mutex
	write := func(m msgOut) {
		wmu.Lock()
		defer wmu.Unlock()
		_ = c.SetWriteDeadline(time.Now().Add(15 * time.Second))
		_ = c.WriteJSON(m)
	}

	for {
		_, data, err := c.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("read: %v", err)
			}
			return
		}
		var in msgIn
		if err := json.Unmarshal(data, &in); err != nil {
			write(msgOut{Op: "error", Message: "invalid json"})
			continue
		}
		switch strings.ToLower(strings.TrimSpace(in.Op)) {
		case "ping":
			write(msgOut{Op: "pong"})
		case "cancel":
			id := strings.TrimSpace(in.ID)
			if id == "" {
				write(msgOut{Op: "error", Message: "cancel: empty id"})
				continue
			}
			if v, ok := runCancels.Load(id); ok {
				if cf, ok := v.(context.CancelFunc); ok {
					cf()
				}
			}
			write(msgOut{Op: "cancel_ack", ID: id})
		case "session":
			act := strings.ToLower(strings.TrimSpace(in.Action))
			switch act {
			case "set_cwd":
				sess.mu.Lock()
				sess.cwd = strings.TrimSpace(in.Path)
				sess.mu.Unlock()
				write(msgOut{Op: "session_ok", ID: in.ID, Message: "set_cwd"})
			case "set_env":
				k := strings.TrimSpace(in.Key)
				if k == "" {
					write(msgOut{Op: "error", ID: in.ID, Message: "set_env: empty key"})
					continue
				}
				sess.mu.Lock()
				sess.env[k] = in.Value
				sess.mu.Unlock()
				write(msgOut{Op: "session_ok", ID: in.ID, Message: "set_env"})
			default:
				write(msgOut{Op: "error", ID: in.ID, Message: "unknown session action"})
			}
		case "run":
			if strings.TrimSpace(in.Cmd) == "" {
				write(msgOut{Op: "error", ID: in.ID, Message: "empty cmd"})
				continue
			}
			runCmd(c, &wmu, in, write, sess)
		default:
			write(msgOut{Op: "error", ID: in.ID, Message: "unknown op"})
		}
	}
}

func runCmd(c *websocket.Conn, wmu *sync.Mutex, in msgIn, write func(msgOut), sess *connSession) {
	timeout := time.Duration(in.TimeoutSec) * time.Second
	if timeout <= 0 || timeout > 24*time.Hour {
		timeout = 120 * time.Second
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	id := strings.TrimSpace(in.ID)
	if id != "" {
		runCancels.Store(id, cancel)
		defer runCancels.Delete(id)
	}
	defer cancel()

	cwd := sess.effectiveCwd(in.Cwd)
	if cdArg, cdOk := tryParsePureCdCommand(in.Cmd); cdOk {
		newCwd := sessionResolveCd(cwd, cdArg)
		if err := checkAgentTerminalWorkspaceCwd(newCwd); err != nil {
			write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
			return
		}
		if sess != nil {
			sess.mu.Lock()
			sess.cwd = newCwd
			sess.mu.Unlock()
		}
		msg := "工作目录已更新: " + newCwd + "\n"
		write(msgOut{Op: "chunk", ID: in.ID, Stream: "stdout", Data: msg})
		write(msgOut{Op: "done", ID: in.ID, ExitCode: 0})
		return
	}
	if err := checkAgentTerminalPermissions(in.Cmd, cwd, in.Confirmed); err != nil {
		if errors.Is(err, ErrConfirmBashMaxSubcommands) {
			write(msgOut{
				Op:      "confirm_required",
				ID:      in.ID,
				Reason:  "bash_max_subcommands",
				Message: "管道/子命令段数超过 permissions.bash_max_subcommands，确认后仍可调",
			})
			return
		}
		write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
		return
	}
	cmd := shellCommand(ctx, in.Cmd, cwd, sess.mergedEnv(in.Env))
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
		return
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
		return
	}
	if err := cmd.Start(); err != nil {
		write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
		return
	}

	pump := func(stream string, r io.Reader) {
		buf := make([]byte, 4096)
		for {
			n, err := r.Read(buf)
			if n > 0 {
				m := msgOut{Op: "chunk", ID: in.ID, Stream: stream, Data: string(buf[:n])}
				wmu.Lock()
				_ = c.SetWriteDeadline(time.Now().Add(30 * time.Second))
				_ = c.WriteJSON(m)
				wmu.Unlock()
			}
			if err != nil {
				break
			}
		}
	}
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		pump("stdout", stdout)
	}()
	go func() {
		defer wg.Done()
		pump("stderr", stderr)
	}()
	wg.Wait()

	err = cmd.Wait()
	if errors.Is(ctx.Err(), context.Canceled) {
		write(msgOut{Op: "cancelled", ID: in.ID})
		return
	}
	code := 0
	if err != nil {
		if x, ok := exitCodeOf(err); ok {
			code = x
		} else {
			write(msgOut{Op: "error", ID: in.ID, Message: err.Error()})
			return
		}
	}
	write(msgOut{Op: "done", ID: in.ID, ExitCode: code})
}

func isLoopbackHost(host string) bool {
	h := strings.Trim(host, "[]")
	if h == "127.0.0.1" || h == "::1" {
		return true
	}
	if ip := net.ParseIP(h); ip != nil {
		return ip.IsLoopback()
	}
	return false
}

func shellCommand(ctx context.Context, cmdline, cwd string, env []string) *exec.Cmd {
	cmdline = strings.TrimSpace(cmdline)
	if runtime.GOOS == "windows" {
		c := exec.CommandContext(ctx, "cmd", "/C", cmdline)
		if cwd != "" {
			c.Dir = cwd
		}
		c.Env = env
		return c
	}
	c := exec.CommandContext(ctx, "bash", "-lc", cmdline)
	if cwd != "" {
		c.Dir = cwd
	}
	c.Env = env
	return c
}

func exitCodeOf(err error) (int, bool) {
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		return ee.ExitCode(), true
	}
	return 0, false
}
