# -*- coding: utf-8 -*-
"""把官方扫描结果导入站点数据表"""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import catalog

catalog.init_db()
n = catalog.import_official()
print("导入官方版本: %d 条" % n)
print("官方统计:", catalog.official_stats())
allq = catalog.list_all_devices()
print("合并后机型总数: %d" % len(allq))
from collections import Counter
print("品牌分布:", dict(Counter(x["brand"] or "其他" for x in allq)))
