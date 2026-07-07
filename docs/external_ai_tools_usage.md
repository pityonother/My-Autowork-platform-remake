# 外部 AI 工具项目使用说明

本文件记录当前机器上已安装或保留的外部成熟工具项目，以及它们适合我们的应用场景。默认规则：外部成熟项目源码统一放在 `C:\Users\ac\tools-projects`，不要混入当前业务仓库。

## 总览

| 工具 | 当前状态 | 主要用途 | 默认使用建议 |
| --- | --- | --- | --- |
| codebase-memory-mcp | 已安装，可用 | 代码索引、调用链、架构图、3D 图 | 查代码结构时优先用 |
| Agent-Reach | 已安装，12/15 渠道可用 | 给 Agent 增强联网读取、搜索、YouTube/RSS/GitHub/V2EX/B站/X/小红书能力 | 做网上调研时用 |
| cognee | 已安装 CLI/库，未配置 LLM key | 长期记忆、知识图谱、跨会话知识库 | 先小样本试，不直接喂业务隐私数据 |
| headroom | 已安装 CLI/代理，未默认启动 | 上下文压缩、token 节省、代理输出压缩 | 长对话/大量日志时按需启动 |
| agent-skills | 已安装 24 个 Codex 技能 | 工程流程技能包：spec、plan、build、test、review、ship 等 | 重启 Codex 后按任务触发 |
| worldmonitor | 已安装依赖，dev server 可运行 | 全球情报/风险/地图大屏参考项目 | 单独运行或参考，不并入业务仓库 |
| Autonomix | 已 clone 并校验插件描述，未接入具体 UE 项目 | Unreal Engine 编辑器 AI 插件 | 提供目标 `.uproject` 后再装进该项目 `Plugins` 并编译 |

`worldmonitor` 是 AGPL-3.0-only 项目，默认只作为单独运行或参考项目，不把源码复制进当前私有业务项目。

## 路径

源码和虚拟环境：

```text
C:\Users\ac\tools-projects\codebase-memory-mcp
C:\Users\ac\tools-projects\Agent-Reach
C:\Users\ac\tools-projects\cognee
C:\Users\ac\tools-projects\headroom
C:\Users\ac\tools-projects\agent-skills
C:\Users\ac\tools-projects\worldmonitor
C:\Users\ac\tools-projects\Autonomix
C:\Users\ac\tools-projects\.venvs\agent-reach
C:\Users\ac\tools-projects\.venvs\cognee
C:\Users\ac\tools-projects\.venvs\headroom
```

工具配置和缓存：

```text
C:\Users\ac\AppData\Local\Programs\codebase-memory-mcp
C:\Users\ac\.cache\codebase-memory-mcp
C:\Users\ac\cbm-lightviews
C:\Users\ac\.mcporter\mcporter.json
C:\Users\ac\.agents\skills\agent-reach
C:\Users\ac\.codex\skills
C:\Users\ac\.cognee
C:\Users\ac\.local\bin\yt-dlp.exe
C:\Users\ac\AppData\Roaming\yt-dlp\config
```

注意：`uv tool update-shell` 已把 `C:\Users\ac\.local\bin` 加入用户 PATH；已经打开的旧终端可能需要重启后才识别 `yt-dlp`。

## codebase-memory-mcp

用途：

- 快速索引当前业务代码。
- 查函数调用链、路由入口、模块关系。
- 用 3D 图看架构热点。
- 适合回答“这个功能从哪个入口进来”“谁调用了这个函数”“哪个模块最复杂”。

常用命令：

```powershell
$bin = "$env:LOCALAPPDATA\Programs\codebase-memory-mcp\codebase-memory-mcp.exe"
& $bin --version
& $bin --% cli --json list_projects "{}"
& $bin --% cli --json index_repository "{\"repo_path\":\"C:/Users/ac/Documents/New_project_2_pro_review_20260518_164100\",\"mode\":\"fast\"}"
```

3D 图：

```powershell
& "$env:LOCALAPPDATA\Programs\codebase-memory-mcp\codebase-memory-mcp.exe" --ui=true --port=9749
```

浏览器打开：

```text
http://localhost:9749
```

优先选择轻量项目：

```text
C-Users-ac-cbm-lightviews-NewProjectOverview
C-Users-ac-cbm-lightviews-NewProjectLight
```

我们的场景：

- 适合用于当前 Python/Flask 业务仓库的结构阅读。
- 适合辅助新 Codex 快速理解 Booking、UFO、dispatch、finance 等模块关系。
- 不适合代替真实样本验证、单元测试、端到端测试。

## Agent-Reach

用途：

- 让 Agent 更方便读取网页、RSS、YouTube 字幕、GitHub、V2EX、B站基础搜索。
- 适合做外部项目调研、竞品调研、GitHub 项目初筛、视频资料总结、RSS 监控。

已验证状态：

- Agent Reach v1.5.0。
- `mcporter` v0.12.2 已全局安装。
- Exa MCP 配置在 `C:\Users\ac\.mcporter\mcporter.json`。
- `yt-dlp` 已安装在 `C:\Users\ac\.local\bin\yt-dlp.exe`。
- yt-dlp 配置已写入 `C:\Users\ac\AppData\Roaming\yt-dlp\config`，内容为 `--js-runtimes node`。
- GitHub 已通过 `gh auth login` 登录，账号为 `pityonother`。
- OpenCLI v1.8.5 已安装并通过浏览器桥扩展连接，daemon 端口为 `19825`。
- `agent-reach doctor` 当前显示 12/15 渠道可用。
- 当前可用渠道包括：GitHub、网页、YouTube、V2EX、RSS、Exa 全网语义搜索、Twitter/X、Reddit、Facebook、Instagram、B站、小红书。

常用命令：

```powershell
$ar = "$env:USERPROFILE\tools-projects\.venvs\agent-reach\Scripts\agent-reach.exe"
& $ar --version
& $ar doctor
```

如果当前终端识别不到 `yt-dlp`，临时执行：

```powershell
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
```

可选渠道：

```powershell
& $ar install --channels=twitter
& $ar install --channels=xiaohongshu
& $ar install --channels=reddit
& $ar install --channels=facebook,instagram
& $ar install --channels=all
```

注意：Twitter/X、小红书、Reddit、Facebook、Instagram 当前走 OpenCLI 浏览器登录态。不要打印、导出或提交任何 cookie；如果登录态失效，让用户在浏览器重新登录后再复查。雪球、LinkedIn、小宇宙仍需单独配置。

我们的场景：

- 看 GitHub 仓库有没有用。
- 搜外部技术方案、库对比、竞品说明。
- 总结 YouTube 技术视频字幕。
- 读取网页/RSS/公开资料。

不适合：

- 处理公司私密数据。
- 在用户没确认的情况下抓取登录态平台。
- 绕过平台限制做高频采集。

## cognee

用途：

- 给 Agent 建长期记忆。
- 把文档、笔记、规则、项目资料整理成知识图谱。
- 支持 `remember`、`recall`、`forget`、`improve`。

已验证状态：

- cognee 1.2.2。
- CLI 可运行。
- 日志写入 `C:\Users\ac\.cognee\logs`。
- 当前未配置 `LLM_API_KEY`，所以不要直接跑正式记忆构建。

常用命令：

```powershell
$cg = "$env:USERPROFILE\tools-projects\.venvs\cognee\Scripts\cognee-cli.exe"
& $cg --version
& $cg --help
```

后续试用前需要配置模型 key，例如：

```powershell
$env:LLM_API_KEY = "你的 key"
& $cg remember "用户偏好：外部成熟工具项目默认放在 C:\Users\ac\tools-projects"
& $cg recall "外部工具项目默认放在哪里？"
```

我们的场景：

- 适合把长期项目经验、业务规则说明、部署规范、常见故障处理沉淀成可检索记忆。
- 适合未来做“公司知识库 / 项目大脑”。
- 可以和当前 memory 文件夹形成互补：memory 文件夹偏规则和历史摘要，cognee 偏可查询知识图谱。

不适合：

- 未经确认直接导入真实客户资料、财务文件、订单文件。
- 替代 Git、测试、真实样本验证。
- 在没有 key 和权限边界时默认后台运行。

## headroom

用途：

- 压缩 Agent 读取的大量日志、搜索结果、文件片段。
- 作为本地代理减少上下文 token。
- 适合长对话、大量工具输出、日志分析、代码库探索。

已验证状态：

- headroom 0.28.0。
- CLI 已安装。
- `headroom doctor` 可运行；当前代理未启动时会显示 proxy not reachable，这是正常状态。

常用命令：

```powershell
$hr = "$env:USERPROFILE\tools-projects\.venvs\headroom\Scripts\headroom.exe"
& $hr --version
& $hr doctor
```

启动代理：

```powershell
& $hr proxy --port 8787
```

另开终端验证：

```powershell
curl http://localhost:8787/health
```

临时让 OpenAI-compatible 客户端走它：

```powershell
$env:OPENAI_BASE_URL = "http://localhost:8787/v1"
```

包装 Codex/Claude 这类操作会改本机工具配置，默认不要自动执行。需要时先说明影响，再运行：

```powershell
& $hr wrap codex
& $hr unwrap codex
```

我们的场景：

- 当 Codex 输出/读取内容特别大、上下文反复爆掉时，作为实验性压缩层。
- 分析长日志、长搜索结果、长代码片段时可以试。
- 目前不建议默认包住 Codex，先按需单次试用。

不适合：

- 对准确性极高、不能接受压缩误差的真实业务数据处理。
- 在未确认时长期驻留后台或改 agent 配置。

## 使用优先级

当前业务项目里建议这样选：

1. 查当前代码结构：优先 `codebase-memory-mcp`。
2. 查网上资料、GitHub、视频、RSS：优先 `Agent-Reach`。
3. 做长期知识库/项目大脑实验：试 `cognee`。
4. 上下文太大、日志太长：试 `headroom`。
5. 需要更严格的软件工程流程：按需使用 `agent-skills`。
6. 看全球情报/风险地图大屏参考：单独运行 `worldmonitor`。
7. 做 Unreal Engine 编辑器内 AI 辅助原型：按项目接入 `Autonomix`。

## agent-skills

用途：

- 给 Codex 增加 24 个工程流程技能。
- 覆盖 spec、plan、build、test、review、ship、security、performance、debugging、documentation 等场景。
- 适合让新对话在复杂任务里更稳定地执行“先定义、再计划、再实现、再验证”的流程。

已安装状态：

- 源码保留在 `C:\Users\ac\tools-projects\agent-skills`。
- 24 个技能已安装到 `C:\Users\ac\.codex\skills`。
- 新技能需要重启 Codex 后才会被新的对话自动发现。

常用检查：

```powershell
Get-ChildItem "$env:USERPROFILE\.codex\skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } |
  Select-Object -ExpandProperty Name
```

我们的场景：

- 用于复杂功能、代码 review、测试策略、性能优化、安全检查、发布检查。
- 不需要每次手动引用所有技能；让 Codex 根据任务触发即可。
- 如果某个技能和当前项目 `AGENTS.md` 冲突，以当前项目 `AGENTS.md` 和用户当轮指令优先。

## worldmonitor

用途：

- 全球情报、地缘风险、市场/能源/供应链/地图大屏参考项目。
- 可单独作为本地 demo 运行，不建议并入当前业务仓库。

已安装状态：

- 源码路径：`C:\Users\ac\tools-projects\worldmonitor`。
- Node 依赖已通过 `npm ci` 安装。
- `npm run typecheck` 已通过。
- 当前 dev server 可运行在 `http://127.0.0.1:3000/`。
- `npm audit` 报告 20 个漏洞（2 low、16 moderate、2 high）；未执行 `npm audit fix`，避免自动改 lockfile。

启动命令：

```powershell
cd C:\Users\ac\tools-projects\worldmonitor
npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:3000/
```

停止：

```powershell
Ctrl+C
```

我们的场景：

- 参考地图大屏、实时 feed、情报面板、数据源组织、风险雷达 UI。
- 可用于研究“供应链/港口/能源/地缘事件”类看板。
- 因为许可证是 AGPL-3.0-only，默认只单独运行或参考设计，不复制源码进私有业务项目。

## Autonomix

用途：

- Unreal Engine 编辑器内 AI 助手插件。
- 用自然语言辅助创建或修改 Blueprint、Widget、Material、Input、关卡对象等编辑器内容。
- 适合独立 UE 原型项目里试验“让 AI 直接参与编辑器工作流”。

已安装状态：

- 源码路径：`C:\Users\ac\tools-projects\Autonomix`。
- 当前 commit：`47a46ae8cc3f00230edceeb33f0d4f9d80cb185b`。
- `Autonomix.uplugin` 已校验可解析：`VersionName` 是 `1.1.0`，包含 5 个 Editor 模块。
- 插件依赖包括 `EditorScriptingUtilities`、`EnhancedInput`、`DataValidation`，可选依赖包括 `PythonScriptPlugin`、`GameplayAbilities`。
- README 要求 Unreal Engine 5.3+，并说明测试过 5.3、5.4、5.5；需要 Visual Studio 2022 或兼容 C++ 编译器。
- 许可证是 MIT。
- 当前只是“本体保留并校验”，还没有装进某个具体 Unreal 项目，因为这一步必须知道目标 `.uproject` 路径并编译验证。

接入具体 Unreal 项目：

```powershell
$project = "C:\Users\ac\Documents\Unreal Projects\YourProject"
$src = "C:\Users\ac\tools-projects\Autonomix"
$dest = Join-Path $project "Plugins\Autonomix"

New-Item -ItemType Directory -Force (Join-Path $project "Plugins")
if (Test-Path $dest) {
  throw "目标插件目录已存在，请先人工确认是否覆盖：$dest"
}
Copy-Item -LiteralPath $src -Destination $dest -Recurse
```

然后：

1. 右键 `.uproject`，选择 `Generate Visual Studio project files`。
2. 用 IDE build 项目，或启动 Unreal Engine 让它自动编译。
3. 在 Unreal 里进入 `Edit -> Plugins`，搜索 `Autonomix`，确认启用后重启编辑器。
4. 在 `Edit -> Project Settings -> Plugins -> Autonomix` 配置模型服务。

模型配置：

- 云模型：Anthropic、OpenAI、Azure OpenAI、Google Gemini、DeepSeek、Mistral、xAI、OpenRouter 等，需要对应 API key。
- 本地模型：Ollama 默认 `http://localhost:11434`，LM Studio 默认 `http://localhost:1234`。
- 不要把 API key 写进仓库；只在 Unreal 项目设置、本机环境或受控配置里保存。

我们的场景：

- 适合用于独立 Unreal 原型项目，加速 Blueprint、UI、材质、输入配置、关卡实验。
- 可以和 Unreal MCP/编辑器自动化形成互补，但不要把它当成普通命令行工具；它需要项目内插件编译和编辑器启用。
- ARK DevKit 或其他非标准 Unreal 环境不要默认安装，先单独确认 UE 版本、插件依赖、项目插件目录、编译日志和回退方式。

## 安全和边界

- 外部项目源码不要复制进当前业务仓库。
- 真实业务文件、客户资料、财务数据、订单数据不要默认导入这些工具。
- 需要 API key、Cookie、浏览器登录态的平台，必须先让用户确认。
- GPL / AGPL / 商业限制许可证项目只做参考或单独运行，不能直接复制进私有业务代码。
- 启动长期后台服务前必须说明端口、停止方式和影响范围。

## 快速检查

```powershell
& "$env:LOCALAPPDATA\Programs\codebase-memory-mcp\codebase-memory-mcp.exe" --version
& "$env:USERPROFILE\tools-projects\.venvs\agent-reach\Scripts\agent-reach.exe" doctor
& "$env:USERPROFILE\tools-projects\.venvs\cognee\Scripts\cognee-cli.exe" --version
& "$env:USERPROFILE\tools-projects\.venvs\headroom\Scripts\headroom.exe" doctor
Get-ChildItem "$env:USERPROFILE\.codex\skills" -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') } | Measure-Object
cd "$env:USERPROFILE\tools-projects\worldmonitor"; npm run typecheck
$u = Get-Content "$env:USERPROFILE\tools-projects\Autonomix\Autonomix.uplugin" -Raw | ConvertFrom-Json; $u | Select-Object FriendlyName, VersionName, Category
```
