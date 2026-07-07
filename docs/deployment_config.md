# 部署配置说明

本项目有开发模式、Launcher 模式和 Mac mini LAN 模式。正式地址不要散落在多个脚本或扩展源码里，按下面的入口配置。

## 运行端口和地址

- `MY_AUTOWORK_HOST`：Mac LAN 脚本监听地址，默认 `0.0.0.0`。
- `MY_AUTOWORK_PORT`：Mac LAN 脚本端口，默认 `8010`。
- `BILL_TOOL_RUNTIME_DIR`：应用实际使用的 runtime 目录。
- `MY_AUTOWORK_RUNTIME_DIR`：Mac 脚本读取的 runtime 目录，脚本启动时会转成 `BILL_TOOL_RUNTIME_DIR`。

## HTTPS 证书

Mac 脚本支持：

- `MY_AUTOWORK_SSL_CERTFILE`
- `MY_AUTOWORK_SSL_KEYFILE`
- `MY_AUTOWORK_SSL_CA_CERTFILE`
- `MY_AUTOWORK_SSL_DIR`

如果配置证书路径，`run_mac_lan.sh` 会用 HTTPS 启动 uvicorn。证书生成和信任说明见 `generate_lan_https_cert.sh` 和 `MAC_MINI_DEPLOY.md`。

## Booking TMS extension 地址

不要手工改 `content.js` 或 `popup.js` 里的地址。源码默认值只用于开发，正式分发使用：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://<Mac-mini-IP>:8010
```

脚本会写入构建输出里的 `config.js`，并生成 `dist/booking_tms_checker_edge` 和 zip。

## Launcher manifest

Launcher 优先读取环境变量：

```text
BILL_TOOL_MANIFEST_URL
```

如果没有环境变量，则读取 Launcher 旁边的 `update_config.json`。发布包与 manifest 说明见 `docs/module_distribution.md`。

## Runtime 边界

Launcher 模式下，模块 runtime 默认位于：

```text
LauncherTool/runtime/module_data/<module_id>
```

Mac mini 模式下，runtime 默认位于：

```text
/Users/Shared/company_tools_data/my_autowork/runtime
```

不要把 runtime、数据库、上传缓存、输出文件或真实业务样本打进发布包。
