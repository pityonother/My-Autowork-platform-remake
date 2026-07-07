# Runtime 数据边界

runtime 是用户数据和运行缓存，不是源代码。

## 不应提交

- `runtime/`
- `uploads/`
- `outputs/`
- `*.db`
- 真实 `.eml`
- 真实 Excel、PDF、图片
- token、cookie、证书、私钥

## 允许清理

只允许清理明确的缓存子目录或 outputs 子项。不要删除 runtime 根目录本身，不要跨出 `BILL_TOOL_RUNTIME_DIR` 指定的目录。

## Launcher 模式

Launcher 会为每个模块设置：

```text
BILL_TOOL_RUNTIME_DIR=<Launcher目录>/runtime/module_data/<module_id>
```

模块更新只替换程序目录，不覆盖用户数据目录。

## 真实样本

真实业务样本只用于本地人工验证。进入 Git 的样本必须 synthetic 或完全脱敏。
