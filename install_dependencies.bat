@echo off
echo installing...
set MIRROR_URL=-i https://pypi.tuna.tsinghua.edu.cn/simple

REM 升级pip到最新版本
python -m pip install --upgrade pip %MIRROR_URL%
REM 安装核心依赖库
pip install %MIRROR_URL% tomli ttkbootstrap requests colorlog pillow winsdk pywin32

echo install complete!
echo press any key...
pause >nul