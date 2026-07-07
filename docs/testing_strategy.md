# 测试策略

本项目的测试目标是保护真实业务规则，同时避免把真实客户数据放入仓库。

## 本地必跑

```powershell
python -m tools.dev_check
pytest -q
```

发布或合并前如果要把质量门收紧，可以使用：

```powershell
python -m tools.dev_check --require-clean --require-ruff
```

PowerShell 下可拆开跑：

```powershell
python -m compileall -q app booking_rules module_entrypoints tools tests
python -m py_compile (Get-ChildItem -LiteralPath . -File -Filter *.py | ForEach-Object { $_.FullName })
pytest -q
```

## 分层测试

- 小单测：规则、文件名、安全边界、配置解析。
- 模块测试：Booking body validation、UFO、dispatch、Launcher。
- smoke 测试：主要页面能返回 200。
- 手工验收：用本地真实样本验证最终 `.eml`、Excel 导出、Mac LAN 和浏览器扩展。

## 样本规则

自动测试只使用 synthetic 或脱敏样本。真实样本不要进入 Git，详见 `tests/fixtures/README.md`。
