# UFO EML 生成与富文本签名实现参考

本文给另一个项目参考 UFO 模块生成 `.eml` 邮件的方法，重点是富文本签名、签名图片、普通附件如何进入最终邮件。

## 相关文件位置

核心实现：

- `ufo_mail_store.py`
  - `UfoMailInput` / `UfoAttachment`：邮件生成输入结构。
  - `get_ufo_signature_settings()`：读取签名开关、HTML、纯文本、图片资产。
  - `save_ufo_signature_settings()`：保存签名配置到 `runtime/ufo_mail.db`。
  - `import_ufo_signature_from_eml()`：从一封已有 `.eml` 中提取 HTML 签名和 cid 图片。
  - `generate_ufo_eml()`：生成最终 `.eml`，包含正文、HTML 签名、inline 图片和附件。

模块封装：

- `app/modules/ufo_mail/service.py`
  - `import_signature()`：保存上传的签名 `.eml`，再调用 `import_ufo_signature_from_eml()`。
  - `generate_mail()`：保存用户上传附件，组装输入，调用 `generate_ufo_eml()`。
  - `generate_mail_from_saved_attachments()`：处理附件后生成输出路径并写 `.eml`。

HTTP 路由：

- `app/modules/ufo_mail/routes.py`
  - `POST /modules/ufo-mail/signature/import`：导入签名 `.eml`。
  - `POST /modules/ufo-mail/signature/enabled`：开启/关闭签名。
  - `POST /modules/ufo-mail/generate`：生成并下载 `.eml`。
  - `POST /modules/ufo-mail/generate/confirm-review`：复用已上传附件继续生成 `.eml`。

页面：

- `templates/ufo_mail.html`
  - 签名导入表单：`/modules/ufo-mail/signature/import`
  - 签名启用开关：`/modules/ufo-mail/signature/enabled`
  - 邮件生成表单：`/modules/ufo-mail/generate`

运行数据：

- `runtime/ufo_mail.db`
  - 表：`ufo_mail_settings`
  - 保存：收发件人、签名 HTML、签名纯文本、签名图片资产 JSON。
- `runtime/ufo_signature/`
  - 保存从签名 `.eml` 中提取出来的 inline 图片。
- `runtime/outputs/`
  - 保存最终生成的 `.eml`。

## 数据结构

`ufo_mail_store.py` 中的最小输入结构：

```python
@dataclass
class UfoAttachment:
    path: Path
    filename: str


@dataclass
class UfoMailInput:
    ufo_no: str
    to_email: str
    cc_email: str
    from_email: str
    issue_ids: Sequence[int]
    attachments: Sequence[UfoAttachment]
```

另一个项目可以直接照这个思路：业务层先把附件保存到本地路径，再把路径和最终显示文件名交给邮件生成函数。

## 签名导入流程

入口：

```text
POST /modules/ufo-mail/signature/import
```

调用链：

```text
routes.py
  -> service.py::import_signature()
    -> ufo_mail_store.py::import_ufo_signature_from_eml()
```

`import_ufo_signature_from_eml()` 做了几件事：

1. 用 `BytesParser(policy=policy.default)` 解析上传的 `.eml`。
2. 遍历 MIME parts：
   - 第一段 `text/html` 作为 HTML 正文来源。
   - 带 `Content-ID` 且类型是 `image/*` 的 part 收集为候选签名图片。
3. 从 HTML 正文中截取签名片段：
   - 优先用 marker，例如 `Thanks & Best regards`。
   - 找不到 marker 时，退回到第一个 `<img>` 或 `<hr>` 附近。
   - 会用 `strip_forwarded_history()` 去掉转发历史中的 `<blockquote>`。
4. 找出签名 HTML 中引用的 `cid:...`。
5. 把对应图片保存到 `runtime/ufo_signature/`。
6. 把签名配置保存到 `ufo_mail_settings`：
   - `signature_enabled`
   - `signature_html`
   - `signature_plain`
   - `signature_assets`
   - `signature_source_name`
   - `signature_updated_at`

`signature_assets` 是 JSON 数组，结构类似：

```json
[
  {
    "cid": "image001.png@01DA...",
    "path": "runtime/ufo_signature/abc123.png",
    "filename": "image001.png",
    "content_type": "image/png"
  }
]
```

## 生成 EML 的关键逻辑

核心函数：

```text
ufo_mail_store.py::generate_ufo_eml()
```

它使用标准库：

```python
from email.message import EmailMessage
from email.policy import SMTP
```

生成流程：

1. 根据问题项生成 subject、纯文本 body、HTML body。
2. 创建邮件：

```python
message = EmailMessage(policy=SMTP)
message["Subject"] = subject
message["From"] = ...
message["To"] = ...
message["Cc"] = ...
```

3. 先设置纯文本正文：

```python
message.set_content(body)
```

4. 如果启用了富文本签名：

```python
message.set_content(f"{body}\r\n\r\n{signature['plain']}")
message.add_alternative(
    f"{body_html}<br>{signature['html']}",
    subtype="html",
)
```

这样最终邮件会有：

- `text/plain`：给不支持 HTML 的客户端备用。
- `text/html`：用于 Outlook 等客户端显示富文本正文和签名。

5. 把签名图片作为 HTML part 的 related inline 资源嵌入：

```python
html_part = message.get_payload()[-1]
html_part.add_related(
    asset_path.read_bytes(),
    maintype=maintype,
    subtype=subtype,
    cid=f"<{cid}>",
    disposition="inline",
)
```

这里最关键的是：

- HTML 里仍然引用原始 `cid:xxx`。
- `add_related(..., cid=f"<{cid}>")` 必须使用相同 cid。
- Outlook 才能把签名里的图片正确显示出来，而不是变成普通附件或丢图。

6. 添加普通附件：

```python
message.add_attachment(
    content,
    maintype=maintype,
    subtype=subtype,
    filename=attachment.filename,
)
```

7. 写出 `.eml`：

```python
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_bytes(message.as_bytes())
```

路由返回下载：

```python
return FileResponse(
    output_path,
    media_type="message/rfc822",
    filename=output_path.name,
)
```

## 另一个项目的最小迁移方案

如果另一个项目只想复用“带富文本签名生成 EML”的能力，建议抽出四类代码：

1. 邮件输入结构
   - `UfoAttachment`
   - 类似 `UfoMailInput` 的 dataclass。

2. 签名存取
   - `get_ufo_signature_settings()`
   - `save_ufo_signature_settings()`
   - 可以继续用 SQLite，也可以换成项目自己的配置表。

3. 签名导入
   - `strip_forwarded_history()`
   - `find_signature_fragment_start()`
   - `extract_signature_html()`
   - `html_to_plain_text()`
   - `import_ufo_signature_from_eml()`

4. EML 生成
   - `generate_ufo_eml()` 的 MIME 构造方式。

另一个项目不一定需要搬 UFO 的问题库逻辑；只要把 subject、body、body_html 换成自己的业务内容即可。

## 注意事项

- 不要只保存签名 HTML；如果签名里有图片，必须同时保存 cid 图片资产。
- 不要改签名 HTML 里的 `cid:` 值，除非同步改 `add_related()` 的 cid。
- `signature_plain` 很重要，它是纯文本邮件 fallback。
- 生成 `.eml` 时建议使用 `EmailMessage(policy=SMTP)`，避免换行和 MIME 格式在 Outlook 中异常。
- 如果图片文件不存在，当前实现会跳过该图片；另一个项目可以改成报错，避免静默丢签名图。
- 签名 `.eml` 的 marker 默认是 `Thanks & Best regards`，不同公司签名可以允许用户输入 marker。
- 最终下载响应建议使用 `message/rfc822`。

## 快速定位清单

开发时可以按下面顺序看代码：

1. `templates/ufo_mail.html`：页面如何上传签名和生成邮件。
2. `app/modules/ufo_mail/routes.py`：请求入口。
3. `app/modules/ufo_mail/service.py`：上传文件保存和业务编排。
4. `ufo_mail_store.py::import_ufo_signature_from_eml()`：签名导入。
5. `ufo_mail_store.py::generate_ufo_eml()`：最终 `.eml` MIME 结构。

