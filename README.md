# My-Autowork Platform Remake

My-Autowork 是一个面向本地和局域网内部使用的业务自动化工作台，用 FastAPI、Jinja2、SQLite、Excel/EML/PDF 解析能力，把账单、清关、财务、Booking、派送邮件和 UFO 邮件等重复工作集中到一个可运行、可测试、可打包的项目里。

它不是 SaaS，也不默认面向公网。默认使用场景是维护者本机、同事电脑、Launcher 分发包，或 Mac mini 局域网服务。

## 核心模块

- 账单：导入总表、账单、派送单并生成校验和回填结果。
- 香港进口清关：从订单和模板生成清关 bill。
- 香港出口清关：管理待清关和已清关记录并导出。
- 财务：导入付款/账单记录、筛选、补录和导出。
- Booking：从客户邮件和附件生成 booking，并提供 body validation。
- Booking TMS extension：在公司 TMS 页面上传 `.xlsx` booking form 到 Booking 服务。
- 派送邮件：解析客户邮件、匹配附件、生成预览和 `.eml`。
- UFO 邮件：保存签名/配置，生成 UFO 邮件输出。
- Launcher：为同事下载、校验、安装和更新独立模块包。

## 技术栈

- Python 3.12+
- FastAPI + Jinja2
- SQLite
- openpyxl / pandas / PIL / email 相关解析库
- PyInstaller 打包
- pytest 自动化测试

## 本地开发启动

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m app.packaging.dev_server reconcile_web_app:app --host 127.0.0.1 --preferred-port 8051
```

Booking 独立入口：

```powershell
python -m app.packaging.dev_server booking_web_app:app --host 127.0.0.1 --preferred-port 8042
```

## 测试

```powershell
python -m tools.dev_check
pytest -q
```

PowerShell 下如果要手动跑编译检查，推荐使用：

```powershell
python -m compileall -q app booking_rules module_entrypoints tools tests
python -m py_compile (Get-ChildItem -LiteralPath . -File -Filter *.py | ForEach-Object { $_.FullName })
```

## 数据安全边界

`runtime/` 是运行时数据目录，不应提交、不应放进审阅包、不应被发布包覆盖。它可能包含数据库、上传缓存、生成结果、邮件草稿、签名模板和模块配置。

真实客户邮件、Excel、PDF、图片、数据库、token、cookie、证书、私钥都不应进入 Git。自动化测试只使用 synthetic 或已脱敏样本，规范见 [tests/fixtures/README.md](tests/fixtures/README.md)。

## Launcher 与模块分发

Launcher 模式下，每个模块的数据目录由 `BILL_TOOL_RUNTIME_DIR` 指向：

```text
LauncherTool/runtime/module_data/<module_id>
```

模块程序目录和用户数据目录分离，更新模块不会覆盖用户数据。详细说明见 [docs/module_distribution.md](docs/module_distribution.md)。

## Mac mini LAN 部署

Mac mini 可作为局域网服务。脚本默认把代码和 runtime 分开，服务地址、端口、证书和数据目录通过环境变量配置。详细步骤见 [MAC_MINI_DEPLOY.md](MAC_MINI_DEPLOY.md)、[docs/deployment_config.md](docs/deployment_config.md) 和 [docs/mac_mini_lan_deployment.md](docs/mac_mini_lan_deployment.md)。

## Booking TMS Extension

源码里的扩展默认值只用于开发。给同事部署时，应通过构建脚本注入当前服务地址：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://booking.tools.home.arpa
```

办公室部署的标准 HTTPS 域名不需要填写端口；直接 IP 回退地址仍应显式写端口。

安装和验收见 [browser_extensions/booking_tms_checker/README.md](browser_extensions/booking_tms_checker/README.md)。

## 已知限制

- Windows Excel COM、Outlook、图片查看器、字体和 macOS/Linux 环境存在差异。
- YOLO/UFO 相关能力需要额外依赖和模型文件。
- 真实业务规则仍在演进，新增样本必须先脱敏。
- 维护文档索引见 [docs/architecture.md](docs/architecture.md)、[docs/runtime_data_policy.md](docs/runtime_data_policy.md)、[docs/testing_strategy.md](docs/testing_strategy.md)。

## 截图计划

公开 README 暂不内置截图，避免误带真实业务数据。后续如需展示，应使用脱敏数据补充首页、Booking body validation、Launcher、UFO 邮件页面截图。
