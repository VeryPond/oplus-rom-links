# -*- coding: utf-8 -*-
"""直链解析：三类下发方式统一成「可下载 URL」。

1) OPPO/一加/realme  component-ota-*.allawn* / allawntech  ->  downloadCheck 需带 userId 换 302
2) OPPO 老包  gauss-componentotamanual.* / cdnorg / bigota  ->  本身就是文件直链
3) 小米系     bigota.d.miui.com 直链；sgp-api.buy.mi.com 需跟 302
"""
import json, threading, time

import urllib.error, urllib.parse, urllib.request

USERID = "oplus-ota|16001011"
UA = "okhttp/4.12.0"
TTL = 25 * 60          # 签名约 30 分钟，留 5 分钟余量


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_cache = {}
_lock = threading.Lock()


def _opener(no_redirect=True):
    hs = [_NoRedirect] if no_redirect else []
    return urllib.request.build_opener(*hs)


def _get(url, headers=None, timeout=25, follow=False, limit=2048):
    """limit=None 表示读全量（小米 JSON 接口需要）。"""
    h = {"User-Agent": UA}
    h.update(headers or {})
    op = _opener(not follow)
    req = urllib.request.Request(url, headers=h)
    n = limit if limit else -1
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(n)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), (e.read(n) if e.fp else b"")


def _hdr(d, key):
    for k, v in d.items():
        if k.lower() == key.lower():
            return v
    return ""


def resolve(source_url):
    """把 source_url 解析成可直接下载的直链。返回 (url, error)。"""
    u = (source_url or "").strip()
    if not u:
        return None, "empty source_url"
    parsed = urllib.parse.urlparse(u)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    # 1) OPPO/一加/realme：downloadCheck 换票（需带 userId）
    if "downloadcheck" in path:
        try:
            st, hd, body = _get(u, headers={"userId": USERID})
            loc = _hdr(hd, "location")
            if st in (301, 302, 303, 307, 308) and loc:
                return _follow_google(loc), None
            try:
                import json as _j
                j = _j.loads(body.decode("utf-8", "replace"))
                return None, "upstream %s: %s" % (st, j.get("responseCode"))
            except Exception:
                return None, "upstream HTTP %s" % st
        except Exception as e:
            return None, str(e)[:120]

    # 2) 小米 sgp-api：是查询接口，返回 JSON，真地址在 rom_url 里
    if "sgp-api.buy.mi.com" in host or "getdevicelist" in path:
        return _resolve_mi_api(u)

    # 3) 其余视为已经可直接下载的直链
    return u, None


def _resolve_mi_api(u, depth=0):
    """从小米 sgp-api 的 JSON 里抠出 rom_url。"""
    try:
        st, hd, body = _get(u, timeout=30, limit=256 * 1024)
        if st != 200:
            return None, "mi api HTTP %s" % st
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception as e:
        return None, "mi api: %s" % str(e)[:100]

    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "rom_url" and isinstance(v, str) and v.startswith("http"):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(data)
    if not found:
        return None, "mi api: no rom_url in response"
    # 优先返回与请求里 op13_version 匹配的那条
    ver = urllib.parse.parse_qs(parsed_q(u)).get("op13_version", [""])[0]
    if ver:
        for f in found:
            if ver in f:
                return f, None
    return found[0], None


def parsed_q(u):
    return urllib.parse.urlparse(u).query


def _follow_google(url, limit=4):
    """NA 包会经过 gvt1 两次跳转，跟到头拿无签名的稳定地址。"""
    if "googleapis.com" in url or "gvt1.com" in url:
        cur = url
        for _ in range(limit):
            try:
                st, hd, _ = _get(cur, headers={"Range": "bytes=0-0"})
            except Exception:
                break
            loc = _hdr(hd, "location")
            if st in (301, 302, 303, 307, 308) and loc:
                cur = loc
                continue
            break
        return cur
    return url


def cached_resolve(rid, source_url):
    now = time.time()
    with _lock:
        hit = _cache.get(rid)
        if hit and now - hit[2] < TTL:
            return hit[0], hit[1], int(now - hit[2])
    url, err = resolve(source_url)
    with _lock:
        _cache[rid] = (url, err, now)
    return url, err, 0


def probe_size(url):
    """用 Range 请求拿文件总大小。"""
    if not url:
        return None
    try:
        st, hd, _ = _get(url, headers={"Range": "bytes=0-0"}, timeout=25)
        cr = _hdr(hd, "content-range")
        if "/" in cr:
            return int(cr.rsplit("/", 1)[-1])
        cl = _hdr(hd, "content-length")
        if cl and cl.isdigit() and st in (200, 206):
            return int(cl)
    except Exception:
        pass
    return None