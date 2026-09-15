# MailMaple

一个基于 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 的 Minecraft 邮件插件，支持玩家之间**携带物品附件**互相发送邮件，可离线收件、可拒收退回，并内置真人/假人识别，避免向假人或从未登录过的玩家发邮件。

> By: Morning_Maple

## 特性

- 玩家之间发送**带物品附件**的邮件，附件原样保存（附魔 / 命名 / lore / 耐久 / 数量等）。
- 灵活的附件来源：主手、整个快捷栏、或自定义指定背包格子。
- 收件箱使用 RText 渲染，**点击即可接受 / 拒绝**（默认填入聊天框待回车，可配置为直接执行），附件多时可悬停查看完整清单。
- 离线收件：邮件按 UUID 存入邮箱。在线收到时即时提醒；离线期间收到的，会在上线时汇总「共收到 x 封」，并显示邮箱容量「持有 / 上限」，附带可点击的 `[查看邮件列表]`。
- 拒收 / 取消会生成**回退邮件**把物品退回，回退邮件只能接受、不可再次拒绝。
- 真人/假人识别：默认按 UUID 版本号自动区分（在线模式），并支持名单/正则兜底，**不会给假人或从未登录过的玩家发邮件**。
- 设置与数据分离，玩家数据**按 UUID 分片存储**，配合**原子写**：每次操作只重写受影响玩家的分片，避免整份重写与写坏损毁（详见「数据存储」）。
- 所有涉及服务端查询的操作均在独立线程执行，不阻塞 MCDR 主线程；命令补全走内存维护的在线玩家集合，即时响应。

## 依赖

- `mcdreforged >= 2.15.7`
- `minecraft_data_api`（用于读取玩家背包 / UUID 等数据）

> 仅适配新版本 Minecraft（1.20.5+，物品使用 data components 格式）。

## 安装

1. 确保服务器已安装 `minecraft_data_api` 插件。
2. 将打包好的 `MailMaple-vX.Y.Z.mcdr` 放入 MCDR 的 `plugins/` 目录（或直接放入 `mail_maple/` 源码文件夹）。
3. 在 MCDR 控制台执行 `!!MCDR reload plugin mail_maple`。

打包源码为 `.mcdr` 文件：

```bash
python pack.py
```

## 命令

> 默认启用 Maple 前缀，入口命令为 `!!mmail`；将配置 `use_maple_prefix` 设为 `false` 后变为 `!!mail`。下表以 `!!mmail` 为例。

| 命令 | 说明 |
|---|---|
| `!!mmail` / `!!mmail help` | 显示帮助 |
| `!!mmail send <目标玩家> <标题> [附件]` | 发送邮件 |
| `!!mmail user` | 查看所有可发送对象（含自己，点击名字可填入发送指令） |
| `!!mmail user add <玩家>` | 手动把玩家加入可发送对象（**要求该玩家在线**） |
| `!!mmail user remove <玩家>` | 把玩家移出可发送对象，并加入精确黑名单 |
| `!!mmail black` | 查看精确名字黑名单 |
| `!!mmail black add <玩家>` | 加入精确黑名单（并立即移出可发送对象） |
| `!!mmail black remove <玩家>` | 移出精确黑名单 |
| `!!mmail list [页数]` | 查看自己的收件箱（可点击操作；页数可省略，默认第 1 页，越界自动钳到最小/最大页，底部可点击翻页） |
| `!!mmail accept <邮件id>` | 接受邮件，领取附件 |
| `!!mmail reject <邮件id>` | 拒绝邮件，附件退回发送者 |
| `!!mmail cancel <邮件id>` | 取消自己发出的、对方未处理的邮件，附件退回自己 |
| `!!mmail expire list [页数]` | 查看自己的过期邮件（只读，邮件 id 前显示 `[过期]`） |
| `!!mmail check expire <玩家> [页数]` | 【管理】查看指定玩家的过期邮件（带回退/强制回退/重发/强制重发按钮） |
| `!!mmail expire push <邮件id> [force]` | 【管理】重发过期邮件给目标：无 force=重进目标收件箱（重置过期、标 `[管理员操作]`）；force=直接发放给目标（需目标在线） |
| `!!mmail expire return <邮件id> [force]` | 【管理】退回过期邮件给发件人：无 force=作为回退件进发件人收件箱；force=直接发放给发件人（需发件人在线） |
| `!!mmail reload` | 重载配置 |

### 邮件 id

邮件 id 采用 `年月日-编号`（如 `260622-18`），编号**每天从 1 重新计数**，所以日常使用都很短、好输入。例如领取今天的第 3 封：

```
!!mmail accept 260622-3
```

在收件箱 `list` 里点击 `[接受]`/`[拒绝]` 按钮会自动带上 id，无需手动输入。

### 标题

标题含空格时用双引号包裹，例如：

```
!!mmail send Steve "生日快乐 送你点东西"
```

### 附件参数

`send` 命令最后的 `[附件]` 参数三选一：

| 写法 | 含义 |
|---|---|
| 留空 | 默认附带**主手物品** |
| `allhand` | 附带**快捷栏 1-9 格**的所有物品 |
| `[(1,5), (15,20), 27, 28]` | 附带指定格子：元组为区间（含两端），整数为单格 |

格子编号说明（1-based）：

- `1-9`：快捷栏（GUI 最底下一排）
- `10-36`：主背包，**从上往下**数
- 不含盔甲 / 副手（这两处的物品无法作为附件发送）

对照背包界面（注意快捷栏是 1-9，主背包下排 28-36 紧挨着快捷栏）：

```
主背包上排:  10 11 12 13 14 15 16 17 18
主背包中排:  19 20 21 22 23 24 25 26 27
主背包下排:  28 29 30 31 32 33 34 35 36   ← 紧挨快捷栏的那一排
快捷栏:       1  2  3  4  5  6  7  8  9    ← 最底下一排
```

> 发送时若指定的格子是空的，会提示「以下格子为空, 已跳过: ...」，方便核对是否数错了位置。

示例：

```
!!mmail send Steve 礼物                      # 主手物品
!!mmail send Steve 整理快捷栏 allhand         # 快捷栏全部
!!mmail send Steve 批量 [(1,5),(15,20),27,28] # 第1-5、15-20、27、28格
```

> 若指定格子全为空（或主手为空），**视为发送失败**，不会生成邮件；只有成功扣除物品才算发送成功。背包满时领取的物品会掉落在脚下。

## 配置

配置文件位于 `config/mail_maple/MailMaple.json`，由插件首次加载时自动生成。**该文件只存设置项**，运行数据（邮件/注册表）另存于 `mail_data/`（见「数据存储」）。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `use_maple_prefix` | `true` | `true` → `!!mmail`，`false` → `!!mail` |
| `use_suggest_command` | `true` | 收件箱按钮点击行为：`true`=填入聊天框待回车（全版本兼容），`false`=直接执行（需 MC<1.19.1 或客户端装 LetMeClickAndSend） |
| `allow_send_to_self` | `false` | 是否允许给自己发邮件 |
| `list_attachment_display` | `3` | 列表中每封邮件最多直接展示的附件数：`0`=只显示「共 x 个附件」，`<0`=按 3，`>36`=按 36（多出的用「等 N 件」省略，完整清单可悬停查看） |
| `list_page_size` | `10` | 收件箱列表每页显示的邮件条数（`<=0` 视为 10） |
| `expire_list_page_size` | `10` | 玩家过期邮件列表每页条数（`<=0` 视为 10） |
| `admin_expire_list_page_size` | `10` | 管理员查看玩家过期邮件每页条数（`<=0` 视为 10） |
| `perm` | 见下 | 各命令所需最低权限等级（0=guest … 4=owner） |
| `default_mail_max` | `50` | 单个玩家邮箱最大邮件数，`0` 为不限制 |
| `mail_expire_seconds` | `259200` | 邮件过期秒数：`<=0`=永不过期（`0` 与负数都表示关闭），正数 N=发送 N 秒后过期。默认 `259200`=3 天（换算：1 小时=3600，1 天=86400，7 天=604800） |
| `admin_ignore_mail_max` | `false` | 管理员重发/退回邮件时是否无视邮箱容量上限 |
| `detect_bot_by_uuid_version` | `true` | 按 UUID 版本号识别假人（在线模式：v4=真人，v3=假人） |
| `bot_name_blacklist` | `[]` | 假人名字黑名单（**标准正则**列表，命中则不自动登记）。如 `["^bot_", "^jqr_"]` 表示以 bot_ / jqr_ 开头 |
| `bot_list` | `[]` | 精确名字黑名单（由 `mail black add/remove`、`mail user remove` 维护） |
| `ignore_case` | `true` | 名字/正则匹配是否忽略大小写 |
| `usercache_path` | `./server/usercache.json` | 服务端 usercache.json 路径，加载时扫描预填已知真人 |

> 运行数据（邮件编号计数、真人注册表、各玩家邮箱）**不再存于本配置文件**，而是分别落在 `mail_data/registry.json` 与 `mail_data/players/<uuid>.json`（见「数据存储」）。因此你手动修改配置文件不会再被邮件操作覆盖。

`perm` 默认：

```json
{
  "help": 0, "user": 0, "list": 0, "send": 0,
  "accept": 0, "reject": 0, "cancel": 0, "expire": 0,
  "manage": 3, "reload": 3
}
```

> `expire` 控制玩家查看自己过期邮件（`mail expire list`）的权限；`manage` 控制 `user add/remove`、`black add/remove`、`check expire`、`expire push/return` 等管理操作的权限。

### 真人 / 假人识别说明

发邮件时目标玩家必须是**已登录过的真人**。自动登记（上线/加载）时按以下优先级判定是否为假人：

1. `bot_list` 精确名单命中 → 假人
2. `bot_name_blacklist` 正则命中 → 假人
3. `detect_bot_by_uuid_version`：UUID version 4 → 真人，version 3 → 假人
4. 以上都不命中 → 默认真人

> 通过 `mail user add` 手动加入的玩家会直接进入可发送对象，**不受上述自动判定影响**（即使名字命中黑名单/正则也保留）。`mail user remove` / `mail black add` 则会移出并拉黑。

> **在线模式**下 Carpet 假人是按名字生成的离线 UUID（v3），真人是正版 UUID（v4），可自动区分，无需任何配置。
>
> **离线 / 盗版模式**下真人也是 v3，无法靠 UUID 区分。若仍保持 `detect_bot_by_uuid_version: true`，真人会被误判为假人而无法登记/收发邮件。**离线服请务必将 `detect_bot_by_uuid_version` 设为 `false`**，改用 `bot_list` 维护假人名单；改完执行 `!!MCDR reload plugin mail_maple` 即可重新登记当前在线玩家。可用 `!!mmail user` 查看已登记的可发送对象。

### 帮助文案

帮助信息的文案集中在 `mail_maple/config.py` 的 `HELP_LINES` 常量中维护，每行形如 `(权限键, 文本)`：`{base}` 会被替换为当前前缀入口命令；`!!mmail help` 会**按玩家的 MCDR 权限过滤**，只展示其有权使用的命令（权限键为 `None` 的标题/页脚始终显示）。

## 邮件流程

- **发送**：扣除发送者指定物品 → 生成邮件存入收件人邮箱（按 UUID）。
- **接受**：附件 `give` 给自己 → 邮件从邮箱移除。
- **拒绝**：邮件移除 → 生成「回退邮件」退回原发送者（`is_rollback=true`，只能接受）。
- **取消**：发送者撤回对方未处理的邮件 → 附件退回发送者。

## 过期邮件

- 是否过期由 `mail_expire_seconds` 决定（`<=0` 永不过期，默认 `259200`=3 天）。访问邮箱相关命令（list / accept / reject / expire list / 玩家上线 / 管理员命令）时会先扫描，把到期邮件从活跃收件箱移入**过期列表**（与活跃邮件同存于该玩家的分片文件 `mail_data/players/<uuid>.json` 的 `expired` 字段）。
- 普通 `mail list` 只显示未过期邮件；过期邮件用 `mail expire list` 查看（玩家只读）。
- 玩家无法对过期邮件接受/拒绝；只能由管理员处理：
  - **重发** `expire push <id>`：邮件重回目标收件箱（重置过期时间，显示 `[管理员操作]`，按容量检查）；`force` 则直接把附件发给目标（需在线）。
  - **退回** `expire return <id>`：作为回退件进发件人收件箱（重置过期时间，按容量检查）；`force` 则直接把附件发给发件人（需在线）。
  - `force` 操作成功后该过期邮件被删除。容量检查可由 `admin_ignore_mail_max` 关闭。
- 收件箱各视图标识顺序：
  - 普通 list：`[接受] [拒绝|不可拒绝] [管理员操作] [回退件] #id 标题 …`
  - 过期 list（玩家只读）：`[管理员操作] [回退件] [过期] #id 标题 …`
  - 管理员 check expire：`[回退] [强制回退] [重发] [强制重发] [管理员操作] [回退件] [过期] #id 标题 …`

## 实现说明

- **物品保真（务实版）**：通过 `minecraft_data_api` 读取物品 components，自写 SNBT 序列化器重建 `give` 命令。覆盖附魔 / 命名 / lore / 耐久 / 数量等绝大多数常见物品；极少数依赖精确 NBT 类型（byte/short/long）的复杂组件可能失真。
- **精确扣除**：按格子用 `item replace entity <玩家> <槽位> with air` 清除，仅清指定格子，不会误删背包别处的同种物品。
- **线程模型**：发送 / 接受 / 拒绝 / 取消 / 玩家上线等含阻塞查询的逻辑都用 `@new_thread` 放到独立守护线程，避免卡住 MCDR 主任务线程。
- **在线集合**：运行时维护在线玩家集合（上线/下线事件 + 加载时 seed），命令补全与"是否在线"判断直接走内存，零延迟；阻塞式的玩家列表查询仅在插件加载时使用一次。
- **Tab 补全**：`send`/`user`/`black`/`check expire` 的玩家名，以及 `accept`/`reject`/`cancel`/`expire push`/`expire return` 的邮件 id 均支持 Tab 补全，全部走内存数据即时返回（accept=收件箱、reject=可拒绝件、cancel=自己发出的、expire push/return=过期件）。
- **UUID 解析**：兼容 1.16+ 的 int array 形式（如 `[I; a,b,c,d]`），查询/解析失败时安全返回 `None`，不会抛错中断调用方。

## 项目结构

```
mail_maple/
  __init__.py        # 事件入口: on_load / on_player_joined / on_player_left / on_unload
  config.py          # Serializable 数据模型(MailSettings / MailRegistry / PlayerData) + 默认配置 + 帮助文案常量
  mail_lib.py        # 存储层(原子写/分片)、过期扫描、真人注册表/反假人、在线集合、命令注册中枢
  item_util.py       # 槽位解析、物品读取、give 重建、精确扣除
  snbt.py            # SNBT 序列化器
  commands/
    send.py          # !!mail send
    mail_list.py     # !!mail list / user / expire list (RText 可点击, 分页)
    handle.py        # !!mail accept / reject / cancel
    admin.py         # user/black 管理 + check expire / expire push / expire return
```

## 数据存储

存储布局（均在 `config/mail_maple/` 下）：

```
config/mail_maple/
├── MailMaple.json              # 仅设置项
└── mail_data/                  # 运行数据 (与设置文件同级)
    ├── registry.json           # 邮件编号计数 (mail_id_date/seq) + 真人注册表 (known_players)
    └── players/
        └── <uuid>.json         # 每个玩家一个分片: mails(活跃) + expired(过期)
```

设计要点：

- **设置与数据分离**：`MailMaple.json` 只存设置项，玩家数据全部在 `mail_data/`。手动改配置不会被邮件操作覆盖。
- **按玩家分片**：每个玩家一个 `players/<uuid>.json`。一次发/收/拒/取消**只重写受影响玩家的分片**（涉及双方就写两个），消除整份重写的写放大，也把损坏影响限制在单个玩家。
- **原子写**：所有写入走「临时文件 → fsync → `os.replace` 覆盖」，任何时刻文件要么旧的完整、要么新的完整，杜绝半截文件。分片数据全空时对应文件会被自动删除。

## 许可证

见 [LICENSE](LICENSE)。
