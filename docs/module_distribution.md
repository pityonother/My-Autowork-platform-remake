# 模块化分发说明

## 这个方案解决什么问题

以前给同事更新工具，容易变成“整个项目复制过去、整个目录覆盖”。这样有两个风险：

- 发布包可能带上维护者本机的 `runtime/*.db`、上传文件、输出文件。
- 同事更新时如果手动覆盖 `runtime/`，自己的数据库和生成结果可能被覆盖。

现在改成：

- 同事电脑只保留一个 `LauncherTool`。
- 每个业务模块都是独立 exe 包。
- Launcher 负责看远端 manifest、下载 zip、校验 hash、安装或更新模块。
- 每个模块的数据目录由 Launcher 单独指定，不跟模块程序目录混在一起。

## 同事电脑上只需要保留 Launcher

同事第一次拿到 `LauncherTool` 后，只需要打开 Launcher。

Launcher 首页会显示：

- 模块名称
- 未安装 / 已安装
- 本地版本
- 远端最新版本
- 可安装 / 可更新 / 已最新 / 下载失败 / 校验失败
- 安装、更新、打开、重试按钮

业务处理仍然在各模块自己的本地 FastAPI 页面里完成。Launcher 不承载账单、清关、财务或邮件解析业务路由。

## 用户数据保存在哪里

Launcher 启动模块时会给子进程设置：

```text
BILL_TOOL_RUNTIME_DIR=<Launcher目录>/runtime/module_data/<module_id>
```

例如：

```text
LauncherTool/runtime/module_data/finance/
LauncherTool/runtime/module_data/export_clearance/
LauncherTool/runtime/module_data/ufo_mail/
```

模块自己的 exe 会安装在：

```text
LauncherTool/runtime/modules/<module_id>/current/
```

所以更新模块时替换的是程序目录，不会覆盖：

- 数据库
- 上传文件
- 输出文件
- 邮件草稿
- 模块设置

如果没有 `BILL_TOOL_RUNTIME_DIR`，旧行为仍然保留：程序会继续使用 exe 或项目旁边的 `runtime/`。

## 维护者如何发布新版本

1. 修改代码。
2. 跑检查：

```bat
python -m tools.dev_check
```

3. 构建发布目录：

```bat
build_release.bat
```

也可以手动指定版本号：

```bat
build_release.bat 2026.05.27+abcdef1
```

4. 把生成的 `release_site/` 上传到静态位置。
5. 同事打开 Launcher，点击“刷新远端版本”，再点对应模块的“安装”或“更新”。

`release_site/` 会包含：

```text
release_site/manifest.json
release_site/launcher/LauncherTool-<version>.zip
release_site/modules/<module_id>/<ModuleTool>-<version>.zip
```

发布包不能包含 `runtime/`。

## 如何配置 update_config.json

Launcher 会优先读取环境变量：

```text
BILL_TOOL_MANIFEST_URL
```

如果没有这个环境变量，就读取 Launcher 旁边的：

```text
update_config.json
```

内容格式：

```json
{
  "manifest_url": "https://example.com/release_site/manifest.json"
}
```

也可以在 Launcher 页面里填写并保存更新地址。

## 用 file:// 共享目录做小团队分发

如果不想上公网，可以把 `release_site/` 放到共享盘、NAS、OneDrive 或 SharePoint 同步目录。

示例：

```text
file:///C:/Shared/release_site/manifest.json
file://///SERVER/Share/release_site/manifest.json
```

只要同事电脑能访问这个 manifest 地址，Launcher 就能下载对应 zip。

manifest 里的 artifact 可以是相对路径，例如：

```json
"artifact": "modules/billing/BillingTool-2026.05.27+abcdef1.zip"
```

也可以是完整的 `https://`、`http://` 或 `file://` 地址。

## 常见问题

### 下载失败

通常是 manifest 地址错、网络断开、共享目录没权限，或 artifact 路径不存在。

处理方法：

- 在 Launcher 页面确认 `manifest_url`。
- 用浏览器或资源管理器打开 manifest 地址。
- 确认 `release_site/modules/...zip` 文件存在。

### hash 校验失败

Launcher 会删除坏 zip，并提示“校验失败，已保留原版本”。

处理方法：

- 重新上传完整的 zip。
- 确认 `manifest.json` 是本次构建生成的，不要手改 sha256。

### 模块正在运行无法更新

如果模块进程还在运行，Launcher 会拒绝更新并提示：

```text
请先关闭该模块后再更新。
```

关闭模块自己的黑色窗口后，再点击更新。

### 更新后想回退

每次更新会把旧版本保存在：

```text
LauncherTool/runtime/modules/<module_id>/previous/
```

需要手动回退时：

1. 关闭该模块。
2. 把 `current/` 改名为 `current_bad/`。
3. 把 `previous/` 改名为 `current/`。
4. 再从 Launcher 打开模块。

用户数据在 `runtime/module_data/<module_id>/`，不需要移动。

### 找不到 manifest

检查：

- `update_config.json` 是否在 Launcher 旁边。
- `manifest_url` 是否是完整地址。
- `file://` 路径是否能在同事电脑上访问。
- 如果设置了 `BILL_TOOL_MANIFEST_URL`，它会覆盖 `update_config.json`。

### runtime 数据在哪里

Launcher 模式下：

```text
LauncherTool/runtime/module_data/<module_id>/
```

旧的全量 exe 或开发模式下：

```text
项目目录/runtime/
```

## 重要提醒

不要把 `runtime/` 打进发布包。

不要让同事手动覆盖 `runtime/`。

不要把维护者本机的 `.db`、上传文件、输出文件发给同事。

正式发布只分发 `LauncherTool` 和 `release_site/` 里的模块 zip。
