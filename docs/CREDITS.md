# 参考与致谢

## 关键参考

| 项目 | 用途 |
|---|---|
| [OPlus-Tracker](https://github.com/SunsetMkt/OPlus-Tracker) | 官方 OTA 接口的完整协议实现（RSA/AES、端点选择、地区配置）。本项目的 `official_ota.py` 基于它的 `tomboy_pro.py` 改写 |
| [realme-ota](https://github.com/R0rt1z2/realme-ota) | 同一条 OTA 链路的另一个实现，用于交叉验证 |
| [OPlus_firmware_download](https://github.com/suddenBook/OPlus_firmware_download) | 说明了 `downloadCheck` → CDN 的换票思路 |
| [bsthen/device-models](https://github.com/bsthen/device-models) | Google Play 官方设备清单，型号 → 全称映射的数据源 |
| [kiwi_sdk](https://gitlab.mokiwi.com/kiwi_sdk/public) | `device/model_db/oppo.go`，981 条 OPPO 系型号代码 |
| [roms.danielspringer.at](https://roms.danielspringer.at/) | 第三方 OTA 目录，提供历史版本深度 |

## 工具

| 工具 | 用途 |
|---|---|
| Python 3.13 | 主语言 |
| `cryptography` | RSA-OAEP / AES-CTR |
| `requests` | HTTP |
| Flask | 站点 |
| Playwright | 页面截图验收 |

## 数据来源

| 数据 | 来源 |
|---|---|
| 版本目录 | `roms.danielspringer.at/api/ota.php`（1391 条）|
| 官方版本 | `component-ota-*.allawn{tech.com,os.com}` 直连扫描（484 条）|
| 机型全称 | `bsthen/device-models`（44080 条，映射 1063 个型号）|
| 型号清单 | kiwi_sdk + 目录站型号合并去重（309 个）|

## 生成说明

本仓库的代码、文档、扫描脚本与验收流程由 **DeepSeek Harness** 生成。
所有协议结论均标注了实测依据（响应码 / 参数篡改结果 / 时间戳解析），
无法确证的部分在文档中明确标注为推测（例如 `sign` 的 HMAC 具体构造、
真正的 TTL 边界）。

## 免责

本项目只做**公开接口的协议对接**：

- RSA 公钥来自官方 APK，是公开的
- 没有破解任何加密算法
- 没有绕过任何访问控制（`userId` 只做格式校验是服务端的设计）

直链是厂商 CDN 的临时凭证，有效期约 30 分钟。
请勿用于商业分发或大规模抓取，由此产生的后果由使用者承担。
