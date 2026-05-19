# Codex 后续重构优化任务清单

> 适用项目：`New project 2` 账单/清关/财务/Booking/派送邮件/UFO 本地工作台  
> 生成时间：2026-05-18  
> 目的：让 Codex 在已有重构基础上继续小步优化，而不是重新大改业务逻辑。

---

## 0. 当前重构评价

当前重构方向是对的：项目已经从单文件/少数脚本，拆出了 `app/core`、`app/shared`、`app/web`、`app/modules/*`，主入口 `reconcile_web_app.py` 也已经不再直接挂大量 `@app.get/@app.post` 路由。

但这次重构更像是 **第一阶段架构骨架**，还不是完全的模块化完成态。现在很多新模块仍是对旧大文件的 re-export / adapter，真正的业务逻辑还主要留在这些旧文件里：

| 文件 | 当前规模 | 主要风险 |
|---|---:|---|
| `dispatch_mail_store.py` | 1629 行 | 派送邮件解析、匹配、预览、命名、生成、设置混在一起 |
| `invoice_reconciler.py` | 1562 行 | 账单核心规则复杂，测试覆盖还不够，暂不建议先大拆 |
| `finance_store.py` | 1234 行 | 解析、判重、数据库、导出、状态管理混在一起 |
| `booking_store.py` | 939 行 | 供应商规则、Excel IO、邮件生成仍有耦合 |
| `mail_classifier_store.py` | 870 行 | IMAP、规则分类、数据库、密码处理集中在一个文件 |
| `customs_reconciler.py` | 701 行 | 进口清关仍是旧式核心逻辑 |
| `export_clearance_store.py` | 661 行 | 仓储逻辑、解析逻辑、导出逻辑混合 |
| `ufo_mail_store.py` | 539 行 | 问题库、签名、邮件生成仍可继续拆 |

结论：**架构入口已经变清楚，后续重点应从“继续拆文件”转成“按模块边界迁移真实业务逻辑 + 补测试护栏”。**

---

## 1. 我本次检查到的验证结果

在解压后的项目根目录执行：

```bash
python -m compileall -q app *.py booking_rules tools tests
```

结果：通过。

执行：

```bash
pytest -q
```

结果：`21 passed, 1 failed`。

失败项：

```text
tests/unit/test_architecture_boundaries.py::test_web_app_import_keeps_heavy_libraries_lazy
```

失败表现：测试认为 `pandas` 和 `PIL.Image` 在 `import reconcile_web_app` 后被加载。

进一步检查后，当前运行环境在 Python 启动时就已经通过 `sitecustomize` 预加载了 `pandas` / `PIL.Image`。在记录 baseline 后再 import app，应用本身没有新增加载这些重依赖；用 `python -S` 加载 site-packages 后再导入，`reconcile_web_app` 也没有加载这些重依赖。

所以这个失败更像是 **测试写法没有扣除环境 baseline**，不是应用导入链真的提前加载了重依赖。

另外执行：

```bash
pytest -q -k 'not web_app_import_keeps_heavy_libraries_lazy'
```

结果：`21 passed, 1 deselected`。

---

## 2. Codex 执行总原则

Codex 开始前必须先读：

```text
AGENTS.md
Codex_refactor_optimization_20260518.md
```

本轮后续优化不要一次性做完。建议一轮只做一个任务编号，例如只做 `P0-1`，验证通过后再继续下一个。

每轮固定流程：

```bash
git status --short
python -m compileall -q app *.py booking_rules tools tests
pytest -q
```

如果没有 Git 仓库，先只做只读检查，不要擅自初始化、提交或清理文件。

禁止事项：

- 不要重写整个项目。
- 不要一轮同时改后端、前端、样式、打包和业务规则。
- 不要删除旧 `*_store.py` / `*_reconciler.py` 文件；先保留兼容入口。
- 不要改变 Excel 导出格式、邮件格式、业务命名规则，除非本轮任务明确要求。
- 不要把真实客户样本、真实邮箱、真实账单数据放进测试 fixtures。
- 不要为了“看起来更优雅”改 UI 文案或样式。

---

## 3. 优先级 P0：先稳定测试与显性 bug

### P0-1 修复懒加载测试的环境基线问题

**问题文件：**

```text
tests/unit/test_architecture_boundaries.py
```

**当前问题：**

`test_web_app_import_keeps_heavy_libraries_lazy` 直接检查 import 后的 `sys.modules`，没有先记录 import 前 baseline。在某些环境中，`sitecustomize` 或测试运行器会在应用导入前加载 `pandas` / `PIL.Image`，导致误判。

**建议改法：**

把测试改成“只断言应用导入没有新增加载重依赖”。示例思路：

```python
script = (
    "import sys; "
    f"heavy = {heavy_modules!r}; "
    "baseline = {name for name in heavy if name in sys.modules}; "
    "import reconcile_web_app; "
    "loaded_after = {name for name in heavy if name in sys.modules}; "
    "newly_loaded = sorted(loaded_after - baseline); "
    "print('\\n'.join(newly_loaded)); "
    "raise SystemExit(1 if newly_loaded else 0)"
)
```

**验收标准：**

```bash
pytest -q tests/unit/test_architecture_boundaries.py::test_web_app_import_keeps_heavy_libraries_lazy
pytest -q
```

全部通过。

---

### P0-2 修复财务页面 `batch_id=abc` 导致 500 的问题

**问题文件：**

```text
app/modules/finance/routes.py
```

**当前问题：**

`finance_records_dashboard()` 里直接执行：

```python
normalized_batch_id = int(batch_id) if batch_id.strip() else None
```

如果访问：

```text
/modules/finance-records?batch_id=abc
```

会触发 `ValueError`，当前返回 500。

**建议改法：**

新增一个小的解析函数，非法值返回 400，或者退回 `None` 并在页面展示错误。推荐 400，避免静默吞错。

示例方向：

```python
def parse_optional_int(value: str, field_name: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是数字。") from exc
```

并加测试。

**建议新增测试：**

```text
tests/smoke/test_pages.py
```

增加：

```python
def test_finance_records_rejects_invalid_batch_id() -> None:
    client = TestClient(main_app, raise_server_exceptions=False)
    response = client.get("/modules/finance-records?batch_id=abc")
    assert response.status_code == 400
```

**验收标准：**

```bash
pytest -q tests/smoke/test_pages.py
pytest -q
```

全部通过。

---

### P0-3 固化当前健康检查脚本

**目标：**

给新 Codex 会话一个固定验证入口，避免每次靠口头回忆。

**建议新增文件：**

```text
tools/dev_check.py
```

**功能：**

按顺序执行：

1. `python -m compileall -q app *.py booking_rules tools tests`
2. `pytest -q`

可选：检测当前是否存在 `.git`，如果有则先打印 `git status --short`。

**验收标准：**

```bash
python tools/dev_check.py
```

能返回清晰结果；失败时显示失败命令。

---

## 4. 优先级 P1：把“表面模块化”推进到“真实边界”

### P1-1 路由层不要直接 import 旧 store/reconciler

当前很多 `routes.py` 仍然直接从旧文件拿类型、常量或工具函数。

典型例子：

```text
app/modules/booking/routes.py          -> from booking_store import BookingPreview, available_suppliers
app/modules/dispatch_mail/routes.py    -> from dispatch_mail_store import ... 多个函数和类型
app/modules/finance/routes.py          -> from finance_store import TASK_STATUS_OPTIONS
app/modules/mail_classifier/routes.py  -> from mail_classifier_store import BUSINESS_LABELS / DEFAULT_* / STATUS_LABELS
app/modules/ufo_mail/routes.py         -> from ufo_mail_store import UfoIssueInput
```

**建议目标：**

路由层只依赖本模块内部文件：

```text
app/modules/<module>/service.py
app/modules/<module>/repository.py
app/modules/<module>/schemas.py
app/modules/<module>/rules.py
app/shared/*
```

旧 store/reconciler 可以暂时继续存在，但应该被 service/repository/rules/schemas 适配，而不是被 routes 直接调用。

**推荐分模块小步做：**

1. 先做 `finance`，因为当前 routes 体量适中。
2. 再做 `ufo_mail`。
3. 再做 `booking`。
4. 最后做 `dispatch_mail`，因为它最复杂。

**验收标准：**

新增或更新架构测试，断言：

```text
app/modules/*/routes.py 不直接 import 顶层 legacy 文件：
- invoice_reconciler
- customs_reconciler
- export_clearance_store
- finance_store
- booking_store
- dispatch_mail_store
- mail_classifier_store
- ufo_mail_store
```

注意：本任务只改 import 边界，不迁移大量业务逻辑。

---

### P1-2 清理 `schema.py` / `schemas.py` 的职责命名

当前有些 schema 文件并不是 schema，而是导出 init 函数：

```text
app/modules/export_clearance/schema.py -> from export_clearance_store import init_db
app/modules/finance/schema.py          -> from finance_store import init_finance_db
app/modules/ufo_mail/schema.py         -> from ufo_mail_store import init_ufo_db
```

这会让后续维护者误解。

**建议改法：**

选择一种统一规则：

- `schemas.py`：只放 dataclass / Pydantic / TypedDict / 类型别名。
- `repository.py`：放 DB 读写。
- `service.py`：放业务流程编排。
- `exports.py`：放导出。
- `rules.py` 或 `rules/*`：放纯业务规则。
- `module_init.py` 或直接由 store adapter 暂时承接 DB init，不要命名为 schema。

**验收标准：**

- 不再有 `schema.py` 导出 `init_db` 这种误导性文件。
- 旧 import 如果存在，保留兼容或同步更新测试。
- `pytest -q` 通过。

---

### P1-3 统一模板对象，不要每个 routes.py 都 create 一次

当前每个 routes.py 基本都有：

```python
templates = create_templates()
```

这不是严重 bug，但会让路由模块 import 时都有初始化动作。

**建议改法：**

使用已有文件：

```text
app/web/templates.py
```

把 routes 里的：

```python
from app.factory import create_templates
templates = create_templates()
```

替换为：

```python
from app.web.templates import templates
```

**验收标准：**

- 所有页面 smoke test 通过。
- 不改变任何模板路径和渲染上下文。

---

## 5. 优先级 P2：按模块逐步迁移旧大文件

### P2-1 派送邮件模块拆分：先迁移纯规则，不碰 UI

**当前最大技术债：**

```text
dispatch_mail_store.py: 1629 行
```

建议先迁移纯函数，风险最低。

**第一步候选：**

从 `dispatch_mail_store.py` 把以下函数的真实实现迁入：

```text
app/modules/dispatch_mail/rules/match.py
- extract_match_tokens
- content_match_score
- score_so_match
- match_dqths

app/modules/dispatch_mail/rules/naming.py
- unique_filename
- build_dispatch_attachment_name
- pick_final_attachment_name
- apply_attachment_names

app/modules/dispatch_mail/rules/classify.py
- looks_like_tan_master_attachment
- classify_attachments
```

旧 `dispatch_mail_store.py` 里保留兼容 import：

```python
from app.modules.dispatch_mail.rules.match import extract_match_tokens, ...
```

不要一轮同时迁移 parse、preview、mail generation。

**验收标准：**

```bash
pytest -q tests/unit/test_dispatch_mail_rules.py
pytest -q
```

全部通过。

---

### P2-2 财务模块拆分：解析/规则/导出/仓储分层

**当前技术债：**

```text
finance_store.py: 1234 行
```

建议迁移顺序：

1. `app/modules/finance/parsers.py`：金额解析、付款描述拆分。
2. `app/modules/finance/rules.py`：业务 key、重复判定、分类规则。
3. `app/modules/finance/repository.py`：list/update/mark/exported 等 DB 操作。
4. `app/modules/finance/exports.py`：OUTBOUND 导出逻辑。
5. `app/modules/finance/service.py`：保留上传、导入、导出编排。

**注意：**

财务模块里“重复导入是正常场景”，不要破坏：

```text
新增 / 重复 / 跳过 / 补录更新
```

这几个统计口径。

**验收标准：**

- 现有 finance 测试通过。
- 增加至少 3 个单元测试：
  - 金额解析。
  - 重复业务 key 判定。
  - 导入重复数据时统计不回退。

---

### P2-3 Booking 模块拆分：供应商规则保持可扩展

当前 Booking 已经有较好的供应商规则目录：

```text
booking_rules/sil.py
booking_rules/weikeng.py
app/modules/booking/rules/registry.py
```

但 `booking_store.py` 仍然承担太多职责。

建议迁移顺序：

1. 把供应商规则注册从 `booking_store.py` 调用链里进一步隔离。
2. 把 Excel 读写工具移动到 `app/modules/booking/excel_io.py`。
3. 把 warehouse mail 生成移动到 `app/modules/booking/mail_builder.py` 的真实实现。
4. 保留 `booking_store.py` 兼容入口，避免独立 Booking app 失效。

**验收标准：**

```bash
pytest -q tests/unit/test_booking_rules.py
pytest -q tests/smoke/test_pages.py
pytest -q
```

全部通过。

---

### P2-4 暂时不要优先大拆 `invoice_reconciler.py`

`invoice_reconciler.py` 虽然大，但它是账单核心，业务规则复杂、隐藏样本多。当前不建议把它作为第一批大迁移对象。

更稳的做法：

1. 先补费用规则测试。
2. 把最纯的规则函数通过 `app/modules/billing/rules/fees.py` 迁移。
3. 迁移后旧函数名继续可用。
4. 每迁移一组函数，跑一次账单相关测试。

---

## 6. 优先级 P3：数据库、运行时和会话治理

### P3-1 真正使用 migration 机制

项目已有：

```text
app/core/db.py::run_migrations
```

但多数 store 仍然是：

```python
CREATE TABLE IF NOT EXISTS ...
if PRAGMA user_version == 0:
    PRAGMA user_version = 1
```

**问题：**

后续如果要加列、改索引、迁移数据，会越来越难验证。

**建议改法：**

每个持久化模块逐步建立 migration 函数：

```python
MIGRATIONS = {
    1: migration_001_initial_schema,
    2: migration_002_add_xxx_column,
}
```

`init_*_db()` 只负责：

```python
with get_connection() as conn:
    run_migrations(conn, MIGRATIONS)
```

**优先模块：**

1. `finance_store.py`
2. `export_clearance_store.py`
3. `mail_classifier_store.py`
4. `ufo_mail_store.py`
5. `dispatch_mail_store.py`

**验收标准：**

- 新增“旧 DB 升级”测试。
- `PRAGMA user_version` 能正确升级。
- 不破坏现有 runtime 数据。

---

### P3-2 给 `SESSION_STORE` 增加 TTL / 清理机制

当前：

```text
app/shared/state.py -> SESSION_STORE = SessionStore()
```

这是本地工具可以接受的中间态，但它没有：

- 创建时间。
- 最近访问时间。
- TTL。
- 最大 session 数。
- 对应 uploads/outputs 清理。

**建议改法：**

先只增加低风险能力：

- `SessionStore.set(session_id, value)` 时记录 `created_at`。
- `cleanup(max_age_hours=24)` 删除过期 session。
- 不自动删除文件，先只清内存。

第二步再做 runtime 文件清理按钮或工具脚本。

**验收标准：**

- SessionStore 单元测试覆盖 set/get/cleanup。
- 不改变现有 route 使用方式，或者保留 `__getitem__/__setitem__` 兼容。

---

### P3-3 把 app import 副作用降到最低

当前 `create_app()` 会在 import 时执行：

```python
ensure_runtime_dirs()
init_databases(db_initializers)
```

这对本地 exe 友好，但对测试、导入分析和后续模块化不够干净。

**建议改法：**

不要一上来大改生命周期。先加参数：

```python
def create_app(..., init_runtime: bool = True) -> FastAPI:
    if init_runtime:
        ensure_runtime_dirs()
        init_databases(db_initializers)
```

测试里可以创建 `init_runtime=False` 的 app，真实入口保持默认行为。

后续再考虑迁移到 FastAPI lifespan。

**验收标准：**

- `reconcile_web_app.py` 行为不变。
- 测试可构建无 DB 初始化副作用的 app。
- smoke test 通过。

---

## 7. 优先级 P4：测试样本与业务规则护栏

### P4-1 扩充 sanitized fixtures

当前已有：

```text
tests/fixtures/sanitized/README.md
```

这是对的。后续每次修一个业务 bug，都应沉淀一个脱敏样本或最小 synthetic fixture。

建议目录：

```text
tests/fixtures/sanitized/billing/
tests/fixtures/sanitized/booking/
tests/fixtures/sanitized/dispatch/
tests/fixtures/sanitized/finance/
tests/fixtures/sanitized/import_customs/
tests/fixtures/sanitized/export_clearance/
tests/fixtures/sanitized/ufo_mail/
```

**注意：**

不要放真实客户名、真实邮箱、真实订单号、真实付款金额、真实附件。

---

### P4-2 先补“纯规则测试”，再补端到端测试

当前最值得补的测试不是完整 E2E，而是业务规则函数：

- Booking：PO 前缀、PACKADC 匹配、箱数/体积规则。
- Dispatch：附件分类、Tan# 匹配、文件命名去重。
- Finance：金额解析、重复导入、导出筛选。
- Export clearance：TAN 规范化、紧急排序、板数/箱数格式。
- Billing：费用名归一化、费用拆分、倍数校验。

原因：纯规则测试最便宜，最能保护后续重构。

---

## 8. 优先级 P5：打包与依赖治理

### P5-1 统一 PyInstaller 配置

当前存在：

```text
build_exe.bat
build_booking_exe.bat
BillClearanceTool.spec
BookingTool.spec
.spec
```

其中 `.spec` 看起来是历史残留：name 为空，datas 也少于当前主打包配置。

**建议：**

1. 明确保留：
   - `BillClearanceTool.spec`
   - `BookingTool.spec`
   - `build_exe.bat`
   - `build_booking_exe.bat`
2. 删除或归档历史残留 `.spec`，但删除前先确认用户本机是否仍在用。
3. 让 bat 和 spec 的 datas/hiddenimports 保持一致。

**验收标准：**

- 打包脚本不会引用不存在的文件。
- spec 和 bat 的数据文件清单一致。
- `booking_template_zh.xlsx`、`templates`、`static` 都在需要的包里。

---

### P5-2 给依赖加版本约束

当前 `requirements.txt` 未锁版本：

```text
fastapi
uvicorn
python-multipart
jinja2
pandas
openpyxl
xlrd
pillow
pypdf
pymupdf
pyinstaller
pytest
httpx
```

**风险：**

- 打包环境漂移。
- Python 3.13 下个别库更新后行为变化。
- `pandas/openpyxl/xlrd/PyInstaller` 组合变化会影响 Excel 读写和 exe 打包。

**建议：**

先不要直接用 `pip freeze` 把所有间接依赖塞进 requirements。更稳的方式是：

```text
requirements.in       # 人类维护的直接依赖
requirements.txt      # 已解析/已锁定版本
```

如果项目维护者不想引入 pip-tools，也至少给直接依赖加最小版本和上限，例如：

```text
fastapi>=0.115,<1
uvicorn>=0.30,<1
pandas>=2.2,<3
openpyxl>=3.1,<4
xlrd>=2.0,<3
pillow>=10,<12
pypdf>=5,<7
pymupdf>=1.24,<2
pyinstaller>=6,<8
pytest>=8,<10
httpx>=0.27,<1
```

具体版本以上机测试通过为准。

**验收标准：**

```bash
pip check
pytest -q
```

通过。

---

## 9. 优先级 P6：前端模板和样式拆分

当前模板和样式已经变大：

```text
static/styles.css                       4020 行
templates/dispatch_mail_preview.html     435 行
templates/finance_records.html           395 行
templates/ufo_mail.html                  337 行
templates/invoice_detail.html            305 行
templates/dispatch_mail_compose.html     288 行
templates/export_customs.html            274 行
```

但这不是第一优先级。建议等后端边界和测试更稳定后再拆。

可行方向：

```text
static/modules/finance.css
static/modules/dispatch_mail.css
static/modules/booking.css

templates/modules/finance/*.html
templates/modules/dispatch_mail/*.html
```

**注意：**

不要在拆模板时顺手改样式和文案。先做到“路径变化但页面显示不变”。

---

## 10. 推荐给 Codex 的执行顺序

建议每次只开一个小任务：

1. `P0-1` 修复懒加载测试 baseline。
2. `P0-2` 修复 finance invalid batch_id 500。
3. `P0-3` 增加 `tools/dev_check.py`。
4. `P1-3` 统一模板对象。
5. `P1-1` 先从 finance routes 移除旧 store 直接 import。
6. `P1-1` 再从 ufo_mail routes 移除旧 store 直接 import。
7. `P2-1` 只迁移 dispatch naming 规则。
8. `P2-1` 只迁移 dispatch matching 规则。
9. `P2-2` 只迁移 finance parsers。
10. `P3-2` 给 SessionStore 增加 TTL 测试和兼容实现。
11. `P5-1` 清理打包配置。
12. `P5-2` 版本约束。

不建议第一轮做：

- 大拆 `invoice_reconciler.py`。
- 大拆 `dispatch_mail_store.py` 全部内容。
- 大改 UI。
- 规则配置化全量迁移。
- 数据库 schema 大改。

---

## 11. 可直接复制给 Codex 的任务提示词

### 提示词 A：修复当前测试失败

```text
请先阅读 AGENTS.md 和 Codex_refactor_optimization_20260518.md。

本轮只做 P0-1：修复 tests/unit/test_architecture_boundaries.py 里懒加载测试没有扣除环境 baseline 的问题。

要求：
1. 不改应用业务代码。
2. 只修改必要测试文件。
3. 测试逻辑改为：记录 import reconcile_web_app 前已经存在于 sys.modules 的 heavy modules，import 后只断言没有新增 heavy modules。
4. 跑：
   - python -m compileall -q app *.py booking_rules tools tests
   - pytest -q tests/unit/test_architecture_boundaries.py::test_web_app_import_keeps_heavy_libraries_lazy
   - pytest -q
5. 输出你改了什么、验证结果是什么。
```

### 提示词 B：修复 finance batch_id 500

```text
请先阅读 AGENTS.md 和 Codex_refactor_optimization_20260518.md。

本轮只做 P0-2：修复 /modules/finance-records?batch_id=abc 返回 500 的问题。

要求：
1. 修改 app/modules/finance/routes.py，给 batch_id 查询参数增加安全解析。
2. 非数字 batch_id 返回 400，不要 500。
3. 增加 smoke test，使用 TestClient(main_app, raise_server_exceptions=False) 验证非法 batch_id。
4. 不改财务业务规则、导出逻辑、模板样式。
5. 跑：
   - python -m compileall -q app *.py booking_rules tools tests
   - pytest -q tests/smoke/test_pages.py
   - pytest -q
6. 输出修改点和验证结果。
```

### 提示词 C：统一模板对象

```text
请先阅读 AGENTS.md 和 Codex_refactor_optimization_20260518.md。

本轮只做 P1-3：把各 routes.py 里的 create_templates() 替换为 app.web.templates.templates。

要求：
1. 不改任何模板文件。
2. 不改任何页面上下文 key。
3. 不改路由路径。
4. 只改 import 和 templates 变量来源。
5. 跑：
   - python -m compileall -q app *.py booking_rules tools tests
   - pytest -q tests/smoke/test_pages.py
   - pytest -q
6. 输出修改文件清单和验证结果。
```

### 提示词 D：派送邮件命名规则迁移

```text
请先阅读 AGENTS.md 和 Codex_refactor_optimization_20260518.md。

本轮只做 P2-1 的一个小子任务：把 dispatch_mail_store.py 中附件命名相关纯函数迁移到 app/modules/dispatch_mail/rules/naming.py。

目标函数：
- unique_filename
- build_dispatch_attachment_name
- pick_final_attachment_name
- apply_attachment_names

要求：
1. app/modules/dispatch_mail/rules/naming.py 放真实实现。
2. dispatch_mail_store.py 保留兼容导入，旧 import 路径不失效。
3. 不改派送邮件 UI、解析流程、邮件生成流程。
4. 不改业务命名结果。
5. 跑：
   - python -m compileall -q app *.py booking_rules tools tests
   - pytest -q tests/unit/test_dispatch_mail_rules.py
   - pytest -q
6. 输出修改点和验证结果。
```

---

## 12. 最终目标状态

理想状态不是“文件越多越好”，而是每个模块都能清楚回答：

```text
routes.py       只负责 HTTP 表单/响应
service.py      只负责编排业务流程
repository.py   只负责 DB 读写
rules.py        只负责纯业务规则
parsers.py      只负责文件/文本解析
exports.py      只负责导出
schemas.py      只负责类型/数据结构
legacy_adapter  只负责兼容旧入口，逐步减少
```

当这个边界稳定后，再做规则配置化、模板拆分和更大的业务重构，风险会低很多。
