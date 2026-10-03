import logging
import sys

import colorlog

#这几个库的 debug 日志太吵, 会把自己的日志淹掉
NOISY_LOGGERS = ["requests", "urllib3", "PIL", "asyncio", "comtypes"]

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

    # 配置根Logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    #打包成无控制台程序时没有 stderr, 这时候就别加终端Handler(界面里那份日志照常)
    if sys.stderr is not None:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    #压掉第三方库的刷屏
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
