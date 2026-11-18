# -*- coding: utf-8 -*-
"""官方 OTA 全机型扫描器

策略：型号 × 地区 × 5 个版本档位后缀
- 国行型号 (P/NE/LE/IN/HD/GM/KB/OP 开头)  先查 cn，再补 eu/in/sg
- 海外型号 (CPH)                          查 eu/in/sg/gl/id/tw/my/vn/th/ph
- realme (RMX)                            同 CPH

通道：GUID 全 0 → /update/v3（有效）；随机 GUID → /update/v6（返回 2201）
"""
import sys, os, io, json, time, re, contextlib, sqlite3, threading, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# 全局静音上游库的 debug 打印（多线程下 redirect_stdout 会互相踩踏）
REAL_OUT = sys.stdout
sys.stdout = open(os.devnull, "w")

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, PARENT)
REF = os.path.join(HERE, "_ref")
os.chdir(REF)
sys.path.insert(0, REF)
sys.path.insert(0, HERE)

import official_ota as O

DB_PATH = os.path.join(HERE, "data", "roms.db")
SUFFIXES = ["_11.A", "_11.C", "_11.F", "_11.H", "_11.J"]

REGIONS_CN = ["cn", "eu", "in", "sg"]
REGIONS_OVERSEAS = ["eu", "in", "sg", "gl", "id", "tw", "my", "vn", "th", "ph"]

_devnull = open(os.devnull, "w")
_print_lock = threading.Lock()

SCHEMA_ADD = """
CREATE TABLE IF NOT EXISTS official_models (
    model TEXT PRIMARY KEY,
    device TEXT,
    brand TEXT,
    regions TEXT,
    scanned_at INTEGER,
    hit_cnt INTEGER DEFAULT 0,
    versions_json TEXT
);
"""


def conn():
    c = sqlite3.connect(DB_PATH, timeout=60)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(SCHEMA_ADD)
    return c


def regions_for(model):
    if model.startswith(("CPH", "RMX")):
        return REGIONS_OVERSEAS
    return REGIONS_CN


def scan_one(model, regions=None, max_regions=None):
    """扫描单个型号，返回命中的版本列表"""
    regions = regions or regions_for(model)
    if max_regions:
        regions = regions[:max_regions]
    found = {}
    for reg in regions:
        try:
            rs = O.query_model(model, reg)
        except Exception:
            continue
        for r in rs:
            v = r.get("version") or ""
            if not v:
                continue
            key = v
            if key not in found:
                found[key] = {
                    "version": v, "region": reg, "link": r.get("link") or "",
                    "size": r.get("size"), "md5": r.get("md5"),
                    "published": r.get("published"), "patch": r.get("patch"),
                    "model": model,
                }
        # 该地区已命中就不必再试其它地区（同型号同一版本只会有一处）
        if found:
            break
    return list(found.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 个型号（调试）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", help="只扫指定型号，逗号分隔")
    ap.add_argument("--max-regions", type=int, default=0)
    args = ap.parse_args()

    models = json.load(open(os.path.join(REF, "scan_final.json"), encoding="utf-8"))
    if args.model:
        want = set(x.strip().upper() for x in args.model.split(","))
        models = [m for m in models if m["model"].upper() in want]
    if args.limit:
        models = models[:args.limit]

    total = len(models)
    print("开始扫描 %d 个型号，并发 %d" % (total, args.workers), file=REAL_OUT, flush=True)

    db = conn()
    done = 0
    hit_models = 0
    total_versions = 0
    t0 = time.time()

    def work(m):
        model = m["model"]
        vers = scan_one(model, max_regions=args.max_regions or None)
        return model, m, vers

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(work, m) for m in models]
            for f in as_completed(futs):
                model, meta, vers = f.result()
                done += 1
                if vers:
                    hit_models += 1
                    total_versions += len(vers)
                try:
                    db.execute(
                        """INSERT OR REPLACE INTO official_models
                           (model,device,brand,regions,scanned_at,hit_cnt,versions_json)
                           VALUES(?,?,?,?,?,?,?)""",
                        (model, meta.get("device") or "", meta.get("brand") or "",
                         ",".join(regions_for(model)), int(time.time()), len(vers),
                         json.dumps(vers, ensure_ascii=False)))
                    db.commit()
                except Exception:
                    pass
                if done % 10 == 0 or done == total:
                    el = time.time() - t0
                    eta = el / done * (total - done) if done else 0
                    with _print_lock:
                        print("[%d/%d] 命中机型 %d, 版本 %d, 已用 %.0fs, 预计剩余 %.0fs"
                              % (done, total, hit_models, total_versions, el, eta),
                              file=REAL_OUT, flush=True)
    finally:
        db.close()

    print("\n完成：扫描 %d 个型号，命中 %d 个，累计 %d 个版本，耗时 %.0fs"
          % (done, hit_models, total_versions, time.time() - t0), file=REAL_OUT, flush=True)


if __name__ == "__main__":
    main()