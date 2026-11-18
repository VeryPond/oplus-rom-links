# -*- coding: utf-8 -*-
"""ROM 目录：抓取 / 入库 / 查询。"""
import hashlib, json, os, socket, sqlite3, sys, time
import urllib.request, urllib.parse, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "roms.db")
CATALOG = "https://roms.danielspringer.at/api/ota.php"

PROXY_CANDIDATES = ["127.0.0.1:7897", "127.0.0.1:7890", "127.0.0.1:10809", "127.0.0.1:1080"]


def detect_proxy():
    """目录站国内需要代理；自动探测常见本地代理端口。"""
    env = os.environ.get("ROMSITE_PROXY")
    if env:
        return {"http": env, "https": env}
    for p in PROXY_CANDIDATES:
        host, port = p.split(":")
        s = socket.socket()
        s.settimeout(0.35)
        try:
            s.connect((host, int(port)))
            return {"http": "http://" + p, "https": "http://" + p}
        except Exception:
            pass
        finally:
            s.close()
    return {}


# 型号前缀 -> 品牌（官方 model code）
_MODEL_BRAND = [
    ("RMX", "realme"),
    ("CPH", "OPPO/OnePlus"),
    ("PJ", "OPPO"), ("PK", "OPPO"), ("PH", "OPPO"), ("PL", "OPPO"), ("PE", "OPPO"),
    ("PF", "OPPO"), ("PA", "OPPO"), ("PB", "OPPO"), ("PD", "OPPO"), ("PG", "OPPO"),
    ("NE", "OnePlus"), ("LE", "OnePlus"), ("IN", "OnePlus"), ("HD", "OnePlus"),
    ("GM", "OnePlus"), ("KB", "OnePlus"), ("OP", "OnePlus"),
]


def brand_of(device):
    d = (device or "").upper()
    if d.startswith("OPPO"):
        return "OPPO"
    if d.startswith("OP "):
        return "OnePlus"
    if d.startswith("REALME"):
        return "realme"
    if d.startswith("XIAOMI"):
        return "Xiaomi"
    if d.startswith("REDMI"):
        return "Redmi"
    if d.startswith("POCO"):
        return "POCO"
    # 纯型号代码（官方接口扫出来的）
    for pref, brand in _MODEL_BRAND:
        if d.startswith(pref):
            return brand
    return "其他"


def resolve_brand(device, model):
    """机型名判断不出来时，退回用 model code 判断"""
    b = brand_of(device)
    if b != "其他":
        return b
    return brand_of(model)


SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    device TEXT NOT NULL,
    region TEXT NOT NULL,
    model TEXT,
    version TEXT,
    ota_version TEXT,
    build TEXT,
    patch TEXT,
    source_url TEXT,
    changelog_url TEXT,
    is_latest INTEGER DEFAULT 0,
    brand TEXT,
    size INTEGER,
    size_at INTEGER,
    resolved_url TEXT,
    resolved_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dev ON releases(device);
CREATE INDEX IF NOT EXISTS idx_dev_reg ON releases(device, region);
CREATE INDEX IF NOT EXISTS idx_build ON releases(build);
CREATE INDEX IF NOT EXISTS idx_brand ON releases(brand);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS official_models (
    model TEXT PRIMARY KEY,
    device TEXT,
    brand TEXT,
    regions TEXT,
    scanned_at INTEGER,
    hit_cnt INTEGER DEFAULT 0,
    versions_json TEXT
);
CREATE TABLE IF NOT EXISTS official_releases (
    id TEXT PRIMARY KEY,
    model TEXT,
    device TEXT,
    brand TEXT,
    region TEXT,
    version TEXT,
    ota_version TEXT,
    link TEXT,
    size INTEGER,
    md5 TEXT,
    published TEXT,
    patch TEXT,
    fetched_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_or_model ON official_releases(model);
CREATE INDEX IF NOT EXISTS idx_or_device ON official_releases(device);
"""


def conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    c = conn()
    c.executescript(SCHEMA)
    c.commit()
    c.close()


def fetch_catalog(timeout=90, retries=4):
    proxy = detect_proxy()
    last = None
    for i in range(retries):
        try:
            handlers = [urllib.request.ProxyHandler(proxy)] if proxy else []
            op = urllib.request.build_opener(*handlers)
            req = urllib.request.Request(CATALOG, headers={"User-Agent": "romsite/1.0"})
            with op.open(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(2 + i * 2)
    raise last


def sync(verbose=True):
    """全量同步目录。返回统计。"""
    init_db()
    data = fetch_catalog()
    rows = data["releases"]
    c = conn()
    cur = c.cursor()
    n_new = 0
    for r in rows:
        rid = r["id"]
        brand = brand_of(r.get("device"))
        exists = cur.execute("SELECT id FROM releases WHERE id=?", (rid,)).fetchone()
        if exists:
            cur.execute(
                """UPDATE releases SET device=?,region=?,model=?,version=?,ota_version=?,
                   build=?,patch=?,source_url=?,changelog_url=?,is_latest=?,brand=? WHERE id=?""",
                (r.get("device"), r.get("region"), r.get("model"), r.get("version"),
                 r.get("ota_version"), r.get("build_timestamp"), r.get("security_patch"),
                 r.get("source_url"), r.get("changelog_url"), 1 if r.get("is_latest") else 0,
                 brand, rid),
            )
        else:
            cur.execute(
                """INSERT INTO releases(id,device,region,model,version,ota_version,build,patch,
                   source_url,changelog_url,is_latest,brand) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, r.get("device"), r.get("region"), r.get("model"), r.get("version"),
                 r.get("ota_version"), r.get("build_timestamp"), r.get("security_patch"),
                 r.get("source_url"), r.get("changelog_url"),
                 1 if r.get("is_latest") else 0, brand),
            )
            n_new += 1
    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('synced_at',?)", (str(int(time.time())),))
    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('catalog_updated_at',?)",
                (data.get("catalog_updated_at") or "",))
    cur.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('upstream_count',?)", (str(len(rows)),))
    c.commit()
    c.close()
    if verbose:
        print("同步完成: 共 %d 条, 新增 %d 条" % (len(rows), n_new), flush=True)
    return {"total": len(rows), "new": n_new}


def stats():
    """合并两个数据源的统计"""
    c = conn()
    q = c.execute
    # 把两源版本合并计数
    base = q("SELECT COUNT(*) c FROM releases").fetchone()["c"]
    try:
        offc = q("SELECT COUNT(*) c FROM official_releases").fetchone()["c"]
    except Exception:
        offc = 0
    m = {r["k"]: r["v"] for r in q("SELECT k,v FROM meta")}

    # 机型与品牌走合并逻辑
    alld = device_index()
    from collections import Counter
    bc = Counter((d["brand"] or "其他") for d in alld)
    rel_by_brand = Counter()
    for d in alld:
        rel_by_brand[d["brand"] or "其他"] += d["count"]

    out = {
        "total": base,
        "official_versions": offc,
        "merged_versions": len({r["version"] for r in
                                [dict(x) for x in q("SELECT version FROM releases")]}) if False else base + offc,
        "devices": len(alld),
        "brands": len(bc),
        "regions": q("SELECT COUNT(DISTINCT region) c FROM releases").fetchone()["c"],
        "synced_at": int(m.get("synced_at") or 0),
        "catalog_updated_at": m.get("catalog_updated_at") or "",
        "brand_counts": [
            {"brand": k, "devices": v, "releases": rel_by_brand.get(k, 0)}
            for k, v in bc.most_common()
        ],
    }
    try:
        out.update(official_stats())
    except Exception:
        pass
    c.close()
    return out


def list_devices(brand=None, q=None, limit=500):
    c = conn()
    sql = ["SELECT device, brand, COUNT(*) n, MAX(build) latest_build,",
           "       SUM(is_latest) latest_cnt FROM releases"]
    where, args = [], []
    if brand:
        where.append("brand=?")
        args.append(brand)
    if q:
        where.append("(device LIKE ? OR model LIKE ?)")
        args.extend(["%" + q + "%", "%" + q + "%"])
    if where:
        sql.append("WHERE " + " AND ".join(where))
    sql.append("GROUP BY device ORDER BY brand, device LIMIT ?")
    args.append(limit)
    rows = c.execute(" ".join(sql), args).fetchall()
    out = []
    for r in rows:
        latest = c.execute(
            """SELECT version,region,model,build,patch,size,id,is_latest FROM releases
               WHERE device=? ORDER BY is_latest DESC, build DESC LIMIT 1""", (r["device"],)
        ).fetchone()
        regs = [x["region"] for x in c.execute(
            "SELECT DISTINCT region FROM releases WHERE device=? ORDER BY region", (r["device"],))]
        out.append({
            "device": r["device"], "brand": r["brand"], "count": r["n"],
            "regions": regs,
            "latest": dict(latest) if latest else None,
        })
    c.close()
    return out


def device_detail(device):
    c = conn()
    rows = c.execute(
        """SELECT * FROM releases WHERE device=? ORDER BY region, build DESC""", (device,)
    ).fetchall()
    c.close()
    if not rows:
        return None
    return {
        "device": device,
        "brand": rows[0]["brand"],
        "models": sorted({r["model"] for r in rows if r["model"]}),
        "regions": sorted({r["region"] for r in rows}),
        "releases": [dict(r) for r in rows],
    }


def get_release(rid):
    c = conn()
    r = c.execute("SELECT * FROM releases WHERE id=?", (rid,)).fetchone()
    c.close()
    return dict(r) if r else None


def save_size(rid, size):
    c = conn()
    c.execute("UPDATE releases SET size=?, size_at=? WHERE id=?", (size, int(time.time()), rid))
    c.commit()
    c.close()


def save_resolved(rid, url):
    c = conn()
    c.execute("UPDATE releases SET resolved_url=?, resolved_at=? WHERE id=?",
              (url, int(time.time()), rid))
    c.commit()
    c.close()


def clear_resolved():
    c = conn()
    c.execute("UPDATE releases SET resolved_url=NULL, resolved_at=NULL")
    c.commit()
    c.close()


# ---------------- 官方接口数据 ----------------

_FULLNAME = None


def _load_fullnames():
    """型号 -> 官方全称（Google Play 设备清单，bsthen/device-models）"""
    global _FULLNAME
    if _FULLNAME is None:
        p = os.path.join(ROOT, "_ref", "bsthen_map.json")
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
            _FULLNAME = {k.upper(): v["name"] for k, v in raw.items() if v.get("name")}
        except Exception:
            _FULLNAME = {}
    return _FULLNAME


# 机型名里的缩写 -> 全称（"OP 15" -> "OnePlus 15"）
_NAME_EXPAND = {
    "OP ": "OnePlus ",
    "OPPO FIND": "OPPO Find",
    "OPPO RENO": "OPPO Reno",
    "OPPO A": "OPPO A",
    "REALME": "realme",
}


_BRAND_PREFIX = {
    "oppo": "OPPO",
    "oneplus": "OnePlus",
    "realme": "realme",
}


def _qualify(name, brand, model):
    """给不带品牌前缀的名字补上品牌（Find X9 -> OPPO Find X9）。"""
    name = (name or "").strip()
    if not name:
        return name
    low = name.lower()
    for kw in ("oppo", "oneplus", "one plus", "realme", "xiaomi", "redmi", "poco"):
        if low.startswith(kw):
            return name
    b = (brand or "").lower().strip()
    pref = _BRAND_PREFIX.get(b)
    if not pref:
        # 从型号推断
        mu = (model or "").upper()
        if mu.startswith("RMX"):
            pref = "realme"
        elif mu.startswith(("NE", "LE", "IN", "HD", "GM", "KB")):
            pref = "OnePlus"
        elif mu.startswith(("CPH", "PL", "PJ", "PK", "PH", "PE", "PF", "PA", "PB", "PD", "PG")):
            pref = "OPPO"
    if not pref:
        return name
    # OPPO 的 Find/Reno/A 系列要保留空格规则
    return "%s %s" % (pref, name)


def full_name(model, current=""):
    """给型号或旧机型名，返回带品牌的全称。"""
    fn = _load_fullnames()
    m = (model or "").upper()
    if m in fn:
        raw = fn[m]
        has_brand = any(raw.lower().startswith(p) for p in
                        ("oppo", "oneplus", "realme", "xiaomi", "redmi", "poco"))
        return raw if has_brand else _qualify(raw, "", m)
    name = (current or "").strip()
    if not name:
        return "%s (型号未收录)" % (model or "")
    # 已经像全称就不动
    if name.startswith(("OnePlus ", "OPPO ", "realme ", "Xiaomi ", "Redmi ", "POCO ")):
        return name
    for abbr, full in _NAME_EXPAND.items():
        if name.upper().startswith(abbr):
            return full + name[len(abbr):]
    return name


_MODEL_MAP = None


def _load_model_map():
    """型号 -> 机型名 映射表（从目录站页面内嵌 JSON 提取）"""
    global _MODEL_MAP
    if _MODEL_MAP is None:
        p = os.path.join(ROOT, "_ref", "model_devices.json")
        try:
            with open(p, encoding="utf-8") as f:
                _MODEL_MAP = json.load(f)
        except Exception:
            _MODEL_MAP = {}
    return _MODEL_MAP


def _device_name_for(model):
    """型号 -> 机型全称。优先 Google Play 全称表，其次目录映射，最后型号代码。"""
    fn = _load_fullnames()
    if model.upper() in fn:
        return fn[model.upper()]
    mp = _load_model_map()
    if model in mp and mp[model]:
        return full_name(model, mp[model])
    c = conn()
    r = c.execute("SELECT device FROM releases WHERE model=? AND device!='' LIMIT 1",
                  (model,)).fetchone()
    if not r or not r["device"]:
        r = c.execute("SELECT device FROM official_models WHERE model=? AND device!='' LIMIT 1",
                      (model,)).fetchone()
    c.close()
    if r and r["device"]:
        return r["device"]
    # 兜底：用型号代码作为显示名，标记为待补充
    return "%s (型号)" % model


def import_official():
    """把 official_models 表里扫描到的版本，落到 official_releases 表"""
    c = conn()
    rows = c.execute("SELECT model, device, brand, versions_json FROM official_models").fetchall()
    n = 0
    now = int(time.time())
    for r in rows:
        try:
            vers = json.loads(r["versions_json"] or "[]")
        except Exception:
            continue
        device = _device_name_for(r["model"])
        brand = r["brand"] or brand_of(device)
        for v in vers:
            ver = v.get("version") or ""
            if not ver:
                continue
            rid = "of_" + hashlib.md5((r["model"] + "|" + ver).encode()).hexdigest()[:20]
            c.execute(
                """INSERT OR REPLACE INTO official_releases
                   (id,model,device,brand,region,version,ota_version,link,size,md5,published,patch,fetched_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, r["model"], device, brand, v.get("region") or "", ver,
                 v.get("ota_version") or ver,
                 v.get("link") or "", v.get("size"), v.get("md5"),
                 v.get("published") or "", v.get("patch") or "", now))
            n += 1
    c.commit()
    c.close()
    return n


OFFICIAL_MIN_FULL = 500 * 1024 * 1024   # 小于 500MB 视为补丁 / 元数据包


def official_stats():
    c = conn()
    q = c.execute
    out = {
        "models_scanned": q("SELECT COUNT(*) c FROM official_models").fetchone()["c"],
        "models_hit": q("SELECT COUNT(*) c FROM official_models WHERE hit_cnt>0").fetchone()["c"],
        "versions": q("SELECT COUNT(*) c FROM official_releases").fetchone()["c"],
        "versions_full": q("SELECT COUNT(*) c FROM official_releases WHERE size>=?",
                           (OFFICIAL_MIN_FULL,)).fetchone()["c"],
        "official_devices": q("SELECT COUNT(DISTINCT device) c FROM official_releases "
                              "WHERE device!=''").fetchone()["c"],
    }
    c.close()
    return out


def list_all_devices(brand=None, q=None, limit=3000, region=None):
    """合并两源，按「机型全称」归并，区域展开为独立条目。

    返回结构：每个 (机型, 区域) 一条，便于按区域浏览。
    """
    c = conn()
    agg = {}

    def add(device, model, region, version, build, size, rid, src):
        # 机型名统一成全称
        name = full_name(model, device)
        key = (name, (region or "").upper())
        it = agg.get(key)
        if it is None:
            it = agg[key] = {
                "device": name, "model": model, "region": (region or "").upper(),
                "brand": resolve_brand(name, model), "count": 0,
                "latest": None, "sources": set(), "models": set(),
            }
        it["count"] += 1
        it["sources"].add(src)
        if model:
            it["models"].add(model)
        b = build or ""
        if it["latest"] is None or b > (it["latest"].get("build") or ""):
            it["latest"] = {"version": version, "build": b, "region": region,
                            "size": size, "id": rid, "src": src}

    for r in c.execute("SELECT device, model, region, version, build, size, id FROM releases"):
        add(r["device"], r["model"], r["region"], r["version"], r["build"],
            r["size"], r["id"], "catalog")
    for r in c.execute("SELECT device, model, region, version, published, size, id FROM official_releases"):
        add(r["device"], r["model"], r["region"], r["version"], r["published"],
            r["size"], r["id"], "official")
    c.close()

    out = []
    for it in agg.values():
        if brand and it["brand"] != brand:
            continue
        if region and it["region"] != region.upper():
            continue
        if q:
            qq = q.upper()
            if qq not in it["device"].upper() and not any(qq in m.upper() for m in it["models"]):
                continue
        it["sources"] = sorted(it["sources"])
        it["models"] = sorted(it["models"])
        out.append(it)
    out.sort(key=lambda x: (x["brand"] or "", x["device"], x["region"]))
    return out[:limit]


def device_index():
    """机型总览（不区分区域，用于首页/品牌页）"""
    rows = list_all_devices()
    agg = {}
    for r in rows:
        it = agg.get(r["device"])
        if it is None:
            it = agg[r["device"]] = {
                "device": r["device"], "brand": r["brand"], "models": set(),
                "regions": set(), "count": 0, "sources": set(), "latest": None,
            }
        it["models"].update(r["models"])
        it["regions"].add(r["region"])
        it["count"] += r["count"]
        it["sources"].update(r["sources"])
        lb = (it["latest"] or {}).get("build") or ""
        rb = (r["latest"] or {}).get("build") or ""
        if it["latest"] is None or rb > lb:
            it["latest"] = r["latest"]
    out = []
    for it in agg.values():
        it["models"] = sorted(it["models"])
        it["regions"] = sorted(it["regions"])
        it["sources"] = sorted(it["sources"])
        out.append(it)
    out.sort(key=lambda x: (x["brand"] or "", x["device"]))
    return out


def regions_summary():
    """全站地区分布"""
    from collections import Counter
    c = Counter()
    for r in list_all_devices():
        c[r["region"]] += 1
    return [{"region": k, "count": v} for k, v in c.most_common()]


def _resolve_device_key(device):
    """把用户传入的名字（可能是全称或旧缩写）解析成数据库里的 device 值集合"""
    name = (device or "").strip()
    keys = {name, name.upper()}
    # 全称 -> 旧名
    for abbr, full in (("OP ", "OnePlus "),):
        if name.upper().startswith("ONEPLUS "):
            keys.add("OP " + name[len("OnePlus "):])
    # 旧名 -> 全称
    if name.upper().startswith("OP "):
        keys.add("OnePlus " + name[3:])
    if name.upper().startswith("OPPO "):
        keys.add(name.upper())
    return keys


def device_detail_all(device):
    """机型详情：目录版 + 官方版合并（接受全称 / 旧缩写 / 型号）"""
    # 先按各种可能的键去试
    found = None
    for k in _resolve_device_key(device):
        d = device_detail(k)
        if d and d["releases"]:
            found = d
            break
    if not found:
        # 再按型号反查
        c0 = conn()
        r0 = c0.execute("SELECT model FROM releases WHERE device=? LIMIT 1", (device,)).fetchone()
        if not r0:
            r0 = c0.execute("SELECT DISTINCT model FROM official_releases WHERE device=? LIMIT 1",
                            (device,)).fetchone()
        c0.close()
        if r0 and r0["model"]:
            fn = full_name(r0["model"])
            for k in (fn, device):
                d = device_detail(k)
                if d and d["releases"]:
                    found = d
                    break
    d = found or {"device": device, "brand": "", "models": [],
                  "regions": [], "releases": []}
    c = conn()
    off = c.execute(
        "SELECT * FROM official_releases WHERE device=? ORDER BY published DESC", (device,)
    ).fetchall()
    c.close()
    merged = []
    seen = set()
    for r in d["releases"]:
        key = (r["version"] or "").strip()
        seen.add(key)
        merged.append({
            "id": r["id"], "version": r["version"], "region": r["region"],
            "model": r["model"], "build": r["build"], "patch": r["patch"],
            "size": r["size"], "is_latest": r["is_latest"], "src": "catalog",
        })
    for r in off:
        ver = (r["version"] or "").strip()
        if ver in seen:
            continue
        seen.add(ver)
        merged.append({
            "id": r["id"], "version": ver, "region": r["region"],
            "model": r["model"], "build": r["published"], "patch": r["patch"],
            "size": r["size"], "is_latest": 0, "src": "official",
        })
    # 统一机型显示名为全称
    disp = full_name((merged[0]["model"] if merged else ""), d.get("device") or device)         if merged and merged[0].get("model") else (d.get("device") or device)
    for r in merged:
        if r.get("model"):
            r["device_disp"] = full_name(r["model"], "")
    d["device"] = disp or d.get("device") or device
    merged.sort(key=lambda x: (x["region"] or "", x["build"] or ""), reverse=True)
    d["releases"] = merged
    if not d["models"]:
        ms = set()
        for r in off:
            if r["model"]:
                ms.add(r["model"])
        d["models"] = sorted(ms)
    d["regions"] = sorted({r["region"] for r in merged if r["region"]})
    if not d["brand"]:
        d["brand"] = brand_of(device)
    return d


def get_official_release(rid):
    c = conn()
    r = c.execute("SELECT * FROM official_releases WHERE id=?", (rid,)).fetchone()
    c.close()
    return dict(r) if r else None


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd == "sync":
        sync()
        print(json.dumps(stats(), ensure_ascii=False, indent=1)[:800])
    elif cmd == "stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=1))