# Mac mini 内网部署交接

更新时间：2026-07-14

本文只记录可提交到 Git 的非敏感部署信息。API 凭据、共享令牌、证书私钥、数据库和真实业务文件不得写入本仓库。

## 网络拓扑

- 上游外网路由：`192.168.1.1`
- 办公室核心 DHCP/DNS 路由：`192.168.10.1`，TP-Link TL-ER3220G
- 无线接入设备：`192.168.10.56`，DHCP 已关闭
- Mac mini 有线固定地址：`192.168.10.4`
- 核心路由已为 Mac mini 配置静态 DHCP 地址和下列静态域名映射

## 服务与域名

| 服务 | 本机后端 | 同事访问地址 |
| --- | --- | --- |
| ImportScreeningApp | `http://127.0.0.1:10081` | `https://screening.tools.home.arpa` |
| datapreview | `http://127.0.0.1:8099` | `https://data.tools.home.arpa` |
| My-Autowork | `https://127.0.0.1:8010` | `https://work.tools.home.arpa` |
| Booking Web | `https://127.0.0.1:8042` | `https://booking.tools.home.arpa` |
| Urgent Tracker | `http://127.0.0.1:10082` | `https://urgent.tools.home.arpa` |

五个域名均由 `192.168.10.1` 解析到 `192.168.10.4`。这些名称只在办公室局域网有效，不应发布到公网 DNS。

## Mac mini 运行状态

- Caddy 由 Homebrew 安装，配置文件为 `/opt/homebrew/etc/Caddyfile`
- Caddy 以系统 LaunchDaemon `homebrew.mxcl.caddy` 运行，监听 `80/443`，开机自动启动
- HTTP 自动跳转到 HTTPS
- HTTPS 服务证书由现有 `My Autowork Local CA` 签发
- 统一业务服务脚本：`/Users/Shared/internal_services.sh`
- 桌面启动入口：`/Users/caiyang/Desktop/My-Server project/start_services.command`
- 运行数据统一放在 `/Users/Shared/company_tools_data`，不得被 Git 更新覆盖

本机 CA 分发文件位于：

```text
/Users/caiyang/Desktop/My-Server project/my-autowork-local-ca.crt
```

客户端必须信任该 CA，才能正常使用这些 HTTPS 域名。不要分发或提交任何 `.key` 文件。

## Booking TMS 插件

插件设置中的服务地址应填写：

```text
https://booking.tools.home.arpa
```

当前 Mac 部署没有设置 `MY_AUTOWORK_ACCESS_TOKEN`，因此插件 Access Token 留空。以后若服务端启用该变量，插件和服务端必须配置相同令牌，但真实值不得提交到 Git。

生成同事安装包：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://booking.tools.home.arpa
```

输出为 `dist\booking_tms_checker_edge` 和 `dist\booking_tms_checker_edge.zip`。同事在 Edge 中加载解压缩扩展后，不要移动扩展目录。

## Urgent Tracker

Windows 客户端服务地址：

```text
https://urgent.tools.home.arpa
```

客户端还需要 Mac 数据目录生成的共享令牌。令牌只应安全地录入客户端，不能通过 Git、聊天记录或部署文档传播。

截至本文更新时间，Mac 服务已运行且数据库为空，但 SF、FedEx、DHL、UPS 正式 API 凭据均未配置。自动查询至少需要从安全渠道补齐：

- `SF_PARTNER_ID`
- `SF_CHECK_WORD`
- `FEDEX_CLIENT_ID`
- `FEDEX_CLIENT_SECRET`

DHL 和 UPS 凭据可在审批完成后再配置。凭据只写入 `/Users/Shared/company_tools_data/urgent_tracker/service.env`。

## 验证命令

```bash
/Users/Shared/internal_services.sh status
launchctl print system/homebrew.mxcl.caddy
curl https://screening.tools.home.arpa
curl https://data.tools.home.arpa
curl https://work.tools.home.arpa/modules/ufo-mail
curl https://booking.tools.home.arpa/modules/booking/body-validation
curl https://urgent.tools.home.arpa/health
```

未安装 CA 的命令行环境需要临时使用 `--cacert` 指向 CA 文件。不要使用 `-k` 作为长期部署方案。

## 更新边界

Git 更新只更新程序代码。以下内容必须保留在 Mac 本地，不得由 `git pull` 覆盖：

- `/Users/Shared/company_tools_data/**`
- `/opt/homebrew/etc/Caddyfile` 的实际部署副本
- 所有 API 凭据和共享令牌
- CA 私钥和服务器私钥
- SQLite 数据库、日志、上传和输出文件
- 路由器 DHCP/DNS 配置

开发机 Codex 处理部署相关改动时，应先阅读本文，再分别检查应用仓库、运行数据目录和系统服务状态，不能假设 `git pull` 等于完整部署。
