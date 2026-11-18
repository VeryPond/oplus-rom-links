# 型号 → 官方全称

站点不显示 `OP 15` 这种缩写。本文说明映射怎么来的、覆盖多少、剩下什么没解决。

---

## 1. 问题

官方接口只返回**型号代码**，响应里没有任何机型名字段：

```json
{
  "version": "CPH2447_13.1.0.596(EX01)",
  "ota_version": "CPH2447_11.A.27_0270_202310120940",
  "security_patch": "2023-10-05",
  "changelog": "https://..."
}
```

`CPH2447` 是 OnePlus 11 的印度版，但响应里看不出来。

第三方目录用的是**市场名**（`OP 11`），跟官方型号代码是两套体系，
没法直接对应。

---

## 2. 试过的四条路

| 来源 | 结果 |
|---|---|
| 官方 API 响应 | 只有型号，无名称 |
| [kiwi_sdk 型号库](https://gitlab.mokiwi.com/kiwi_sdk/public) `oppo.go` | 981 条型号 + OS 版本，**无名称字段** |
| 目录站 HTML 内嵌 JSON | 只有 102 个型号的映射，且用的是缩写名 |
| OPPO/一加官网 | 没有暴露型号清单 API，页面也扒不到 |

---

## 3. 最终方案：Google Play 设备清单

[bsthen/device-models](https://github.com/bsthen/device-models) —— 从 Google Play
官方支持的设备列表自动生成，44080 条，JSON 结构：

```json
{
  "PLK110":  {"brand": "OnePlus", "name": "OnePlus 15"},
  "PJZ110":  {"brand": "OnePlus", "name": "OnePlus 13"},
  "CPH2797": {"brand": "OPPO",    "name": "Find X9"},
  "NE2210":  {"brand": "OnePlus", "name": "OnePlus 10 Pro"}
}
```

**覆盖结果：200 个已扫型号全部映射成功（100%）**。

---

## 4. 两个需要补丁的地方

### 4.1 OPPO 条目名字不带品牌

bsthen 里 `CPH2797` 的 name 是 `Find X9`，不是 `OPPO Find X9`。
所以要对 OPPO 系补前缀：

```python
_BRAND_PREFIX = {"oppo": "OPPO", "oneplus": "OnePlus", "realme": "realme"}

# 型号前缀推断
P 系国行 -> OPPO      (PL/PJ/PK/PH/PE/PF/PA/PB/PD/PG 开头)
CPH     -> OPPO
NE/LE/IN/HD/GM/KB -> OnePlus
RMX     -> realme
```

### 4.2 有 7 个型号 bsthen 也没收录

第一轮统计时剩 7 个显示成 `PHK110 (型号未收录)`：

```
PERM10  PFEM10  PFVM10  PGIM10  PHA120  PHK110  RMX2155
```

原因是 bsthen 的 key 是 **Google Play 的设备标识**，不完全等于型号代码。
第二轮我加了「按型号反查」的兜底逻辑后，这 7 个也全部解析出来了。

---

## 5. 全称规则的实现

```python
def full_name(model, current=""):
    fn = _load_fullnames()          # bsthen 映射表
    m = model.upper()
    if m in fn:
        raw = fn[m]
        has_brand = any(raw.lower().startswith(p) for p in
                        ("oppo", "oneplus", "realme", "xiaomi", "redmi", "poco"))
        return raw if has_brand else _qualify(raw, "", m)
    # 兜底：把旧缩写展开
    ...
```

---

## 6. 映射表位置

`_ref/bsthen_map.json` —— 1063 条精确映射，格式：

```json
{"CPH2447": {"brand": "OnePlus", "name": "OnePlus 11"}}
```

重新生成：

```bash
curl -o _ref/bsthen.json https://raw.githubusercontent.com/bsthen/device-models/main/devices.json
python tools/build_name_map.py
```

---

## 7. 一个坑：同名不同型

`PLJ110` 和 `CPH2797` 都是 `OPPO Find X9`（国行 / 海外），
按名称归并后会自动合成同一个机型条目 —— 这是**预期行为**，
因为用户关心的是「Find X9 有哪些版本」，而不是哪个 SKU 代码。

但要保留型号列，否则分不清哪个包对应哪台机器。
