# 项目交接文档

## 1. 项目概览

本项目是一套围绕日常物流/账单/清关/邮件工作的桌面化业务工具，当前以 `FastAPI + Jinja2 + 本地 SQLite + Excel/EML 解析` 为核心。

项目目标不是做一个通用 SaaS，而是持续沉淀为“贴合当前业务口径”的本地工作台，帮助完成以下高频任务：

- 账单总表自动回填与校验
- 香港进口清关 bill 模板回填
- 香港出口清关记录管理、排序与导出
- 财务记录导入、筛选与导出
- Booking 生成
- 派送邮件生成
- UFO 邮件签名/模板记忆

当前项目已经从“单点脚本”演变成“多模块工作台”。

---

## 2. 当前技术架构

### 2.1 后端

- Web 框架：`FastAPI`
- 模板渲染：`Jinja2`
- 运行入口：`reconcile_web_app.py`
- exe 启动入口：`packaged_app.py`
- 本地运行目录管理：`app_paths.py`

### 2.2 数据存储

当前主要依赖本地 SQLite 和 JSON 文件：

- `runtime/finance_records.db`
- `runtime/export_clearance.db`
- `runtime/dispatch_mail.db`
- `runtime/ufo_mail.db`

### 2.3 前端

- 服务端模板：`templates/*.html`
- 样式文件：`static/styles.css`
- 目前无前后端分离
- 页面交互以原生 JS 为主

### 2.4 打包

- 打包脚本：`build_exe.bat`
- PyInstaller spec：`BillClearanceTool.spec`
- 生成 exe 目录：`dist/BillClearanceTool/`

---

## 3. 核心模块说明

### 3.1 首页工作台

文件：

- `reconcile_web_app.py`
- `templates/index.html`
- `static/styles.css`

作用：

- 作为模块入口页
- 当前已接入账单、香港进口清关、香港出口清关、财务、Booking、派送邮件、UFO 邮件模块

### 3.2 账单模块

核心文件：

- `invoice_reconciler.py`
- `templates/billing_import.html`
- `templates/session.html`
- `templates/invoice_detail.html`

已实现能力：

- 导入总表、单页账单、派送单、真实数据源
- 依据 SLI / EXTR / Tan / 费用规则回填总账单
- 多文件批量导入
- 中间态预览
- 单页账单详情核查
- 费用项目汇总与异常提醒
- 板数/箱数拆分规则
- 多种费用名称繁简识别
- Excel 样式/行数适配修正

已沉淀的重要规则示例：

- 进仓费与停车费分拆
- 装卸费按 `63.78/板 + 10/箱` 拆分
- 派送费、机场附加费必须为 `239.16` 整数倍
- 快递费必须为 `30` 整数倍
- 特定费用项必填校验

### 3.3 香港进口清关模块

核心文件：

- `customs_reconciler.py`
- `templates/customs.html`
- `templates/import_customs_import.html`

已实现能力：

- 上传订单管理、真实数据源、bill 模板
- 生成中间态清关数据
- 显示作业时间、无缝号、港车车牌、箱数、PCS、毛重、金额等依据
- bill 第 3 子表回填
- 依据 `UDR no.` 检测模板里已存在正式数据并导出时跳过重复
- 支持模板复制后导出，不直接破坏原模板

### 3.4 香港出口清关模块

核心文件：

- `export_clearance_store.py`
- `templates/export_customs.html`
- `templates/export_customs_batch.html`

已实现能力：

- 导入批次保存
- 待清关/已清关状态管理
- 紧急程度排序
- GUI 状态切换
- 导出 `pending` / `clearance` 结果
- 已清关表格导出格式定制
- 重复记录去重

已实现的关键调整：

- 已清关后 GUI 不再按待办颜色标红
- “优先级”列对于已清关显示为“已清关”
- `全部已清关` 子表增加 `出货时间`
- `板数/箱数` 展示为 `3板/225箱`

### 3.5 财务模块

核心文件：

- `finance_store.py`
- `templates/finance_records.html`
- `templates/finance_batch.html`

已实现能力：

- 支出/付款记录导入
- 批次概念保留
- 记录筛查与导出
- SO/客户信息补录
- 导入判重
- 导出按筛选条件为准，而非历史导出状态强绑定

当前业务特点：

- 用户会多次重复导入相似 payment 数据
- 导入后需要清楚区分“新增/重复/跳过/补录更新”

### 3.6 Booking 模块

核心文件：

- `booking_store.py`
- `booking_rules/sil.py`
- `templates/booking.html`

已实现能力：

- 从客户 `.eml` 读取附件
- 解析 `INV / PACK` 数据
- 按供应商规则生成 booking 数据
- 特定 `PO 前缀 -> 采购方` 映射
- `MAWB#` 提取
- 首行箱数/体积特殊规则
- 批次号为空自动补 `0`
- `Box#` 统计箱数
- 体积按 `箱数 * 0.01`
- 富文本仓库邮件模板生成

当前已落地的供应商规则：

- 目前重点完成的是 `SIL-FUCA`
- 规则文件位于：`booking_rules/sil.py`

### 3.7 派送邮件模块

核心文件：

- `dispatch_mail_store.py`
- `templates/dispatch_mail.html`
- `templates/dispatch_mail_preview.html`
- `templates/dispatch_mail_compose.html`
- `templates/dispatch_attachment_preview.html`

已实现能力：

- 导入客户原始 `.eml`
- 自动抽取 Tan 总表、DQT 装箱单、交仓文件
- 总表截图预览
- DQT / 交仓文件匹配
- 按规则重命名
- 邮件 To/Cc/From 记忆
- 邮件正文实时预览
- 截图嵌入 HTML 邮件正文
- 导出 `.eml`

最近新增：

- 第二步“仓库地址与注意事项”页面可直接看到每票绑定的 DQT 与交仓文件引用
- 自动命名状态下优先显示规则命名，而不是误保留原文件名

### 3.8 UFO 邮件模块

核心文件：

- `ufo_mail_store.py`
- `templates/ufo_mail.html`

已实现能力：

- EML 签名导入
- 支持富文本签名
- 支持内联图片 / 艺术字图片
- 签名开始标记识别
- 签名内容本地记忆

---

## 4. 关键目录说明

### 4.1 代码目录

- `reconcile_web_app.py`：主路由与页面组织
- `invoice_reconciler.py`：账单规则主逻辑
- `customs_reconciler.py`：进口清关逻辑
- `export_clearance_store.py`：出口清关逻辑
- `finance_store.py`：财务模块逻辑
- `booking_store.py`：Booking 解析与邮件生成
- `dispatch_mail_store.py`：派送邮件解析、匹配、生成
- `ufo_mail_store.py`：UFO 邮件模块

### 4.2 运行时目录

- `runtime/outputs`：导出结果
- `runtime/uploads`：上传缓存
- `runtime/booking_sil_fuca_warehouse_template`：SIL-FUCA 仓库邮件富文本模板
- `runtime/ufo_signature`：UFO 签名模板/资源

说明：

- `runtime/uploads`、调试图片、临时输出可周期性清理
- `runtime/*.db`、签名模板、仓库邮件模板不应随意删除

---

## 5. 项目迄今为止最重要的经验总结

### 5.1 经验一：业务自动化不是“抽象建模优先”，而是“样本驱动优先”

这套系统真正推进最快的时候，不是先设计抽象架构，而是直接拿真实账单、派送单、订单管理、客户邮件、仓库邮件样本往里打。

结论：

- 真实样本比口头描述更重要
- 文件命名、Excel 结构、费用名称、人工备注里藏着大量隐性规则
- 很多规则只有见到异常样本才会暴露

### 5.2 经验二：中间态预览比“全自动”更重要

用户真正需要的不是一个黑盒自动填表器，而是：

- 能自动做 70%-90%
- 剩下 10%-30% 可以被看见、被校验、被人工修正

所以项目里大量加入了：

- 预览表
- 匹配截图
- 单页详情
- 文件引用
- 状态提醒

这是正确方向。

### 5.3 经验三：规则经常变化，必须接受“规则是产品的一部分”

例如：

- 费用映射口径变更
- 机场附加费繁简并存
- 供应商映射按 `PO 前缀` 调整
- 交仓文件命名规则动态变化

说明这不是“一次开发完就稳定”的项目，而是业务规则会持续演进的工具。

### 5.4 经验四：Excel/EML 解析最难的不是读文件，而是识别“真正有用的主体区域”

典型难点：

- 表头不固定
- 附件命名不统一
- 同一字段繁简混写
- 主体表格外有噪音内容
- 同一种文件不同月份结构轻微变化

所以解析层要尽量做：

- 模糊列识别
- 多关键字兜底
- 多格式兼容
- 不依赖单一文件名

### 5.5 经验五：本地记忆配置非常有价值

例如：

- UFO 签名模板记忆
- 派送邮件收件人记忆
- SIL-FUCA 仓库邮件富文本模板记忆

这类“只设置一次，之后反复复用”的功能，实际节省时间很多。

---

## 6. 当前项目存在的主要技术债

### 6.1 编码/乱码问题仍然存在历史包袱

当前部分模板和 Python 源码里仍可见历史乱码痕迹，尤其是早期经过不同编码环境反复修改的文件。

影响：

- 某些文案可能出现问号或乱码
- 后续 patch 修改容易命中失败

建议：

- 全项目统一改为 `UTF-8`
- 对关键模板和核心 Python 文件做一次编码清洗

重点文件：

- `dispatch_mail_store.py`
- `templates/dispatch_mail_preview.html`
- `templates/dispatch_mail_compose.html`
- `packaged_app.py`

### 6.2 规则仍然过多写死在代码里

目前许多业务规则直接写在 Python 中。

风险：

- 每次改规则都要改代码
- 难以让业务人员自助调整

建议：

- 将高频规则逐步外置到 JSON / YAML / Excel 配置表
- 至少先外置：
  - `费用名称映射`
  - `供应商/PO 前缀映射`
  - `费用倍数校验规则`
  - `邮件模板常量`

### 6.3 模块边界已有雏形，但还不够彻底

目前虽然按功能拆到了多个 store/reconciler，但 `reconcile_web_app.py` 仍然较大。

建议：

- 按模块拆路由
- 把页面路由从主文件继续分离
- 让每个模块有更清晰的输入/输出模型

### 6.4 缺少系统化测试

当前验证方式仍以“真实样本手测”为主。

风险：

- 修一个模块容易影响另一个模块
- 打包后行为不一定与开发环境完全一致

建议：

- 最低限度补充：
  - 解析测试
  - 命名规则测试
  - 判重测试
  - 导出模板结构测试

### 6.5 运行缓存清理机制不完善

项目会产生：

- `runtime/uploads`
- `runtime/outputs`
- 调试图片/临时附件

建议：

- 增加“清理缓存”按钮
- 或者增加“保留最近 N 天输出”的自动清理策略

---

## 7. 后续建议改进方向

### 7.1 第一优先级：规则配置化

目标：

- 降低每次改规则都要改代码的成本

建议落地顺序：

1. 先配置化 Booking `PO 前缀 -> 采购方`
2. 再配置化账单费用映射
3. 再配置化清关字段映射和校验常量

### 7.2 第二优先级：编码治理

目标：

- 消灭乱码
- 降低后续维护成本

建议：

- 对关键模板、关键 Python 文件统一转成 UTF-8
- 逐个页面修正文案

### 7.3 第三优先级：前端交互一致性

当前项目已有几种风格：

- 较新卡片式工作台风格
- 较旧朴素模板页

建议：

- 统一模块页头、卡片、按钮、提示框、状态芯片样式
- 统一“导入 -> 预览 -> 编辑 -> 导出”流程体验

### 7.4 第四优先级：补测试样本库

建议建立一个仅内部使用的样本目录规范：

- `samples/billing/`
- `samples/customs_import/`
- `samples/customs_export/`
- `samples/finance/`
- `samples/booking/`
- `samples/dispatch_mail/`

并保留：

- 正常样本
- 异常样本
- 特殊命名样本

### 7.5 第五优先级：日志与诊断

建议给关键模块加入更明确的诊断信息，例如：

- 某个附件为何被识别成交仓文件
- 某个记录为何被判重
- 某个导出行为为何跳过

这样以后排查比“看结果猜原因”轻松得多。

---

## 8. 运行与维护说明

### 8.1 开发环境启动

项目目录：

- `C:\Users\ac\Documents\New project 2`

常规启动方式：

- 运行 `run_reconcile_web.bat`
- 或用 `.venv` 执行 `uvicorn`

### 8.2 exe 启动

入口：

- `packaged_app.py`

行为：

- 自动寻找可用端口
- 启动本地 Web 服务
- 自动打开浏览器

### 8.3 打包

打包脚本：

- `build_exe.bat`

当前打包会带上：

- `templates`
- `static`
- `sample_price.xlsx`
- `booking_template_zh.xlsx`
- `runtime/*.db`
- `runtime/ufo_signature`
- `runtime/booking_sil_fuca_warehouse_template`

输出目录：

- `dist/BillClearanceTool/`

### 8.4 备份建议

建议至少保留三类备份：

- 源码备份
- exe 发布包备份
- runtime 数据备份

尤其注意：

- 数据库
- 签名模板
- 仓库邮件模板

---

## 9. 当前最值得注意的风险点

### 9.1 派送邮件模块仍在快速演化

这是最近改动最频繁的模块之一，页面和命名逻辑都在持续调整。

建议：

- 每次改完都重新上传真实 `.eml` 全流程测试

### 9.2 Booking 与仓库邮件模板依赖真实业务样本

如果后续客户邮件附件命名、结构再变化，可能需要继续补规则。

### 9.3 财务模块的“重复导入即正常场景”必须保留

财务导入不应以“只导一次”为前提。

未来任何改动都要尊重这一点。

### 9.4 进口清关导出与模板已有内容的去重逻辑不能回退

当前已经根据 `UDR no.` 做了模板内已有正式数据检测，后续修改不能误删这层保护。

---

## 10. 接手建议

如果后续由新的开发者继续维护，建议按这个顺序接手：

1. 先通读本交接文档
2. 运行本地项目，逐个模块点一遍
3. 重点看以下文件：
   - `reconcile_web_app.py`
   - `invoice_reconciler.py`
   - `customs_reconciler.py`
   - `export_clearance_store.py`
   - `finance_store.py`
   - `booking_store.py`
   - `dispatch_mail_store.py`
4. 先处理编码和文案清洗
5. 再处理规则配置化
6. 最后补自动化测试

不建议一上来就大重构。

更适合的方式是：

- 一边维护功能
- 一边把最稳定的规则抽离
- 一边补样本和测试

---

## 11. 结论

这套项目已经具备明确业务价值，且已经形成可持续扩展的工作台雏形。

它最成功的地方有三点：

- 非常贴近真实工作流
- 愿意保留中间态给人工核查
- 能把“经验型口径”逐步沉淀进工具

它后续最重要的三件事也很明确：

- 规则配置化
- 编码治理
- 测试与样本体系化

只要继续沿着这个方向推进，这个项目完全可以从“个人高效工具”继续成长为“部门级业务操作台”。
