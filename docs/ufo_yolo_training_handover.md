# UFO/RH 标签 YOLO 视觉识别训练交接文档

更新时间：2026-05-19  
适用项目：`C:\Users\ac\Documents\New_project_2_pro_review_20260518_164100`

## 1. 背景

当前项目已经重构为更清晰的模块结构，UFO 相关能力主要分布在：

- `app/modules/ufo_mail/`：重构后的 UFO 邮件模块，包含 routes、service、rules、repository、mail_builder、signature 等分层。
- `ufo_mail_store.py`：旧模块兼容入口，部分功能仍由重构模块通过 legacy adapter 复用。
- `templates/ufo_mail.html`：UFO 邮件页面。
- `static/modules/ufo_mail/styles.css`：UFO 邮件页面样式。
- `tools/ufo_cover_detector.py`：当前 UFO 覆盖区域评估工具，使用固定 POD 区域和启发式图像规则识别后续页 RH 标签。
- `tools/ufo_cover_detector_gui.py`：给业务人员试用的 GUI。
- `tools/run_ufo_cover_detector_gui.bat`：开发环境下启动 GUI。

业务目标是把正常 RH 文件转换成 UFO 文件：

1. POD 页上的 RH 号替换成 UFO 号。
2. 后续页面所有人工贴上的 RH 标签需要遮盖。
3. 遮盖不是纯白块，而是使用当前页面覆盖区域周围的均衡灰度图，视觉上接近“贴图覆盖”。

当前最大的难点是后续页面的 RH 标签坐标不固定。仓库是在实体文件上人工贴标签，位置没有稳定坐标。现有启发式检测已经能覆盖一部分样本，但在 `RH2603378.pdf` 这类样本上仍会出现漏判、误判。因此下一阶段建议用 YOLO 训练视觉检测模型，专门定位需要遮盖的 RH 纸质标签。

## 2. 本交接目标

训练一个目标检测模型，用于在 PDF 页面渲染图上定位“需要遮盖的 RH 纸质标签”。

第一阶段只做检测评估：

- 输入：RH PDF。
- 输出：带检测框的评估 PDF，以及结构化 JSON 检测结果。
- 人工验收：业务人员确认红框是否完整框住需要遮盖的 RH 标签。

第二阶段再做自动 UFO PDF 生成：

- POD 固定区域替换 RH 号为 UFO 号。
- 后续页根据 YOLO 检测框做灰度贴图遮盖。
- 输出最终 UFO PDF 副本，不覆盖原始 PDF。

## 3. 第一版不做什么

- 不识别货物信息、Flex PO、Flex PN、COO 等业务字段。
- 不 OCR RH 号，也不判断 RH 号是否正确。
- 不自动决定 UFO 号码，UFO 号码仍由用户手填或从文件名/业务系统取得。
- 不直接覆盖真实业务 PDF 原件。
- 不把训练数据、客户 PDF、标注图片提交进 Git。
- 不训练通用条码识别模型。目标是识别整张 RH 贴纸区域，不是识别任意条码。

## 4. 推荐方案

使用 Ultralytics YOLO 做单类目标检测：

- 任务类型：`detect`
- 主类别：`rh_sticker`
- 检测目标：完整 RH 纸质标签，包括条码、文字、边框、白色标签底，以及遮盖需要的少量外扩余量。
- 训练设备：本机 NVIDIA 4070 Ti，使用 CUDA。
- 训练方式：迁移学习，从官方小模型或中等模型开始。
- 模型选择：按当前 Ultralytics 官方稳定版本选择 `n` 或 `s` 尺寸模型。官方文档目前示例使用 `yolo26n.pt`，如果本地安装版本仍是 `yolo11n.pt` 或 `yolov8n.pt`，命令结构不变，只替换 `model=`。

选择 YOLO 的原因：

- RH 标签是视觉对象，位置不固定，规则坐标不适合。
- 目标数量少，页面背景类型有限，迁移学习适合。
- YOLO 推理速度快，后续可以嵌进当前 PDF 工具链。
- 业务上最重要的是“不漏掉 RH 标签”，可以通过召回率和人工复核 PDF 控制风险。

## 5. 类别设计

第一版只建议一个类别：

```yaml
names:
  0: rh_sticker
```

不要一开始拆成 `barcode`、`rh_text`、`label_border` 等多个类别。业务动作是覆盖整张标签，不是分别处理条码和文字。类别越多，标注成本越高，也更容易在集成时发生框合并问题。

可选扩展：

- `pod_rh_area`：如果未来 POD 模板不固定，再考虑训练 POD RH 区域。
- 不建议增加 `ignore_header_barcode` 类别。页眉条码、表格线、订单号条码应该作为负样本出现，不标注即可，让模型学会不检出它们。

## 6. 数据准备

### 6.1 输入来源

从真实业务 RH PDF 中抽样，但必须只读原件：

- 不修改原始 PDF。
- 不把真实 PDF 放进 Git。
- 不把客户敏感 PDF 上传到第三方云标注平台，除非业务明确允许。
- 建议训练临时数据放在 `runtime/yolo_ufo_dataset/`，因为 `runtime/` 已经被 `.gitignore` 忽略。

### 6.2 PDF 转图片

YOLO 训练需要图片。建议把每页 PDF 渲染成 PNG：

- DPI：先用 `200` 或 `240`。
- 如果标签很小、训练后框偏紧，再尝试 `300`。
- 文件命名保留 PDF 名和页码，例如 `RH2603378_p003.png`。
- 渲染整页，不要只裁下半页，否则模型无法学会排除页眉条码和其他相似区域。

### 6.3 标注工具

推荐本地标注工具，避免上传真实业务文件：

- Label Studio 本地版。
- CVAT 本地部署。
- 其他可导出 YOLO 格式的本地工具也可以。

导出格式：YOLO detection TXT。

目录建议：

```text
runtime/yolo_ufo_dataset/
  images/
    train/
    val/
    test/
  labels/
    train/
    val/
    test/
  ufo_rh_sticker.yaml
```

`ufo_rh_sticker.yaml` 示例：

```yaml
path: C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_ufo_dataset
train: images/train
val: images/val
test: images/test
names:
  0: rh_sticker
```

## 7. 标注规范

应该框住整张需要遮盖的 RH 标签：

- 包含条码。
- 包含 RH 号文字。
- 包含白色标签底。
- 包含标签边缘。
- 如果业务遮盖需要多盖一点，标注框可以比标签边缘外扩 2-4 个像素。

不应该标注：

- POD 页固定 RH 号区域，第一版由模板处理。
- 页眉原生条码。
- PDF 原本表格里的 Reference、DN、PO、SKU 等字段。
- 非 RH 标签的仓库贴纸。
- 只有表格线、黑块、盖章、签名的区域。

模糊情况：

- RH 标签被截断但仍需要遮盖：框住可见部分，并在后处理时外扩。
- 一页有多个 RH 标签：每个都单独标注。
- 一页没有 RH 标签：保留图片，但不要创建任何框；这类负样本很重要。
- 标签旋转或倾斜：用水平外接矩形框完整盖住，不需要做旋转框。

## 8. 样本量建议

先做小规模 pilot：

- Pilot：30-50 份 PDF。
- 页面数：约 150-300 页。
- 正样本：至少 80-150 个 RH 标签框。
- 负样本：至少 100 页没有 RH 标签或只有页眉条码、表格条码的页面。

如果 pilot 可用，再扩到：

- 100-200 份 PDF。
- 覆盖不同扫描质量、打印质量、贴标位置、页面方向、PDF 模板。
- 每次新增失败样本后做增量训练或重新训练。

数据切分必须按 PDF 文件切分，不要把同一个 PDF 的不同页面同时放进 train 和 val/test，否则验证结果会虚高。

推荐比例：

- train：70%
- val：20%
- test：10%

## 9. 训练环境

建议单独建立训练环境，不要直接污染当前项目 `.venv`。

原因：

- 当前项目是业务工具环境，主要用于 FastAPI、Excel、PDF、EML。
- YOLO/PyTorch/CUDA 包较大，版本变化快。
- 训练环境出问题不应该影响业务工具打包。

推荐：

- Windows 11。
- Python 3.11 或 3.12。
- NVIDIA 驱动正常，`nvidia-smi` 能看到 4070 Ti。
- PyTorch CUDA 版本按 PyTorch 官方安装页选择。
- Ultralytics 按官方文档安装并锁定版本。

基础检查命令：

```powershell
nvidia-smi
python --version
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
yolo checks
```

说明：

- GPT 不能替你在云端直接训练本地模型。
- GPT 可以写脚本、检查日志、分析漏判样本、设计标注规范。
- 真正的训练计算跑在本机 4070 Ti 或云 GPU 上。

## 10. 训练命令草案

安装示例，具体 CUDA 命令以 PyTorch 官方页面为准：

```powershell
python -m venv .venv-yolo
.\.venv-yolo\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install ultralytics
```

如果官方选择器给出的 CUDA 平台不是 `cu128`，以官方选择器结果为准。

训练示例：

```powershell
yolo detect train `
  model=yolo26n.pt `
  data="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_ufo_dataset/ufo_rh_sticker.yaml" `
  epochs=100 `
  imgsz=1024 `
  batch=-1 `
  device=0 `
  patience=30 `
  project="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_runs" `
  name="ufo_rh_sticker_pilot_v1"
```

参数说明：

- `device=0`：使用第一张 NVIDIA GPU。
- `batch=-1`：让 Ultralytics 自动按显存选择 batch，适合 4070 Ti。
- `imgsz=1024`：比默认 640 更适合小标签检测；如果显存吃紧可降到 800 或 960。
- `patience=30`：验证指标长期不提升时提前停止。
- `project` 放到 `runtime/`，避免训练输出进入 Git。

验证：

```powershell
yolo detect val `
  model="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_runs/ufo_rh_sticker_pilot_v1/weights/best.pt" `
  data="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_ufo_dataset/ufo_rh_sticker.yaml" `
  imgsz=1024 `
  device=0
```

预测抽查：

```powershell
yolo detect predict `
  model="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_runs/ufo_rh_sticker_pilot_v1/weights/best.pt" `
  source="C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100/runtime/yolo_ufo_dataset/images/test" `
  imgsz=1024 `
  conf=0.25 `
  save=True `
  save_txt=True `
  device=0
```

## 11. 评估标准

不要只看 mAP。业务指标更重要。

必须统计：

- 漏判页数：有 RH 标签但没有任何检测框。
- 漏判标签数：实际 RH 标签数 - 检出标签数。
- 误判页数：没有 RH 标签但检测出框。
- 严重误判：检测框盖住关键业务字段、表格金额、Reference DN、页眉条码等。
- 框覆盖质量：预测框是否完整覆盖标签，是否需要后处理外扩。

建议验收阈值：

- 测试集 RH 标签召回率 >= 98%。
- 业务人工抽查 20 份未参与训练的 PDF，不允许漏掉 RH 标签。
- 每 100 页严重误判 <= 1。
- 预测框经过后处理外扩后，能完整盖住标签。
- 最终进入自动遮盖前，仍必须先输出评估 PDF 让用户确认。

在这个业务里，漏判比误判更危险；但误判如果盖住重要字段，也会造成正式文件不可用。所以第一版建议保留“红框评估 PDF”作为人工复核关口。

## 12. 与重构后项目的集成方向

建议不要直接推翻 `tools/ufo_cover_detector.py`，而是在现有工具旁边加 YOLO 通道。

推荐新增或调整：

- `tools/ufo_yolo_predictor.py`：加载模型，输入页面图片，输出像素坐标框。
- `tools/ufo_pdf_render.py`：如有必要，抽出 PDF 渲染和坐标转换逻辑。
- `tools/ufo_cover_detector.py`：保留 CLI 入口，增加 `--model-path`、`--use-yolo`、`--conf` 参数。
- `tools/ufo_cover_detector_gui.py`：增加模型文件选择、置信度输入、检测方式选择。
- `app/modules/ufo_file/` 或 `app/modules/ufo_pdf/`：如果后续要把 UFO PDF 生成接入 Web 工作台，建议新增独立模块，不要塞进 `app/modules/ufo_mail/`，因为邮件生成和 PDF 生成是两个业务边界。

推荐输出结构：

```json
{
  "input_pdf": "RH2603378.pdf",
  "model": "best.pt",
  "pages": [
    {
      "page": 2,
      "boxes": [
        {
          "kind": "rh_sticker",
          "score": 0.91,
          "x0": 452.1,
          "y0": 737.3,
          "x1": 528.4,
          "y1": 774.8,
          "source": "yolo"
        }
      ]
    }
  ]
}
```

坐标转换注意：

- YOLO 在渲染图片像素坐标上预测。
- PDF 遮盖需要 PDF page point 坐标。
- 转换公式要保留渲染 DPI、图片宽高、PDF page rect 宽高。
- 后处理建议对预测框做轻微外扩，避免框太紧造成残留。

后处理建议：

- `conf` 初始值 0.25，用测试集调优。
- 对同一页重叠框做 NMS 或合并。
- 对极小框、极长页眉条码框做规则过滤。
- 对检测框统一外扩 2-4 mm。
- 保留当前 POD 固定框逻辑。

## 13. 最终 UFO PDF 生成方案

最终自动化流程建议：

1. 用户选择 RH PDF。
2. 用户填写 UFO 号码。
3. 系统渲染 PDF 页面。
4. POD 页按固定区域替换 RH 号和页眉条码。
5. 后续页用 YOLO 检测 RH 标签框。
6. 输出红框评估 PDF。
7. 用户确认后，系统生成最终 UFO PDF。
8. 最终 PDF 保存为新文件，例如 `UFO26051201_from_RH2603378.pdf`。

灰度贴图遮盖策略：

- 在目标框四周取样，而不是纯白填充。
- 避免取到文字、条码、表格线，可优先取目标框上下左右的空白区域。
- 生成覆盖图时做轻微 blur/noise，使其接近扫描背景。
- 如果四周都不是空白，降级为局部中位灰度填充。

## 14. 风险点

### 14.1 数据隐私

训练图片来自真实业务 PDF，可能包含客户信息、订单号、地址、金额等。默认不能上传到公开平台，不能提交 Git，不能发给无权限人员。

### 14.2 标注不一致

如果有人框条码、有人框整张贴纸，模型会学乱。必须先给标注人员 10-20 张样例，统一规则后再批量标。

### 14.3 负样本不足

页眉条码、表格线、Reference DN 区域都很像 RH 标签。如果负样本少，模型会误判。必须保留大量“没有 RH 标签但有类似结构”的页面。

### 14.4 PDF 渲染差异

训练时用 200 DPI，推理时用 300 DPI，可能导致框尺度和效果变化。训练、验证、生产推理最好固定同一套 DPI 和图像预处理。

### 14.5 模型版本不可复现

必须记录：

- Python 版本。
- PyTorch 版本。
- Ultralytics 版本。
- CUDA 版本。
- 训练命令。
- 数据集版本。
- `best.pt` 来源。

### 14.6 误判造成文件损坏

自动遮盖如果误盖关键字段，会影响正式文件可用性。第一版必须保留评估 PDF 人工确认，不要直接生成最终遮盖文件。

## 15. 第一轮实施计划

### MVP

- 写一个 PDF 批量渲染脚本，把样本 RH PDF 转成 PNG。
- 建立 `runtime/yolo_ufo_dataset/` 数据目录。
- 标注 30-50 份 PDF。
- 训练 `rh_sticker` 单类检测模型。
- 用 holdout PDF 输出预测图片和红框评估 PDF。
- 只做评估，不做正式遮盖。

### Next

- 把 `best.pt` 接进 `tools/ufo_cover_detector.py`。
- GUI 增加模型路径、置信度、检测方式。
- 输出 JSON 检测结果。
- 对预测框做外扩、过滤、合并。
- 将 YOLO 结果和 POD 固定框合并到同一份评估 PDF。

### Later

- 用户确认评估框后生成最终 UFO PDF。
- 做灰度贴图遮盖。
- 做模型版本管理和数据集版本管理。
- 把失败样本收集成再训练数据。
- 视需要导出 ONNX/TensorRT，用于更快推理。

## 16. 交给下一位开发者的最小任务清单

1. 先不要改正式业务 PDF，先做训练数据准备脚本。
2. 从 30-50 份 RH PDF 渲染页面图片。
3. 按本文档标注 `rh_sticker`。
4. 建立 `ufo_rh_sticker.yaml`。
5. 在单独 YOLO 环境里确认 4070 Ti 可用。
6. 训练 pilot v1。
7. 对未参与训练的 PDF 生成预测图。
8. 整理漏判/误判样例。
9. 如果 pilot 召回率不够，补标失败样本再训。
10. 达到验收标准后，再进入项目集成。

## 17. 当前可复用资产

已有：

- PDF 渲染逻辑：`tools/ufo_cover_detector.py`
- POD 固定框逻辑：`POD_FIXED_BOXES`
- 检测结果数据结构：`DetectionBox`
- 红框评估 PDF 输出逻辑：`draw_assessment_pdf`
- GUI 壳：`tools/ufo_cover_detector_gui.py`
- 重构后的 UFO 邮件模块：`app/modules/ufo_mail/`

需要新增：

- PDF 页面批量导出图片脚本。
- YOLO 标注数据目录。
- YOLO 训练环境。
- YOLO 推理封装。
- 失败样本复盘记录。

## 18. 验收口径

训练任务完成不等于 UFO 文件生成功能完成。

训练任务完成的标准：

- 有可复现的数据集目录和 `yaml`。
- 有训练命令记录。
- 有 `best.pt` 模型。
- 有验证指标。
- 有至少 20 份未参与训练 PDF 的评估输出。
- 业务人工确认没有漏掉 RH 标签。
- 已知误判有记录，并说明是否可接受。

UFO 文件生成功能完成的标准：

- 输入 RH PDF 和 UFO 号。
- 输出评估 PDF。
- 用户确认后输出最终 UFO PDF。
- 原始 RH PDF 不被覆盖。
- POD RH 号替换正确。
- 后续页 RH 标签被完整遮盖。
- 遮盖区域视觉上接近周围灰度背景。

## 19. 参考资料

- Ultralytics YOLO 训练文档：https://docs.ultralytics.com/modes/train/
- Ultralytics CLI 文档：https://docs.ultralytics.com/usage/cli/
- PyTorch 本地安装文档：https://pytorch.org/get-started/locally/
