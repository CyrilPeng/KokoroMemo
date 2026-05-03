# KokoroMemo Android 安装包

本包面向 Android/Termux 部署，已内置 KokoroMemo 后端源码、预构建 Web UI 和安装脚本。用户不需要在手机上运行 `npm install` 或 `npm run build`。

## 安装

### 推荐：Termux 一键安装

在 Termux 中推荐使用 Gitee 地址执行：

```bash
curl -fsSL https://gitee.com/Cyril_P/KokoroMemo/raw/main/scripts/termux-setup.sh | bash
```

如果你可以稳定访问 GitHub，也可以使用 GitHub 地址：

```bash
curl -fsSL https://github.com/CyrilPeng/KokoroMemo/raw/main/scripts/termux-setup.sh | bash
```

脚本会自动安装必要依赖、下载当前稳定版 `Android-Termux-aarch64` 单包、安装并启动服务。脚本不会执行 `pkg upgrade` 全量系统升级，避免第一次安装额外下载大量 Termux 系统包。

安装过程中如果 Termux 提示 `openssl.cnf` 等配置文件是否覆盖，脚本会默认保留当前配置并继续安装；如果虚拟环境创建失败，脚本会自动补齐 pip/ensurepip 组件后重试。

Termux 端会优先使用系统预编译的 `python-pydantic`，避免在手机上编译 `pydantic-core` / Rust 扩展。如果你看到旧脚本正在下载 `pydantic_core-*.tar.gz`，请按 `Ctrl+C` 取消后重新运行上面的一键安装命令。

为了避免首次安装卡在 GitHub 或镜像清单请求上，安装脚本默认不请求 `latest.json`，而是直接使用内置的当前稳定版本下载地址。安装完成后可用 `kokoromemo update` 检查后续更新。

脚本内部会优先切换到清华 Termux 源，并在依赖安装失败时尝试其他镜像。如果仍然提示某个软件源连接失败，例如 `Unable to connect to linux.domainesia.com`，可以单独执行换源命令后再重试：

```bash
sed -i 's|^deb .*termux-main.*|deb https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main stable main|' $PREFIX/etc/apt/sources.list
pkg update -y
```

如果看到 Termux 正在下载大量系统包且速度很慢，可以先按 `Ctrl+C` 取消，执行上面的换源命令后重新运行一键安装。

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
