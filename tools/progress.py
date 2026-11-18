# -*- coding: utf-8 -*-
"""查看官方接口扫描进度"""
import sys, sqlite3, os
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "roms.db")
if not os.path.exists(DB):
    print("数据库不存在：%s" % DB)
    print("先运行 python app.py（会自动同步第三方目录），或 python tools/scan_official.py")
    sys.exit(0)

TOTAL = 309  # _ref/scan_final.json 里的型号总数
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
try:
    n = c.execute("SELECT COUNT(*) c FROM official_models").fetchone()["c"]
    hit = c.execute("SELECT COUNT(*) c FROM official_models WHERE hit_cnt>0").fetchone()["c"]
    ver = c.execute("SELECT SUM(hit_cnt) s FROM official_models").fetchone()["s"] or 0
except sqlite3.OperationalError:
    print("尚未扫描过官方接口（缺少 official_models 表）")
    print("运行 python tools/scan_official.py --workers 10 开始扫描")
    sys.exit(0)
print("扫描进度: %d / %d 型号 (%.0f%%)" % (n, TOTAL, 100*n/TOTAL if TOTAL else 0))
print("命中: %d 个型号, %d 个版本" % (hit, ver))
c.close()