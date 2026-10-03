# WMC-Bridge-Plugin
![tip](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white) ![tip](https://badgen.net/github/license/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/github/commits/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/github/last-commit/Hu-XiaoYan/WMC-Bridge-Plugin) ![tip](https://badgen.net/badge/Last-Version/Beta-1.0/cyan)  
一个简单的Python插件, 可将不支持SMTC或支持SMTC不完全的音乐软件正在播放的音乐信息映射到SMTC和文本文件中

#### 目前支持的播放器
![tip](https://badgen.net/badge/网易云音乐-3.0+/已支持/green) ![tip](https://badgen.net/badge/汽水音乐/已支持/green) ![tip](https://badgen.net/badge/千千静听/正在尝试开发/red) 
可在issue中提出你需要支持的播放器  

#### 目前项目可实现的功能以及当前存在的问题
* 实时更新歌曲名, 艺术家  ✔️  
* 实时输出当前播放歌曲的时间线及实时歌词到路径下 ✔️  
* 汽水音乐由于使用的分享页API, 可能导致部分歌曲没有歌词, 外文歌只能显示原文歌词 ❌
* 汽水音乐由于使用锚点更新SMTC的播放状态, 可能导致插件和实际上的时间有1-2秒差距 ℹ️
 
#### 使用教程
* 首先打开软件和音乐播放器, 点击开始监听
* 在OBS添加一个来源为文件的文本源 (/data/你使用的音乐播放器/lyric.txt)
* 在Tuna中将音乐来源改为WindowsMediaControl 并选中python.exe
* 在Tuna中开启尝试下载歌曲封面(不用开搜索遗失的封面选项)
* 在OBS中添加一个图片源, 路径就是刚刚设定的歌曲封面路径
* (可选)添加Tuna进度条控件

至此您应该可以正常使用这个插件了, 如果有BUG请及时提issue