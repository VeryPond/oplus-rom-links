# 直链签名机制

实测日期：2026-11-18。对象：`gauss-compota-c-cn.allawnfs.com`（国行）
与 `gauss-compota-c-sg.allawnofs.com`（海外，OSS2 签名）。

---

## 1. 签名从哪来

OPPO 升级客户端拿到的不是文件 URL，而是**下载校验地址**：

```
https://component-ota-cn.allawntech.com/downloadCheck
    ?c=<32hex>      # 包 ID
    &p=<92hex>      # 设备/版本策略串
    &d=<78hex>      # 固定串
    &g=<32hex>      # 分组/灰度 ID
    &id=<24hex>     # 数据库记录 ID
    &taste=1&supportDLTaste=0&mode=1&tr=manual
    &s=<32hex>      # 签名
```

它**必须带 `userId` 头**才会 302 跳转到 CDN，否则返回：

```json
{"body":null,"errMsg":"[traceId=...] 2306","responseCode":2306}
```

带上去之后：

```
HTTP 302
Location: https://gauss-compota-c-cn.allawnfs.com/remove-<c>/g-<g>/component-ota/26/10/08/<hash>.zip
          ?sign=<32hex>&t=<8hex>&AWSAccessKeyId=...&Expires=...&Signature=<urlencoded>
```

这个 Location 就是直链。

---

## 2. userId 只校验格式

| userId 值 | 结果 |
|---|---|
| `oplus-ota\|16001011` | 302 |
| `oplus-ota\|12345678` | 302 |
| `oplus-ota\|1` | 302 |
| `oplus-ota\|99999999999` | 302 |
| `oplus-ota\|16001011 `（尾部空格） | 302 |
| `oplus-ota`（无竖线） | 2309 |
| `foo\|16001011` | 2309 |
| `OPPO\|16001011` | 2309 |
| `16001011`（纯数字） | 2309 |
| 不带 | 2306 |

判据是 **`oplus-ota|<任意数字>`** 这个格式，后面的数字随便填，
**不校验账号真实性**。

---

## 3. 真正被校验的是「取件码」

对 `downloadCheck` 的每个参数做篡改测试：

| 动作 | 结果 |
|---|---|
| `c` / `p` / `d` / `g` / `id` / `s` 任一改一位 | `2404` |
| 上述任一**删掉** | `500` |
| 拿 A 包的 `c` 配 B 包的 `s`（跨包拼接） | `2404` |

所以 `c&p&d&g&id&s` 是一组**防篡改的取件码**，本身就是授权凭据（capability URL）。
它不绑定 IP（走代理/直连都能换）、不绑定 UA、不是一次性（连续重放 8 次全成功）。

---

## 4. 直链上那组 AWS 参数是装饰

把签名 URL 的参数逐个篡改，用 `Range: bytes=0-63` 探测：

| 篡改 | 结果 |
|---|---|
| `Signature` 首字符改成 A | **206 照过** |
| `Signature` 整个清空 | **206 照过** |
| `Signature` 参数删掉 | **206 照过** |
| `AWSAccessKeyId` 删掉 | **206 照过** |
| `Expires` +86400（延长一天） | **206 照过** |
| `Expires` -86400（设为过去） | **206 照过** |
| **`sign` 改一位** | **403** |
| **`sign` 删掉** | **403** |
| **`t` 删掉** | **403** |
| **路径里的 hash 改一位** | **403** |

结论：真正的闸门是 **`sign` + `t` + 路径**。
`AWSAccessKeyId` / `Expires` / `Signature` 是从对象存储网关透传下来、
CDN 实际**不校验**的字段。

最小可用参数集实测：**`sign` + `t` 两个就够**（只留 `sign` 会 403）。

> 但不要据此认为签名可以随便改 —— 下面说明为什么。

---

## 5. sign 是 path + t 的确定性函数

连续 6 次请求同一条取件码：

```
#1  t=6afda5ef  sign=8bf7067b60124d8a55f7b849f35daf60
#2  t=6afda5f0  sign=5a1d9c354d3f75bc6a758413343af30d
#3  t=6afda5f0  sign=5a1d9c354d3f75bc6a758413343af30d   <- 同一个 t，同一个 sign
#4  t=6afda5f1  sign=7401783d1cb14f08156ae6461710f4bf
#5  t=6afda5f1  sign=7401783d1cb14f08156ae6461710f4bf   <- 同上
#6  t=6afda5f2  sign=b95fc6edbe00a93468cbe67bfcb86613
```

- 同一秒（同一 `t`）→ **每次都是同一个 sign**
- 换一秒 → sign 必变
- `t` 是**发起请求的时刻**（hex unix 秒）

即 `sign = HMAC(secret, path ‖ t)` 截断到 128 bit。
没有 secret 无法伪造，但**也不需要伪造 —— 直接问源站要就行**。

「`sign` 改一位就 403」说明它是与路径绑定的有效凭证，
不是说明 30 分钟是硬失效 —— `Expires` 不参与校验，
真正的时间窗在 `sign` 的 HMAC 里（或者 CDN 侧另有 TTL）。

---

## 6. 有效期

从参数拆解：

```
t        = 0x6afda511 = 1795007761  -> 2026-11-18 21:16:01   (请求时刻)
Expires  = 1795009543               -> 2026-11-18 21:45:43
Expires - t = 1782 秒 = 29.7 分钟
```

实测：昨天（约 23 小时前）生成的直链，今天请求返回 **403**。

站点缓存 TTL 设为 **25 分钟**，留 5 分钟余量。

---

## 7. 三种 CDN 主机

不是所有地区都用同一个域名，签名格式也不一样：

| 主机 | 签名格式 |
|---|---|
| `gauss-compota-c-cn.allawnfs.com` | AWS 风格（`AWSAccessKeyId` + `Signature`）|
| `gauss-compota-c-sg.allawnofs.com` | **OSS2 风格**（`x-oss-signature` + `x-oss-expires`）|
| `gauss-compotaauto-c-cn.allawnfs.com` | 同上，auto 通道 |

所以解析时必须**直接跟着 Location 走**，不能假定只有一个域名。

---

## 8. 小米系是另一套

`sgp-api.buy.mi.com` 返回的不是文件，是一个 JSON：

```json
{"code":0,"data":{"device_data":{"device_list":{
  "POCO F6 EEA":{"stable_rom":{"version":"OS3.0.304.0.WNPEUXM",
                               "rom_url":"https://ultimateota.d.miui.com/....zip?t=...&s=..."}}
}}}}
```

要递归找 `rom_url` 字段。注意这个 JSON 有 2121 字节，
早期我用 `read(2048)` 读，把 JSON 截断了，导致 POCO 全部 502。
改成读全量后正常。

---

## 9. 实证记录

```
OPPO     A6 PRO 5G      206  5.4G  OK
OnePlus  OP 10 PRO      206  6.7G  OK
realme   16 Pro         206  8.2G  OK
Xiaomi   15             206  7.9G  OK
Redmi    17             206  4.8G  OK
POCO     F6             206  5.9G  OK
```

全部返回 `Content-Range: bytes 0-63/<total>` 且首字节 `PK\x03\x04`。
