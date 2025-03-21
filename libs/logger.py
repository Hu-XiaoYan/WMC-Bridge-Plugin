import logging
import colorlog

def setup_colored_log():
    #如果有重复Handler直接返回
    if logging.getLogger().hasHandlers():
        return

    #定义颜色配置
    log_colors = {'DEBUG': 'green','INFO': 'white','WARNING': 'yellow','ERROR': 'red',
'CRITICAL': 'white,bg_red',}

    #创建ColorFormatter
    formatter = colorlog.ColoredFormatter(
fmt='%(log_color)s%(asctime)s [%(levelname)s] %(funcName)s -> %(message)s',
datefmt='%Y-%m-%d %H:%M:%S',
log_colors=log_colors)

    # 创建StreamHandler并设置格式
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # 配置根Logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)