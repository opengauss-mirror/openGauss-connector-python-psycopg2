# openGauss Python Connector pre-commit 使用指南

本仓库通过 `pre-commit` 在本地提交前检查本次修改，尽量在推送和代码评审前发现问题。

## 检查标准来源

检查规则不是从其他仓库原样复制，而是按以下顺序确定：

1. 仓库已有配置，例如 `tox.ini` 中的 Flake8 规则和 85 字符行宽。
2. 仓库支持的运行环境；业务代码仍兼容 `setup.py` 声明的 Python 3.6+。
3. openGauss 其他仓库共用的文件卫生、安全和安装方式。
4. 存量代码基线。可能被存量问题影响的检查只报告相对 `HEAD` 新增或修改的行。

因此，本仓库没有直接启用 oGMemory 使用的 Ruff、Mypy 和 Black/Darker，也没有在缺少
`.clang-format` 标准的情况下强制格式化 C/C++ 代码。

## 已启用的检查

| 检查 | 范围 | 行为 |
| --- | --- | --- |
| 行尾空格 | 本次修改的文本行 | 自动清理；Markdown 硬换行保留两个空格 |
| 文件末尾换行 | 本次涉及的文件 | 自动修复 |
| Python 语法 | 本次涉及的 Python 文件 | 报告错误 |
| Flake8 | 本次修改的 Python 行 | 使用 `tox.ini` 中的现有规则 |
| Codespell | 本次修改的源码和文档行 | 报告疑似拼写错误 |
| Bandit | 本次修改的生产 Python 行 | 报告中高风险且高置信度问题 |
| YAML/JSON/TOML | 本次涉及的配置文件 | 校验语法 |
| 合并标记、大小写冲突、私钥、大文件 | 本次提交 | 报告错误 |

测试和示例目录不执行 Bandit；`tests/dbapi20.py` 继续沿用 `tox.ini` 中的 Flake8 豁免。
`scripts/build/appveyor.py` 中包含仓库已有的测试私钥夹具，因此只对该文件豁免私钥检测。

## 首次安装

每个本地克隆执行一次：

```bash
cd <openGauss-connector-python-psycopg2 仓库根目录>
bash setup-pre-commit.sh
```

如需临时使用其他 PyPI 镜像：

```bash
PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple bash setup-pre-commit.sh
```

脚本会把工具安装到 `.pre-commit-venv/`，不会修改全局 pip 配置，也不要求手动激活虚拟
环境。工具环境需要 Python 3.10+，这不会改变驱动业务代码对 Python 3.6+ 的兼容要求。

## 日常使用

正常提交即可：

```bash
git add <files>
git commit -m "your message"
```

如果钩子自动修改了文件，本次提交会停止。检查修改后重新暂存并提交：

```bash
git diff
git add <fixed files>
git commit -m "your message"
```

手动检查仍在工作区或暂存区中的修改：

```bash
.pre-commit-venv/bin/pre-commit run --files lib/example.py
```

运行所有钩子：

```bash
.pre-commit-venv/bin/pre-commit run --all-files
```

其中 Flake8、Codespell、Bandit 和行尾空格检查仍只处理相对 `HEAD` 发生变化的行，避免
存量问题阻塞提交。其他通用钩子会检查全部指定文件，因此执行 `--all-files` 前建议保持
工作区干净并先查看 `git status`。若需要查看全仓 Flake8 基线，可以单独执行：

```bash
.pre-commit-venv/bin/flake8 .
```

## 必要时跳过

优先只跳过确定需要放行的检查：

```bash
SKIP=codespell-changed-lines git commit -m "your message"
```

紧急情况下可跳过全部检查：

```bash
git commit --no-verify -m "your message"
```

跳过检查应作为例外，并在后续补充正常验证。

## 常见问题

### 提示 `.pre-commit-venv/bin/python` 不存在

在仓库根目录重新执行：

```bash
bash setup-pre-commit.sh
```

### 工具安装失败

确认可以访问 GitCode 和所选 PyPI 镜像。必要时删除不完整的 `.pre-commit-venv/` 后重试。

### 如何卸载

```bash
.pre-commit-venv/bin/pre-commit uninstall
rm -rf .pre-commit-venv/
```
