# 架构速览

My-Autowork 是一个 FastAPI 多模块工作台。主入口 `reconcile_web_app.py` 组合各模块路由，独立模块入口位于 `module_entrypoints/`，共享 app 创建逻辑在 `app/factory.py`。

## 模块边界

- `app/modules/*/routes.py`：页面和表单入口。
- `app/modules/*/service.py`：模块服务层。
- `app/modules/*/repository.py`：SQLite 或本地状态读写。
- 顶层 legacy 文件保留旧业务逻辑，逐步用 `legacy_adapter.py` 包起来，不一次性重写。
- `app/shared/`：跨模块复用的文件、上传、字体、日志、状态和错误工具。

## 入口

- `reconcile_web_app.py`：完整工作台。
- `booking_web_app.py`：Booking 独立入口。
- `launcher_web_app.py`：模块 Launcher。
- `module_entrypoints/*.py`：PyInstaller 模块化分发入口。

## 维护原则

新增功能优先小步接入现有模块；拆 legacy 文件时保持外部 API 不变，并先补测试。
