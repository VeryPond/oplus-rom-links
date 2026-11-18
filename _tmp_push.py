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
    return r.returncode, (r.stdout.decode("utf-8","replace") + r.stderr.decode("utf-8","replace")).replace(tok, "***").strip()

git(["git", "rm", "--cached", "_clean.py", "-q"])
git(["git", "add", "-A"])
msg = ("fix: tools/progress.py 空库友好提示 + 清理误提交的临时脚本\n\n"
       "- progress.py: 数据库不存在或未扫描时给出指引，不再抛 OperationalError\n"
       "- 删除 _clean.py / _push_fix.py / .msg 等误提交文件")
open(os.path.join(REPO, ".m"), "w", encoding="utf-8").write(msg)
rc, out = git(["git", "commit", "-F", ".m"])
print("commit rc=%d" % rc, out[:250])
os.remove(os.path.join(REPO, ".m"))
rc, out = git(["git", "push", "https://%s@github.com/VeryPond/oplus-rom-links.git" % tok,
               "HEAD:refs/heads/main"])
print("push rc=%d" % rc, out[-300:])
