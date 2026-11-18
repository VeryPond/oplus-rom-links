# 官方 OTA 接口协议

设备无关。分析对象：`component-ota-{cn,eu,in,sg}.allawn{tech.com,os.com}`。
参考实现：[OPlus-Tracker](https://github.com/SunsetMkt/OPlus-Tracker) 的 `tomboy_pro.py`。

---

## 1. 加密协议

请求和响应都是加密的，涉及两套算法：

```
客户端                                    服务端
  |                                         |
  |  随机生成 AES-256 key (32B) + IV (16B)   |
  |  AES key 用厂商 RSA 公钥加密 (OAEP-SHA1)  |
  |  → base64 → 放进 protectedKey 头          |
  |                                         |
  |  POST { params: {cipher, iv} }  ------>  |
  |     cipher = AES-CTR(JSON body, key, iv) |
  |                                         |
  |  <------  {cipher, iv}                   |
  |  用同一个 key 解密                        |
```

关键点：

- **AES key 是客户端随机生成的**，不是协商出来的
- RSA 只用来传这把临时 key，加密的是 `base64(aes_key)`，不是请求体
- 请求体用 **AES-CTR**（不是 CBC/GCM），IV 随请求发送
- 响应加密用的是**同一个 key**，但 IV 是响应里自带的新 IV

### RSA 公钥按地区分四套

```
cn  -> MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...   (public_key_version 1615879139745)
eu  -> MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...   (1615897067573)
in  -> MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...   (1615896309308)
sg  -> MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...   (1615895993238)
```

公钥是**公开的**（写在官方 APK 里），本项目没有做任何绕过。

---

## 2. 请求头

| 头 | 值 | 说明 |
|---|---|---|
| `otaVersion` | `PLK110_11.C` | **关键**，见第 3 节 |
| `model` | `PLK110` | 型号代码 |
| `mode` | `manual` | 手动检查 |
| `nvCarrier` | `10010111` | 运营商 ID，按地区 |
| `language` | `zh-CN` | 按地区 |
| `protectedKey` | JSON | `{"SCENE_1":{"protectedKey":"...","version":"...","negotiationVersion":"1615879139745"}}` |
| `deviceId` | 随机 64 字符 | |
| `pipelineKey` | `ALLNET` | |
| `infVersion` | `1` | |

---

## 3. 三个坑

### 3.1 GUID 决定走 v3 还是 v6

```python
endpoint_ver = "/update/v6" if (pre == "1") or (guid and guid != "0"*64) else "/update/v3"
```

| GUID | 端点 | 结果 |
|---|---|---|
| 随机 64 位 | `/update/v6` | **`2201`**（拒绝） |
| `"0"*64` | `/update/v3` | **`200`**（正常） |

这个坑卡了很久。我用参考实现的 CLI 能跑通，自己按同样逻辑调用却一直 2201。
对比源码才发现 CLI 的 `--guid` 默认值是 `"0"*64`。

```python
# 错误的写法
cfg = QueryConfig(..., guid=generate_random_string(64))

# 正确的写法
cfg = QueryConfig(..., guid="0" * 64)
```

### 3.2 otaVersion 必须带档位后缀

直接传型号：

```
otaVersion = "PLK110"  ->  HTTP 500  未知异常，请联系管理员
```

必须拼成版本前缀，服务端会自己补全剩余部分：

```
otaVersion = "PLK110_11.A"  ->  200
otaVersion = "PLK110_11.C"  ->  200
```

所以扫描时要枚举后缀：

```python
SUFFIXES = ["_11.A", "_11.C", "_11.F", "_11.H", "_11.J"]
```

服务端补全后返回内部串，形如：

```
PLK110_11.C.80_1800_202610290542
   |     |   |    |       |
   |     |   |    |       +-- 构建时间 YYYYMMDDHHMM
   |     |   |    +---------- 内部版本号
   |     |   +--------------- 档位序号
   |     +------------------- 档位（A/C/F/H/J）
   +------------------------- 型号
```

### 3.3 地区不对就查不到

同一个机型在不同地区是**不同的 model 代码**：

| 机型 | 国行 | 印度 | 全球/欧洲 |
|---|---|---|---|
| OnePlus 15 | `PLK110` | `CPH2745` | `CPH2747` |
| OPPO Find X9 | `PLJ110` | — | `CPH2797` |

如果只查 `cn`，CPH 系型号会有一半查不到。实测 12 个 CPH 型号只查 cn 时全灭，
换成对应地区后 3 个命中（`CPH2603` → eu/sg/ru/tr/th/id/tw/my/vn/ph 全可以，
`CPH2321` → 只有 in，`CPH2005` → 只有 eu）。

扫描策略按前缀分：

```python
REGIONS_CN       = ["cn", "eu", "in", "sg"]                      # P/NE/LE 开头
REGIONS_OVERSEAS = ["eu", "in", "sg", "gl", "id", "tw", "my", "vn", "th", "ph"]  # CPH/RMX
```

---

## 4. 响应码

| 码 | 含义 | 是不是错误 |
|---|---|---|
| `200` | 成功 | — |
| `2004` | 该版本档位不存在 | **不是**，正常响应 |
| `2201` | GUID / 参数不对 | 是 |
| `2306` | 缺 `userId`（downloadCheck 那条链路） | 是 |
| `500` | 版本号格式不对 | 是 |

`2004` 是扫描时最常见的响应 —— 说明这个档位确实没有版本，换下一个后缀继续。

---

## 5. 响应里的字段

解密后是 JSON，实际用到的：

```json
{
  "version": "PLK110_17.0.1.201(CN01)",
  "ota_version": "PLK110_11.C.80_1800_202610290542",
  "security_patch": "2026-11-01",
  "changelog": "https://gauss-compotacostauto-cn.allawnfs.com/....html"
}
```

**注意有兩套版本号**：

| 字段 | 示例 | 用途 |
|---|---|---|
| `version` | `PLK110_17.0.1.201(CN01)` | 用户能识别，**站内展示这个** |
| `ota_version` | `PLK110_11.C.80_1800_202610290542` | 内部串，**只用来解析构建时间** |

早期版本我把 `ota_version` 当成版本号显示，结果页面上全是
`PLK110_11.C.80_1800_202610290542.97.8cf4de31` 这种用户看不懂的串。已修正。

---

## 6. 扫描成本

| 项目 | 数值 |
|---|---|
| 型号数 | 309 |
| 每型号请求数 | 5 后缀 × 4~10 地区 |
| 并发 | 10 |
| 总耗时 | **约 22 分钟** |
| 命中 | 200 / 309 |
| 得到版本 | 484 |

型号清单来源见 [DEVICE_NAMES.md](DEVICE_NAMES.md)。
