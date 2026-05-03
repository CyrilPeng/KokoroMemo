# KokoroMemo Android 安装包

本包面向 Android/Termux 部署，已内置 KokoroMemo 后端源码、预构建 Web UI 和安装脚本。用户不需要在手机上运行 `npm install` 或 `npm run build`。

## 安装

```bash
tar -xzf KokoroMemo-vX.Y.Z-Android-Termux-aarch64.tar.gz
cd KokoroMemo-Android-Termux-aarch64
bash install.sh
bash start.sh
```

启动后访问：

```text
Web UI: http://127.0.0.1:14514
OpenAI Base URL: http://127.0.0.1:14514/v1
```

如果首选端口不可用，请以启动脚本输出的实际端口为准。

## 常用命令

```bash
bash start.sh      # 启动
bash stop.sh       # 停止
bash restart.sh    # 重启
bash doctor.sh     # 诊断环境
bash backup.sh     # 备份 config.yaml 和 data/
```

## 包选择

- `Android-Termux-aarch64`：推荐，大多数现代 Android 手机使用。
- `Android-ProotUbuntu-aarch64`：Termux 原生安装失败时使用，需要先进入 proot Ubuntu 环境。

请不要混用不同运行环境的包；Termux 原生 wheel 与 proot Ubuntu wheel 不保证兼容。

