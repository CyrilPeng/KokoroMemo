# 发布构建流程

KokoroMemo 的发布工作流支持两种入口：

- 推送 `v*` tag：自动构建所有平台产物，并发布到 GitHub Release。
- 手动触发 `构建与发布` workflow：输入任意版本号构建产物，默认只上传 artifacts，不发布 Release。

## 发布前本地检查

正式发版或手动 dry-run 前，建议先在本地跑一轮和 CI 口径一致的检查：

```bash
uvx ruff check app/ tests/ benchmarks/ .github/scripts/
uvx ruff format --check app/ tests/ benchmarks/ .github/scripts/
python .github/scripts/stamp_version.py --check
uv run --extra dev python -m pytest tests/test_ux_api.py -q -k "airp_first_run_status"
uv run --extra dev python benchmarks/run_airp_benchmark.py --smoke --report-dir benchmarks/reports/first-run
```

其中 `tests/test_ux_api.py` 会覆盖 `/admin/airp-first-run-status` 的空状态和完整闭环响应，确保仪表盘验收面板、CLI 或后续自动化都使用同一套 AIRP 首次成功契约。

CI 的 `后端测试（pytest）` job 会把这组测试作为独立步骤 `验证 AIRP 首次成功契约` 运行，然后再跑全量后端测试和 smoke benchmark。Release workflow 的 `发布前 AIRP 检查` 也会先运行同一个契约测试，再进入 benchmark 测试和完整 benchmark；这些检查都通过 ASGI 测试客户端完成，不依赖真实后端服务。

如果已经启动本地服务，也可以直接读取接口确认下一步：

```bash
curl http://127.0.0.1:14514/admin/airp-first-run-status
```

如果启用了 Admin Token，请按当前管理 API 的鉴权方式携带 token。

当接口返回 `ready: true` 后，再运行完整 AIRP benchmark 或触发发布工作流。

## 手动 dry-run

适合在正式发版前验证 CI 链路、产物命名和版本写入。

GitHub 页面操作：

1. 打开 Actions -> `构建与发布`。
2. 点击 `Run workflow`。
3. `version` 填写目标版本，例如 `0.13.1` 或 `v0.13.1`。
4. `publish_release` 保持 `false`。
5. 等待 workflow 完成。

GitHub CLI：

```bash
gh workflow run release.yml -f version=0.13.1 -f publish_release=false
```

dry-run 通过标准：

- `准备构建参数` 输出版本号和 `发布到 Release：false`。
- `发布前 AIRP 检查` 中的 `验证 AIRP 首次成功契约`、AIRP benchmark 测试和完整 AIRP benchmark 均通过，并上传 `airp-benchmark-release` artifact。
- 后端、桌面端和 Android 单包构建 job 通过。
- Artifacts 中出现对应版本号的产物，例如 `KokoroMemo-0.13.1-Windows-Portable.zip`。
- `发布 GitHub Release` job 被跳过。

## 手动发布

手动发布适合补发指定提交的版本，或在 tag 之外复用同一套构建流程。

```bash
gh workflow run release.yml -f version=0.13.1 -f publish_release=true
```

手动发布会创建或更新 `v0.13.1` 的 GitHub Release，并把当前触发 workflow 的提交作为 Release target。除非需要补发，不建议用手动发布替代 tag 发布。

## Tag 发布

正式发布仍推荐使用 tag：

```bash
git tag v0.13.1
git push origin v0.13.1
```

tag 发布会自动：

- 验证 `/admin/airp-first-run-status` 的首次成功契约。
- 运行完整 AIRP benchmark。
- 构建后端二进制、桌面包和 Android 单包。
- 生成 `latest.json` 与 `SHA256SUMS.txt`。
- 创建或更新 GitHub Release。

## 版本一致性

CI 会运行：

```bash
python .github/scripts/stamp_version.py --check
```

检查以下文件版本是否一致：

- `pyproject.toml`
- `gui/package.json`
- `gui/package-lock.json`
- `gui/src-tauri/tauri.conf.json`
- `gui/src-tauri/Cargo.toml`

构建时 workflow 会运行：

```bash
python .github/scripts/stamp_version.py --version <version>
```

它会把输入版本写入后端、前端和 Tauri/Cargo 元数据，并生成 `app/_version.py` 作为打包后的后端版本兜底。
