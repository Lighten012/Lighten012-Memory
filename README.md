# Lighten012-Memory

给 Codex 一份跨会话的个人记忆。你说“帮我记住，弯道回放要看刹车点”，Codex 会保存这条记录。下次问“之前想分析什么时候踩踏板？”，它可以用语义搜索找回原文。说“忘掉刚才那条赛车笔记”可以删除它。

[lighten012-memory skill](skills/lighten012-memory/SKILL.md) 告诉 AI 什么时候记、查、改、删。独立的 Python MCP 服务负责读写 SQLite。所有记录都可被这四个工具访问。向量可以交给 Ollama、OpenAI 官方 API 或其他兼容接口计算。

```text
Codex ──MCP──► 记忆服务 ──► SQLite（正文、属性和向量）
                  └──────► embedding 接口（本机或远端）
```

## 让 AI 按这份 README 安装

把仓库链接和这句话发给有终端权限的 AI 即可。

> 帮我按 README 安装 Lighten012-Memory。先问我需要选择的地方，再检查环境、补齐依赖，最后用一条临时记忆验证跨会话读写并删掉它。

### 安装前，先问用户

用户只说“帮我安装”时，先问下面两个问题，等用户选好再安装依赖、下载模型或调用 API。用户已经说清的部分直接沿用。尤其是“本地部署”可能只指数据库放在本机，仍需确认用谁的向量模型。

1. **记忆存在哪里？** “把记忆服务和数据库放在运行 Codex 的这台机器上，还是放在你的另一台服务器？如果已经有运行中的 Lighten012-Memory，也可以直接接入。”
2. **谁来计算向量？** “你想在记忆服务所在机器用 Ollama 跑模型，用另一台机器的 Ollama，直接用 OpenAI 的 embedding API，还是用其他兼容 API？”本机 Ollama 会占用本机资源。选择远端服务时，保存的正文和搜索词会发到该服务；使用 OpenAI 官方 API 会产生 API 用量。

只追问所选方案缺的信息。部署到另一台机器时，确认目标主机和可用的连接方式。选远端 Ollama 或其他兼容 API 时，确认接口基址和模型名。选 OpenAI 官方 API 时，服务地址已知，可建议 `text-embedding-3-small`，请用户在记忆服务机器上配置自己的 API 密钥，无需在聊天中粘贴。选本机 Ollama 时，先列出已安装的模型，有合适的就复用，需要下载时再确认模型名。若用户已有记忆服务，只需确认客户端可访问的 MCP 地址，直接完成第 1 步的客户端准备和第 4、5 步。

例如用户回答“记忆存在这台 Mac，向量直接用 OpenAI”，就应在 Mac 上部署 Python 服务和 SQLite，配置 OpenAI 接口，跳过整个 Ollama 安装步骤。

以下命令适用于 macOS 和 Linux。同一台机器上的命令可在同一个终端依次执行；切换终端后，按文中的赋值重新设置 `cfg` 和 `mcp_url`。

### 1. 准备程序和仓库

先检查 `git --version`、`uv --version` 和 `codex --version`。已有的程序可以直接用。macOS 有 Homebrew 时，缺少哪项就安装哪项，例如 `brew install git uv`、`brew install --cask codex`。Linux 可用系统包管理器安装 Git（Debian/Ubuntu 为 `sudo apt-get install git`），缺少 uv 时运行 `curl -LsSf https://astral.sh/uv/install.sh | sh`，缺少 Codex CLI 时运行 `curl -fsSL https://chatgpt.com/codex/install.sh | sh`。安装后重新打开终端或按安装器提示加载 PATH。首次使用 Codex 按客户端提示登录。[uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) · [Codex CLI 安装说明](https://developers.openai.com/codex/cli/)

```sh
# 建议选长期保留的位置，已克隆时直接进入原目录。
git clone https://github.com/Lighten012/Lighten012-Memory.git
cd Lighten012-Memory
uv sync --locked
```

uv 按锁文件创建 `.venv`，需要 Python 3.11 或更高版本；若没有合适的解释器，可先执行 `uv python install 3.12`。安装的 skill 链接指向这份仓库，后续在此更新。

### 2. 配置用户选好的 embedding 接口

**本机 Ollama。** 安装并启动 Ollama。macOS 可用 `brew install ollama` 和 `brew services start ollama`；已有 Ollama App 或服务时，直接复用。Linux 可运行 `curl -fsSL https://ollama.com/install.sh | sh` 安装 Ollama，使用 systemd 的机器可通过 `sudo systemctl start ollama` 启动服务。检查模型，缺少时再下载。[Ollama Linux 安装说明](https://docs.ollama.com/linux)

```sh
curl -fsS http://127.0.0.1:11434/api/version
ollama list
# 把下面的名字换成与用户选定的模型
model='qwen3-embedding:8b-q8_0'
ollama show "$model" >/dev/null || ollama pull "$model"
```

**远端 Ollama、OpenAI 官方 API 或其他兼容 API。** 跳过上面的安装和下载命令，直接在记忆服务所在机器上配置相应接口。

以上方案使用同一个配置文件。首次安装先创建，之后编辑原文件就能保留既有设置。

```sh
cfg_dir="${XDG_CONFIG_HOME:-$HOME/.config}/lighten012-memory"
mkdir -p "$cfg_dir"
cfg="$cfg_dir/service.env"
if [ ! -e "$cfg" ]; then (umask 077 && cp service.env.example "$cfg"); fi
```

| 选择 | `EMBEDDING_PROVIDER` | `EMBEDDING_BASE_URL` | `EMBEDDING_MODEL` | `EMBEDDING_API_KEY` |
|---|---|---|---|---|
| 本机 Ollama | `ollama` | `http://127.0.0.1:11434` | 已选的模型名，例如 `qwen3-embedding:8b-q8_0` | 留空 |
| 远端 Ollama | `ollama` | 用户的 Ollama 实例基址 | 该实例已安装的模型名 | 网关需要时设置 |
| OpenAI 官方 API | `openai` | `https://api.openai.com/v1` | 例如 `text-embedding-3-small` | 用户的 OpenAI API 密钥 |
| 其他兼容 API | `openai` | 供应方给出的 API 基址，通常以 `/v1` 结尾 | 供应方的 embedding 模型 ID | 供应方要求时设置 |

把所选行的值写入 `$cfg`，密钥保留在服务机的配置或进程环境里。Ollama 基址后由服务追加 `/api/embed`，OpenAI 官方和兼容基址后追加 `/embeddings`。默认 Ollama 模型请求 768 维；其他情况读取服务实际返回的维度。[Ollama embedding API](https://docs.ollama.com/api/embed) · [OpenAI embeddings API](https://developers.openai.com/api/reference/resources/embeddings/methods/create)

在仓库根目录先发送一句测试文本验证，输出一个正整数才表示模型可用。这一步不会写入记忆库。

```sh
uv run --locked --env-file "$cfg" python -c 'import sys; sys.path.insert(0, "tools"); import memory; print(len(memory.embed("部署测试")))'
```

### 3. 在保存数据库的机器上启动记忆服务

以下命令从仓库根目录执行。先检查所选端口。若输出 `lighten012-memory` 及四个工具名，说明服务已就绪，可以跳到第 4 步。

```sh
mcp_url="http://127.0.0.1:${LIGHTEN012_PORT:-8765}/mcp"
uv run --locked python tools/check.py "$mcp_url"
```

首次安装时，检查通常会提示连接失败。确认端口空闲后运行下面的命令。若端口已有其他服务，可先 `export LIGHTEN012_PORT=18765`，再按上一步重新设置并检查 `mcp_url`。

```sh
cfg="${XDG_CONFIG_HOME:-$HOME/.config}/lighten012-memory/service.env"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/lighten012-memory"
umask 077
mkdir -p "$state_dir"
nohup uv run --locked --env-file "$cfg" python tools/server.py \
  </dev/null >>"$state_dir/service.log" 2>&1 &
```

启动后再次运行 `uv run --locked python tools/check.py "$mcp_url"`，直到能列出四个工具。若进程退出或几秒后仍无法连接，查看 `tail -n 30 "$state_dir/service.log"`。机器重启后可重复本步骤。修改 `service.env` 后需重启服务才能生效，可通过 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 找到监听进程（端口按实际值替换），核对进程后再停止。

### 4. 在使用 Codex 的机器上安装 skill、注册工具

**先确定 Codex 连接的地址。** 同机部署时沿用第 3 步的 `mcp_url`。如果只有模型在云端，地址也照旧。只有记忆服务在另一台机器时，才需要从客户端建立 SSH 转发，例如 `ssh -N -L 18765:127.0.0.1:8765 user@your-memory-host`。保持隧道运行，在客户端另一终端设置 `mcp_url=http://127.0.0.1:18765/mcp`。服务机只需仓库、uv 和可达的模型；客户端准备仓库、uv 和 Codex 即可。

**安装 skill。** 在客户端的仓库根目录执行以下命令。默认安装到当前用户的 Codex，之后可以从任意项目使用。[Codex skill 位置](https://developers.openai.com/codex/skills/)

```sh
skills_dir="${LIGHTEN012_SKILLS_DIR:-$HOME/.agents/skills}"
skill_src="$(pwd -P)/skills/lighten012-memory"
skill_dest="$skills_dir/lighten012-memory"
mkdir -p "$skills_dir"
if [ ! -e "$skill_dest" ] && [ ! -L "$skill_dest" ]; then ln -s "$skill_src" "$skill_dest"; fi
test "$skill_dest" -ef "$skill_src"
```

最后一行成功表示已链接到这份仓库。若失败，用 `ls -ld "$skill_dest"` 查看同名目标，核对用户想使用哪一份。

**注册 MCP。** 先在客户端验证连通性，再查看 Codex 是否已有同名配置。[Codex MCP 配置](https://developers.openai.com/codex/mcp/)

```sh
uv run --locked python tools/check.py "$mcp_url"
codex mcp get lighten012-memory --json
```

只有查询提示未注册时，才执行下面的 `add`。已有配置的 `transport.url` 应等于 `$mcp_url`，且 `enabled` 为 `true`；两项都符合即可复用。同名配置不同则先核对目标服务。注册一次后，Codex 会从该服务发现全部四个工具。

```sh
codex mcp add lighten012-memory --url "$mcp_url"
codex mcp get lighten012-memory --json
```

### 5. 验证 Codex 真的能用

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

## 习惯与规则

这三个 Markdown 文件预留给用户填写，初始内容为空。安装环境时保留其现有内容。

- `habits/` 放项目习惯，例如 [Project-Habit.md](habits/Project-Habit.md)。
- `rules/` 放特定环境的规则，分别是 [内网项目规则](rules/Inner-Project-Rule.md) 和 [Tencent 项目规则](rules/Tencent-Project-Rule.md)。
