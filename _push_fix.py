# -*- coding: utf-8 -*-
import subprocess, sys, os, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = r"E:\灵感构图\romsite"
r = subprocess.run([r"C:\Program Files\Git\bin\bash.exe", "-lc",
                    'bash "$HOME/.dsh/bin/dsh-key" get GITHUB_TOKEN'],
                   capture_output=True, text=True, timeout=60)
tok = r.stdout.strip()
env = os.environ.copy(); env["GIT_TERMINAL_PROMPT"] = "0"

def git(args, timeout=300):
    r = subprocess.run(args, cwd=REPO, capture_output=True, timeout=timeout, env=env)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return r.returncode, out.replace(tok, "***").strip()

# 确认 tomboy_pro.py / config.py 会被加入
print("=== 检查新增文件 ===")
rc, out = git(["git", "status", "--porcelain"])
for line in out.split("\n"):
    if line.strip(): print("  " + line)

msg = "fix: 修复克隆后不可用的 5 个 HIGH 问题\n\n" \
      "1. .gitignore 误排除 _ref/tomboy_pro.py 与 config.py（运行时依赖，必须入库）\n" \
      "2. 新增 requirements.txt（flask / cryptography / requests）\n" \
      "3. tools/scan_official.py 路径 bug：_ref 与 data 用 HERE 而非 PARENT\n" \
      "4. 入口脚本加 UTF-8 输出重配置，修复 Windows 下中文乱码\n" \
      "5. README 补依赖说明与重新扫描章节"
open(os.path.join(REPO, ".msg"), "w", encoding="utf-8").write(msg)

git(["git", "add", "-A"])
rc, out = git(["git", "commit", "-F", ".msg"])
print("\ncommit rc=%d" % rc, out[:300])
os.remove(os.path.join(REPO, ".msg"))

rc, out = git(["git", "push", "https://%s@github.com/VeryPond/oplus-rom-links.git" % tok,
               "HEAD:refs/heads/main"])
print("\npush rc=%d" % rc)
print(out[-500:])
