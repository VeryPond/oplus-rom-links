fix: 修复克隆后不可用的 5 个 HIGH 问题

1. .gitignore 误排除 _ref/tomboy_pro.py 与 config.py（运行时依赖，必须入库）
2. 新增 requirements.txt（flask / cryptography / requests）
3. tools/scan_official.py 路径 bug：_ref 与 data 用 HERE 而非 PARENT
4. 入口脚本加 UTF-8 输出重配置，修复 Windows 下中文乱码
5. README 补依赖说明与重新扫描章节