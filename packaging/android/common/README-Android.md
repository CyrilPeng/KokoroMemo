# KokoroMemo Android 安装包

本包面向 Android/Termux 部署，已内置 KokoroMemo 后端源码、预构建 Web UI 和安装脚本。用户不需要在手机上运行 `npm install` 或 `npm run build`。

## 安装

### 推荐：Termux 一键安装

在 Termux 中执行：

```bash
pkg update -y && pkg install -y curl python && curl -fsSL https://github.com/CyrilPeng/KokoroMemo/raw/main/scripts/termux-setup.sh | bash
```

如果 GitHub 访问不稳定，可以使用 Gitee 地址：

```bash
pkg update -y && pkg install -y curl python && curl -fsSL https://gitee.com/Cyril_P/KokoroMemo/raw/main/scripts/termux-setup.sh | bash
```

脚本会自动安装基础依赖、读取 `latest.json`、下载最新 `Android-Termux-aarch64` 单包、校验 SHA256、安装并启动服务。

### 手动安装单包

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
bash update.sh     # 检查并更新到最新版本
bash doctor.sh     # 诊断环境
bash backup.sh     # 备份 config.yaml 和 data/
```

如果使用一键安装脚本，还会创建 `kokoromemo` 命令：

```bash
kokoromemo start      # 启动
kokoromemo stop       # 停止
kokoromemo update     # 更新
kokoromemo doctor     # 诊断
```

## 更新

```bash
bash update.sh
```

更新脚本会自动选择当前运行环境对应的 Android aarch64 包，校验 SHA256 后替换程序文件。

更新会保留 `config.yaml` 和 `data/`，并在 `backups/` 下生成更新前的数据备份和程序备份。

## 包选择

- `Android-Termux-aarch64`：推荐，大多数现代 Android 手机使用。
- `Android-ProotUbuntu-aarch64`：Termux 原生安装失败时使用，需要先进入 proot Ubuntu 环境。

请不要混用不同运行环境的包；Termux 原生 wheel 与 proot Ubuntu wheel 不保证兼容。
