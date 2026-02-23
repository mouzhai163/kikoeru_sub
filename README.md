# Kikoeru 字幕显示工具（Windows）

本项目用于在 Windows 下为 **Kikoeru** 网站显示桌面悬浮字幕。 这个项目是我让AI花了两个半小时写出来的. 感觉还行吧,目前可以兼容我的kikoeru库和asmr.one的网站,至于其他版本,理论上来说是可以的.

## 功能

- 打开 Kikoeru 页面并播放音频时，自动识别并显示字幕
- 字幕悬浮窗始终置顶，可拖动、可锁定（鼠标穿透）
- 支持调整字幕字体大小、颜色、窗口尺寸
- 字幕默认白色并带描边，提升可读性
- 配置自动保存到程序同目录 `settings.json`

## 运行环境

### 直接使用 EXE

- Windows 10/11 64 位
- 不需要安装 Python

### 从源码运行

- Python 3.10+
- 依赖：`requirements.txt`

### 源码方式

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```





### 在线乞讨

如果对你有帮助,可以考虑给我赏口饭吃.  真的要吃不上饭了....  在线接爬虫,程序开发 nextJS全栈开发

