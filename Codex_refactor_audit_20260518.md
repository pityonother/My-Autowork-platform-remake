# Codex 重构结果审核报告

> 审核对象：`New_project_2_pro_review_20260518_160214` 代码包  
> 审核时间：2026-05-18  
> 结论：**这轮 Codex 执行质量整体合格，可以认为重构推进了一大步；但建议先修 2 个 P0/P1 输入边界问题，再继续下一轮拆分。**

---

## 1. 验证结果

在解压后的项目根目录执行：

```bash
python -m compileall -q app *.py booking_rules tools tests
pytest -q
```

结果：

```text
compileall：通过
pytest：49 passed
```

继续执行：

```bash
python tools/dev_check.py
```

结果：

```text
tools/dev_check.py：通过，内部 pytest 也是 49 passed
```

补充检查：

```text
zip 原包文件数：196
原包内 .pyc：0
原包内 __pycache__：0
原包内 .pytest_cache：0
原包内 runtime/：0
```

说明：本次 review 包本身没有把运行库、缓存、runtime 数据库打进去，这点是合格的。

我本地执行 `python -m pip check` 时失败，原因是当前审核环境里已有的 `moviepy` 要求 `pillow<12`，但环境装的是 `pillow 12.2.0`。项目自己的 `requirements.txt` 已经写了 `pillow>=10,<12`，所以这更像是审核环境污染，不直接算本项目缺陷。

---

## 2. 这轮做得好的地方

### 2.1 P0 问题基本已处理

上一轮指出的懒加载测试误判已经修好：

```text
tests/unit/test_architecture_boundaries.py::test_web_app_import_keeps_heavy_libraries_lazy
```

现在会先记录 import 前 baseline，再判断 `reconcile_web_app` 是否新增加载重依赖。

`/modules/finance-records?batch_id=abc` 的 500 也已修复，现在通过 `parse_optional_int()` 返回 400，并加了 smoke test。

### 2.2 路由层边界明显变干净

现在 `app/modules/*/routes.py` 已经不再直接 import 顶层旧文件：

```text
invoice_reconciler.py
customs_reconciler.py
export_clearance_store.py
finance_store.py
booking_store.py
dispatch_mail_store.py
mail_classifier_store.py
ufo_mail_store.py
```

这比上一版清晰很多。旧逻辑被集中到各模块的 `legacy_adapter.py`，这符合“先隔离，再迁移”的节奏。

### 2.3 真实业务逻辑迁移已有进展

这次不是只做 re-export。已有一批真实逻辑迁入模块目录：

```text
app/modules/booking/excel_io.py
app/modules/booking/mail_builder.py
app/modules/dispatch_mail/rules/classify.py
app/modules/dispatch_mail/rules/match.py
app/modules/dispatch_mail/rules/naming.py
app/modules/finance/parsers.py
app/modules/finance/rules.py
app/modules/export_clearance/rules.py
app/modules/mail_classifier/rules.py
app/modules/ufo_mail/rules.py
```

旧 store 文件里也保留了兼容 import，这个迁移方式比较稳。

### 2.4 工程护栏增强

新增/改进点包括：

```text
tools/dev_check.py
requirements.in
requirements.txt 版本范围
数据库 migration 封装
SessionStore TTL/cleanup
schema.py -> schemas.py 命名清理
模板对象统一到 app/web/templates.py
模块 CSS 拆分
PyInstaller 配置检查测试
sanitized fixtures 目录结构
```

这说明 Codex 没有盲目大拆，而是按前一份建议做了不少工程治理。

---

## 3. 需要马上让 Codex 修的点

## P0-1：财务导出接口的非法汇率仍会返回 500

### 问题

当前 `/modules/finance-records/export` 在 `exchange_rate=abc` 时仍然返回 500。

我手动验证：

```python
from fastapi.testclient import TestClient
from reconcile_web_app import app

client = TestClient(app, raise_server_exceptions=False)
response = client.post(
    "/modules/finance-records/export",
    data={"exchange_rate": "abc"},
    files={"bill_file": ("bill.xls", b"abc", "application/vnd.ms-excel")},
)
print(response.status_code)
```

当前结果：

```text
500
```

原因是：

```text
app/modules/finance/parsers.py::parse_exchange_rate()
```

直接执行：

```python
Decimal(text)
```

非法输入会抛 `decimal.InvalidOperation`，而：

```text
app/modules/finance/routes.py::export_finance_bill()
```

只 catch 了 `ValueError`。

### 建议修法

推荐让 parser 层统一把非法汇率转成 `None`，再由 service 层现有逻辑抛 `ValueError`：

```python
from decimal import Decimal, InvalidOperation


def parse_exchange_rate(value: str | None) -> Decimal | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return quantized(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
```

然后补测试：

```python
def test_finance_export_rejects_invalid_exchange_rate() -> None:
    client = TestClient(main_app, raise_server_exceptions=False)
    response = client.post(
        "/modules/finance-records/export",
        data={"exchange_rate": "abc"},
        files={"bill_file": ("bill.xls", b"abc", "application/vnd.ms-excel")},
    )
    assert response.status_code == 400
```

### 验收标准

```bash
pytest -q tests/smoke/test_pages.py
pytest -q tests/unit/test_finance_rules.py
pytest -q
```

---

## P0-2：UFO 邮件输出文件名存在路径穿越风险

### 问题

这个问题不是本轮才引入的，但这轮已经在重构 UFO 模块，建议马上一起修掉。

当前：

```text
app/modules/ufo_mail/service.py
```

使用用户输入的 `ufo_no` 直接拼输出文件名：

```python
output_name = f"{detected_ufo_no or 'ufo_mail'}_{session_id}.eml"
output_path = OUTPUT_DIR / output_name
```

如果用户提交：

```text
../../pwn
```

在勾选至少一个 issue 后，文件会被写到 `runtime/outputs` 外面。

### 建议修法

新增一个只用于文件名的安全 stem 函数，不要直接用用户输入拼路径：

```python
import re


def safe_ufo_output_stem(value: str) -> str:
    text = (value or "").strip()
    match = re.search(r"\bUFO\d{6,}\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe[:80] or "ufo_mail"
```

然后：

```python
output_stem = safe_ufo_output_stem(detected_ufo_no)
output_path = OUTPUT_DIR / f"{output_stem}_{session_id}.eml"
```

最好再加一个 resolve 校验：

```python
resolved = output_path.resolve()
if not resolved.is_relative_to(OUTPUT_DIR.resolve()):
    raise ValueError("输出文件名不合法。")
```

### 建议测试

```python
def test_ufo_mail_output_path_stays_inside_output_dir(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path)
    path = service.generate_mail(
        issue_ids=[1],
        attachments=[],
        ufo_no="../../pwn",
        to_email="",
        cc_email="",
        from_email="",
    )

    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert ".." not in path.name
    assert "/" not in path.name
    assert "\\" not in path.name
```

如果这个测试依赖 runtime DB，建议先抽出纯函数 `safe_ufo_output_stem()` 单测，再补 service 集成测试。

### 验收标准

```bash
pytest -q tests/unit/test_ufo_mail_rules.py
pytest -q tests/smoke/test_pages.py
pytest -q
```

---

## 4. 建议继续优化，但不必立刻阻塞合并的点

## P1-1：主入口仍直接 import 顶层旧 store 初始化函数

现在 routes 层已经干净，但主入口还有：

```text
reconcile_web_app.py
```

里面直接 import：

```python
from dispatch_mail_store import init_dispatch_db
from export_clearance_store import init_db as init_export_clearance_db
from finance_store import init_finance_db
from mail_classifier_store import init_mail_classifier_db
from ufo_mail_store import init_ufo_db
```

这不影响当前运行，但从架构边界看，主入口最好也只依赖 `app.*`。建议下一轮把 DB initializer 也通过模块内部暴露，例如：

```text
app/modules/finance/repository.py::init_finance_db
app/modules/export_clearance/repository.py::init_export_clearance_db
app/modules/ufo_mail/repository.py::init_ufo_db
```

然后 `reconcile_web_app.py` 只 import app modules。

同时新增架构测试，覆盖 root entrypoint，不只覆盖 `app/modules/*/routes.py`。

---

## P1-2：legacy_adapter 目前是“隔离”但还不是“懒加载”

虽然 heavy library 懒加载测试通过，但 import `reconcile_web_app` 后，所有旧顶层 store/reconciler 实际上仍会被加载：

```text
invoice_reconciler
customs_reconciler
export_clearance_store
finance_store
booking_store
dispatch_mail_store
mail_classifier_store
ufo_mail_store
```

这不是 bug，因为现在目标主要是边界清晰；但下一阶段如果要进一步降低启动副作用，可以把部分 `legacy_adapter.py` 改成函数内 import 或薄 wrapper。

不要一次性做完。建议优先从 `finance` / `ufo_mail` 这种小模块开始。

---

## P1-3：测试数量增加了，但还偏“结构测试”

当前 49 个测试过得很顺，但很多测试还是在检查结构和 import 边界。后续更应该补业务行为测试。

优先补：

```text
finance：非法汇率、重复导入、补录更新统计
ufo_mail：输出文件名安全、手输 UFO 编号、附件名检测
booking：SIL-FUCA warehouse template 保存/加载/替换
booking：xls/xlsx 读取缓存不影响结果
export_clearance：旧 DB migration 后字段完整性
mail_classifier：规则冲突、缺附件、转发/回复组合场景
```

---

## P1-4：requirements 目前是版本范围，不是完全锁定

现在 `requirements.in` 和 `requirements.txt` 内容相同，都是直接依赖版本范围。这比裸依赖强很多，可以接受。

但如果后续要稳定打包 exe，建议引入二选一：

```text
方案 A：requirements.in 维护范围，requirements.txt 用 pip-tools 生成精确锁定版本
方案 B：继续保持范围，但在 AGENTS.md / README 明确 Python 版本和创建 venv 的步骤
```

否则不同电脑装出来的 pandas/openpyxl/PyInstaller 组合仍可能不同。

---

## 5. 本轮综合评价

这轮 Codex 做得比上一轮扎实：

```text
测试从 22 个左右扩到 49 个
P0 的懒加载测试误判修掉了
finance batch_id 500 修掉了
routes 直接依赖旧 store 的问题基本清掉了
schema 命名误导修掉了
真实规则逻辑开始迁入模块
migration/session/dev_check/requirements/static split 都有推进
```

当前不建议继续大规模拆 `invoice_reconciler.py` 或 `dispatch_mail_store.py`。下一轮最稳的顺序是：

```text
1. 修 finance export invalid exchange_rate 500
2. 修 UFO output filename path traversal
3. 把 reconcile_web_app.py 的旧 store initializer import 移进 app/modules 内部
4. 给 finance/ufo/booking 补业务行为测试
5. 再继续迁移 finance repository / export_clearance repository
```

---

## 6. 可直接给 Codex 的提示词

```text


本轮只做两个输入边界修复，不继续大拆模块、不改 UI、不改业务文案：

任务 1：修复 /modules/finance-records/export 在 exchange_rate=abc 时返回 500 的问题。
要求：
- 修改 app/modules/finance/parsers.py::parse_exchange_rate。
- 非法 Decimal 输入返回 None 或由 service 统一转成 ValueError。
- 最终 HTTP 返回 400，不要 500。
- 增加 TestClient 测试。

任务 2：修复 app/modules/ufo_mail/service.py 里 ufo_no 直接拼 output_path 的路径穿越风险。
要求：
- 新增纯函数 safe_ufo_output_stem。
- output_path 必须始终位于 OUTPUT_DIR 内。
- 用户输入 ../../pwn、..\\..\\pwn、带斜杠/反斜杠/冒号/换行的 ufo_no 都不能影响输出目录。
- 增加单元测试或 service 集成测试。

验证命令：
python -m compileall -q app *.py booking_rules tools tests
pytest -q tests/smoke/test_pages.py
pytest -q tests/unit/test_finance_rules.py
pytest -q tests/unit/test_ufo_mail_rules.py
pytest -q

不要做：
- 不要拆 invoice_reconciler.py。
- 不要改模板和 CSS。
- 不要改邮件正文格式。
- 不要改 Excel 导出格式。
- 不要删除旧 store 兼容入口。
```
