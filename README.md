# SenseVoice 全局听写（Windows）

在任何软件里**单按右 Alt** 开始说话，**再按一下**结束，文字自动输入到光标处。识别用本地 SenseVoice 模型（sherpa-onnx，只用 CPU），不联网、不要账号。

- 安装：`python setup.py`（需要 Python 3.9+）
- 打开 / 关闭：双击 `start_sensevoice.cmd` / `stop_sensevoice.cmd`
- 设置：`config.py`

## 文档（`getting-started/`）
| 文档 | 内容 |
|---|---|
| [迁移到新电脑.md](getting-started/迁移到新电脑.md) | 三步安装 |
| [项目说明.md](getting-started/项目说明.md) | 用法、流程、代码讲解、资源占用、模型原理、环境说明 |
| [开发日志.md](getting-started/开发日志.md) | 每一轮的要求、改动、问题和测试 |
| [模型调研.md](getting-started/模型调研.md) | 可替换模型的公开 benchmark 和建议 |
| [词库与纠错方案.md](getting-started/词库与纠错方案.md) | 专有名词纠错 / 自动学习方案（未实现） |

## 分支
- `sensevoice`：当前版本（本地 SenseVoice）
- `master`：早期 Codex 版（依赖 Codex 自带听写，已停用）
