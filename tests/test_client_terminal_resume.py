# -*- coding: utf-8 -*-
from agents.client_terminal_resume import (
    format_terminal_results_prompt,
    merge_client_shell_cwd,
    normalize_terminal_results,
)


def test_normalize_and_format():
    raw = [
        {
            "command": "echo hi",
            "cwd": "C:\\work",
            "exitCode": 0,
            "ok": True,
            "stdout": "hi\n",
        }
    ]
    rows = normalize_terminal_results(raw)
    assert len(rows) == 1
    assert rows[0]["exit_code"] == 0
    text = format_terminal_results_prompt(raw)
    assert "本机终端子 Agent" in text
    assert "echo hi" in text
    assert "hi" in text


def test_merge_client_shell_cwd():
    p = merge_client_shell_cwd({"command": "ls"}, {"cwd": "/tmp/proj", "platform": "linux"})
    assert p["cwd"] == "/tmp/proj"
    p2 = merge_client_shell_cwd({"command": "ls", "cwd": "/keep"}, {"cwd": "/tmp"})
    assert p2["cwd"] == "/keep"
