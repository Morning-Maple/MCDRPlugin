# TpMaple 🍁

一个功能齐全的 [MCDReforged](https://github.com/Fallen-Breath/MCDReforged) 传送管理插件，提供 sethome、warp 地标、back、坐标传送、tpa 等常用传送功能。

## 功能一览

> 下表命令均以默认的 **Maple 前缀**（`!!m...`）形式展示。若在配置中关闭 `use_maple_prefix`，则所有命令去掉前缀中的 `m`，例如 `!!mtpa` → `!!tpa`、`!!mtpm` → `!!tpm`。详见[配置说明](#配置说明)。

| 命令 | 说明 |
|------|------|
| `!!msethome <名字>` | 将当前位置设为家，名字重复则覆盖（名字仅允许英文字母和数字） |
| `!!mhome` | 列出你所有已设置的家 |
| `!!mhome list [页]` | 分页查看家列表（带可点击翻页） |
| `!!mhome <名字>` | 传送到指定的家 |
| `!!mdelhome <名字>` | 删除指定的家 |
| `!!mwp` | 列出全服地标（所有人可见） |
| `!!mwp list [页]` | 分页查看全服地标列表（带可点击翻页） |
| `!!mwp <名字>` | 传送到指定的全服地标 |
| `!!msetwp <名字> [注释]` | 在当前位置创建一个全服地标，注释可选（需要权限 ≥ 2） |
| `!!mdelwp <名字>` | 删除指定的全服地标（需要权限 ≥ 2） |
| `!!mwp help` | 显示**地标专属**帮助（不显示家/tpa 等命令），可简写 `!!mwp h` |
| `!!mwp reload` | 重新载入配置文件 |
| `!!mwp reset` | 清空所有玩家数据与地标（需二次确认） |
| `!!mback` | 精确传送回上一次的传送/死亡地点 |
| `!!mback safe` | 安全传送到上一次的传送/死亡地点附近（死在岩浆/危险处时用） |
| `!!mtpm <x> <y> <z> [维度]` | 传送到指定坐标，维度可选（不填则为当前维度） |
| `!!mtpa <玩家名>` | 请求传送到目标玩家的位置 |
| `!!mtpahere <玩家名>` | 请求目标玩家传送到你的位置 |
| `!!mtpaccept` | 同意最近一条传送请求 |
| `!!mtpacancel` | 拒绝最近一条传送请求 |
| `!!mtpm help` | 显示帮助信息（家 / back / 坐标传送 / tpa，不含地标命令） |
| `!!mtpm reload` | 重新载入配置文件（需要管理员权限） |

## 安装

### 依赖

- **MCDReforged** >= 2.15.7
- **minecraft_data_api** 插件（MCDR 插件依赖，需单独安装）

### 安装步骤

1. 将 `tp_maple/` 文件夹放入 MCDR 的 `plugins/` 目录
2. 确保已安装 [minecraft_data_api](https://github.com/MCDReforged/MinecraftDataAPI) 插件
3. 启动或重载 MCDR，插件会自动在插件数据文件夹 `config/tp_maple/` 下生成 `TpMaple.json` 配置文件

## 配置说明

配置文件路径：`config/tp_maple/TpMaple.json`（插件数据文件夹，由 MCDR 官方配置 API 管理）

> 配置由 MCDR 的 `load_config_simple` 加载：新增配置项时会自动补全缺失的键（含 `perm`/`cd` 等嵌套子键），无需手动迁移旧配置；默认配置中不存在的多余顶层键会被自动移除。

```json
{
    "use_maple_prefix": true,
    "use_suggest_command": true,
    "perm": {
        "help": 0,
        "reload": 3,
        "sethome": 1,
        "home": 1,
        "delhome": 1,
        "wp": 1,
        "setwp": 2,
        "delwp": 2,
        "back": 1,
        "tpm": 1,
        "tpa": 1,
        "tpahere": 2,
        "tpaccept": 0,
        "tpacancel": 0
    },
    "cd": {
        "home": 100,
        "wp": 10,
        "back": 60,
        "tpm": 60,
        "tpa": 60
    },
    "default_sethome_max": 3,
    "home_list_page_size": 10,
    "warp_max": 20,
    "warp_list_page_size": 10,
    "tp_delay": 5,
    "tpa_timeout": 60,
    "tp_move_threshold": 1.0,
    "tp_check_interval": 0.5,
    "debug_teleport_log": false
}
```

### 配置项详解

#### 命令前缀 (`use_maple_prefix`)

| 值 | 命令形式 | 示例 |
|----|----------|------|
| `true`（默认） | 带 Maple 前缀 `!!m...` | `!!mtpa`、`!!mhome`、`!!mtpm` |
| `false` | 默认前缀 `!!...` | `!!tpa`、`!!home`、`!!tpm` |

用于规避与其他插件的命令冲突。修改后需要 **重载插件或重启服务器** 才会重建命令树生效；帮助信息会自动切换为对应版本。

#### 可点击文本行为 (`use_suggest_command`)

控制聊天中可点击按钮（死亡提示的 `[精确返回]`/`[安全返回]`、tpa 的 `[同意]`/`[拒绝]`）的点击行为：

| 值 | 行为 | 适用 |
|----|------|------|
| `true`（默认） | `suggest_command`：点击把命令**填入聊天框**，玩家按回车发送 | 纯原版客户端，全版本兼容 |
| `false` | `run_command`：点击**直接执行** | 需 MC < 1.19.1，或客户端安装 [LetMeClickAndSend](https://github.com/Fallen-Breath/LetMeClickAndSend) mod |

> 原因：原版 Minecraft 自 1.19.1 起限制了 `run_command` 只能执行以 `/` 开头的命令，导致 `!!` 开头的 MCDR 命令无法通过点击直接发送。`suggest_command` 不受此限制。此项为运行时读取，改完即时生效，无需重载。

#### 权限 (`perm`)

MCDR 权限等级对照：`0` = guest, `1` = user, `2` = helper, `3` = admin, `4` = owner

| 键 | 默认值 | 说明 |
|----|--------|------|
| `help` | 0 | 查看帮助信息 |
| `reload` | 3 | 重载配置文件 |
| `sethome` | 1 | 设置家 |
| `home` | 1 | 传送回家 |
| `delhome` | 1 | 删除家 |
| `wp` | 1 | 查看地标列表 / 传送到地标 |
| `setwp` | 2 | 创建地标（管理级） |
| `delwp` | 2 | 删除地标（管理级） |
| `back` | 1 | 回到死亡点 |
| `tpm` | 1 | 坐标传送 |
| `tpa` | 1 | 请求传送到他人 |
| `tpahere` | 2 | 请求他人传送到自己 |
| `tpaccept` | 0 | 同意传送请求 |
| `tpacancel` | 0 | 拒绝传送请求 |

> **帮助信息按权限过滤，并按命令树分组**：`!!mtpm help` 只显示**家 / back / 坐标传送 / tpa** 的命令行，地标命令请用 `!!mwp help`（可简写 `!!mwp h`）。两者都会按玩家权限过滤掉无权使用的行 —— 例如权限等级为 `1` 的玩家看不到 `tpahere`（需 2）和 `reload`（需 3）。控制台/管理员可见全部。

#### 冷却时间 (`cd`)

单位为秒，设为 `0` 表示无冷却。各功能独立计时。

| 键 | 默认值 | 说明 |
|----|--------|------|
| `home` | 100 | home 传送冷却 |
| `wp` | 10 | warp 地标传送冷却 |
| `back` | 60 | back 传送冷却 |
| `tpm` | 60 | 坐标传送冷却 |
| `tpa` | 60 | tpa/tpahere 冷却 |

#### 其他配置

| 键 | 默认值 | 说明 |
|----|--------|------|
| `default_sethome_max` | 3 | 每个玩家最多设置的家数量 |
| `home_list_page_size` | 10 | `!!mhome list` 每页显示的家数量 |
| `warp_max` | 20 | 全服地标总数量上限（所有玩家共用） |
| `warp_list_page_size` | 10 | `!!mwp list` 每页显示的地标数量 |
| `tp_delay` | 5 | tpa/tpahere 同意后延迟传送秒数，`0` 为立即传送 |
| `tpa_timeout` | 60 | tpa/tpahere 请求超时秒数 |
| `tp_move_threshold` | 1.0 | 延迟传送期间移动取消阈值（±格，xyz 各自判断） |
| `tp_check_interval` | 0.5 | 延迟传送期间位置检测间隔（秒） |
| `debug_teleport_log` | false | 传送审计日志开关，详见下方 |

#### 传送审计日志 (`debug_teleport_log`)

默认 `false`，此时**不产生任何传送相关日志**。

设为 `true` 后，会在服务端日志记录每次传送的**前后坐标、目标点与耗时**，便于排查「传送失败/传送到了错误位置」这类问题；地标的创建与删除也会一并记录：

```
[TpMaple] 传送成功 [home] Morning_Maple → 家 base 主世界 (10.0, 64.0, 20.0) | 前 主世界 (1.0, 64.0, 2.0) | 后 主世界 (10.0, 64.0, 20.0) | 耗时 0.51s
[TpMaple] 传送取消 [wp] Morning_Maple → 地标 spawn 主世界 (0.0, 64.0, 0.0) | 原因 冷却剩余 3s
[TpMaple] 地标创建 [setwp] Helper: shop 主世界 (120.0, 64.0, -30.0)
```

> 传送是高频操作，因此该开关**默认关闭**：开启后全量记录会让日志迅速膨胀，且记录「传送后坐标」需要额外回查一次玩家位置（会有一次 `tp_check_interval` 的等待）。仅在排查问题时临时开启即可。

#### 玩家数据（分片存储）

玩家数据按 UUID 分片存储于 `config/tp_maple/player_data/players/<uuid>.json`，每个玩家一个文件，与配置文件分离。自动管理，**无需手动编辑**；数据全空时对应分片文件会被自动删除。

#### 地标数据（全服共享）

全服地标存储于 `config/tp_maple/warp_data/warps.json`（单文件，原子写），与玩家数据分离。同样自动管理，**无需手动编辑**；无地标时文件会被自动删除。

```json
{
    "warps": {
        "shop": {
            "x": 120.0,
            "y": 64.0,
            "z": -30.0,
            "dimension": "minecraft:overworld",
            "creator": "Helper",
            "created_at": 1759355400.0,
            "comment": "主城商店"
        }
    }
}
```

> `comment` 为 1.2.1 新增字段；旧地标没有该字段时列表会显示为「无」，不影响使用。

## 功能细节

### 列表的排序规则

`!!mhome`（家列表）与 `!!mwp`（地标列表）均按名字排序，复刻 **Windows 资源管理器的自然排序**
（即 Windows 实际使用的 `StrCmpLogicalW`，本项目已用该系统函数对约 1.3 万个名字做过逐条对拍，结果完全一致）：

| 规则 | 示例 |
|------|------|
| 数字按**数值**比较（自然排序） | `wp2` < `wp10`，`endfarm2` < `endfarm10` |
| 数字块整体**排在字母前** | `1st` < `afk`，`11` < `a` |
| **前导零**：数值相同时位数多者在前 | `wp001` < `wp01` < `wp1` |
| **忽略大小写**，相等者保持数据原有先后 | `Shop` 与 `shop` 视为同级 |
| 短者在前（前缀关系） | `wp` < `wp1` |

排序在**分页之前**执行，因此每页内容稳定、翻页不会出现重复或遗漏。

> 说明：Windows 对中文是按区域设置（拼音/笔画）排序的，本插件未复刻该行为 ——
> 非 ASCII 字符退化为按 Unicode 码位比较。由于家名/地标名本身限定为 ASCII 字母数字，
> 实际不受影响。

### sethome / home / delhome

- 使用玩家 UUID 作为唯一标识符存储数据
- 家的名字**仅允许英文字母和数字**（不含中文、下划线及其他特殊符号）
- 家的名字重复时自动覆盖，不重复时检查数量上限
- home 传送使用普通传送（直接 tp 到记录的坐标和维度），传送成功提示显示维度中文名
- `!!mhome` 列表中每个家前都带 **可点击 `[传送]` / `[删除]` 按钮**（点击行为见 `use_suggest_command`）
- 列表按名字**自然排序**（与 `!!mwp` 同一套规则，见 [列表的排序规则](#列表的排序规则)）
- delhome 删除指定名字的家，名字不存在时会提示

### warp（地标传送）

与 `home` 不同，地标是**全服共享**的：任何玩家都能查看列表并传送，因此适合用于服务器公共传送点（主城、商店、刷怪塔等）。

- **可见性**：`!!mwp` 列表对所有玩家（含权限 1）可见，能互相看到对方创建的地标
- **权限分离**：
  - 查看列表与传送使用 `wp` 权限（默认 1）
  - 创建 / 删除使用 `setwp` / `delwp` 权限（默认 2，即 helper 及以上）
- **数量上限**：`warp_max`（默认 20）为**全服共用**上限，`setwp` 新增时会校验（`!!mwp` 标题栏显示 `当前数量/上限`）；可先 `!!mdelwp` 腾出名额
- **名字规则**：与家一致，**仅允许英文字母和数字**；`list` / `help` / `h` / `reload` / `reset` 为保留字（它们是 `!!mwp` 的子命令，作为名字会导致命令不可达，故创建时直接拒绝）
- **注释**：`!!msetwp` 的第二个参数，**可选**。允许中文与空格（含空格时需用引号包裹，如 `!!msetwp shop "主城 商店"`），上限 32 字符；颜色码与换行会被自动剔除，避免污染列表渲染
- **重名处理**：`!!msetwp` 遇到同名地标会**拒绝**，提示先 `!!mdelwp` 删除，避免误覆盖他人地标；如需修改注释，同样需先删除后重建
- **独立命令树**：地标有自己的一套命令与帮助，**不依赖 `!!mtpm`**：
  - `!!mwp help`（可简写 `!!mwp h`）：显示**仅地标相关**的帮助
  - `!!mwp reload`：重新载入配置文件（与 `!!mtpm reload` 同一套逻辑）
  - `!!mwp reset` / `!!mwp reset confirm`：清空所有玩家数据与地标（与 `!!mtpm reset` 清空范围相同）
  - 相应地，`!!mtpm help` 中**不再出现**地标相关命令行
- **列表**：`!!mwp` / `!!mwp list [页]` 分页展示（每页条数见 `warp_list_page_size`），标题显示 `(总数/上限) 第 x/y 页`
  - **排序**：按名字以 **Windows 资源管理器风格的自然排序**（复刻 `StrCmpLogicalW`）排列，详见下方
  - 每条占**两行**（用 `\n` 在同一条消息内换行，不额外刷屏）：
    - 第一行：可点击按钮 + 名字 + 维度（中文）+ 坐标（保留 1 位小数）
    - 第二行：`-- 注释内容` / `@创建人` / 创建时间（`YYYY-MM-DD HH:MM`，本地时区）
  - 每条前带 **可点击 `[传送]` 按钮**；有 `delwp` 权限的玩家额外带 **可点击 `[删除]` 按钮**（点击行为见 `use_suggest_command`）
  - 例如：

    ```
      [传送] [删除] shop — 主世界 (120.0, 64.0, -30.0)
          -- 主城商店  | @Helper  | 2026-10-02 05:30
    ```
  - 底部带可点击的 `[上一页]` / `[下一页]`
  - `!!mwp <名字>` 传送到指定地标（普通传送，受 `cd.wp` 冷却限制）
- **back 联动**：地标传送前会记录传送前位置为 back 点，落地后可 `!!mback` 返回
- **reset 联动**：执行 `!!mtpm reset` 或 `!!mwp reset` 都会连同所有地标一并清空（两者清空范围相同，均需二次确认）

### back

- **back 点（上一次的传送/死亡地点）**：插件维护一个运行时（不持久化，重启/重载清空）的「back 点」，会被以下事件覆盖为**最近一次**的位置：
  - 调用本插件的传送前的位置：`tpm`、接受 `tpa`/`tpahere`、`home`、`wp`（地标传送）、以及 `back` 自身（因此连续 `back` 可在两点间来回）
  - 玩家死亡：死亡时记录死亡地点（读取原版 `LastDeathLocation`）
  - 若运行时尚无 back 点（如刚重启），`!!mback` 会回退到实时查询原版死亡点
- `!!mback`：**精确**传送回 back 点（x/y/z/维度完全一致），成功提示「已回到上一次的传送/死亡地点」
  - **虚空兜底**：若目标点处于虚空高度（主世界 `y < -128`，地狱/末地 `y < -64`），精确传送会再次坠亡，此时自动降级为 **±8 格高精度安全传送**，并提示「精确传送不可用，已降级使用高精度安全传送替代」
- `!!mback safe`（可简写 `!!mback s`）：使用安全传送（`spreadplayers`），在 back 点 xz ±64 格范围内寻找安全落点，y 轴自动；适合目标处为岩浆等危险地形
  - **传送校验**：安全传送可能找不到落点而静默失败，因此传送后会回查玩家位置（位移之和 > 4 视为成功）；若失败则提示「未找到安全的落点，传送失败」并**退还冷却**（且不更新 back 点）
- 两者共用同一权限（`back`）与冷却（`cd.back`）
- 玩家死亡时会收到带 **可点击 `[精确返回]` / `[安全返回]` 按钮** 的提示（点击行为见 `use_suggest_command`）

### tpm（坐标传送）

- 维度参数可选，不填则使用玩家当前所在维度
- 维度使用全称，如 `minecraft:overworld`、`minecraft:the_nether`、`minecraft:the_end`
- 输入时有维度提示词补全

### tpa / tpahere

- **tpa**：发起方传送到目标方的位置
- **tpahere**：目标方传送到发起方的位置
- 被请求方会收到带 **可点击 `[同意]` / `[拒绝]` 按钮** 的提示，点击即执行对应命令（无需手动输入）
- 请求以栈结构存储（后进先出），accept/cancel 操作栈顶
- 请求超时后自动失效（`tpa_timeout` 设为 `0` 表示永不超时）
- 同意后支持延迟传送，延迟期间被传送方移动超过阈值、或切换维度则取消
- 移动取消只通知被传送方，另一方无感
- 玩家离线时，以其为目标的待处理请求会自动清理，避免内存泄漏

## 项目结构

```
tp_maple/
├── __init__.py              # 插件入口 + 事件监听（加入/离开/死亡检测）
├── default_config.py        # 配置定义 + 维度数据 + 死亡关键词 + 帮助生成
├── my_lib.py                # 配置读写 + 数据管理 + 命令注册 + 在线/死亡检测
├── context.py               # 玩家命令上下文（样板收敛：仅玩家校验 / 取 UUID）
├── pagination.py            # 通用分页类 Paginator（页码夹取 / 切片 / 翻页栏）
├── teleport.py              # 全局传送服务 TeleportService（精确 / 安全 / 延迟）
├── cooldown.py              # 冷却管理工具类
├── utils.py                 # 工具函数（NBT int array → UUID、Windows 风格自然排序键）
└── commands/
    ├── __init__.py
    ├── home.py              # sethome / home / delhome
    ├── warp.py              # setwp / wp / delwp（全服地标）
    ├── back.py              # back
    ├── tp.py                # tpm（坐标传送）
    └── tpa.py               # tpa / tpahere / tpaccept / tpacancel
```

### 分层设计

```
commands/*            ← 业务层：只负责「定位目标点 + 组装参数」
    │                    例如「查到家 base 的坐标」后调用传送服务
    ├── context.py        resolve_player(source) 统一「仅玩家可执行 / 取 UUID」
    ├── pagination.py     Paginator 统一列表分页
    └── teleport.py       TeleportService 统一传送流程
          ├── 冷却校验与扣除（失败自动退还）
          ├── back 点记录（供 !!mback 返回）
          ├── 传送执行（tp / spreadplayers）
          ├── 结果校验（安全传送回查位置）
          ├── 玩家提示（文案模板由业务传入，服务负责渲染）
          └── 审计日志（受 debug_teleport_log 开关控制）
```

业务命令统一在**查询目标点之前**调用 `service.ensure_ready(ctx, feature)` 做冷却预检，这样提示顺序恒为「冷却中」优先于「未找到目标」——否则冷却中的玩家会先看到目标查询结果甚至「正在查询死亡记录……」这类过程性提示，随后才被冷却拦下，造成"传送已开始"的误导。`precise`/`safe` 内部仍会再校验一次冷却（幂等、不重复提示），因此即使漏调预检，冷却也不会失效。

业务命令不直接拼 `tp` 指令、不直接操作冷却与 back 点，因此新增一个传送玩法时，只需组装一个 `TpTarget`：

```python
ctx = resolve_player(source)
if ctx is None:
    return
if not tp_core.service.ensure_ready(ctx, "wp"):      # 冷却预检（先于目标查询）
    return

info = my_lib.get_warps().get(warp_name)
if info is None:
    ctx.reply(f"{TAG}§c未找到名为 §e{warp_name} §c的地标")
    return

tp_core.service.precise(ctx, tp_core.TpTarget(
    x=info["x"], y=info["y"], z=info["z"], dimension=info["dimension"],
    feature="wp",                                    # 冷却与日志的功能名
    label=f"地标 {warp_name}",                       # 审计日志里的目标描述
    success_msg="§a已传送到地标 §e" + warp_name + " §7— {dim_cn} ({x}, {y}, {z})",
))
```

## 许可证

[CC0 1.0 Universal](LICENSE)

## 作者

**Morning_Maple**
