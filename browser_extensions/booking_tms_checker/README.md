# Booking Form 质检助手 Edge 插件

这个插件只做一件事：在公司 TMS 页面右下角显示一个 Booking 质检入口。选择 `.xlsx` booking form 后，点击“上传并打开筛查结果”，插件会把文件提交到 Mac mini 上的 Booking Web 服务，并在新标签页打开筛查结果。

## 安装

1. 打开 Edge 的 `edge://extensions/`。
2. 打开“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择本目录：`browser_extensions/booking_tms_checker`。

> 这是“加载解压缩的扩展”，必须在 `edge://extensions/` 中保持“已启用”。如果 Edge 或公司的浏览器策略把它停用，插件代码无法绕过 Edge 的停用，也不能自行修改浏览器策略；需要手动重新启用，或由 IT 另行部署受管扩展。
>
> Edge 会记住所选文件夹的绝对路径。安装后请长期保留该文件夹，不要移动、重命名或删除；更新时在原文件夹覆盖后点击“重新加载”。

## 配置 Mac mini 地址

点击浏览器工具栏里的插件图标，填写 Mac mini 内网地址，例如：

```text
https://<Mac-mini-IP>:8010
```

源码里的本地开发默认值是：

```text
https://127.0.0.1:8010
```

给同事部署时不要手工改源码，使用打包脚本生成带默认服务地址的版本：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://<Mac-mini-IP>:8010
```

详细步骤见 `DEPLOYMENT.md`。

## 使用

1. 打开公司 TMS 页面：

```text
http://www.clztoud.com:8008/SupplierInquiry/index.html
https://smooth.clztoud.com/Home/AdminDefault
```

2. 页面右下角会出现“Booking 质检”浮窗。
3. 点击“选择 booking form 并筛查”。
4. 选择供应商填好的 `.xlsx` booking form。
5. 点击“上传并打开筛查结果”。
6. 插件会在新标签页打开 Mac mini 的筛查结果页。

浮窗默认保持展开。点击标题栏右侧的 `−` 只会收起内容，并保留可见的展开入口；TMS 的 SPA/DOM 重绘如果移除了浮窗节点，插件会自动恢复它，不使用定时轮询。

## 重启验收

1. 重启电脑，或完全退出所有 Edge 窗口后重新打开 Edge。
2. 打开 `edge://extensions/`，确认“Booking Form 质检助手”仍保持“已启用”，且没有加载错误。
3. 打开匹配的 SMOOTH TMS 页面，确认右下角默认出现展开的“Booking 质检”浮窗。
4. 在 TMS 内切换页面或触发页面重绘，确认浮窗仍在；若页面曾移除它，应自动恢复且不出现重复浮窗。

如果第 2 步显示插件已被 Edge 停用，应先手动重新启用再继续。代码无法绕过 Edge 的停用，因此这类情况不能只靠页面脚本修复。

## 设计边界

- 插件不保存 booking form。
- 插件不做业务规则判断。
- 插件不直接访问 SIL-FUCA 周期接口。
- 所有筛查、修正建议、周期匹配、导出修正版，都由 Mac mini 后端完成。
- 插件不会修改 Windows 注册表、Edge 策略或扩展启用状态。

## 权限

当前插件只请求：

```text
storage
```

页面注入范围只限制在：

```text
http://www.clztoud.com:8008/SupplierInquiry/*
https://smooth.clztoud.com/Home/*
```
