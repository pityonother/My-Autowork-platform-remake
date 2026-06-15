# UFO 模块业务与实现总览（给 Pro 评估）

生成日期：2026-05-22

## 1. 项目业务背景

这个项目是本地运行的业务工具集合，重构后用 FastAPI + Jinja 模板组织多个模块。当前重点是 `UFO mail` 模块：用户选择问题单、收发件人、附件和 UFO 编号后，系统生成可用 Outlook 打开的 `.eml` 邮件。

UFO 业务里的关键附件通常是原始 RH 入仓文件。实际操作目标不是只发原始 RH 文件，而是生成一个新的 UFO PDF：

1. 保留原始文件页面内容。
2. 将第一页 POD 上的 RH 编号替换成人工输入的 UFO 编号。
3. 将后续内容页里的 RH 标签自动遮盖。
4. 把处理后的新 PDF 作为最终 `.eml` 附件。

## 2. 本轮已经实现的能力

### 2.1 UFO 邮件原有能力

- 管理 UFO 问题单模板。
- 保存收件人、抄送人、发件人设置。
- 导入并复用邮件签名。
- 用户上传附件后生成 `.eml` 文件。

### 2.2 新增 RH/UFO PDF 自动处理流程

入口仍然是原来的 UFO 邮件生成页面：`/modules/ufo-mail`。

用户流程：

1. 用户选择问题单。
2. 用户手工输入 UFO 编号，例如 `UFO26052201`。
3. 用户上传 TIF/PDF 和其他照片附件。
4. 点击生成 `.eml`。
5. 系统先处理 TIF/PDF，再把新 PDF 放进 `.eml`。

后端处理流程：

1. 上传文件先保存到 `runtime/uploads/<session_id>/`。
2. 对 `.pdf`、`.tif`、`.tiff` 附件执行 UFO 遮盖处理。
3. 如果同批上传同时存在 PDF 和 TIF，当前逻辑优先使用 PDF，跳过 TIF。
4. 第一页使用 POD 定位规则替换 RH 编号：
   - 优先读取 PDF 文字层里的 RH 编号。
   - 如果没有文字层，使用图像锚点定位：左侧 QR、右上条形码。
   - 如果锚点识别失败，使用归一化比例坐标兜底。
5. 第 2 页以后使用 YOLO 模型检测 RH 标签：
   - `conf >= 0.70`：自动遮盖。
   - `0.50 <= conf < 0.70`：生成复核报告，并阻止邮件生成。
   - `conf < 0.50`：忽略。
6. 对检测框做合并、扩边，并采样周围背景色遮盖。
7. 重新合成为 UFO PDF。
8. 原 UFO 邮件模块把处理后的 PDF 和其他附件一起写入 `.eml`。

### 2.3 缓存清理

UFO 页面新增“清理输出缓存”按钮，只清理 `runtime/outputs/` 下的输出缓存，用于删除旧 `.eml`、处理后的 PDF、预览 PNG 和报告文件，避免长时间使用后输出目录堆积。

## 3. 关键代码位置

- UFO 页面路由：`app/modules/ufo_mail/routes.py`
- UFO 邮件生成服务：`app/modules/ufo_mail/service.py`
- RH/UFO PDF 处理器：`app/modules/ufo_mail/cover_processor.py`
- UFO 页面模板：`templates/ufo_mail.html`
- UFO 页面样式：`static/modules/ufo_mail/styles.css`
- UFO 原邮件/问题单存储适配：`ufo_mail_store.py`
- YOLO 训练/数据工具：`tools/ufo_prepare_yolo_dataset.py`、`tools/ufo_export_training_pages.py`
- YOLO 模型交接文档：`docs/ufo_yolo_training_handover.md`

## 4. 模型与依赖

已纳入 Git 和评估包的模型文件：

`app/modules/ufo_mail/models/ufo_rh_sticker_final_20260521.pt`

兼容旧本机开发目录：

`runtime/yolo_runs/ufo_rh_sticker_final_20260521/weights/best.pt`

跨平台运行配置：

- `UFO_YOLO_MODEL`：可选。指定自定义模型路径；不设置时使用随代码提交的模型文件。
- `UFO_YOLO_DEVICE`：可选。默认 `auto`，交给 ultralytics 自动选择；Windows 可按需要设为 `cpu` 或 `0`，Mac mini 可按需要设为 `cpu` 或 `mps`。

当前项目不打包环境目录。主 Web 环境依赖见：

`requirements.txt`

YOLO/RH 遮盖运行环境依赖参考：

`requirements-yolo.txt`

当前代码会优先尝试使用项目根目录下的 `.venv-yolo`，找不到时回退到当前 Python。给 Pro 评估时需要注意：评估包不包含 `.venv-yolo`，需要按目标机器重新安装 YOLO 运行依赖。

## 5. 输出与隐私边界

运行时目录说明：

- `runtime/uploads/`：用户上传的临时附件。
- `runtime/outputs/`：生成的 `.eml`、处理后 PDF、预览 PNG、报告文件。
- `runtime/ufo_mail.db`：本地 UFO 模板、收发件人和签名配置数据库。

本评估包默认不包含：

- `.venv/`
- `.venv-yolo/`
- `runtime/uploads/`
- `runtime/outputs/`
- `runtime/*.db`
- 训练数据集、debug 输出、真实业务附件

这样做是为了避免把环境、缓存和真实业务数据一起交给外部评估。

## 6. 已验证内容

自动化验证：

```powershell
.\.venv\Scripts\python.exe -m py_compile app\modules\ufo_mail\service.py app\modules\ufo_mail\cover_processor.py app\modules\ufo_mail\routes.py
.\.venv\Scripts\python.exe -m pytest -q
```

当前结果：

- UFO 单元测试：`13 passed`
- 全量测试：`65 passed`

样本验证：

- 用用户提供的 TIF/PDF 样本跑过 PDF 优先逻辑。
- 用 `RH2603633.pdf` 这种整体偏歪的 POD 样本调整过第一页“入仓单号”定位，避免旧 RH 前缀残留。
- 用条形码下方 RH 样本调整过右上区域遮盖范围。

## 7. Pro 重点评估建议

1. 审查 `cover_processor.py` 的第一页 POD 定位策略是否足够稳定。
2. 审查 PDF/TIF 同批上传时“有 PDF 就跳过 TIF”的业务假设；如果未来允许多份不同 RH 文档同批上传，建议改为按文件名/页数/业务编号做成对判断。
3. 审查 `0.50 - 0.70` 复核清单的产品形态；当前是阻止生成并给 CSV 报告，后续可以做成页面复核入口。
4. 审查 main env 与 YOLO env 的依赖分离方式；当前采用 `.venv` + `.venv-yolo` 双环境，适合本地工具，但打包成 exe 前需要明确模型和 YOLO 依赖的分发方式。
5. 检查旧模块源码中历史中文默认文案是否存在编码显示问题；当前运行配置主要来自本地 DB，同步过用户的实际模板，但源码默认值建议后续统一清理编码。

## 8. 快速运行参考

主 Web 服务可用以下方式运行：

```powershell
.\.venv\Scripts\python.exe packaged_app.py
```

或者：

```powershell
.\.venv\Scripts\python.exe -m uvicorn reconcile_web_app:app --host 127.0.0.1 --port 8010
```

UFO 页面：

`http://127.0.0.1:8010/modules/ufo-mail`
