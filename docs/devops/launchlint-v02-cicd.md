# LaunchLint v0.2 CI/CD 流水线设计

## 概述

两条 GitHub Actions workflow，均在 `projects/launchlint/.github/workflows/` 下。

## CI: `ci.yml`

**触发条件：**
- push 到 `main` 分支
- 任意 PR 到 `main` 分支

**步骤：**
1. checkout
2. 安装 `uv`（启用缓存）
3. 缓存 `~/.cache/uv`
4. `uv sync --dev --frozen` 安装所有依赖（包括 dev）
5. `uv run ruff check src tests` — lint
6. `uv run pyright src` — 类型检查
7. `uv run pytest --cov=src --cov-fail-under=80 --cov-report=term-missing tests/` — 测试，覆盖率门槛 80%

**超时：** 2 分钟。超过则 fail。

**并发：** 同一 ref 的 workflow 自动取消，避免排队积压。

---

## CD: `release.yml`

**触发条件：** push 语义化 tag (`v0.2.0`、`v0.2.1` 等)

**前置要求：** tag push 前 CI 必须 green（测试已在 release job 内复跑，确保 trust nothing）。

**步骤：**
1. checkout
2. 安装 uv（启用缓存）
3. 缓存 `~/.cache/uv`
4. `uv sync --frozen` 安装依赖
5. `uv run pytest tests/` 复跑测试
6. `uv build` 构建 wheel/sdist 到 `dist/`
7. `uv publish --token $PYPI_TOKEN` 上传 PyPI
8. `softprops/action-gh-release@v2` 创建 GitHub Release，自动生成 release notes

**超时：** 3 分钟。

---

## 依赖变化

`pyproject.toml` 新增：

```toml
[project.optional-dependencies]
dev = [
    "ruff>=0.9",
    "pyright>=1.1",
    "pytest>=8.0",
    "pytest-cov>=4.0",
]
```

开发时 `uv sync --dev` 安装所有依赖。CI 用 `--frozen` 确保 lock 文件不被意外修改。

---

## 缓存策略

- `~/.cache/uv`：按 OS + `pyproject.toml` hash 做 key，每次 workflow 尽可能命中
- 缓存 key 格式：`uv-{os}-{hash}`，restore-keys 兼容同一 OS 的相邻 hash

---

## 版本规范

- 语义化版本（semver）：`vMAJOR.MINOR.PATCH`
- tag 由人类或 script 打：`git tag v0.2.0 && git push --tags`
- CI 不负责版本号校验，由 release workflow 的 PyPI publish 隐式验证

---

## PyPI Token 配置

GitHub repo 需要添加 secret：`PYPI_TOKEN`，格式为 `pypi-...`（Test PyPI 用 `PYPI_TEST_TOKEN` 换 `UV_PUBLISH_TOKEN`）。

路径：Settings > Secrets and variables > Actions > New repository secret。

---

## 一人公司原则

- **零手动操作**：push code = CI，push tag = 上线
- **不过度设计**：不用 matrix build（单 Python 版本足矣），不用冗余 step
- **快速反馈**：2 分钟内 CI 出结果，出错直接看到哪一步
