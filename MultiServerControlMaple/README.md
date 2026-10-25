# MultiServerControlMaple

一个基于 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 的多子服控制插件。

> By: Morning_Maple

> 已在主服内实现子服的查看 / 启动 / 关闭 / 重启，以及把主服存档全量同步到子服；并对外分发自定义事件。启停功能**仅适配 Windows**。

## 背景

服务器资源有限，但又想多开几个服务器，并希望通过一个主服务器（如生存服）来控制其他子服务器（镜像、创造、小游戏等），直接在主服开关子服，方便操作。本插件参考自 [Morning-Maple/MultiServerControl](https://github.com/Morning-Maple/MCDRPlugin/tree/master/MultiServerControl)，按 Maple 系插件的工程规范重写。

## 依赖

- `mcdreforged >= 2.15.7`

## 安装

1. 将打包好的 `MultiServerControlMaple-vX.Y.Z.mcdr` 放入 MCDR 的 `plugins/` 目录（或直接放入 `multi_server_control_maple/` 源码文件夹）。
2. 在 MCDR 控制台执行 `!!MCDR reload plugin multi_server_control_maple`。

打包源码为 `.mcdr` 文件：

```bash
python pack.py
```

## 命令

> 命令前缀固定为 `!!mscm`（本插件不与市面插件冲突，无需前缀切换开关）。

| 命令 | 说明 |
|---|---|
| `!!mscm` / `!!mscm help` | 显示帮助 |
| `!!mscm show` | 查看所有子服信息（名字 / 可同步或独立 / 在线离线 / 人数） |
| `!!mscm show <名字>` | 查看指定子服详情（在线人数、在线玩家名单、`[同步] [停止/开启] [重启]` 与 `[连接到此服务器]`） |
| `!!mscm sync <名字>` | 把主服存档全量镜像同步到子服（需二次确认） |
| `!!mscm start <名字>` | 启动子服（仅 Windows） |
| `!!mscm stop <名字>` | 关闭子服，依赖 rcon（需二次确认） |
| `!!mscm restart <名字> [sync]` | 重启子服，可选先同步主服存档（需二次确认） |
| `!!mscm reload` | 重载配置 |

> 子服在线与否、人数通过 Server List Ping（SLP）探测：能 ping 通即视为「玩家可进入」=在线。
> `[连接到此服务器]` 走 Velocity 的 `/server <英文名>`；show 详情里的 `[同步]`/`[停止或开启]`/`[重启]` 均为可点击按钮，点击后对应命令（sync/stop/restart）会各自弹出二次确认。
> 所有二次确认都同时提供 `[确认]`/`[取消]` 可点击按钮与命令式输入（`... confirm` / `... cancel`）两种方式。

### sync（同步存档）

`!!mscm sync <英文名>` —— 把主服整个 `world` 全量镜像同步到子服。

- **镜像式**复制：先清空目标 world 再从主服拷贝，使子服与主服一致（会删除目标多余旧文件），不可撤销，故需二次确认（点 `[点击确认同步]` 或执行 `!!mscm sync <名字> confirm`）。
- 安全：`can_sync=false` 的独立服拒绝同步；目标子服在线则拒绝（须先关闭）；同步期间主服 `save-off` + `save-all flush`，结束后必定 `save-on`；`session.lock` 强制忽略，叠加配置的 `sync_ignore_files`（正则）。

#### 同步白名单（`sync_whitelist`）

用于让**子服保留自己的专属文件**，不被主服覆盖。典型场景：子服有自己的 `config/carpet.conf`，主服也有一份，但你希望同步后子服仍用自己那份。

```jsonc
"create": {
    "can_sync": true,
    "sync_source": "./server/world",
    "sync_target": "C:/game-create/server/world",
    "sync_whitelist": [
        "config/carpet.conf",   // 单个文件（精确相对路径）
        "config/",              // 整个目录
        "*.conf"                // 通配符
    ]
}
```

匹配规则（glob 语法，路径相对 `sync_source`）：

| 写法 | 含义 |
|------|------|
| `config/carpet.conf` | 精确匹配该相对路径 |
| `config/` | 结尾带 `/`：整个目录及其下全部文件 |
| `*.conf` | 通配符；`*` 可跨目录，故能命中任意层级的 `.conf` |
| `carpet.conf` | 不含 `/` 时**额外按文件名匹配**，等价于「任意目录下的 carpet.conf」 |

注意事项：

- **大小写不敏感**（与 Windows 文件系统一致）；反斜杠会自动归一化为 `/`
- **子服没有该文件时，同步后仍然没有** —— 白名单是「取消主服该文件的同步」，不会回退用主服的版本。因此新加子服首次同步时，白名单里的文件不会被创建
- **白名单优先于 `sync_ignore_files`**：同一路径两者都命中时，保留子服版本（详见下方「黑白名单对照」）
- `session.lock` **永不参与**（即使被白名单命中），它是运行中的锁文件
- 镜像同步会先清空子服，所以实现上是「先清空 → 从备份里捞回白名单文件 → 再拷主服的非白名单文件」；峰值磁盘占用仍约为存档的 2 倍
- 白名单为空时**没有任何额外开销**（不会多遍历一遍目录）

#### 黑白名单对照（`sync_ignore_files` vs `sync_whitelist`）

两者**匹配的是同一套路径**（相对 `sync_source`），很容易被误认为"重复功能"，但作用完全不同：

> **两个列表都是「不要用主服的版本」，区别只在于「那用什么」：**
> - **黑名单** → 不要主服的，**结果就是这个路径没有**
> - **白名单** → 不要主服的，**结果用子服原来的那份**

根源在于同步是**镜像式**的：先清空子服，再从主服拷。所以「跳过不拷」的后果是**删除**，而不是"保留原样"。

| | 匹配对象 | 命中后的效果 |
|---|---|---|
| `sync_ignore_files`（黑名单） | 主服的路径 | 不从主服拷 → 因为子服已被清空，**同步后该路径不存在** |
| `sync_whitelist`（白名单） | 主服与子服的同一相对路径 | ① 先从备份捞回**子服的版本** ② 再挡住主服的版本 → **结果用子服的** |

**优先级：白名单无条件优先。** 实现顺序决定了这一点 —— 恢复阶段只查白名单、完全不看黑名单，所以只要命中白名单，子服的版本一定会被捞回来；黑名单最多只能阻止主服的版本过来，拦不住子服的版本回去。

实测真值表（`carpet.conf` 在主服和子服都有、内容不同）：

| 黑名单 | 白名单 | 同步后子服里的 `carpet.conf` |
|---|---|---|
| - | - | **主服版本**（子服被覆盖） |
| 命中 | - | **不存在**（子服那份清了，主服那份没拷） |
| - | 命中 | **子服版本** ← 通常想要的效果 |
| 命中 | **命中** | **子服版本**（白名单赢） |

其他情况：

- **主服有、子服没有** → 命中白名单时**仍然没有**（不会退回用主服的）
- **子服独有、主服没有** → 未命中白名单会被**删除**（镜像语义）；命中白名单则**保留**
- **`session.lock`** → 无论两个列表怎么配，**都不会存在**（硬编码强制排除）

> ⚠️ **两个坑**
>
> **1. 两个列表的语法不同** —— 混用时极易写错：
>
> | | 语法 | 正确写法示例 | 错误写法 |
> |---|---|---|---|
> | `sync_ignore_files` | **正则**（`re.search`） | `\.conf$`、`session/` | `*.conf`（无效正则，会退化成字面量匹配，结果什么都不忽略） |
> | `sync_whitelist` | **glob**（`fnmatch`） | `*.conf`、`config/` | `\.conf$`（glob 里 `\.` 就是字面反斜杠+点，永远不命中） |
>
> **2. 白名单不看「谁更具体」** —— 只要命中就赢，不比较规则的精确程度。
> 例如黑名单写 `config/carpet.conf`、白名单写 `config/`，结果是 `carpet.conf` **又用回子服的版本**（因为父目录白名单命中了它）。
> 建议**同一个路径不要同时出现在两个列表里**。

**该用哪个：**

| 目的 | 用哪个 |
|---|---|
| 这个文件/目录**压根不要出现在子服里**（锁文件、日志、缓存） | 黑名单 `sync_ignore_files` |
| 这个文件/目录**要用子服自己的版本**，别被主服覆盖（如 `config/carpet.conf`） | 白名单 `sync_whitelist` |

同步完成的提示会区分两类文件：

```
[MSC] 同步完成！共复制 128 个文件，保留子服自有 3 个 (白名单)，用时 2.4s
```

其中「保留子服自有」就是白名单命中的文件数。

> **安全性**：只要有一个白名单文件恢复失败（被占用、权限不足、磁盘异常等），
> 整次同步会**中止并回滚**，子服存档保持同步前的原样，不会出现「配置被删掉却又报同步成功」的情况。
> 因为白名单路径既不会被主服覆盖、也不在拷贝范围内，备份里那份就是唯一副本，必须保证它不丢。

### start / stop / restart（子服进程控制，仅 Windows）

- `!!mscm start <英文名>`：在子服 `path` 目录下开一个**独立新控制台窗口**执行 `start_command`。`start_command` 为 list 时用 `&&` 依次执行各条，为 str 时执行该脚本文件；均通过 `cmd /c`（子服进程退出后窗口自动关闭）。已在线则拒绝重复启动。发出启动命令后会**在后台线程轮询 SLP 监听启动**（间隔 `startup_poll_interval`，最长 `startup_timeout`），检测到在线即回报成功；监听期间该子服被加锁，其它 start/stop/restart 会被挡下并提示。
- `!!mscm stop <英文名>`：通过 rcon（`host` + `rcon_port` + `rcon_password`）向子服发 `stop`，需 `rcon_enable=true`。会踢下线，需二次确认；确认提示中会显示**目标服务器当前在线人数与玩家名单**（通过 SLP 探测），提醒是否还有人。
- `!!mscm restart <英文名>`：若在线先经 rcon 关闭并轮询等待其离线（超时 60s），再启动。需二次确认，确认提示同样会提示在线人数/玩家。
- `!!mscm restart <英文名> sync`：关闭 → 同步主服存档到该子服 → 启动。需 `can_sync=true`，需二次确认。
- 在线判定统一用 SLP；同名子服的 start/stop/restart 互斥，防止重复提交。

## 配置

配置文件位于 `config/multi_server_control_maple/MultiServerControlMaple.json`，由插件首次加载时自动生成。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `use_suggest_command` | `true` | 可点击文本点击行为：`true`=填入聊天框待回车（全版本兼容），`false`=直接执行 |
| `probe_timeout` | `1.0` | 子服状态探测（SLP）的超时秒数 |
| `startup_timeout` | `60` | `start`/`restart` 后监听子服启动的最长等待秒数（超时则提示未检测到在线） |
| `startup_poll_interval` | `5` | 启动监听时每次 SLP 探测的间隔秒数 |
| `perm` | 见下 | 各命令所需最低权限等级（0=guest … 4=owner） |
| `servers` | 见下 | 各子服配置，键=子服英文名（同时用于命令参数与 Velocity `/server` 名） |

`perm` 默认：

```json
{ "help": 0, "reload": 3, "show": 0, "sync": 3, "start": 3, "stop": 3, "restart": 3 }
```

`servers` 中每个子服的字段（键 = 子服英文名，用于命令参数与 Velocity `/server`）：

| 字段 | 说明 |
|---|---|
| `cn_name` | 中文名（展示用；不填则展示英文 key） |
| `can_sync` | 是否可与主服同步存档（`true`=可同步主服，`false`=独立服务器），仅展示用 |
| `host` | 子服地址（一般为本机 `127.0.0.1`）；用于 SLP 状态探测，也复用为 rcon 地址 |
| `port` | 子服游戏端口，用于 SLP 状态探测 |
| `rcon_enable` | 是否启用 rcon（默认 `false`；不启用则无法用 `stop` 关闭子服） |
| `rcon_port` | 子服 rcon 端口，**必须 ≠ `port`** |
| `rcon_password` | 子服 rcon 密码 |
| `path` | 子服根目录（`server` 文件夹的上一级，如 `server` 在 `C:/game/server` 则 `path=C:/game`） |
| `start_command` | 启动命令（仅 Windows）：list 则进入 `path` 开 cmd 顺序执行各条；str 则执行 `path` 下指定脚本文件。启动会开独立新控制台窗口 |
| `sync_source` | 同步源 = 主服（本机）的 `world` 目录（一般 `./server/world`），只同步 world 内资源 |
| `sync_target` | 同步目标 = 子服的 `world` 目录 |
| `sync_ignore_files` | 同步时忽略列表（**正则**）：结尾带 `/` 忽略整个目录（如 `session/`），其余按正则 `re.search` 匹配相对 `sync_source` 的相对路径；`session.lock` 始终忽略。⚠️ 写 `*.conf` 是无效正则，要写 `\.conf$` |
| `sync_whitelist` | **同步白名单**（**glob**）：命中路径一律**采用子服自己的版本**，源的版本不会覆盖过去。语法与优先级详见「[黑白名单对照](#黑白名单对照sync_ignore_files-vs-sync_whitelist)」 |
| `description` | 备注（可选） |

> **启停仅适配 Windows。** 同步安全策略：目标子服在线则拒绝同步（须先 `stop`）；同步前对主服 `save-off`+`save-all`，完成后 `save-on`。

首次加载会写入 `mirror` / `create` 两个示例子服，可自行增删修改。

## 自定义事件

MultiServerControlMaple 通过 `ServerInterface.dispatch_event` 分发自定义事件，事件 ID 统一以 `multi_server_control_maple.` 为前缀（见 `default_config.EVENT_NS`），其他插件可监听这些时机：

```python
def on_msc_event(server, *args):
    pass

server.register_event_listener('multi_server_control_maple.<event_name>', on_msc_event)
```

已定义的事件：

| 事件 ID | 触发时机 | 参数 |
|---|---|---|
| `multi_server_control_maple.server_synced` | 子服存档同步完成 | `(name: str,)` |
| `multi_server_control_maple.server_start` | 已发出子服启动命令 | `(name: str,)` |
| `multi_server_control_maple.server_stop` | 已发出子服关闭命令 | `(name: str,)` |
| `multi_server_control_maple.server_restart` | 子服重启完成（已发出启动命令） | `(name: str,)` |

## 项目结构

```
multi_server_control_maple/
  __init__.py        # 事件入口: on_load / on_unload
  default_config.py  # 默认配置 + 帮助文案 + 事件命名空间
  my_lib.py          # 配置读写、权限/前缀、子服配置访问、事件分发、命令注册中枢
  slp.py             # Server List Ping 工具 (探测子服在线/人数/版本/延迟)
  utils.py           # 通用工具 (子服名校验等)
  commands/
    __init__.py
    show.py          # !!mscm show [名字]
    sync.py          # !!mscm sync <名字> -- 全量镜像同步主服存档到子服
    control.py       # !!mscm start/stop/restart <名字> -- 子服进程控制 (仅 Windows)
```

> 数据文件：主配置 `config/multi_server_control_maple/MultiServerControlMaple.json`。

## 许可证

见 [LICENSE](LICENSE)（CC0 1.0 Universal）。
