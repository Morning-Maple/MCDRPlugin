import json
import os.path
import re
import shutil

from mcdreforged.api.all import *

from multi_server_control import my_lib


def on_load(server: PluginServerInterface, old):
    """
    插件加载时需要干的工作
    :param server: 本次实例
    :param old: 该模块上一次的实例
    :return:
    """
    my_lib.register(server)


def on_unload(server: PluginServerInterface):
    """
    插件被卸载的时候需要干的工作
    :param server: 本次实例
    :return:
    """
    server.logger.info('[MSC]已被卸载')


def on_info(server: PluginServerInterface, info: Info):
    """
    常规服务器输出事件处理（服务器输出一行新文本或从控制台中键入文本时触发）
    :param server:
    :param info:
    :return:
    """
    # if not info.is_user and re.fullmatch(r'Starting Minecraft server on \S*', info.content):
    #     server.logger.info('Minecraft is starting at address {}'.format(info.content.rsplit(' ', 1)[1]))


def on_user_info(server: PluginServerInterface, info: Info):
    """
    用户发送消息时处理
    """
    # if info.content == '!!example':
    #     server.reply(info, 'example!!')
