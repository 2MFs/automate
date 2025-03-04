<div align="center"><a name="readme-top"></a>

<img src="./resources/logo.png" width="120" height="120" alt="autoMate logo">
<h1>autoMate</h1>
<p><b>🤖 AI驱动的本地自动化工具 | 让电脑自己会干活</b></p>

</div>

## 💡项目简介

autoMate 是一款革命性的AI+RPA自动化工具，基于OmniParser构建，让AI成为你的"数字员工"，它能够：

- 📊 自动操作您的电脑界面，完成复杂的工作流程；
- 🔍 智能理解屏幕内容，模拟人类视觉和操作；
- 🧠 自主决策，根据任务需求进行判断并采取行动；
- 💻 支持本地化部署，保护您的数据安全和隐私。

不同于传统RPA工具的繁琐规则设置，autoMate借助大语言模型的能力，只需用自然语言描述任务，AI就能完成复杂的自动化流程。从此告别重复性工作，专注于真正创造价值的事情！

## ✨功能特点
- 🔮 无代码自动化 - 使用自然语言描述任务，无需编程知识
- 🖥️ 全界面操控 - 支持任何可视化界面的操作，不限于特定软件
- 🚅 简化安装 - 比官方版本更简洁的安装流程，支持中文环境，一键部署
- 🔒 本地运行 - 保护数据安全，无需担心隐私泄露
- 🌐 多模型支持 - 兼容主流大型语言模型

## 🚀快速开始

### 📦安装
Clone项目，然后安装环境：

```bash
git clone https://github.com/yuruotong1/autoMate.git
cd autoMate
conda create -n "automate" python==3.12
conda activate automate
pip install -r requirements.txt
```
### 🎮启动应用

```bash
python main.py
```
然后在浏览器中打开`http://localhost:7888/`，配置您的API密钥和基本设置。


## 📝常见问题

### 🔧CUDA版本不匹配问题
可以通过`pip list`查看pytorch版本，然后从[官网]([官网](https://pytorch.org/get-started/locally/)查看支持的cuda版本。如果cuda不匹配就无法使用GPU，这会导致运行过程非常卡。比如如果`pip list`查看的 torch 版本为 2.6.0，那么它只支持cuda版本为11.8、12.4和12.6，请升级或者降级你的cuda版本到这几个版本。

如果启动时报：“显卡驱动不适配，请根据readme安装合适版本的 torch”。那么你需要：
1. 卸载当前PyTorch版本
```shell
pip uninstall torch torchvision torchaudio
```
2. 安装支持CUDA 12.6（你自己的cuda版本）的PyTorch版本，访问PyTorch官网(https://pytorch.org/get-started/locally/)
然后复制网站生成的安装命令，类似于：
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
```

## 🤝 参与共建

请参考[贡献指南](https://s0soyusc93k.feishu.cn/wiki/ZE7KwtRweicLbNkHSdMcBMTxngg?from=from_copylink).

> 强烈推荐阅读 [《提问的智慧》](https://github.com/ryanhanwu/How-To-Ask-Questions-The-Smart-Way)、[《如何向开源社区提问题》](https://github.com/seajs/seajs/issues/545) 和 [《如何有效地报告 Bug》](http://www.chiark.greenend.org.uk/%7Esgtatham/bugs-cn.html)、[《如何向开源项目提交无法解答的问题》](https://zhuanlan.zhihu.com/p/25795393)，更好的问题更容易获得帮助。

<a href="https://github.com/yuruotong1/autoMate/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=yuruotong1/autoMate" />
</a>

⭐ 如果这个项目对您有帮助，请给个Star支持一下！⭐