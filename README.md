# OPPO / 一加 / realme 官方 ROM 直链解析与浏览器

> 本仓库由 DeepSeek Harness 生成。供研究与个人设备维护使用。所有直链都是厂商临时签名，不要长期保存或公开转发。

针对 OPPO 系（OPPO / OnePlus / realme）做了一件事：把官方 OTA 的**下载校验地址**解析成**可直接下载的 CDN 直链**，
并把 233 个机型、418 个「机型×地区」条目整理成一个可浏览的站点。

起因是常见的做法（扒第三方目录）只有 103 个机型 —— 那是别人爬虫的天花板。
要全机型只能直连厂商自己的 OTA 服务器，而那个接口是 RSA + AES 双重加密的。

## 结果

真机无关，纯协议对接。当前覆盖：

| 项目 | 数量 |
|---|---|
| 机型（官方全称去重） | **233** |
| 机型 × 地区 条目 | **418** |
| 地区 | 18 |
| 目录源版本 | 1391 |
| 官方接口版本 | 484（其中 413 个完整包 >500MB）|

实测解析成功率：6 个品牌各取 2 个机型，**12/12 返回 206 + 正确大小 + PK 头**。

## 两种下发方式

站点同时吃两个源，机制完全不同：

| 源 | 给的是什么 | 怎么处理 |
|---|---|---|
| 第三方目录 `roms.danielspringer.at` | `downloadCheck?` 校验地址 | 带 `userId` 头请求，取 302 的 Location |
| 厂商官方接口 `component-ota-*.allawn*` | RSA/AES 加密响应 | 解密后直接拿到带签名的 CDN 地址 |

## 官方接口怎么打通

这部分是核心，详见 [docs/OFFICIAL_API.md](docs/OFFICIAL_API.md)。协议是：

1. 随机生成 AES-256 key，用厂商 RSA 公钥做 **RSA-OAEP(SHA1)** 加密后放进 `protectedKey` 头
2. 请求体 AES-CTR 加密，连同 IV 一起 POST 出去
3. 响应解密，里面有 `version`（市场版本号）和下载地址

**三个卡住过很久的坑**：

| 坑 | 现象 | 解法 |
|---|---|---|
| GUID 取值 | 随机 64 位 GUID → 走 `/update/v6` → 返回 `2201` | **全 0 GUID** → 走 `/update/v3` → 正常 200 |
| 版本号格式 | 直接传型号 → `500` | 必须拼成 `MODEL_11.A` 前缀，服务端自动补全 |
| 地区参数 | 只查 `cn` → CPH/RMX 型号约 50% 查不到 | CPH/RMX 要查 `eu`/`in`/`sg`/`gl`/`id`/`tw`/`my`/`vn`/`th`/`ph` |

第一条最难发现：我用参考实现能跑通，自己按同样逻辑调用却一直 2201。
对比源码才发现 CLI 的 `--guid` 默认值是 `"0"*64`，走的是 v3 而不是 v6。

`2004` 是正常响应，意思是「该版本档位没有版本」，不是错误。

## 站点

```bash
pip install flask
python app.py
# 打开 http://127.0.0.1:8000
```

首次运行会自动从第三方目录同步（约 10 秒，国内需要代理）。
官方接口的数据已经在 `data/roms.db` 里，不联网也能浏览。

### 页面

| 路径 | 说明 |
|---|---|
| `/` | 双源统计 + 品牌入口 + 地区入口 |
| `/brand/<品牌>` | 品牌下所有机型 |
| `/region/<地区码>` | 该地区所有机型 |
| `/device/<机型全称>` | 详情，按地区分组，标注数据来源 |
| `/go/<id>` | 302 跳直链 |

## 机型名用全称

不显示 `OP 15` 这种缩写。映射表来自 [bsthen/device-models](https://github.com/bsthen/device-models)
（Google Play 官方设备清单，44080 条），200 个已扫型号**全部映射成功**。

| 型号 | 显示 |
|---|---|
| `PLK110` / `CPH2747` / `CPH2745` | **OnePlus 15** |
| `PJZ110` | **OnePlus 13** |
| `CPH2797` / `PLJ110` | **OPPO Find X9** |
| `NE2210` | **OnePlus 10 Pro** |

## 区域是完全分开的

同一机型不同地区是独立条目，不合并：

```
OPPO Find X9       → CN / EU / ID / IN / MY / SG / TH / TW / VN  （9 个）
OPPO Find X9 Ultra → APC / EU / ID / IN / JP / MX / MY / SG / TH / TW / VN （11 个）
OnePlus 15         → CN / EU / GLO / IN / NA   （5 个）
```

## 目录

```
app.py                Flask：页面 + API
catalog.py            双源合并、全称映射、区域拆分
resolver.py           目录源直链解析（downloadCheck → CDN）
official_ota.py       官方接口（RSA/AES 协议）
scan_official.py      全机型扫描器
import_official.py    扫描结果入库
data/roms.db          SQLite（两个源都在里面）
_ref/                 参考实现、型号清单、全称映射表
docs/                 说明文档（见下）
```

## 文档

| 文件 | 内容 |
|---|---|
| [docs/OFFICIAL_API.md](docs/OFFICIAL_API.md) | 官方接口协议、RSA/AES 细节、三个坑 |
| [docs/SIGNATURE.md](docs/SIGNATURE.md) | 直链签名机制实测：哪个参数真校验、有效期多长 |
| [docs/DEVICE_NAMES.md](docs/DEVICE_NAMES.md) | 型号 → 全称映射的来源与实现 |
| [docs/REGIONS.md](docs/REGIONS.md) | 区域拆分口径、地区码表 |
| [docs/PITFALLS.md](docs/PITFALLS.md) | 踩过的坑 |
| [docs/CREDITS.md](docs/CREDITS.md) | 参考项目与工具 |

## 已知限制

1. **官方源直链是扫描快照**（约 30 分钟有效），过期需重扫。目录源可实时重解析。
2. **地区未穷举**：每型号试 4~10 个主要地区，冷门地区（`sa`/`mea`/`roe`/`la`）可能有漏。
3. **依赖第三方目录站**：它的 API 变了或限流，目录源就不可用。
4. **不是生产级部署**：Flask 开发服务器，建议只在本机或局域网用。

## 免责

本项目只做**公开接口的协议对接**，不破解、不绕过任何加密（RSA 公钥是公开的）。
直链是厂商 CDN 的临时凭证，有效期约 30 分钟。请勿用于商业分发或大规模抓取。

## License

MIT
