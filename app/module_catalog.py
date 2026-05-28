from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDefinition:
    module_id: str
    title: str
    badge: str
    subtitle: str
    description: str
    route_path: str
    start_port: int
    exe_name: str
    artifact_name_prefix: str
    runtime_data_dir_name: str
    router_import_path: str
    db_initializer_import_path: str | None = None

    @property
    def exe_stem(self) -> str:
        return self.exe_name.removesuffix(".exe")


MODULE_CATALOG: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        module_id="billing",
        title="做账单",
        badge="账单处理",
        subtitle="总账回填与单页账单核对",
        description="上传空白账单格式、派送单、单页账单和 Flex Tan# 总表，先预览再导出。",
        route_path="/modules/billing",
        start_port=8031,
        exe_name="BillingTool.exe",
        artifact_name_prefix="BillingTool",
        runtime_data_dir_name="billing",
        router_import_path="app.modules.billing.routes:router",
    ),
    ModuleDefinition(
        module_id="import_customs",
        title="香港进口清关",
        badge="进口清关",
        subtitle="bill 模板回填",
        description="上传空白 bill、订单管理和真实数据源，查看中间态并导出进口清关结果。",
        route_path="/modules/import-customs",
        start_port=8032,
        exe_name="ImportCustomsTool.exe",
        artifact_name_prefix="ImportCustomsTool",
        runtime_data_dir_name="import_customs",
        router_import_path="app.modules.import_customs.routes:router",
    ),
    ModuleDefinition(
        module_id="export_clearance",
        title="香港出口清关",
        badge="历史批次",
        subtitle="带历史批次与待清关排序",
        description="上传 Flex Tan# 总表，保存历史批次、查看待清关优先级，并沿用旧项目导出逻辑。",
        route_path="/modules/export-customs",
        start_port=8033,
        exe_name="ExportClearanceTool.exe",
        artifact_name_prefix="ExportClearanceTool",
        runtime_data_dir_name="export_clearance",
        router_import_path="app.modules.export_clearance.routes:router",
        db_initializer_import_path="export_clearance_store:init_db",
    ),
    ModuleDefinition(
        module_id="finance",
        title="财务记录",
        badge="持久化任务",
        subtitle="payment 到 OUTBOUND",
        description="记录代支付任务、跟踪付款进度，并按规则回填到 bill 的 OUTBOUND。",
        route_path="/modules/finance-records",
        start_port=8034,
        exe_name="FinanceTool.exe",
        artifact_name_prefix="FinanceTool",
        runtime_data_dir_name="finance",
        router_import_path="app.modules.finance.routes:router",
        db_initializer_import_path="finance_store:init_finance_db",
    ),
    ModuleDefinition(
        module_id="mail_classifier",
        title="邮件标签分类器",
        badge="自动标签",
        subtitle="网易企业邮箱到业务标签",
        description="只读同步邮箱邮件，按规则生成项目内标签，并支持人工确认。",
        route_path="/modules/mail-classifier",
        start_port=8035,
        exe_name="MailClassifierTool.exe",
        artifact_name_prefix="MailClassifierTool",
        runtime_data_dir_name="mail_classifier",
        router_import_path="app.modules.mail_classifier.routes:router",
        db_initializer_import_path="mail_classifier_store:init_mail_classifier_db",
    ),
    ModuleDefinition(
        module_id="ufo_mail",
        title="UFO 邮件生成器",
        badge="异常反馈",
        subtitle="问题库勾选生成 eml",
        description="维护常用异常反馈库，勾选问题并附上 UFO 文件和图片，生成英文邮件草稿。",
        route_path="/modules/ufo-mail",
        start_port=8036,
        exe_name="UfoMailTool.exe",
        artifact_name_prefix="UfoMailTool",
        runtime_data_dir_name="ufo_mail",
        router_import_path="app.modules.ufo_mail.routes:router",
        db_initializer_import_path="ufo_mail_store:init_ufo_db",
    ),
    ModuleDefinition(
        module_id="dispatch_mail",
        title="派送邮件生成器",
        badge="派送邮件",
        subtitle="客户邮件到仓库派送邮件",
        description="从客户邮件提取附件，自动改名、按 Tan# 拆段，并生成发给仓库的 .eml。",
        route_path="/modules/dispatch-mail",
        start_port=8037,
        exe_name="DispatchMailTool.exe",
        artifact_name_prefix="DispatchMailTool",
        runtime_data_dir_name="dispatch_mail",
        router_import_path="app.modules.dispatch_mail.routes:router",
        db_initializer_import_path="dispatch_mail_store:init_dispatch_db",
    ),
    ModuleDefinition(
        module_id="booking",
        title="Booking 生成器",
        badge="自动填表",
        subtitle="CCIXLS 到 booking form",
        description="上传客户 CCIXLS，按供应商规则生成 booking_template_zh 的填好稿。",
        route_path="/modules/booking",
        start_port=8038,
        exe_name="BookingTool.exe",
        artifact_name_prefix="BookingTool",
        runtime_data_dir_name="booking",
        router_import_path="app.modules.booking.routes:router",
    ),
)

MODULES_BY_ID = {module.module_id: module for module in MODULE_CATALOG}
