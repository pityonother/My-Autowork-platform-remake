# Booking Form 质检助手 Edge 插件

这个插件只做一件事：在公司 TMS 页面右下角显示一个 Booking 质检入口。选择 `.xlsx` booking form 后，点击“上传并打开筛查结果”，插件会把文件提交到 Mac mini 上的 Booking Web 服务，并在新标签页打开筛查结果。

## 安装

1. 打开 Edge 的 `edge://extensions/`。
2. 打开“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择本目录：`browser_extensions/booking_tms_checker`。

## 配置 Mac mini 地址

点击浏览器工具栏里的插件图标，填写 Mac mini 内网地址，例如：

```text
https://192.168.10.205
```

本地开发默认值是：

```text
https://192.168.10.205
```

给同事部署时不要手工改源码，使用打包脚本生成带默认服务地址的版本：

```powershell
python tools\build_booking_tms_checker_extension.py --server-base https://192.168.10.205
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

## 设计边界

- 插件不保存 booking form。
- 插件不做业务规则判断。
- 插件不直接访问 SIL-FUCA 周期接口。
- 所有筛查、修正建议、周期匹配、导出修正版，都由 Mac mini 后端完成。

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
