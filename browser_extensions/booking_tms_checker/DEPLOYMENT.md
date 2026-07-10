# Booking TMS 质检插件内网部署

目标：同事在 SMOOTH TMS 页面选择 booking form 后，直接打开服务器上的筛查结果页。

## 1. Mac mini 启动 Booking Web 服务

服务必须监听内网网卡，不能只监听 `127.0.0.1`：

```powershell
python -m uvicorn reconcile_web_app:app --host 0.0.0.0 --port 8010
```

同事电脑需要能打开：

```text
https://<Mac-mini-IP>:8010/modules/booking/body-validation
```

如果打不开，先检查 Mac mini 防火墙、端口、内网 IP 是否正确。

## 2. 生成同事安装用插件包

在项目根目录运行：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://<Mac-mini-IP>:8010
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

这是“加载解压缩的扩展”，安装后必须在 `edge://extensions/` 中保持“已启用”。如果 Edge 或公司的浏览器策略将它停用，代码无法绕过 Edge 的停用，也不会尝试修改 Windows 注册表或 Edge 策略；需要手动重新启用，或由 IT 另行部署受管扩展。

Edge 会记住所选文件夹的绝对路径。安装后请长期保留 `dist\booking_tms_checker_edge`，不要移动、重命名或删除；更新包时覆盖原目录并点击“重新加载”。

## 4. 验收

1. SMOOTH TMS 右下角出现“Booking 质检”浮窗。
2. 选择 `.xlsx` booking form。
3. 点击“上传并打开筛查结果”。
4. 新标签页打开 `https://<Mac-mini-IP>:8010/modules/booking/body-validation/session/...`。
5. 页面直接显示源数据导入表和错误标红。
6. 点击“查看修正建议”后出现第二张建议表。
7. 可以导出修正版。

### 4.1 重启与页面重绘验收

1. 重启电脑，或完全退出所有 Edge 窗口后重新打开 Edge。
2. 打开 `edge://extensions/`，确认“Booking Form 质检助手”仍保持“已启用”，且没有加载错误。
3. 重新打开 SMOOTH TMS 页面，确认浮窗默认展开。
4. 点击浮窗右上角的 `−`，确认内容收起但展开入口仍可见；点击 `+` 后应重新展开。
5. 在 TMS 内切换页面或触发 SPA/DOM 重绘，确认浮窗不会永久消失，也不会重复出现多个。

如果第 2 步显示插件已停用，先手动启用再继续验收。页面内的自动恢复只处理 TMS 重绘移除浮窗的情况，不能恢复被浏览器禁用的扩展。

## 5. 地址变更

如果 Mac mini IP 或端口变化，有两种方式：

- 重新运行打包脚本，发新版插件目录给同事。
- 让同事点击插件图标，在设置里手动填写新的服务地址，然后刷新 TMS 页面。
