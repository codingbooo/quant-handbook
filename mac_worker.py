#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hermes Mac Local Worker
运行在 Mac 本地 Aqua 会话中，开机自启，单向轮询云端任务。
"""
import urllib.request
import json
import time
import subprocess
import os
import sys

SERVER_URL = "http://81.70.98.56:18888"

def run_applescript(script):
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return p.returncode == 0, p.stdout.strip(), p.stderr.strip()

def handle_fanqie_meta(params):
    # 修改番茄小说书名与简介
    book_title = params.get("title", "")
    book_intro = params.get("intro", "")
    
    # 构造通过 Chrome 页面注入执行的 JavaScript
    js_code = f"""
    (() => {{
        const titleInput = document.querySelector('input[placeholder*="书名"], input[placeholder*="作品名称"]');
        if (titleInput && "{book_title}") {{
            titleInput.value = "{book_title}";
            titleInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
            titleInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        const introArea = document.querySelector('textarea[placeholder*="简介"], textarea[placeholder*="作品介绍"]');
        if (introArea && `{book_intro}`) {{
            introArea.value = `{book_intro}`;
            introArea.dispatchEvent(new Event('input', {{ bubbles: true }}));
            introArea.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
        return "SUCCESS";
    }})()
    """
    as_script = f'''
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "fanqienovel.com" or URL of t contains "dragonread.com" then
                    tell t to execute javascript "{js_code.replace('"', '\\"')}"
                    return "DONE"
                end if
            end repeat
        end repeat
        return "NO_TAB"
    end tell
    '''
    ok, out, err = run_applescript(as_script)
    return {"success": ok and ("DONE" in out), "output": out, "error": err}

def handle_miniapp_preview(params):
    # 调用微信开发者工具 CLI 进行打版与真机预览推送
    project_path = params.get("project_path", "/Users/liangbo/work/code/lushu-app")
    cli_path = "/Applications/wechatwebdevtools.app/Contents/MacOS/cli"
    if not os.path.exists(cli_path):
        return {"success": False, "error": "WeChat DevTools CLI not found at " + cli_path}
    
    p = subprocess.run([cli_path, "auto-preview", "--project", project_path], capture_output=True, text=True)
    return {"success": p.returncode == 0, "output": p.stdout, "error": p.stderr}

def poll_once():
    url = f"{SERVER_URL}/api/worker/heartbeat"
    req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            task = data.get("task")
            if not task:
                return
            
            task_id = task.get("id")
            task_type = task.get("type")
            params = task.get("params", {})
            
            res = {}
            if task_type == "fanqie_meta":
                res = handle_fanqie_meta(params)
            elif task_type == "miniapp_preview":
                res = handle_miniapp_preview(params)
            else:
                res = {"success": False, "error": f"Unknown task type: {task_type}"}
            
            # 回传结果
            report_url = f"{SERVER_URL}/api/worker/task/report"
            report_data = json.dumps({"task_id": task_id, "result": res}).encode("utf-8")
            req_rep = urllib.request.Request(report_url, data=report_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_rep, timeout=10) as rep_resp:
                pass
    except Exception as e:
        # 网络断开或休眠时静默等待
        pass

def main():
    while True:
        poll_once()
        time.sleep(10)

if __name__ == "__main__":
    main()
