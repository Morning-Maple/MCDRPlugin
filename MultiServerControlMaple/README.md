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

> **新装默认值就是 `["carpet.conf"]`** —— 全新配置开箱即用地保留子服 carpet 配置。
> 但从旧版本升级的子服不会被自动改成这个值（升级保持原行为，`[]`），需要的话手动加。

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

#### 额外同步项（`sync_extra`）

world 同步只覆盖 `sync_source` → `sync_target` 这一棵树。但很多插件配置在 world **外面**（如 `server/config/xxx.yml`），这些用 `sync_extra` 显式指定：

```jsonc
"mirror": {
    "sync_source": "./server/world",
    "sync_target": "C:/game-mirror/server/world",
    "sync_extra": [
        {
            "source": "./server/config/carpet.conf",
            "target": "C:/game-mirror/server/config/carpet.conf"
        },
        {
            "source": "./server/plugins/MyPlugin",
            "target": "C:/game-mirror/server/plugins/MyPlugin"
        }
    ]
}
```

形态：列表，每项 `{"source": ..., "target": ...}`。路径可绝对，或相对 MCDR 工作目录。

**同步行为：**

| source 是 | 行为 |
|---|---|
| 文件 | 覆盖目标同名文件（目标不存在则创建） |
| 目录 | **合并**：递归拷贝并覆盖同名文件；**目标独有的文件保留不动**（便于插件配置目录） |

这与 world 同步的"镜像"语义不同 —— 额外项是**合并**，不会删掉子服原有的其他文件。

**执行时机**：在 world 同步成功之后进行，共用同一次二次确认与 `save-off`/`save-all` 保护窗口。

**失败处理**：单项失败**只回滚该项**（已覆盖的文件恢复原内容、新建的文件删除），其他项继续；最后汇总哪些失败。若存在失败项，会跳过 `server_synced` 事件派发，避免下游误判子服已完全一致。

**配置校验（任一项不合法都会拒绝整次同步）：**

| 校验 | 原因 |
|---|---|
| `source` / `target` 必填 | — |
| `source` 必须存在 | 否则会静默漏同步 |
| **`source` 与 `sync_source` 不得重叠** | 双向判断：不能是它的**内部路径**，也**不能是它的父目录**（如把 `./server` 配成源，会把整个 world 重复拷一遍，绕过 ignore/白名单） |
| **`target` 与 `sync_target` 不得重叠** | 同上 |
| `target` 不能位于主服 world 内 | 不能往主服存档里写东西 |
| `source` 不能位于子服 world 内 | 不应从子服存档读取 |
| `source` ≠ `target`，且 `target` 不能在 `source` 内部 | 否则会自我递归拷贝 |

> 注：`sync_source` 的**兄弟目录**（如 `./server/world_extra`）是允许的 —— 只要不存在包含关系就行。

出错时会在**游戏内**逐条列出错误并提示"同步已中止"，同时写入**服务端日志**，例如：

```
[MSC] [额外同步] 第 1 项 源与 world 同步源重叠 (不能是它的父目录或内部路径): E:\...\server
[MSC] 同步已中止: 请修正 sync_extra 配置后重试
```

配置有误时**不会开始任何拷贝**（也不会 `save-off`），对现有数据零影响。

#### 常见场景速查

| 我想要… | 怎么配 |
|---|---|
| 子服用自己的 `carpet.conf`，其他都跟主服 | 新装默认已包含 `["carpet.conf"]`；旧配置请手动加 `"sync_whitelist": ["carpet.conf"]` |
| 子服整个 `config/` 目录都用自己的一套 | `"sync_whitelist": ["config/"]` |
| 所有 `.yml` 配置都用子服的 | `"sync_whitelist": ["*.yml"]` |
| 某个文件**只放主服用**，子服不要有 | `"sync_ignore_files": ["那个文件名或其正则"]` |
| 把 world 外的插件配置也同步过去 | 加 `"sync_extra": [{"source": ..., "target": ...}]` |
| 让子服 `carpet.conf` 跟主服保持一致（放弃默认行为） | `"sync_whitelist": []` |

> 一句话区分：**白名单保子服，黑名单删文件**。详见上面的[黑白名单对照](#黑白名单对照sync_ignore_files-vs-sync_whitelist)。

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
| `sync_ignore_files` | 同步时忽略列表（**正则**）：结尾带 `/` 忽略整个目录（如 `session/`），其余按正则 `re.search` 匹配相对 `sync_source` 的相对路径；`session.lock` 始终忽略。⚠️ 写 `*.conf` 是无效正则，要写 `\.conf$`。默认 `["session.lock"]` |
| `sync_whitelist` | **同步白名单**（**glob**）：命中路径一律**采用子服自己的版本**，源的版本不会覆盖过去。**新装默认 `["carpet.conf"]`**（carpet 配置几乎总是各服不同）；升级时为保持原行为补 `[]`。语法与优先级详见「[黑白名单对照](#黑白名单对照sync_ignore_files-vs-sync_whitelist)」 |
| `sync_extra` | **额外同步项**：把 world 之外的文件/目录一并同步，列表，每项 `{"source": ..., "target": ...}`。目录为**合并**语义（目标独有文件保留）。**默认 `[]`**。详见「[额外同步项](#额外同步项sync_extra)」 |
| `description` | 备注（可选） |

> **启停仅适配 Windows。** 同步安全策略：目标子服在线则拒绝同步（须先 `stop`）；同步前对主服 `save-off`+`save-all`，完成后 `save-on`。

首次加载会写入 `mirror` / `create` 两个示例子服，可自行增删修改。

### 完整配置示例

一个「镜像服」的典型配置 —— 同步 world，保留子服自己的 `carpet.conf`，并额外带上两个 world 之外的插件配置：

```jsonc
{
    "use_suggest_command": true,
    "probe_timeout": 1.0,
    "startup_timeout": 60,
    "startup_poll_interval": 5,
    "perm": {
        "help": 0, "reload": 3, "show": 0,
        "sync": 3, "start": 3, "stop": 3, "restart": 3
    },
    "servers": {
        "mirror": {
            "cn_name": "镜像服",
            "can_sync": true,
            "host": "127.0.0.1",
            "port": 25566,
            "rcon_enable": true,
            "rcon_port": 25576,
            "rcon_password": "改成你自己的密码",
            "path": "D:/game-mirror",

            // ---- world 同步 ----
            "sync_source": "./server/world",
            "sync_target": "D:/game-mirror/server/world",

            // 复制的忽略列表 (正则)。session.lock 本来就强制忽略, 可不写
            "sync_ignore_files": ["session.lock", "logs/"],

            // 白名单: 这些路径用**子服自己的版本**, 不被主服覆盖
            // "carpet.conf" 不含 / 时会按文件名匹配, 等价于「任意目录下的 carpet.conf」
            "sync_whitelist": ["carpet.conf", "datapacks/local/"],

            // 额外同步项: world 之外的东西 (文件或目录)
            // 目录为合并语义: 只覆盖同名文件, 子服独有的文件保留
            "sync_extra": [
                {
                    "source": "./server/config/carpet.conf",
                    "target": "D:/game-mirror/server/config/carpet.conf"
                },
                {
                    "source": "./server/config/MyPlugin",
                    "target": "D:/game-mirror/server/config/MyPlugin"
                }
            ],

            "description": "主服镜像, 可与主服同步存档"
        },
        "create": {
            "can_sync": false,
            "host": "127.0.0.1",
            "port": 25567,
            "description": "创造服, 独立存档"
        }
    }
}
```

### 升级注意（旧版本 → 1.2.0）

**升级不会改变你线上正在生效的同步行为。** 配置加载时只会给**已存在的子服**补上缺失的字段，且遵循两条原则：

1. **字段已存在就完全不动** —— 哪怕是你特意设的空列表，也不会被覆盖
2. **补进去的是中性值**，不是新装默认值

| 字段 | 已存在 | 缺失时补的（升级） | 新装默认 |
|---|---|---|---|
| `sync_whitelist` | **不动** | `[]`（= 纯镜像，与旧行为一致） | `["carpet.conf"]` |
| `sync_extra` | **不动** | `[]` | `[]` |
| `sync_ignore_files` | **不动** | `["session.lock"]`（本来就强制忽略，无影响） | `["session.lock"]` |

> 💡 **为什么升级补的是 `[]` 而不是 `["carpet.conf"]`**：
> 老配置里没有这个字段，说明子服的 `carpet.conf` 一直是**被主服覆盖**的。
> 如果升级时补成 `["carpet.conf"]`，行为会**悄悄变成保留子服版本** —— 这类静默变更很危险。
> 所以升级保持原样，想启用新默认行为的话请**手动**加：
>
> ```jsonc
> "sync_whitelist": ["carpet.conf"]
> ```

同时：**不会**把你删掉的示例子服（`mirror` / `create`）加回来 —— 迁移只遍历你实际拥有的子服。

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
