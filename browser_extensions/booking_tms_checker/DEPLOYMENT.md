# Booking TMS 质检插件内网部署

目标：同事在 SMOOTH TMS 页面选择 booking form 后，直接打开服务器上的筛查结果页。

## 1. Mac mini 启动 Booking Web 服务

服务必须监听内网网卡，不能只监听 `127.0.0.1`：

```powershell
python -m uvicorn booking_web_app:app --host 0.0.0.0 --port 8042
```

同事电脑需要能打开：

```text
https://192.168.10.4:8042/modules/booking/body-validation
```

如果打不开，先检查 Mac mini 防火墙、端口、内网 IP 是否正确。

## 2. 生成同事安装用插件包

在项目根目录运行：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://192.168.10.4
```

脚本会生成：

```text
dist\booking_tms_checker_edge
dist\booking_tms_checker_edge.zip
```

`config.js` 会被写入这次部署的默认服务地址。同事通常只需要加载 `dist\booking_tms_checker_edge` 文件夹。

## 3. 同事安装

1. 打开 Edge 的 `edge://extensions/`。
2. 打开“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择 `dist\booking_tms_checker_edge` 文件夹。
5. 刷新 `https://smooth.clztoud.com/Home/AdminDefault`。

## 4. 验收

1. SMOOTH TMS 右下角出现“Booking 质检”浮窗。
2. 选择 `.xlsx` booking form。
3. 点击“上传并打开筛查结果”。
4. 新标签页打开 `https://192.168.10.4:8042/modules/booking/body-validation/session/...`。
5. 页面直接显示源数据导入表和错误标红。
6. 点击“查看修正建议”后出现第二张建议表。
7. 可以导出修正版。

## 5. 地址变更

如果 Mac mini IP 或端口变化，有两种方式：

- 重新运行打包脚本，发新版插件目录给同事。
- 让同事点击插件图标，在设置里手动填写新的服务地址，然后刷新 TMS 页面。
