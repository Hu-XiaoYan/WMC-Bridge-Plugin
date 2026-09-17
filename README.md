# WMC-Bridge-Plugin
![tip](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white) ![tip](https://badgen.net/github/license/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/github/commits/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/github/last-commit/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/badge/Last-Test-Version/Beta-0.2/cyan)  
一个简单的Python插件, 可将网易云音乐正在播放的音乐信息映射到文本文件中
目前该项目处于测试状态, 暂时不会发包  
若有需要可以运行install_dependencies.bat安装依赖后运行run-ttk.py使用  

#### 目前支持的播放器
![tip](https://badgen.net/badge/网易云音乐/已支持/green)  
可在issue中提出你需要支持的播放器  

#### 目前项目可实现的功能以及当前存在的问题
* 实时更新歌曲名, 艺术家  ✅  
* 实时输出当前播放歌曲的时间线及实时歌词到路径下 ✅  

#### 使用效果
![使用效果](./md/使用效果.png)  
#### 使用教程
请等待正式版发布后查看教程, 或查询Tuna插件基础用法  
#### 基址列表
若没有你需要的版本, 可以使用CE自行抓取或提ISSUE  
* 网易云音乐
    * Ver3.1.9 --> now
    position = 0x1be2300
    end = 0x1c3ccd8
    song_id = [0x01c3c030, 0x10, 0x8, 0x10, 0x68]
    * Ver3.1.7 --> 3.1.8
    position = 0x1b4f200
    end = 0x1ba74f8
    song_id = [0x01ba6a20, 0x10, 0x8, 0x10, 0x68]
    * Ver3.1.5 --> 3.1.6  
    position = 0x1a0cf70
    end = 0x1a5d268
    song_id = [0x01a5c790, 0x10, 0x8, 0x10, 0x68]