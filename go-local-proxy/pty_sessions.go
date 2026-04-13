package main

import (
	"encoding/base64"
	"fmt"
	"io"
	"log"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// 每个会话只打一次：transform 把整段输出吃成空（误判 UTF-16 等）时便于发现。
var ptyEmptyTransformOnce sync.Map

type ptySessionMap struct {
	mu sync.Mutex
	m  map[string]*ptySession
}

func newPtySessionMap() *ptySessionMap {
	return &ptySessionMap{m: make(map[string]*ptySession)}
}

func (sm *ptySessionMap) killAll() {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	for id, s := range sm.m {
		if s != nil {
			s.stop()
		}
		delete(sm.m, id)
	}
}

type ptySession struct {
	id   string
	sh   *interactiveShell
	cwd  string // 已规范化，与 term_start 比对用
	cols int
	rows int
}

func normPtyCwd(cwd string) string {
	s := strings.TrimSpace(cwd)
	if s == "" {
		return ""
	}
	return filepath.Clean(s)
}

func (sm *ptySessionMap) start(clientSessionID, cwd string, cols, rows int, writeJSON func(ptyWireOut)) error {
	if clientSessionID == "" {
		return fmt.Errorf("empty client_session_id")
	}
	if cols <= 0 {
		cols = 80
	}
	if rows <= 0 {
		rows = 24
	}
	wantCwd := normPtyCwd(cwd)

	sm.mu.Lock()
	if sess, ok := sm.m[clientSessionID]; ok && sess != nil && sess.sh != nil && sess.sh.alive() {
		if sess.cwd == wantCwd {
			if sess.cols != cols || sess.rows != rows {
				if err := sess.sh.resize(cols, rows); err != nil {
					log.Printf("[pty] resize (reuse) %s: %v", clientSessionID, err)
				}
				sess.cols, sess.rows = cols, rows
			}
			sm.mu.Unlock()
			if ptyDebugEnabled() {
				log.Printf("[pty-debug] term_started (reuse) id=%q cwd=%q cols=%d rows=%d", clientSessionID, sess.cwd, sess.cols, sess.rows)
			}
			writeJSON(ptyWireTermStarted(clientSessionID, sess.cwd))
			return nil
		}
	}
	if old, ok := sm.m[clientSessionID]; ok && old != nil {
		old.stop()
		delete(sm.m, clientSessionID)
	}
	sm.mu.Unlock()

	sh, err := spawnInteractiveShell(wantCwd, cols, rows)
	if err != nil {
		return err
	}

	sess := &ptySession{id: clientSessionID, sh: sh, cwd: wantCwd, cols: cols, rows: rows}

	sm.mu.Lock()
	sm.m[clientSessionID] = sess
	sm.mu.Unlock()

	if ptyDebugEnabled() {
		log.Printf("[pty-debug] session spawned id=%q cwd=%q cols=%d rows=%d -> term_started", clientSessionID, wantCwd, cols, rows)
	}

	writeJSON(ptyWireTermStarted(clientSessionID, wantCwd))

	if ptyDebugEnabled() {
		log.Printf("[pty-debug] shellPostStartNudge id=%q", clientSessionID)
	}
	shellPostStartNudge(sh)

	go func() {
		buf := make([]byte, 32768)
		var outCarry []byte
		var outChunkSeq int
		for {
			n, err := sh.Stdout.Read(buf)
			if n > 0 {
				var out []byte
				if sh.pipeStdoutUTF16 {
					out = transformPtyConsoleOutput(&outCarry, buf[:n])
				} else {
					outCarry = nil
					out = append([]byte(nil), buf[:n]...)
				}
				if ptyDebugEnabled() {
					outChunkSeq++
					log.Printf("[pty-debug] stdout read id=%q #%d raw=%d out=%d carry_left=%d",
						clientSessionID, outChunkSeq, n, len(out), len(outCarry))
				}
				if n > 0 && len(out) == 0 {
					if _, already := ptyEmptyTransformOnce.LoadOrStore(clientSessionID, true); !already {
						headN := n
						if headN > 64 {
							headN = 64
						}
						log.Printf("[pty] %s: %d raw bytes -> empty after transform (head=% x). ConPTY 应为 UTF-8；若误判 UTF-16 会吞光。可设 BADCASE_PTY_DEBUG=1。",
							clientSessionID, n, buf[:headN])
					}
				}
				if len(out) > 0 {
					b64 := base64.StdEncoding.EncodeToString(out)
					writeJSON(ptyWireOut{Event: "term_output", ClientSessionID: clientSessionID, B64: b64})
				}
			}
			if err != nil {
				if err != io.EOF {
					log.Printf("[pty] read %s: %v", clientSessionID, err)
				}
				break
			}
		}
		sm.mu.Lock()
		cur, ok := sm.m[clientSessionID]
		stillOurs := ok && cur == sess
		if stillOurs {
			delete(sm.m, clientSessionID)
		}
		sm.mu.Unlock()
		if stillOurs {
			writeJSON(ptyWireOut{Event: "term_exit", ClientSessionID: clientSessionID})
		}
		ptyEmptyTransformOnce.Delete(clientSessionID)
		sess.stop()
	}()

	return nil
}

func (sm *ptySessionMap) writeInput(clientSessionID, b64 string) error {
	if clientSessionID == "" || b64 == "" {
		return nil
	}
	sm.mu.Lock()
	s, ok := sm.m[clientSessionID]
	sm.mu.Unlock()
	if !ok || s == nil || s.sh == nil {
		return fmt.Errorf("no session")
	}
	raw, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		return err
	}
	_, err = s.sh.Stdin.Write(raw)
	return err
}

func (sm *ptySessionMap) resize(clientSessionID string, cols, rows int) {
	sm.mu.Lock()
	s, ok := sm.m[clientSessionID]
	sm.mu.Unlock()
	if !ok || s == nil || s.sh == nil {
		return
	}
	if err := s.sh.resize(cols, rows); err != nil {
		log.Printf("[pty] resize %s: %v", clientSessionID, err)
		return
	}
	sm.mu.Lock()
	if cur, ok2 := sm.m[clientSessionID]; ok2 && cur == s {
		cur.cols, cur.rows = cols, rows
	}
	sm.mu.Unlock()
}

func (sm *ptySessionMap) closeOne(clientSessionID string) {
	if clientSessionID == "" {
		return
	}
	sm.mu.Lock()
	s, ok := sm.m[clientSessionID]
	if ok {
		delete(sm.m, clientSessionID)
	}
	sm.mu.Unlock()
	if s != nil {
		s.stop()
	}
}

func (s *ptySession) stop() {
	if s == nil || s.sh == nil {
		return
	}
	s.sh.stop()
}

// shellPostStartNudge 写入一次 CRLF，促使 PowerShell 等在 ConPTY/管道下尽快吐出提示符（与前端首帧 fit 并行）。
func shellPostStartNudge(sh *interactiveShell) {
	if sh == nil || sh.Stdin == nil {
		return
	}
	go func() {
		time.Sleep(120 * time.Millisecond)
		_, _ = sh.Stdin.Write([]byte("\r\n"))
	}()
}
