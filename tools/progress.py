# -*- coding: utf-8 -*-
import sys, sqlite3, json
sys.stdout.reconfigure(encoding='utf-8')
import os
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "roms.db")
c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
n = c.execute("SELECT COUNT(*) c FROM official_models").fetchone()["c"]
hit = c.execute("SELECT COUNT(*) c FROM official_models WHERE hit_cnt>0").fetchone()["c"]
ver = c.execute("SELECT SUM(hit_cnt) s FROM official_models").fetchone()["s"] or 0
print("扫描进度: %d / 309 型号 (%.0f%%)" % (n, 100*n/309))
print("命中: %d 个型号, %d 个版本" % (hit, ver))
c.close()
