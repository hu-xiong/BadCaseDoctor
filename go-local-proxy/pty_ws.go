package main

import (
	"encoding/json"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// 浏览器嵌入式终端：与 electronPtySocketAdapter 同一套事件名与负载（client_session_id + b64）。

type ptyWireIn struct {
	Event           string `json:"event"`
	ClientSessionID string `json:"client_session_id"`
	Cols            int    `json:"cols"`
	Rows            int    `json:"rows"`
	Cwd             string `json:"cwd"`
	Mode            string `json:"mode"`
	B64             string `json:"b64"`
}

type windowsPtyOut struct {
	Backend     string `json:"backend"`
	BuildNumber int    `json:"build_number,omitempty"`
}

type ptyWireOut struct {
	Event           string         `json:"event"`
	ClientSessionID string         `json:"client_session_id,omitempty"`
	B64             string         `json:"b64,omitempty"`
	Message         string         `json:"message,omitempty"`
	Cwd             string         `json:"cwd,omitempty"`
	WindowsPty      *windowsPtyOut `json:"windows_pty,omitempty"`
}

func ptyWireTermStarted(clientSessionID, cwd string) ptyWireOut {
	out := ptyWireOut{Event: "term_started", ClientSessionID: clientSessionID, Cwd: cwd}
	if wp := newTermStartedWindowsPty(); wp != nil {
		out.WindowsPty = wp
	}
	return out
}

func handlePtyTerminal(w http.ResponseWriter, r *http.Request) {
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil && !isLoopbackHost(host) {
		http.Error(w, "forbidden", http.StatusForbidden)
		return
	}
	c, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[pty] upgrade: %v", err)
		return
	}
	defer c.Close()
	idleConnEnter()
	defer idleConnLeave()

	sessions := newPtySessionMap()
	defer sessions.killAll()

	var wmu sync.Mutex
	writeJSON := func(v ptyWireOut) {
		wmu.Lock()
		defer wmu.Unlock()
		_ = c.SetWriteDeadline(time.Now().Add(60 * time.Second))
		_ = c.WriteJSON(v)
	}

	for {
		_, data, err := c.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("[pty] read: %v", err)
			}
			return
		}
		touchClientActivity()
		var in ptyWireIn
		if err := json.Unmarshal(data, &in); err != nil {
			writeJSON(ptyWireOut{Event: "term_error", Message: "invalid json"})
			continue
		}
		ev := strings.ToLower(strings.TrimSpace(in.Event))
		switch ev {
		case "term_start":
			if in.Mode != "" && in.Mode != "local" {
				writeJSON(ptyWireOut{
					Event:           "term_error",
					ClientSessionID: in.ClientSessionID,
					Message:         "Web 本机 Go 终端仅支持 local 模式。",
				})
				continue
			}
			if ptyDebugEnabled() {
				log.Printf("[pty-debug] term_start id=%q cwd=%q cols=%d rows=%d mode=%q",
					in.ClientSessionID, in.Cwd, in.Cols, in.Rows, in.Mode)
			}
			if err := sessions.start(in.ClientSessionID, in.Cwd, in.Cols, in.Rows, writeJSON); err != nil {
				log.Printf("[pty] term_start failed id=%q: %v", in.ClientSessionID, err)
				writeJSON(ptyWireOut{Event: "term_error", ClientSessionID: in.ClientSessionID, Message: err.Error()})
			}
		case "term_input":
			if err := sessions.writeInput(in.ClientSessionID, in.B64); err != nil {
				log.Printf("[pty] term_input: %v", err)
			}
		case "term_resize":
			if ptyDebugEnabled() {
				log.Printf("[pty-debug] term_resize id=%q cols=%d rows=%d", in.ClientSessionID, in.Cols, in.Rows)
			}
			sessions.resize(in.ClientSessionID, in.Cols, in.Rows)
		case "term_close":
			sessions.closeOne(in.ClientSessionID)
		default:
			// ignore
		}
	}
}
