# Git + Codex 小白使用指南（更新版）

> 目标：你不需要成为程序员，也能用 Git 降低 Codex 改坏项目的风险。  
> 核心思想：Git 是“存档点”，Codex 是“执行者”，你负责确认关键按钮。  
> 本版新增：Codex 会话异常、命令环境异常、只提交目标文件、如何处理未提交残留。

---

## 1. Git 到底是什么？

可以把 Git 理解成游戏里的“存档系统”。

- **仓库 repo**：被 Git 管理的项目文件夹。
- **commit**：一个存档点。项目能跑的时候就存一下。
- **diff**：这次和上次相比，改了哪里。
- **branch 分支**：开一条临时路线试改，不影响主线。
- **restore**：把还没存档的改动撤回。
- **GitHub**：把 Git 仓库放到云端，方便备份、同步、让 Codex/ChatGPT 读取。

你不需要一开始学全，只需要掌握：

```text
git status   看现在脏不脏
git diff     看 Codex 改了什么
git commit   存一个安全点
git restore  撤回没保存的改动
```

---

## 2. 我每次都要自己操作 Git 命令吗？

不一定。

### 情况 A：Codex 能正常运行 Git

Codex 通常可以帮你运行命令、查看 diff、跑测试。你的任务是：

- 让 Codex 先解释命令。
- 让 Codex 先跑低风险检查命令。
- 对提交、删除、回滚、push 这类动作做确认。

你可以这样要求 Codex：

```text
我不懂 Git。你可以帮我运行只读检查命令，比如 git status 和 git diff。
但任何会修改文件、提交、删除、回滚、push 的命令，都必须先解释风险并等我确认。
```

### 情况 B：Codex 不能正常运行 Git，但你电脑可以

这次你遇到的就是这种：Codex 旧会话里 `git/python/powershell/cmd` 启动失败，但你自己的 cmd 里正常。

这时以**你本机普通终端结果**为准。

你手动跑：

```bat
git --version
python --version
git status --short
git diff --stat
```

然后把结果贴给 Codex。让它只分析，不要写代码。

提示词：

```text
我已经在本机普通 cmd 里跑了这些命令。请以后以我本机结果为准。
现在不要写代码、不要 git add、不要 commit、不要 restore、不要 reset、不要 clean、不要 push。
只分析当前工作区状态和下一步建议。
```

### 情况 C：你电脑和 Codex 都不能正常运行 Git/Python

如果你在自己终端也看到 Git、Python、PowerShell、cmd 无法启动，或者出现 `0xC0000142` / `-1073741502` 之类错误，先不要开发。

建议顺序：

1. 重启电脑。
2. 重新打开项目文件夹。
3. 先跑：

```bat
git --version
python --version
git status --short
```

恢复后再让 Codex 继续。

---

## 3. 最小安全流程：每次让 Codex 做事前后都这样

### 开始前

让 Codex 做：

```text
请先读取 AGENTS.md。
请先运行或指导我运行：

git status --short

然后告诉我：
1. 现在项目是否干净；
2. 有没有上次没保存的改动；
3. 是否有 unrelated 残留；
4. 是否建议先 commit 再继续。
不要写代码。
```

### Codex 改完后

让 Codex 做：

```text
请先不要继续改。
请给我：
1. git status --short
2. git diff --stat
3. 本轮改了哪些文件
4. 每个文件为什么改
5. 如何验证
6. 是否建议 commit
```

### 你确认满意后

你可以让 Codex 准备 commit：

```text
我确认这轮可以保存。
请告诉我需要 git add 哪些文件，并给一个 commit message。
不要 push。
不要使用 git add .。
```

---

## 4. 第一次给项目加 Git：小白版

> 建议：第一次做之前，先手动复制整个项目文件夹，作为额外保险。

### 第 0 步：确认 Git 是否安装

在终端 / PowerShell 输入：

```bash
git --version
```

如果能看到版本号，说明已安装。

### 第 1 步：进入项目文件夹

Windows PowerShell 示例：

```powershell
cd "你的项目路径"
```

或者在项目文件夹地址栏输入：

```text
cmd
```

按回车，会直接在当前项目目录打开命令行。

### 第 2 步：初始化 Git

```bash
git init
```

这一步只是让当前文件夹变成 Git 仓库。

### 第 3 步：创建 `.gitignore`

`.gitignore` 是“不要被 Git 存档的文件清单”。

通用小白版：

```gitignore
# secrets
.env
*.env
*.key
*.pem
*.p12
*.pfx

# Python
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/

# Node
node_modules/
dist/
build/
.next/
.nuxt/

# local runtime data
runtime/uploads/
runtime/outputs/
runtime/archive/
uploads/
outputs/
*.db
*.sqlite
*.sqlite3

# Office temp files
~$*.xlsx
~$*.docx
~$*.pptx

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/
```

### 第 4 步：检查会被 Git 管理的文件

```bash
git status --short
```

如果看到 `.env`、真实客户文件、数据库、上传文件、输出文件出现在列表里，先停下，不要 commit。

把结果贴给 Codex：

```text
这是 git status --short 的结果。请帮我判断有没有不该提交的敏感文件或业务文件。不要执行 git add。
```

### 第 5 步：第一次存档

确认没有敏感文件后：

```bash
git add .
git commit -m "chore: initial project checkpoint"
```

注意：只有第一次初始化、且你确认没有敏感文件时，才可以考虑 `git add .`。平时开发不建议这样用。

---

## 5. 每次开发的推荐流程

### 1）先确认当前干净

```bash
git status --short
```

如果没有输出，说明很干净。

如果有输出，比如：

```text
 M dispatch_mail_store.py
```

说明这个文件有未提交改动。

如果有很多文件，比如：

```text
 M booking_store.py
 M dispatch_mail_store.py
 M invoice_reconciler.py
```

不要继续开发。先让 Codex 分类：

```text
请不要写代码。
请把这些未提交文件分成：
1. 本轮相关；
2. unrelated 残留；
3. 不确定，需要我确认。
```

### 2）让 Codex 做小范围改动

```text
请读取 AGENTS.md。
本轮只做：
不做：
验收标准：
先计划，不要写代码。
```

### 3）看它改了什么

```bash
git diff --stat
git diff
```

如果只想看某个文件：

```bash
git diff -- 文件名
```

例如：

```bash
git diff -- dispatch_mail_store.py
```

### 4）满意就保存

只 add 目标文件：

```bash
git add 文件名1 文件名2
git commit -m "简短说明这次改了什么"
```

例子：

```bash
git add dispatch_mail_store.py
git commit -m "fix: split final dispatch email table image"
```

不要用：

```bash
git add .
git add -A
```

因为它们可能把 unrelated 残留一起提交。

### 5）不满意就先别撤回，先问清楚

撤回命令很有用，但对小白有风险。

撤回单个文件：

```bash
git restore 文件名
```

撤回本轮所有未提交改动：

```bash
git restore .
```

注意：`git restore .` 会丢掉所有未提交改动。用之前让 Codex 帮你确认。

---

## 6. 哪些命令安全，哪些命令危险？

### 安全：通常只是查看

```bash
git status --short
git diff --stat
git diff
git diff -- <file>
git log --oneline -5
git branch --show-current
```

### 中等风险：会改变 Git 状态，但通常可控

```bash
git add <file>
git commit -m "..."
git switch -c <branch>
git restore <file>
git revert <commit>
```

### 高风险：小白不要直接跑

```bash
git reset --hard
git clean -fd
git clean -fdx
git add .
git add -A
rm -rf ...
del /s ...
rmdir /s ...
```

看到这些命令时，先问：

```text
这条命令会不会删除文件、丢失未提交改动，或把 unrelated 文件加入提交？有没有更安全的替代方案？
```

---

## 7. 这次事件给你的固定处理法

### 7.1 Codex 说有很多未提交文件，但你怀疑不对

你自己在项目目录跑：

```bat
git status --short
```

以你看到的结果为准。

如果 Codex 旧会话的信息和你的本机结果冲突，告诉 Codex：

```text
你之前看到的 Git 状态已过期。请以我刚刚贴出的本机 git status --short 为准。
不要继续引用旧状态。
```

### 7.2 只剩一个文件改动时

比如：

```text
 M dispatch_mail_store.py
```

这是好状态。你可以继续：

```bat
git diff --stat
git diff -- dispatch_mail_store.py
python -m py_compile dispatch_mail_store.py
```

然后根据验收结果决定是否提交。

### 7.3 提交成功后

提交后再看：

```bat
git status --short
```

如果没有输出，说明当前很干净。

你可以告诉 Codex：

```text
我已经提交成功，git status --short 没有输出。
当前工作区干净。接下来继续时请从 AGENTS.md 开始，先计划，不要直接写代码。
```

---

## 8. 用 GitHub 是必须的吗？

不是必须。

### 只用本地 Git

适合：你只是想有存档点、能回退、知道 Codex 改了什么。

优点：简单，不用上传代码。

### 用 GitHub 私有仓库

适合：你想云端备份、跨设备、让 ChatGPT/Codex 更方便读你的仓库。

注意：

- 建议用 private repo。
- 不要上传 `.env`、真实业务文件、数据库、客户资料。
- push 之前一定看 `.gitignore` 和 `git status`。

---

## 9. 给 Codex 的 Git 小白提示词

每次新任务前可以发：

```text
请读取 AGENTS.md。
我不熟悉 Git，所以你必须按小白模式协助我：

1. 开始前先检查 git status --short。
2. 不要直接运行高风险命令。
3. 每次只给我 1–3 个操作。
4. 所有 Git 命令都要解释用途和风险。
5. 修改后必须给 git diff --stat 和修改文件清单。
6. 不要 commit，除非我说“可以保存”。
7. 不要 push，除非我明确说“可以推到 GitHub”。
8. 不要使用 git add .，除非我明确说“提交全部”。
9. 如果 Codex 内部命令失败，以我本机终端结果为准。

本轮目标：
只做：
不做：
验收标准：

先计划，不要写代码。
```

如果你很累，只发这个：

```text
按 AGENTS.md 和 Git 小白模式执行。先检查状态，再计划，不要写代码。
```

如果现场混乱，发这个：

```text
进入现场稳定化模式。不要写代码。
只整理当前 Git 状态、未提交改动、命令环境和下一步建议。
不要 git add / commit / restore / reset / clean / push。
```

---

## 10. 最小口诀

```text
先看状态：git status
再让 Codex 计划
确认范围再改
改完看差异：git diff
只 add 目标文件
满意再存档：git commit
不满意先诊断，不急着 restore
```

你不需要一次学会 Git。先学会“看改动”“只提交目标文件”和“存档点”，就已经能把 Codex 合作的风险降很多。
