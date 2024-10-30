DEFAULT_CONFIG = \
    {
        "server_list": [
            "mirror",
            "create"
        ],
        "perm": {
            "help": 0,
            "list": 1,
            "reload": 2,
            "sync": 2,
            "start": 2,
            "stop": 2,
            "show": 1,
            "status": 1,
        },
        "mirror": {
            "can_sync": True,
            "description": "镜像服务器",
            "port": 25566,
            "rcon": {
                "enable": True,
                "host": "127.0.0.1",
                "port": 25576,
                "password": "abc1234"
            },
            "source": "./server",
            "target": "./Mirror/server",
            "ignore_files": [
                "pca.conf",
                "carpet.conf"
            ]
        },
        "create": {
            "can_sync": False,
            "description": "创造服务器",
            "port": 25567,
            "rcon": {
                "enable": False,
                "host": "127.0.0.1",
                "port": 25577,
                "password": "password"
            },
            "source": "./server",
            "target": "./Create/server",
            "ignore_files": [
                "pca.conf",
                "carpet.conf"
            ]
        }
    }

PLUGIN_METADATA = "1.0.0-beta.1"

# 默认帮助信息
HELP_MSG = '''{:=^50}
§b!!msc §r- §6显示帮助信息
§b!!msc help §r- §6显示帮助信息
§b!!msc list §r- §6显示在册的服务器名字
§b!!msc reload §r- §6重新载入配置
§b!!msc sync <server_name> §r- §6对名为server_name的服务器进行同步
§b!!msc start <server_name> §r- §6启动名为server_name的服务器
§b!!msc stop <server_name> §r- §6关闭名为server_name的服务器（需要开启Rcon）
§b!!msc show <server_name> §r- §6查看名为server_name的服务器信息
§b!!msc status <server_name> §r- §6查询名为server_name的服务器的状态（正在运行/已关闭）
{:=^50}''' \
    .format(' §b[MultiServerControl] 帮助信息 §r',
            ' §b[MultiServerControl] Version: {} §r'
            .format(PLUGIN_METADATA))
