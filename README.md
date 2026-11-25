# Lighten Memory · 本地预览

这是可以实际新增、更新、检索的原型，默认独立使用本目录下的 `preview.sqlite3`，不接入已有笔记库，不修改 Codex 或 Ollama 配置。

## 你可以先看这些

- [Project-Habit.md](rules/Project-Habit.md)：做项目时的默认习惯。
- [Inner-Project-Rule.md](rules/Inner-Project-Rule.md)：内网项目要遵循的规则。
- [Tencent-Project-Rule.md](rules/Tencent-Project-Rule.md)：Tencent 公司项目要遵循的规则。
- `skills/shared-memory/SKILL.md`：告诉 AI 何时查记忆、何时写记忆。现在只是项目内预览，未安装。
- `tools/memory.py`：三个可运行的工具（新增、查询、更新）。预览用 Python 标准库，便于在这台 Mac 零安装试用；尚未封装成 Go 服务或 MCP。

三份文件都是空模板，由你手动维护，与记忆库分开。预览不会自动加载它们，记忆工具也不会修改它们。项目同时适用两份规则时，同时遵守；有冲突先确认。真实内网或公司要求请保留在相应的授权环境，不要填入公开仓库。

## 试一下

在终端打开本目录，运行下面的命令。它们只操作预览数据库，且只有你明确加上 `--share` 的记录才允许 AI 模式读取。

```sh
# 先进入你下载或克隆的项目目录
python3 tools/memory.py create '赛车遥测：我想在弯道回放里看刹车点。这个点子先不做。' --share --meta '{"status":"paused"}'
python3 tools/memory.py search '哪个想法是用来看入弯时什么时候踩踏板的？' --as-ai
python3 tools/memory.py update 1 '赛车遥测准备试做，先只录刹车和车速。' --meta '{"status":"ready"}'
python3 tools/memory.py search '遥测' --as-ai
```

首次运行使用已有的本地 Ollama 模型 `qwen3-embedding:8b-q8_0`，会比后续查询慢。默认向量为 768 维，只是预览值。没有下载新模型；原文发给本机回环地址上的 Ollama，不交给外部 API。

## 底层与边界

- `memories` 保存正文、可见性、时间和可选 JSON 属性，不要求标题、目录、标签或项目 ID。
- `memory_vectors` 保存模型名、维度、正文版本和预计算向量。正文先保存；模型失败时，记录依然可以用文字搜索。正文改了，旧向量在事务里作废。
- 文字用不区分大小写的整串匹配，涵盖 `Go`、`循环` 之类短词；语义用精确余弦扫描，两路一起排序。原型没有 ANN 索引。
- `--as-ai` 是给你观察可见性差异的模拟开关，不是权限隔离。验收后应由单独的服务实施权限，不能给 AI 一个可以绕过服务直接读数据库的账号或执行环境。
- 下一步才是 Go 服务、网页编辑、真正的权限控制和 MCP 接入。这次没有部署、自动同步或让 dot 直接写入。

参考：[Ollama Embedding API](https://docs.ollama.com/api/embed)。
