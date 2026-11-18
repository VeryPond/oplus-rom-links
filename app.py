# -*- coding: utf-8 -*-
"""ROM 站：Flask 后端 + JSON API + 直链跳转。"""
import os, threading, time

import sys as _sys
if _sys.platform == "win32":
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


from flask import Flask, abort, jsonify, redirect, render_template, request

import catalog
import resolver

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


def _link_expires_in(url):
    """从 CDN 链接里读过期时间"""
    import re, time as _t
    if not url:
        return 0
    m = re.search(r"(?:Expires|x-oss-expires)=(d+)", url)
    if m:
        return max(0, int(m.group(1)) - int(_t.time()))
    return 0


REGION_NAMES = {
    "CN": "中国大陆", "IN": "印度", "EU": "欧洲", "EEA": "欧洲经济区",
    "GLO": "全球", "NA": "北美", "RU": "俄罗斯", "TR": "土耳其",
    "TH": "泰国", "ID": "印度尼西亚", "MY": "马来西亚", "SG": "新加坡",
    "VN": "越南", "TW": "台湾", "JP": "日本", "MX": "墨西哥",
    "APC": "亚太", "SA": "沙特", "MEA": "中东非洲", "PH": "菲律宾",
    "ROE": "欧亚", "LA": "拉美", "BR": "巴西",
}


@app.template_filter("region_name")
def region_name(code):
    c = (code or "").upper()
    return REGION_NAMES.get(c, c)


@app.template_filter("filesize")
def filesize(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return "%.2f %s" % (n, u)
        n /= 1024.0
    return "%.2f PB" % n

_sync_state = {"running": False, "last": 0, "last_result": None, "error": None}


def _bg_sync():
    if _sync_state["running"]:
        return
    _sync_state["running"] = True
    try:
        r = catalog.sync(verbose=False)
        _sync_state["last_result"] = r
        _sync_state["last"] = int(time.time())
        _sync_state["error"] = None
    except Exception as e:
        _sync_state["error"] = str(e)[:300]
    finally:
        _sync_state["running"] = False


@app.route("/favicon.ico")
def favicon():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" rx="14" fill="#0b0f16"/>'
           '<circle cx="32" cy="32" r="13" fill="none" stroke="#37d6a0" stroke-width="5"/>'
           '<circle cx="32" cy="32" r="4" fill="#37d6a0"/></svg>')
    return app.response_class(svg, mimetype="image/svg+xml")


@app.route("/")
def index():
    s = catalog.stats()
    s.update(catalog.official_stats())
    allq = catalog.device_index()
    # 品牌分布（合并后）
    from collections import Counter
    bc = Counter(x["brand"] or "其他" for x in allq)
    rels = Counter()
    for x in allq:
        rels[x["brand"] or "其他"] += x["count"]
    brands = [{"brand": k, "devices": v, "releases": rels.get(k, 0)}
              for k, v in bc.most_common()]
    hot = sorted(allq, key=lambda d: (d["latest"] or {}).get("build") or "", reverse=True)[:24]
    regions = catalog.regions_summary()
    return render_template("index.html", stats=s, brands=brands, devices=hot[:24],
                           regions=regions)


@app.route("/brand/<brand>")
def brand_page(brand):
    devs = catalog.device_index()
    devs = [d for d in devs if d["brand"] == brand]
    if not devs:
        abort(404)
    s = catalog.stats()
    s.update(catalog.official_stats())
    return render_template("brand.html", brand=brand, devices=devs, stats=s)


@app.route("/device/<path:device>")
def device_page(device):
    d = catalog.device_detail_all(device)
    if not d or not d.get("releases"):
        abort(404)
    s = catalog.stats()
    s.update(catalog.official_stats())
    return render_template("device.html", d=d, stats=s)


@app.route("/region/<code>")
def region_page(code):
    rows = catalog.list_all_devices(region=code)
    if not rows:
        abort(404)
    s = catalog.stats()
    return render_template("region.html", code=code.upper(), rows=rows, stats=s)


@app.route("/search")
def search_page():
    q = (request.args.get("q") or "").strip()
    devs = catalog.device_index() if q else []
    if q:
        qq = q.upper()
        devs = [d for d in devs
                if qq in d["device"].upper() or any(qq in m.upper() for m in d["models"])]
    s = catalog.stats()
    s.update(catalog.official_stats())
    return render_template("search.html", q=q, devices=devs, stats=s)


# ---------------- API ----------------

@app.route("/api/stats")
def api_stats():
    s = catalog.stats()
    s["sync"] = _sync_state
    return jsonify(s)


@app.route("/api/catalog-devices")
def api_catalog_devices():
    brand = request.args.get("brand")
    q = request.args.get("q")
    return jsonify(catalog.list_devices(brand=brand, q=q))


@app.route("/api/device/<path:device>")
def api_device(device):
    d = catalog.device_detail_all(device)
    if not d:
        return jsonify({"error": "not found"}), 404
    return jsonify(d)


@app.route("/api/resolve/<rid>")
def api_resolve(rid):
    if rid.startswith("of_"):
        o = catalog.get_official_release(rid)
        if not o:
            return jsonify({"error": "not found"}), 404
        return jsonify({
            "id": rid, "device": o["device"], "region": o["region"],
            "version": o["version"], "url": o["link"], "size": o["size"],
            "cached_age": 0, "ttl": 0,
            "expires_in": _link_expires_in(o["link"]),
            "source": "official",
        })
    r = catalog.get_release(rid)
    if not r:
        return jsonify({"error": "not found"}), 404
    url, err, age = resolver.cached_resolve(rid, r["source_url"])
    if not url:
        return jsonify({"id": rid, "error": err}), 502
    size = r.get("size")
    if not size:
        size = resolver.probe_size(url)
        if size:
            catalog.save_size(rid, size)
    return jsonify({
        "id": rid, "device": r["device"], "region": r["region"], "version": r["version"],
        "url": url, "size": size, "cached_age": age, "ttl": resolver.TTL,
        "expires_in": max(0, resolver.TTL - age),
    })


@app.route("/api/size/<rid>")
def api_size(rid):
    if rid.startswith("of_"):
        o = catalog.get_official_release(rid)
        if not o:
            return jsonify({"error": "not found"}), 404
        return jsonify({"id": rid, "size": o["size"], "cached": True})
    r = catalog.get_release(rid)
    if not r:
        return jsonify({"error": "not found"}), 404
    if r.get("size"):
        return jsonify({"id": rid, "size": r["size"], "cached": True})
    url, err, _ = resolver.cached_resolve(rid, r["source_url"])
    if not url:
        return jsonify({"id": rid, "error": err}), 502
    size = resolver.probe_size(url)
    if size:
        catalog.save_size(rid, size)
    return jsonify({"id": rid, "size": size, "cached": False})


@app.route("/api/sizes")
def api_sizes():
    """批量取大小：并发解析 + 落库，只处理还没大小的。"""
    from concurrent.futures import ThreadPoolExecutor
    ids = [x for x in (request.args.get("ids") or "").split(",") if x][:80]
    if not ids:
        return jsonify({"sizes": {}})

    c = catalog.conn()
    known, todo = {}, []
    for rid in ids:
        row = c.execute("SELECT id,source_url,size FROM releases WHERE id=?", (rid,)).fetchone()
        if not row:
            continue
        if row["size"]:
            known[rid] = row["size"]
        else:
            todo.append((rid, row["source_url"]))
    c.close()

    def work(item):
        rid, src = item
        try:
            url, err, _ = resolver.cached_resolve(rid, src)
            if not url:
                return rid, None
            n = resolver.probe_size(url)
            if n:
                catalog.save_size(rid, n)
            return rid, n
        except Exception:
            return rid, None

    if todo:
        with ThreadPoolExecutor(max_workers=10) as ex:
            for rid, n in ex.map(work, todo):
                if n:
                    known[rid] = n
    return jsonify({"sizes": known})


@app.route("/go/<rid>")
def go(rid):
    """浏览器点「下载」走这里：302 到直链。"""
    if rid.startswith("of_"):
        o = catalog.get_official_release(rid)
        if not o or not o["link"]:
            abort(404)
        return redirect(o["link"], code=302)
    r = catalog.get_release(rid)
    if not r:
        abort(404)
    url, err, _ = resolver.cached_resolve(rid, r["source_url"])
    if not url:
        return render_template("error.html", rid=rid, err=err, r=r), 502
    return redirect(url, code=302)


@app.route("/api/all-devices")
def api_all_devices():
    """机型 x 区域 的扁平列表"""
    return jsonify(catalog.list_all_devices(
        brand=request.args.get("brand"),
        q=request.args.get("q"),
        region=request.args.get("region")))


@app.route("/api/devices")
def api_device_index():
    """机型总览（不含区域拆分）"""
    return jsonify(catalog.device_index())


@app.route("/api/regions")
def api_regions():
    return jsonify(catalog.regions_summary())


@app.route("/api/official-stats")
def api_official_stats():
    return jsonify(catalog.official_stats())


@app.route("/api/sync", methods=["POST"])
def api_sync():
    token = request.headers.get("X-Sync-Token") or request.args.get("token")
    expect = os.environ.get("ROMSITE_SYNC_TOKEN", "romsite-dev")
    if token != expect:
        return jsonify({"error": "forbidden"}), 403
    threading.Thread(target=_bg_sync, daemon=True).start()
    return jsonify({"started": True, "state": _sync_state})


if __name__ == "__main__":
    catalog.init_db()
    if catalog.stats()["total"] == 0:
        print("数据库为空，正在首次同步...", flush=True)
        _bg_sync()
    port = int(os.environ.get("ROMSITE_PORT", "8000"))
    print("ROM 站: http://127.0.0.1:%d" % port, flush=True)
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)