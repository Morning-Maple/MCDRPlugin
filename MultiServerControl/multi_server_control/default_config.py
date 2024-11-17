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
            "restart": 2,
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

PLUGIN_METADATA = "1.0.1"

START_WAIT_TIME = 10

# 默认帮助信息
HELP_MSG = '''{:=^50}
§b!!msc  §f-- §6显示帮助信息
§b!!msc help  §f-- §6显示帮助信息
§b!!msc list  §f-- §6显示在册的服务器名字
§b!!msc reload  §f-- §6重新载入配置文件
§b!!msc restart §e<server_name>  §f-- §6对目标服务器进行重启
§b!!msc restart §e<server_name> §bsync  §f-- §6对目标服务器进行同步并重启
§b!!msc sync §e<server_name>  §f-- §6对目标服务器进行同步
§b!!msc start §e<server_name>  §f-- §6启动目标服务器
§b!!msc stop §e<server_name>  §f-- §6关闭目标服务器（需要开启Rcon）
§b!!msc show §e<server_name>  §f-- §6查看目标服务器信息
§b!!msc status §e<server_name>  §f-- §6查询目标服务器的状态
{:=^50}
§lBy：§6§lMorning_Maple
''' \
    .format(' §b[MultiServerControl] 帮助信息 §r',
            ' §b[MultiServerControl] Version: {} §r'
            .format(PLUGIN_METADATA))
