# AdvMaple 🍁

一个基于 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 的 **Minecraft 成就库存插件**。

思路很简单：**把某个玩家的成就抓取成一份「库存」，然后随时把这份库存分发给其他玩家。**

```
 一个玩家  ──grab──▶  库存 (持久化)  ──give──▶  全服 / 指定玩家
```

> By: Morning_Maple

## 特性

- **库存模型**：`stock` 抓取一次，存成快照。抓完就**可以不管原玩家了** —— 哪怕他删档、改名、转服，库存依然能分发
- **持久化**：库存写在插件数据目录的 `stock.json`，重启 / 重载都不丢
- **单份库存**：再次 `stock` 就覆盖，指令简单直观
- **自助同步**：普通玩家（权限 1）可用 `!!madv self` 给自己增量补齐，由服务端开关控制，管理员可游戏内热更新
- **只增不减**：分发给玩家时只授予其缺失的成就，**从不撤销**对方自己额外获得的成就
- **只处理在线玩家**：分发通过服务端命令完成，即时生效、服务端权威
- **自动排除配方类**：`minecraft:recipes/...` 默认不进库存，避免分发时灌入数百条把配方书塞爆
- **精确判定「已完成」**：只算 `done: true` 的成就，部分达成条件的不算
- **命令量最小化**：先算差集再下发，只对真正缺失的成就发命令
- **智能跳过**：玩家已拥有全部成就 → 不发多余命令；不在线 → 跳过并提示
- **限速保护**：`grant_interval` 控制逐条命令间隔，避免瞬间灌入导致卡服
- 命令都在独立线程执行，不阻塞 MCDR 主线程；Tab 补全全部走内存，零延迟

## 依赖

- `mcdreforged >= 2.15.7`
- `minecraft_data_api`（用于查询在线玩家列表与 UUID）

## 安装

1. 确保服务器已安装 `minecraft_data_api` 插件
2. 将 `AdvMaple-vX.Y.Z.mcdr` 放入 MCDR 的 `plugins/` 目录（或直接放入 `adv_maple/` 源码文件夹）
3. 在 MCDR 控制台执行 `!!MCDR reload plugin adv_maple`
4. **确认配置里的 `advancements_dir` 正确**（见下方配置说明）

打包源码为 `.mcdr` 文件：

```bash
python pack.py
```

## 命令

> 默认启用 Maple 前缀，入口命令为 `!!madv`；将配置 `use_maple_prefix` 设为 `false` 后变为 `!!adv`。下表以 `!!madv` 为例。

| 命令 | 说明 | 默认权限 |
|---|---|---|
| `!!madv` / `!!madv help` | 显示帮助（按权限过滤） | 0 |
| `!!madv self` | **给自己**增量补齐库存中的成就（已有的跳过） | **1** |
| `!!madv stock` | 查看当前库存（概要 + 第 1 页明细） | 3 |
| `!!madv stock list [页]` | 分页查看库存里的成就 id | 3 |
| `!!madv stock <玩家>` | **抓取**该玩家的成就作为库存（覆盖旧的） | 3 |
| `!!madv give` | **分发**库存给全服在线玩家 | 3 |
| `!!madv give <玩家>` | 分发库存给指定玩家 | 3 |
| `!!madv give <玩家> <成就id>` | 只分发单个成就（id 可 Tab 补全） | 3 |
| `!!madv switch` | 查看自助同步开关状态 | 3 |
| `!!madv switch on` / `off` | **热更新**自助同步开关 | 3 |
| `!!madv reload` | 重载配置 | 3 |

> **权限走 MCDR 原生权限体系**（`0`=guest … `4`=owner）。管理类命令（`stock` / `give` / `switch` / `reload`）默认需要 **3（admin）**；只有 `!!madv self` 是给普通玩家的 1 级命令，且**还受服务器开关约束**（见下）。

### 自助同步（`!!madv self`）

给普通玩家的便利功能：玩家自己触发，把库存里有、自己还没有的成就补上。

- **默认关闭**：配置项 `allow_self_sync` 默认为 `false`，需要在服务端开启
- **热更新**：权限 3 的玩家可在游戏内直接开/关，无需重载插件

```bash
!!madv switch          # 查看当前是否开启
!!madv switch on       # 开启（立即生效并写回配置文件）
!!madv switch off      # 关闭
```

开启后普通玩家用：

```bash
!!madv self            # 给自己补齐缺失的成就，已有的自动跳过
```


### 典型用法

```bash
# 1. 把成就刷满的那个玩家的成就抓成库存（需要 admin）
!!madv stock Steve

# 2. 看看库存里有什么
!!madv stock
!!madv stock list 2      # 第 2 页

# 3. 分发给全服（所有在线玩家）
!!madv give

# 4. 只给某个人
!!madv give Alex

# 5. 只补一个成就
!!madv give Alex minecraft:story/mine_diamond

# 6. 开放自助同步，让玩家自己补（管理员）
!!madv switch on

# 7. 玩家自己触发（权限 1 即可）
!!madv self
```

效果示例：

```
[AdvMaple] 分发完成: 库存来自 Steve (37 个成就)
  Alex   新增 12 个成就
  Notch  新增 37 个成就
  Herobrine 无需分发 (已拥有全部 37 个成就)
[AdvMaple] 共处理 2 名玩家, 下发 49 条 grant 命令
```

## 配置

配置文件位于 `config/adv_maple/AdvMaple.json`，首次加载时自动生成。

| 字段 | 默认值 | 说明 |
|---|---|---|
| `use_maple_prefix` | `true` | `true` → `!!madv`，`false` → `!!adv`。**修改后需重载插件才会重建命令树**（`!!madv reload` 只重载配置，会提示你重载插件） |
| `use_suggest_command` | `true` | 列表翻页按钮点击行为：`true`=填入聊天框待回车（全版本兼容），`false`=直接执行 |
| `advancements_dir` | `./server/world/advancements` | **玩家成就存档目录**，相对路径基于 MCDR 工作目录。抓取时从这里读 |
| `usercache_path` | `./server/usercache.json` | 服务端 `usercache.json`。**玩家名 → UUID 的首选来源**（本地文件、零延迟，同时覆盖在线与离线玩家）；未命中时才回退查询 API |
| `exclude_prefixes` | `["minecraft:recipes/"]` | 抓取时不进库存的成就 id 前缀列表 |
| `grant_interval` | `0.02` | 逐条下发命令的间隔秒数，`0` 表示不限速 |
| `list_page_size` | `10` | `!!madv stock list` 每页条数 |
| `allow_self_sync` | `false` | 是否允许普通玩家用 `!!madv self` 自助补成就。可用 `!!madv switch on\|off` 在游戏内热更新（会写回本文件） |
| `perm` | 见下 | 各命令所需最低权限等级（0=guest … 4=owner） |

`perm` 默认：

```json
{
  "help": 0,
  "stock": 3,
  "grab": 3,
  "give": 3,
  "self": 1,
  "switch": 3,
  "reload": 3
}
```

> `stock` 控制「查看库存」，`grab` 控制「抓取库存」—— 两者默认都是 3。
> `self` 是唯一给普通玩家（1 级）的命令，但仍需 `allow_self_sync` 开启后才真正可用。
> `switch` 控制开关的热更新，默认 3（admin）。

> ⚠️ **升级注意**：配置加载只会**补全缺失的键**，**不会覆盖你已设置的值**。
> 因此如果你曾装过本插件的早期版本，升级后 `perm` 里已有的项（如 `stock` / `give`）
> 会**保留旧值**，不会自动变成新的默认 3。
> 若需要采用新默认值，请删除 `config/adv_maple/AdvMaple.json` 让插件重新生成，
> 或手动把 `perm` 里各项改成你想要的等级。

> **`advancements_dir` 是最容易配错的一项**。它必须指向服务端存档里的 `advancements` 文件夹。
> 若你的服务端 `level-name` 不是 `world`（例如 `server.properties` 里写的是 `level-name=myworld`），
> 就要改成 `./server/myworld/advancements`。
> 配置不对时插件会明确报错并打印实际查找的路径，方便核对。

## 工作原理

### 为什么「读文件、写命令」

| 方向 | 手段 | 原因 |
|------|------|------|
| **读**（抓取） | 读 `advancements/<uuid>.json` | 原版**没有任何命令**能列出某玩家已有的成就，文件是唯一数据源。**只读**在线玩家的存档是安全的（服务器仅在保存时写回，不会锁文件）。 |
| **写**（分发） | `advancement grant <目标> only <成就id>` | 在线玩家的成就在服务器内存里，直接改存档文件会在下次保存时被覆盖。用命令让服务端自己改，即时生效且服务端权威。 |

### 为什么必须逐条

原版**没有**「把 A 的成就复制给 B」的单条命令：

```
/advancement grant <targets> only    <advancement> [criterion]
/advancement grant <targets> until   <advancement>
/advancement grant <targets> through <advancement>
/advancement grant <targets> from    <advancement>
/advancement grant <targets> everything
```

`from` 后面跟的是**进度树节点**（含义是「从该节点及其所有子节点」），**不是玩家**。所以只能先把成就抓成列表，再逐条授予。

### 「已完成」的判定

只统计存档里 `done` 为 `true` 的条目。部分达成条件（`done: false`）的不算：

```json
{
  "minecraft:story/mine_diamond": {
    "criteria": { "get_diamond": "2026-10-02 12:00:00 +0800" },
    "done": true                                  ← 进库存
  },
  "minecraft:adventure/adventuring_time": {
    "criteria": { "biome_plains": "..." },
    "done": false                                 ← 不进库存
  }
}
```

### 库存文件

```
config/adv_maple/
├── AdvMaple.json      # 设置
└── stock.json         # 库存 (抓取后生成)
```

```json
{
    "source": "Steve",
    "uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",
    "created_at": 1761400000.0,
    "ids": [
        "minecraft:nether/root",
        "minecraft:story/mine_diamond"
    ]
}
```

**这份库存是自包含的** —— 分发时只读 `stock.json`，不再访问原玩家的存档。

## 已知限制

- **只处理在线玩家**：离线玩家无法用命令写入（直接改文件会被内存覆盖），因此分发时会跳过并提示。
- **`!!madv self` 默认关闭**：需管理员用 `!!madv switch on` 开启；关闭时该命令会直接提示并拒绝。
- **单份库存**：再次 `stock` 会覆盖旧库存（按设计，保持最简单）。
- **成就只显示 id**：形如 `minecraft:story/mine_diamond`，不显示中文标题。
- **玩家名 `list` 无法抓取**：与 `!!madv stock list` 冲突（解析时字面量子命令优先），会明确拒绝。
- 匹配玩家名时**不区分大小写**。

## 项目结构

```
adv_maple/
  __init__.py        # 事件入口: on_load / on_player_joined / on_player_left / on_unload
  default_config.py  # 默认配置 + 帮助文案
  my_lib.py          # 配置读写、权限/前缀、在线玩家集合、命令注册中枢
  advancement.py     # 存档读取、usercache 解析、库存存取、grant 下发
  pagination.py      # 通用分页组件
  utils.py           # NBT int array → UUID
  commands/
    __init__.py
    stock.py         # !!madv stock [list [页]] / !!madv stock <玩家>
    give.py          # !!madv give [玩家 [成就id]] / !!madv self
    switch.py        # !!madv switch [on|off]
```

## 许可证

见 [LICENSE](../LICENSE)。

## 作者

**Morning_Maple**
