# Lighten012-Memory

给 Codex 一份跨会话的个人记忆。你说“帮我记住，弯道回放要看刹车点”，Codex 会保存这条记录。下次问“之前想分析什么时候踩踏板？”，它可以用语义搜索找回原文。说“忘掉刚才那条赛车笔记”可以删除它。

[lighten012-memory skill](skills/lighten012-memory/SKILL.md) 告诉 AI 什么时候记、查、改、删。独立的 Python MCP 服务负责读写 SQLite。所有记录都可被这四个工具访问。Ollama 或兼容 API 负责计算向量，模型可以和服务在同一台机器，也可以在云端。

```text
Codex ──MCP──► 记忆服务 ──► SQLite（正文、属性和向量）
                  └──────► embedding 接口（本机或远端）
```

## 让 AI 按这份 README 安装

可直接给有终端权限的 AI 这段话，按实际部署替换方括号部分。

> 请按 Lighten012-Memory 的 README 安装到当前用户的 Codex。我的模型是［本机 Ollama / 远端 Ollama 的地址和模型名 / OpenAI 兼容 API 的基址和模型名］。请检查已有环境，补齐缺项，启动服务，安装 skill 并注册工具。用一条专门的测试记忆验证跨会话读写，再按它的 ID 删除。完成时告诉我数据库位置、实际使用的模型以及各项验收结果。

下列命令适用于 macOS 和 Linux 的终端。默认让记忆服务与 Codex 同机，通过 `127.0.0.1:8765` 连接。只把模型放到云端可以直接用这个默认布局。

### 1. 准备程序和仓库

先检查 `git --version`、`uv --version` 和 `codex --version`。已有的程序可以直接用。macOS 有 Homebrew 时，缺少哪项就安装哪项，例如 `brew install git uv`、`brew install --cask codex`。Linux 可用系统包管理器安装 Git（Debian/Ubuntu 为 `sudo apt-get install git`），缺少 uv 时运行 `curl -LsSf https://astral.sh/uv/install.sh | sh`，缺少 Codex CLI 时运行 `curl -fsSL https://chatgpt.com/codex/install.sh | sh`。安装后重新打开终端或按安装器提示加载 PATH。首次使用 Codex 按客户端提示登录。[uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) · [Codex CLI 安装说明](https://developers.openai.com/codex/cli/)

```sh
# 建议选长期保留的位置，已克隆时直接进入原目录。
git clone https://github.com/Lighten012/Lighten012-Memory.git
cd Lighten012-Memory
uv sync --locked
```

uv 按锁文件创建 `.venv`，需要 Python 3.11 或更高版本；若没有合适的解释器，可先执行 `uv python install 3.12`。安装的 skill 链接指向这份仓库，后续在此更新。

### 2. 选择 embedding 接口

**本机 Ollama。** 安装并启动 Ollama。macOS 可用 `brew install ollama` 和 `brew services start ollama`；已有 Ollama App 或服务时，直接复用。Linux 可运行 `curl -fsSL https://ollama.com/install.sh | sh` 安装 Ollama，使用 systemd 的机器可通过 `sudo systemctl start ollama` 启动服务。检查模型，缺少时再下载。[Ollama Linux 安装说明](https://docs.ollama.com/linux)

```sh
curl -fsS http://127.0.0.1:11434/api/version
ollama show qwen3-embedding:8b-q8_0 >/dev/null || ollama pull qwen3-embedding:8b-q8_0
```

**远端 Ollama 或兼容 API。** 确认记忆服务所在机器可以访问对应地址。只用远端模型时，本机只需 Git、uv 和 Codex。记忆服务会把待索引记录的正文和用于查找记忆的查询文本发往所选地址。请使用允许接收这些内容的服务。

三种方案使用同一个配置文件。首次安装先创建，之后编辑原文件就能保留既有设置。

```sh
cfg_dir="${XDG_CONFIG_HOME:-$HOME/.config}/lighten012-memory"
mkdir -p "$cfg_dir"
cfg="$cfg_dir/service.env"
if [ ! -e "$cfg" ]; then (umask 077 && cp service.env.example "$cfg"); fi
```

| 设置 | 本机 Ollama | 远端 Ollama | OpenAI 兼容 API |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` | `openai` |
| `EMBEDDING_BASE_URL` | `http://127.0.0.1:11434` | 你的 Ollama 实例基址 | 供应方给出的 API 基址，通常以 `/v1` 结尾 |
| `EMBEDDING_MODEL` | `qwen3-embedding:8b-q8_0` | 该实例中实际安装的模型名 | 供应方的 embedding 模型 ID |
| `EMBEDDING_API_KEY` | 留空 | 网关需要 Bearer 凭据时设置 | 供应方要求时设置 |

把上表对应值写入 `$cfg`，密钥保留在本机配置或进程环境里。Ollama 基址后由服务追加 `/api/embed`，OpenAI 兼容基址后追加 `/embeddings`。默认 Ollama 模型请求 768 维；其他情况读取服务实际返回的维度。[Ollama embedding API](https://docs.ollama.com/api/embed) · [OpenAI 兼容接口](https://docs.ollama.com/api/openai-compatibility)

在仓库根目录先发送一句测试文本验证，输出一个正整数才表示模型可用。这一步不会写入记忆库。

```sh
uv run --locked --env-file "$cfg" python -c 'import sys; sys.path.insert(0, "tools"); import memory; print(len(memory.embed("部署测试")))'
```

### 3. 启动服务、安装 skill、注册 MCP

```sh
./scripts/install.sh
codex mcp get lighten012-memory --json
```

脚本按锁文件准备环境，在后台启动或复用回环地址上的服务，实际握手并核对四个工具。随后把 skill 链接到 `~/.agents/skills/lighten012-memory`，并执行下列注册。相同配置重复安装会复用现有服务、数据库和注册项。若已有同名 skill 指向其他位置或同名 MCP 地址不同，脚本会给出冲突位置或原因。[Codex skill 位置](https://developers.openai.com/codex/skills/) · [Codex MCP 配置](https://developers.openai.com/codex/mcp/)

```sh
# 安装脚本会执行；手工注册时也可以独立使用。
codex mcp add lighten012-memory --url http://127.0.0.1:8765/mcp
```

要换监听端口，可运行 `LIGHTEN012_PORT=18765 ./scripts/install.sh`。直接执行脚本适合个人机器，重启机器后再运行一次。修改 `service.env` 后要重启记忆服务，正在运行的进程不会重新读取文件。日志默认在 `~/.local/state/lighten012-memory/service.log`，可用 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 查看监听进程，核对是本项目的 Python 服务后再用 `kill <PID>` 停止它。

**如果记忆服务也要放在另一台机器**，在服务机完成第 1、2 步中的 uv、仓库和模型配置，运行下面的服务命令。该机器只需要能访问 SQLite 和所选模型。可交给已有的进程管理器常驻。回环监听让库内所有记录只通过本机或受信任的隧道访问。

```sh
# 服务机，保持进程运行
uv run --locked --env-file "$cfg" python tools/server.py

# Codex 客户端，先建立 SSH 转发，保持此连接
ssh -N -L 18765:127.0.0.1:8765 user@your-memory-host

# 客户端的另一终端，在仓库中安装 skill 并注册转发地址
./scripts/install.sh --client-only http://127.0.0.1:18765/mcp
```

### 4. 验证 Codex 真的能用

在仓库以外的目录打开新 Codex 会话。可用 `$lighten012-memory` 显式指定 skill，也可以直接用自然语言。若列表仍是旧的，重启 Codex。下面的流程只涉及刚创建的测试记录。

1. 说“帮我记住一条安装测试记忆：我想在赛车回放里看入弯前的刹车点。请给我记录 ID。”检查工具返回 `saved: true`、`indexed: true`，记下实际 ID。
2. 换一个新会话，问“安装测试里，我之前想分析什么时候踩踏板？”检查找回的是同一个 ID；不同措辞可以验证语义路径。
3. 说“把这条测试记忆改成只记录刹车压力和车速。”检查 ID 未变、`revision` 增加，再搜一次核对新正文。
4. 说“忘掉 ID 为［实际 ID］的这条安装测试记忆。”检查 `deleted: true`。再搜相同描述，其他相似笔记仍可能出现，刚删的 ID 应已消失。

## 工具与数据

| 工具 | 用法 |
|---|---|
| `memory_create(body, meta?)` | 保存一条记忆。返回 ID 和是否成功生成向量。 |
| `memory_search(query, limit?)` | 按文字和语义找回候选，默认 5 条，可取 1–50 条。文字命中优先，同组按余弦相似度排序。 |
| `memory_update(id, body, meta?)` | 按 ID 更正正文。省略属性会保留原值，传对象会替换属性。更新后旧版本向量立即失效。 |
| `memory_delete(id)` | 永久删除一个 ID 的正文和向量。ID 已不存在时返回 `deleted: false`。后续新增记忆会使用新 ID。 |

SQLite 默认位置是 `~/.local/share/lighten012-memory/memory.sqlite3`，设置了 `XDG_DATA_HOME` 时改用相应的数据目录。也可在 `service.env` 里用 `LIGHTEN012_DB` 指定绝对路径。只有明确要沿用旧预览库时才将它指向 `preview.sqlite3`；首次打开会在事务中迁移，保留 ID、原文、属性、时间和有效向量，旧 `private` 记录也会变为可查。迁移前可用 SQLite 的 `.backup` 保存一致快照。

默认检索会扫描当前模型和维度匹配的向量。模型离线时，正文仍可保存和按文字找回，`embedding_warning` 会说明失败。模型恢复后可对缺向量的记录重新调用更新。变更模型或服务基址后，新查询只比较同一配置生成的向量；旧记录仍支持文字搜索，更新后会按新配置建索引。

需要排查时，可在仓库根目录运行 `uv run --locked python tools/check.py http://127.0.0.1:8765/mcp` 检查 MCP 握手和工具清单。CLI 与 MCP 共用同一套逻辑，例如 `uv run --locked --env-file "$cfg" python tools/memory.py search '刹车'`。运行 `uv run --locked python -m unittest discover -s tests -v` 会使用临时数据库做回归测试。

[项目习惯](rules/Project-Habit.md)、[内网项目规则](rules/Inner-Project-Rule.md) 和 [Tencent 项目规则](rules/Tencent-Project-Rule.md) 是由你手工维护的空模板，与记忆库独立。
