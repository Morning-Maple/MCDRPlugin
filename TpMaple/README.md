# TpMaple 🍁

一个功能齐全的 [MCDReforged](https://github.com/Fallen-Breath/MCDReforged) 传送管理插件，提供 sethome、home、back、坐标传送、tpa 等常用传送功能。

## 功能一览

> 下表命令均以默认的 **Maple 前缀**（`!!m...`）形式展示。若在配置中关闭 `use_maple_prefix`，则所有命令去掉前缀中的 `m`，例如 `!!mtpa` → `!!tpa`、`!!mtpm` → `!!tpm`。详见[配置说明](#配置说明)。

| 命令 | 说明 |
|------|------|
| `!!msethome <名字>` | 将当前位置设为家，名字重复则覆盖（名字仅允许英文字母和数字） |
| `!!mhome` | 列出你所有已设置的家 |
| `!!mhome list [页]` | 分页查看家列表（带可点击翻页） |
| `!!mhome <名字>` | 传送到指定的家 |
| `!!mdelhome <名字>` | 删除指定的家 |
| `!!mback` | 精确传送回上一次的传送/死亡地点 |
| `!!mback safe` | 安全传送到上一次的传送/死亡地点附近（死在岩浆/危险处时用） |
| `!!mtpm <x> <y> <z> [维度]` | 传送到指定坐标，维度可选（不填则为当前维度） |
| `!!mtpa <玩家名>` | 请求传送到目标玩家的位置 |
| `!!mtpahere <玩家名>` | 请求目标玩家传送到你的位置 |
| `!!mtpaccept` | 同意最近一条传送请求 |
| `!!mtpacancel` | 拒绝最近一条传送请求 |
| `!!mtpm help` | 显示帮助信息 |
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
        "back": 1,
        "tpm": 1,
        "tpa": 1,
        "tpahere": 2,
        "tpaccept": 0,
        "tpacancel": 0
    },
    "cd": {
        "home": 100,
        "back": 60,
        "tpm": 60,
        "tpa": 60
    },
    "default_sethome_max": 3,
    "home_list_page_size": 10,
    "tp_delay": 5,
    "tpa_timeout": 60,
    "tp_move_threshold": 1.0,
    "tp_check_interval": 0.5
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
| `back` | 1 | 回到死亡点 |
| `tpm` | 1 | 坐标传送 |
| `tpa` | 1 | 请求传送到他人 |
| `tpahere` | 2 | 请求他人传送到自己 |
| `tpaccept` | 0 | 同意传送请求 |
| `tpacancel` | 0 | 拒绝传送请求 |

> **帮助信息按权限过滤**：执行 `!!tpm` / `!!tpm help` 时，帮助列表只会显示该玩家**权限足够**的命令行。例如权限等级为 `1` 的玩家看不到 `tpahere`（需 2）和 `reload`（需 3）。控制台/管理员可见全部。

#### 冷却时间 (`cd`)

单位为秒，设为 `0` 表示无冷却。各功能独立计时。

| 键 | 默认值 | 说明 |
|----|--------|------|
| `home` | 100 | home 传送冷却 |
| `back` | 60 | back 传送冷却 |
| `tpm` | 60 | 坐标传送冷却 |
| `tpa` | 60 | tpa/tpahere 冷却 |

#### 其他配置

| 键 | 默认值 | 说明 |
|----|--------|------|
| `default_sethome_max` | 3 | 每个玩家最多设置的家数量 |
| `home_list_page_size` | 10 | `!!mhome list` 每页显示的家数量 |
| `tp_delay` | 5 | tpa/tpahere 同意后延迟传送秒数，`0` 为立即传送 |
| `tpa_timeout` | 60 | tpa/tpahere 请求超时秒数 |
| `tp_move_threshold` | 1.0 | 延迟传送期间移动取消阈值（±格，xyz 各自判断） |
| `tp_check_interval` | 0.5 | 延迟传送期间位置检测间隔（秒） |

#### 玩家数据（分片存储）

玩家数据按 UUID 分片存储于 `config/tp_maple/player_data/players/<uuid>.json`，每个玩家一个文件，与配置文件分离。自动管理，**无需手动编辑**；数据全空时对应分片文件会被自动删除。

## 功能细节

### sethome / home / delhome

- 使用玩家 UUID 作为唯一标识符存储数据
- 家的名字**仅允许英文字母和数字**（不含中文、下划线及其他特殊符号）
- 家的名字重复时自动覆盖，不重复时检查数量上限
- home 传送使用普通传送（直接 tp 到记录的坐标和维度），传送成功提示显示维度中文名
- `!!mhome` 列表中每个家前都带 **可点击 `[传送]` / `[删除]` 按钮**（点击行为见 `use_suggest_command`）
- delhome 删除指定名字的家，名字不存在时会提示

### back

- **back 点（上一次的传送/死亡地点）**：插件维护一个运行时（不持久化，重启/重载清空）的「back 点」，会被以下事件覆盖为**最近一次**的位置：
  - 调用本插件的传送前的位置：`tpm`、接受 `tpa`/`tpahere`、`home`、以及 `back` 自身（因此连续 `back` 可在两点间来回）
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
├── teleport.py              # 传送底层（普通 / 安全 / 延迟 / 传送校验）
├── cooldown.py              # 冷却管理工具类
├── utils.py                 # 工具函数（NBT int array → UUID）
└── commands/
    ├── __init__.py
    ├── home.py              # sethome / home / delhome
    ├── back.py              # back
    ├── tp.py                # tpm（坐标传送）
    └── tpa.py               # tpa / tpahere / tpaccept / tpacancel
```

## 许可证

[CC0 1.0 Universal](LICENSE)

## 作者

**Morning_Maple**
