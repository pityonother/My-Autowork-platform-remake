# Booking Form 生成器 · 开发需求说明

> 目标：在现有 FastAPI + Jinja2 项目里**新增一个独立模块**，与 `做账单 / 香港进口清关 / 香港出口清关 / 财务记录 / UFO 邮件生成器 / 派送邮件生成器` **同级并列**（一起出现在首页 `index.html` 的模块卡片里）。
>
> 输入：客户发来的一份 `*_CCIXLS.xls`（我方各供应商命名规则不同，首批要支持 **SIL 供应商**）。
> 输出：填好的 `booking_template_zh.xlsx`（每行一笔料号，附若干固定常量列）。
> 中间帮我做：按供应商规则读取源 Excel、清洗字段（含科学计数法）、去重、按模板列映射写入，超出模板原有行数时**自动追加同格式的行**。
>
> **架构必须配置驱动**：SIL 是第一家供应商，后面还会接入别的供应商，各家列名和规则都不同，不要把 SIL 的规则硬编码到主流程里。

---

## 一、模块定位

**这是一个全新的独立模块，不要修改任何现有模块的代码逻辑。** 与 UFO 邮件、派送邮件是平级兄弟模块，只是恰好都做 Excel 填表。

### 1.1 需要新增的文件

| 类型 | 路径 | 作用 |
| --- | --- | --- |
| 新增模板 | `templates/booking.html` | 上传页 + 预览 / 生成 |
| 新增主模块 | `booking_store.py` | 解析、清洗、写回、下载的调度层 |
| 新增规则目录 | `booking_rules/__init__.py` | 供应商规则注册表 |
| 新增规则文件 | `booking_rules/sil.py` | **SIL 供应商**的列映射 + 清洗规则（本次交付） |
| 新增规则文件（占位） | `booking_rules/_template.py` | 提供给未来新供应商复制的空白模板 |
| 新增 sqlite 表（可选） | `booking_sessions` | 如果要记住上次选的供应商 |

### 1.2 只允许动这两个现有文件（只追加、不改既有逻辑）

- `reconcile_web_app.py`：追加 3~4 个新路由 + 1 个 `import booking_store`
- `templates/index.html`：在模块卡片列表**追加 1 张**新卡片

### 1.3 严禁改动

`ufo_mail_store.py`、`templates/ufo_mail.html`、派送邮件模块、做账单模块、清关模块、财务模块等**任何已有代码**。

### 1.4 样式约定

- 复用 `static/styles.css` 里既有的通用类（`.shell.wide / .panel / .topbar / .primary-btn / .secondary-btn / .field / .status-chip / .ufo-dropzone` 等）
- 新增样式一律追加到文件末尾，前缀 `.booking-xxx`
- **不要修改现有 CSS 规则**
- 视觉沿用项目既有米黄 + 橙棕 + 绿主题

### 1.5 首页入口卡片（`templates/index.html` 追加一张）

- 标题：`Booking 生成器`
- 副标题：`CCIXLS → booking form`
- 描述：`上传客户 CCIXLS，自动按供应商规则生成 booking_template_zh 的填好稿。`
- 链接：`/modules/booking`
- 图标字母：`K`（或 `B`，避开已用过的）
- 徽章：`自动填表`

---

## 二、业务背景

- 客户每批货会给我们一个 `*_CCIXLS.xls` 作为数据源
- 我方仓库侧有一份固定模板 `booking_template_zh.xlsx`，每笔料号一行
- 原来靠人工照着源文件逐列抄进模板，容易错位、漏字段、PN 变科学计数法
- 本模块要接管这整个抄写过程，并且把多供应商规则插件化

---

## 三、输入物

### 3.1 客户数据源 `.xls`

- 样本文件：`C:\Users\ac\Desktop\booking data from customer\2604171828_CCIXLS.xls`
- 样本目录（可能不止一份）：`C:\Users\ac\Desktop\booking data from customer`
- 文件命名规律：`{时间戳}_CCIXLS.xls`（"以 CCIXLS 为命名规则"）
- 一份 `.xls` 内含**多个 sheet**：
  - **`detail`**（或名字含 "detail"）：主字段来源
  - **`PACKADCXLS`**（或名字含 "PACKADCXLS"）：`Inv. Ref. No.` 字段来源
  - 其他 sheet 可忽略
- 编码/格式注意：`.xls` 为 **Excel 97-2003 格式**，Python 侧建议用 `xlrd==1.2.0` 读取

### 3.2 Booking 模板 `.xlsx`

- 样本文件：`C:\Users\ac\Desktop\booking data from customer\booking_template_zh (1).xlsx`
- 这是 `.xlsx`，用 `openpyxl` 读写
- 保留模板本身的样式（字体、边框、合并单元格、列宽、数字格式），**不要整张重建**
- 只写入"数据行"区域，表头和固定说明区不要覆盖

### 3.3 用户在 GUI 填的
- **供应商**（下拉，首期只有 "SIL"）
- 上传客户的 `.xls`（单文件）
- 可选的"备注 / 批次标识"（暂未要求，留扩展位即可）

---

## 四、输出物

一份填好的 `booking_template_zh_YYYYMMDDHHMMSS.xlsx`，可下载。

- 模板中原有 N 行数据区：若源数据行数 ≤ N，多余行保持空白
- 若源数据行数 > N：**追加新行**，新行的字体 / 边框 / 对齐 / 数字格式**必须完全复制模板最后一个数据行的样式**（使用 `openpyxl` 的 `copy.copy(cell._style)` 或 `openpyxl.utils.cell` 工具，逐 cell 复制）
- 常量列（单位 / 箱号 / LEDBinCode / 最小包装数 / 每箱标准数）每行都要填

---

## 五、SIL 供应商 · 字段映射规则

> 首期需求交付的规则。实现时必须写进 `booking_rules/sil.py`，不要写进主流程。

### 5.1 主体数据映射（`detail` sheet → booking form 数据行）

| CCIXLS `detail` 列 | booking form 目标列 | 处理 |
| --- | --- | --- |
| `Customer PO` | `订单号` | **值 + `"-0001"` 后缀拼接** |
| `Customer Part Number` | `启益料号` | **强制文本读取**，保留完整数字，避免被 Excel 转成科学计数法 |
| `HS Desc` | `商品名称` | 原样 |
| `Quantity` | `数量` | 数值 |
| `Net Weight` | `净重` | 数值 |
| `Gross Weight` | `毛重` | 数值 |
| `DC` | `生产日期` | **按源表原值原样填入**，不做日期格式转换 |
| `CofO` | `产地 (made in)` | 原样 |
| `Lot #` | `批次` | 原样 |
| `MFR Name` | `品牌` | 原样 |

### 5.2 Inv. Ref. No. 对应（`PACKADCXLS` sheet → booking form 数据行）

- 在 `PACKADCXLS` sheet 里，对 `Inv. Ref. No.` 这一列**按 `Cust P/O`、`Cust Part`、`Quantity` 三列组合去重**
- 去重后保留每组第一个出现的 `Inv. Ref. No.`
- 去重后剩余记录条数**应当等于** `detail` sheet 的 line 条数
  - 若不相等：在 GUI 给出**黄色警告**，但不阻塞生成
- 配对方式：用去重结果里的 `(Cust P/O, Cust Part, Quantity)` 三元组去匹配 `detail` 行的 `(Customer PO, Customer Part Number, Quantity)`
- 配到之后把 `Inv. Ref. No.` 填进 booking form 的 **`发票号`** 列（已确认）

### 5.3 科学计数法处理（关键）

源表里 `Customer Part Number` 和 `Cust Part` 都是长数字（如 `1234567890123`），在 Excel 里显示为 `1.23457E+12`，**肉眼看到的不是真值**。

已确认：**料号不会以 `0` 开头**，所以可以安全地按纯数字处理。

- 用 `xlrd` 读 `.xls` 时，cell type 为 `XL_CELL_NUMBER`，拿到的是 `float`；直接 `int(value)` 再转 `str` 会在极端情况丢精度
- **推荐方案**：`'{:.0f}'.format(value)` 保留整数位全部数字（不会产生前导 0 丢失问题）
- 写入 booking form 时，**目标单元格设置为文本格式**（`cell.number_format = '@'`），以免 `.xlsx` 又把它显示成科学计数法

### 5.4 常量列（每行都一样）

| booking form 目标列 | 固定值 |
| --- | --- |
| `单位` | `PCS` |
| `箱号` | `0` |
| `LEDBinCode` | `无` |
| `最小包装数` | 同该行 `数量` |
| `每箱标准数` | 同该行 `数量` |

---

## 六、多供应商扩展架构

### 6.1 目录结构

```
booking_store.py              # 调度层：读文件 → 调规则 → 写模板 → 打包下载
booking_rules/
    __init__.py               # 规则注册表：SUPPLIER_RULES = {"SIL": sil_rule, ...}
    sil.py                    # 本次交付
    _template.py              # 空白模板文件，未来新增供应商照着复制
```

### 6.2 每个供应商规则文件必须导出一个统一接口

建议签名（具体可由 codex 微调，但要明确"配置驱动"）：

```python
# booking_rules/sil.py

SUPPLIER_NAME = "SIL"

SOURCE_SHEETS = {
    "detail": ["detail"],           # 可写多个候选名，忽略大小写
    "packadc": ["PACKADCXLS"],
}

COLUMN_MAP = {
    # booking form 目标列名 : 源 sheet + 源列名 + 可选清洗函数
    "订单号":      ("detail",  "Customer PO",           "suffix_0001"),
    "启益料号":    ("detail",  "Customer Part Number",  "as_text"),
    "商品名称":    ("detail",  "HS Desc",               None),
    "数量":        ("detail",  "Quantity",              "as_number"),
    "净重":        ("detail",  "Net Weight",            "as_number"),
    "毛重":        ("detail",  "Gross Weight",          "as_number"),
    "生产日期":    ("detail",  "DC",                    None),
    "产地 (made in)": ("detail", "CofO",               None),
    "批次":        ("detail",  "Lot #",                 None),
    "品牌":        ("detail",  "MFR Name",              None),
}

CONSTANTS = {
    "单位": "PCS",
    "箱号": "0",
    "LEDBinCode": "无",
    # "最小包装数" / "每箱标准数" 由调度层在读到"数量"后自动回填
}

# 额外自定义步骤（SIL 的 Inv. Ref. No 去重逻辑）
def post_process(detail_rows, packadc_rows):
    """
    返回一个与 detail_rows 等长的列表，每项是 { "Inv. Ref. No.": str } 之类字段，
    供调度层按顺序写回 booking form 的对应列。
    """
    ...
```

> codex 可以根据需要调整命名/签名，**关键是"SIL 的规则 = 一份数据 + 少量函数"、主流程不写 if supplier == 'SIL'**。

### 6.3 注册新供应商的流程（给未来的人用）

1. 在 `booking_rules/` 下 `cp _template.py newone.py`
2. 填 `SUPPLIER_NAME`、`SOURCE_SHEETS`、`COLUMN_MAP`、`CONSTANTS`、`post_process`
3. `booking_rules/__init__.py` 里把它加入 `SUPPLIER_RULES`
4. 前端下拉会自动出现（路由从 `SUPPLIER_RULES.keys()` 取值）

---

## 七、行数超限时的补行规则

1. 读取 `booking_template_zh.xlsx` 第一张数据 sheet 的"数据行"起止（通过模板里现有的空行 / 表头行判断，或者让规则文件显式写出 `DATA_START_ROW=3, DATA_END_ROW=50` 之类）
2. 假设源数据有 K 行：
   - K ≤ `DATA_END_ROW - DATA_START_ROW + 1` → 正常填，其余留空
   - K 更多 → **往下追加 (K - 可用行) 行**，每行每个单元格：
     - 值 = 来自规则的数据
     - 样式 = `copy.copy(template_row_cell._style)`（`font / fill / border / alignment / number_format / protection` 全部复制）
     - 合并单元格（如果模板某行有合并）也要复制 `merged_cells` 范围
3. 底部若有"合计行 / 说明行"（看样本确认），追加行要插入到它之前，不要覆盖

---

## 八、GUI 流程

极简单页：

1. 顶栏：标题 / 说明 / 返回首页按钮（样式仿 UFO 邮件页）
2. 表单区：
   - 供应商下拉（首期只 `SIL`）
   - 上传客户 `.xls`（dropzone，单文件，`required`）
   - 「预览」按钮
3. 预览结果区（POST 回同一页）：
   - 顶部小结：识别到的 detail 行数 / 去重后 packadc 行数 / 是否相等
   - 表格：把即将写入 booking form 的行（全部列）列出来给人工眼看
   - 如有警告（数量不一致 / 某字段为空 / 某料号 PN 疑似被截断），顶部显示黄色 `.ufo-alert` 风格横幅
   - 「生成并下载 .xlsx」按钮
4. 错误路径：如解析失败 / sheet 缺失 / 必须列缺失 → 红色横幅，保留表单让用户重传

> 单步完成即可，无需像派送邮件那样两步走，因为没有需要人工补充的业务字段。

---

## 九、边界与异常

| 情况 | 行为 |
| --- | --- |
| 上传的不是 `.xls` 或名字里不含 `CCIXLS` | 只做提示不阻塞 |
| `detail` sheet 缺失 | 红色报错，终止 |
| `PACKADCXLS` sheet 缺失 | 黄色警告，`Inv. Ref. No.` 列留空继续生成 |
| `detail` 列名大小写不一致 / 前后空格 | 自动 `strip().lower()` 比对，能匹配就用 |
| `detail` 某必需列缺失 | 红色报错并列出缺失项 |
| 去重后 packadc 行数 ≠ detail 行数 | 黄色警告，只把能对上的填进去，对不上的那几行 `Inv. Ref. No.` 留空 |
| 长 PN 在 Excel 里呈科学计数法 | 按 §5.3 处理 |
| 某行 `数量` 为空或 0 | 黄色警告，常量列仍按规则填，`最小包装数/每箱标准数` 也随之为 0 |
| 源文件有 10000+ 行 | 不做特殊处理，`openpyxl` 吃得下 |
| 模板数据行数用完 | 按 §7 追加 |

---

## 十、技术建议

- Web 框架：FastAPI + Jinja2（与现有项目一致）
- 读 `.xls`：`xlrd==1.2.0`（新版去了 xlsx 支持但仍支持 xls）
- 读/写 `.xlsx`：`openpyxl`
- 去重：`pandas.DataFrame.drop_duplicates(subset=[...], keep='first')` 省事；或纯 `dict` 手写
- 样式复制：`copy.copy(cell._style)` 搭配 `openpyxl.utils` 的合并单元格 API
- 会话：输出文件放 `runtime/outputs/booking_{session_id}.xlsx`
- 持久化（可选）：如果要记住"上次选的供应商" / "上次上传文件名"，用 sqlite 表 `booking_sessions`
- 不引入 React / Vue，不引入 pandas 也可以（只是用来简化去重），避免再增依赖可行

---

## 十一、参考样本（必读）

> 开发前请务必打开看一遍真实样本：

| 用途 | 路径 |
| --- | --- |
| 客户 CCIXLS 样本 | `C:\Users\ac\Desktop\booking data from customer\2604171828_CCIXLS.xls` |
| 客户 CCIXLS 目录（多份） | `C:\Users\ac\Desktop\booking data from customer` |
| Booking 模板 | `C:\Users\ac\Desktop\booking data from customer\booking_template_zh (1).xlsx` |

---

## 十二、已确认的关键事项

✅ **已确认**（可直接实现，无需再问）：

- `Inv. Ref. No.` → booking form 的 **`发票号`** 列
- `DC`（生产日期） → **按源表原值原样填入**，不做任何日期格式转换
- 料号 `Customer Part Number` / `Cust Part` **不会以 `0` 开头**，可以用 `'{:.0f}'.format(value)` 安全转字符串
- `detail` 与 `PACKADCXLS` 是**同一份** `.xls` 里的两个 sheet

⚠️ **动手前建议再确认**（不影响大体实现，但会影响细节）：

1. **booking 模板数据区起止行** 固定吗？如果固定，能否把 `DATA_START_ROW / DATA_END_ROW` 写死进 `sil.py`？（codex 打开样本模板自测一下就能知道）
2. **追加行时底部是否有"合计 / 签字"等保留行** 要避开？（codex 看样本即可判断，必要时再回问）
3. **`HS Desc` / `MFR Name` 等文本列是否可能含换行或制表符**？若有，保留原格式即可

---

## 十三、交付检查清单（开发完成时自查）

- [ ] `/modules/booking` 路由可访问，首页卡片点击能跳转
- [ ] 能正确读取样本 `2604171828_CCIXLS.xls` 的 `detail` + `PACKADCXLS` 两个 sheet
- [ ] `detail` 所有行按 §5.1 映射写入模板，肉眼 diff 无错位
- [ ] 长 PN（`Customer Part Number` / `Cust Part`）在生成的 `.xlsx` 里**以文本完整显示**，不出现 `E+` 科学计数法
- [ ] `PACKADCXLS` 按 `(Cust P/O, Cust Part, Quantity)` 去重后的 `Inv. Ref. No.` 正确填入 booking form 对应行
- [ ] `单位=PCS / 箱号=0 / LEDBinCode=无 / 最小包装数=数量 / 每箱标准数=数量` 每行都对
- [ ] 人为构造行数超过模板的测试文件，追加行样式与上方行**完全一致**（字体 / 边框 / 数字格式）
- [ ] 模板本身的表头、合并单元格、列宽 **未被破坏**
- [ ] `booking_rules/sil.py` 独立成文件，主流程不含 `"SIL"` 字面量，新增 `_template.py` 可作为未来供应商起步
- [ ] 不触碰 UFO 邮件、派送邮件、做账单等任何现有模块代码
