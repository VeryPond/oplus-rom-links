# -*- coding: utf-8 -*-
"""官方 OTA 全机型查询器（v3 通道，全0 GUID）

给一个 model code，枚举版本档位后缀，返回该型号所有可查到的完整 OTA。
"""
import sys, os, io, json, time, re, contextlib, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ref"))
_REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ref")
os.chdir(_REF)
sys.path.insert(0, _REF)
sys.stdout.reconfigure(encoding='utf-8', errors="replace")

import tomboy_pro as T

ZERO_GUID = "0" * 64
SUFFIXES = ["_11.A", "_11.C", "_11.F", "_11.H", "_11.J"]

_lock = threading.Lock()


def _published_from_ota(ota_version):
    """内部串形如 PLK110_11.C.76_1760_202610051308，尾部是 YYYYMMDDHHMM。"""
    import re as _re
    m = _re.search(r"_(\d{12})$", ota_version or "")
    if not m:
        return ""
    s = m.group(1)
    return "%s-%s-%s %s:%s" % (s[0:4], s[4:6], s[6:8], s[8:10], s[10:12])


def _one(model, ota_prefix, region="cn", mode="manual"):
    """单次查询。返回 dict 或 None"""
    try:
        po, pm = T.process_ota_version(ota_prefix, region, "0", "0", None)
        cfg = T.QueryConfig(ota_version=po, model=pm, region=region,
                            mode=mode, guid=ZERO_GUID)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = T.query_update(cfg)
        if not (r and r.success):
            return None
        d = r.data or {}
        out = {
            "components": [],
            # 市场版本号（如 PLK110_17.0.1.201(CN01)）与内部 OTA 版本号分开存
            "display_version": (d.get("version") or "").strip(),
            "ota_version": (d.get("ota_version") or "").strip(),
            "patch": (d.get("security_patch") or "").strip(),
            "changelog": (d.get("changelog") or "").strip(),
            "published": (d.get("publishedTime") or "").strip()
                         or _published_from_ota(d.get("ota_version") or ""),
            "code": r.response_code,
        }
        for c in (r.components or []):
            out["components"].append({
                "name": c.name,
                "version": c.version,
                "link": c.link,
                "size": getattr(c, "size", None),
                "md5": getattr(c, "md5", None),
            })
        return out
    except Exception:
        return None


def query_model(model, region="cn"):
    """枚举后缀，合并去重。返回 [(version, link, size)]"""
    seen = {}
    for suf in SUFFIXES:
        r = _one(model, model + suf, region)
        if not r:
            continue
        disp = (r.get("display_version") or "").strip()
        for c in r["components"]:
            v = disp or (c.get("version") or "")
            if v and v not in seen:
                seen[v] = {
                    "version": v,
                    "ota_version": r.get("ota_version") or c.get("version") or "",
                    "link": c.get("link") or "",
                    "size": c.get("size"), "md5": c.get("md5"),
                    "published": r.get("published") or "",
                    "patch": r.get("patch") or "",
                    "changelog": r.get("changelog") or "",
                }
    return list(seen.values())


if __name__ == "__main__":
    import concurrent.futures as cf
    models = sys.argv[1:] or ["PLK110"]
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda m: (m, query_model(m)), models))
    for m, rs in res:
        print("%s -> %d 个版本  (%.1fs)" % (m, len(rs), time.time()-t0))
        for r in rs:
            print("   %-34s %-10s %s" % (r["version"], r.get("size") or "?", (r["link"] or "")[:50]))
    print("总耗时 %.1fs" % (time.time()-t0))