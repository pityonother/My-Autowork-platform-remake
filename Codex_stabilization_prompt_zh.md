# Codex 现场稳定化提示词

当你感觉 Codex 又开始混乱、Git 状态不清、命令跑不通、或者你不知道它到底改了什么时，直接复制下面这段给 Codex。

```text
请进入现场稳定化模式。

不要写代码。
不要修改任何文件。
不要清理 runtime。
不要启动隐藏后台服务。
不要 git add / commit / push / restore / reset / clean。
不要手动写 Git 对象。

请先读取 AGENTS.md，然后只做只读检查和整理。

本轮只需要输出：

【当前风险】
【命令环境状态】
【Git 状态】
【未提交改动清单】
【本轮真正相关改动】
【unrelated 残留改动】
【需要我手动确认的事项】
【下一步最安全动作】

如果你不能运行 git/python/powershell/cmd，请明确说明失败，不要绕过正常命令继续操作。
如果你的结果和我本机终端结果冲突，以我本机终端结果为准。
如果信息不足，请写“不确定”，不要猜。
```

---

## 用户本机检查命令

在项目文件夹地址栏输入 `cmd`，按回车，然后一条一条运行：

```bat
git --version
python --version
git status --short
git diff --stat
```

把结果贴给 Codex，再说：

```text
这是我本机普通 cmd 的结果。请以这个为准。
现在不要写代码，只分析当前状态和下一步建议。
```

---

## 只提交一个目标文件的安全提示词

```text
我只想保存本轮目标文件，不想提交 unrelated 残留。

请先只读分析：
1. git status --short
2. git diff --stat
3. git diff -- 目标文件

然后告诉我：
- 这个文件的改动是否都属于本轮目标；
- 有没有 unrelated change；
- 提交前还需要验证什么；
- 如果确认提交，应该运行哪两条命令。

不要使用 git add .。
不要 commit，直到我说可以保存。
```
