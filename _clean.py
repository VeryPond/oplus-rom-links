# -*- coding: utf-8 -*-
import subprocess, sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = r"E:\灵感构图\romsite"
r = subprocess.run([r"C:\Program Files\Git\bin\bash.exe", "-lc",
                    'bash "$HOME/.dsh/bin/dsh-key" get GITHUB_TOKEN'],
                   capture_output=True, text=True, timeout=60)
tok = r.stdout.strip()
env = os.environ.copy(); env["GIT_TERMINAL_PROMPT"] = "0"
def git(args, timeout=300):
    r = subprocess.run(args, cwd=REPO, capture_output=True, timeout=timeout, env=env)
    out = r.stdout.decode("utf-8","replace") + r.stderr.decode("utf-8","replace")
    return r.returncode, out.replace(tok, "***").strip()

# 删除误提交的临时文件
for f in [".msg", "_push_fix.py"]:
    p = os.path.join(REPO, f)
    if os.path.exists(p): os.remove(p)

git(["git", "add", "-A"])
rc, out = git(["git", "commit", "-m", "chore: remove accidentally committed temp scripts"])
print("commit rc=%d" % rc, out[:200])
rc, out = git(["git", "push", "https://%s@github.com/VeryPond/oplus-rom-links.git" % tok,
               "HEAD:refs/heads/main"])
print("push rc=%d" % rc, out[-300:])
