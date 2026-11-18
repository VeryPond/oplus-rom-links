# 踩过的坑

## 1. GUID 全 0 才能走 v3

参考实现的 CLI `--guid` 默认值是 `"0" * 64`，我照着逻辑写却用了随机 GUID：

```python
# 一直返回 2201
cfg = QueryConfig(..., guid=generate_random_string(64))
```

对比源码才发现端点选择逻辑：

```python
endpoint_ver = "/update/v6" if (pre == "1") or (guid and guid != "0"*64) else "/update/v3"
```

**随机 GUID → v6 → 2201；全 0 GUID → v3 → 200。**

## 2. 读 JSON 固定 2048 字节会截断

小米 `sgp-api.buy.mi.com` 返回的 JSON 有 **2121 字节**。
我的 `_get()` 默认 `read(2048)`，截断后 `json.loads` 报错：

```
mi api: Expecting ',' delimiter: line 1 column 2025 (char 2024)
```

表现是整个 POCO 品牌的解析全部 502。改成 `read(limit)` 且 `limit=None` 表示读全量后正常。

## 3. otaVersion 必须是版本前缀

```
otaVersion = "PLK110"        -> HTTP 500 未知异常，请联系管理员
otaVersion = "PLK110_11.A"   -> 200
```

必须枚举 `_11.A` / `_11.C` / `_11.F` / `_11.H` / `_11.J`，服务端才肯补全。

## 4. 2004 不是错误

```json
{"body": null, "errMsg": "[traceId=...] artifactV1Result is empty", "responseCode": 2004}
```

这是「该档位没有版本」的正常响应。早期我把它当失败处理，导致统计逻辑混乱。

## 5. 版本号有两套，别把内部串当版本号展示

```json
{
  "version":     "PLK110_17.0.1.201(CN01)",          <- 用户看这个
  "ota_version": "PLK110_11.C.80_1800_202610290542"   <- 内部串
}
```

第一版我用了 `ota_version`，页面上全是：

```
PLK110_11.C.80_1800_202610290542.97.8cf4de31
```

用户完全看不懂。而且同一机型会因为内部串不同被记成多条重复版本
（906 条 vs 修正后的 484 条）。

## 6. 海外 model 代码要查对应地区

只查 `cn` 时，CPH/RMX 系型号约一半查不到。实测：

```
CPH2603  -> eu/sg/ru/tr/th/id/tw/my/vn/ph 都可以
CPH2321  -> 只有 in
CPH2005  -> 只有 eu
```

所以扫描要按前缀决定地区列表。

## 7. 多线程 + redirect_stdout 会互相踩

参考实现里有大量 `print` 调试输出。我原本用
`contextlib.redirect_stdout(io.StringIO())` 包住每次调用，
在多线程下这些上下文管理器会争用同一个全局 stdout，导致输出泄漏、
甚至把自己的打印吞掉。

改成**全局静音**：

```python
REAL_OUT = sys.stdout
sys.stdout = open(os.devnull, "w")
# 之后统一 print(..., file=REAL_OUT)
```

## 8. Flask 开发服务器重启有延迟窗口

反复重启服务时，`Invoke-WebRequest` 会撞上 `ERR_CONNECTION_REFUSED`。
测试脚本要带重试：

```python
for _ in range(20):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/stats", timeout=3)
        break
    except Exception:
        time.sleep(2)
```

## 9. 模板里的反引号

用 JS 模板字符串写 Python/Markdown 文件时，
Markdown 代码块的反引号会和 JS 语法冲突，报
`Expected a semicolon / Expected ',', got 'string literal'`。

解决办法：用 `String.raw` + `chr(96)*3` 拼接，或者分段 `push` 字符串。

## 10. 机型名归并后 detail 页面 404

把 `OP 15` 统一成 `OnePlus 15` 之后，详情页查不到数据了 ——
因为数据库里的 `device` 字段还是旧名 `OP 15`。

需要做**双向解析**：

```python
def _resolve_device_key(device):
    keys = {device, device.upper()}
    if name.upper().startswith("ONEPLUS "):
        keys.add("OP " + name[8:])       # 全称 -> 旧名
    if name.upper().startswith("OP "):
        keys.add("OnePlus " + name[3:])  # 旧名 -> 全称
    return keys
```

---

## 附：签名相关的坑见 [SIGNATURE.md](SIGNATURE.md)，接口协议的坑见 [OFFICIAL_API.md](OFFICIAL_API.md)。
