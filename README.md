# Mole 开发产物安全清理 Skill

以 [Mole](https://github.com/tw93/Mole) 为主要盘点与清理工具，补充跨项目的开发产物保留规则。**macOS 为主，同时支持 Windows**。用于 Codex、Xcode 和其他编程项目积累的构建缓存、旧模拟器、独立测试截图、抽帧和录屏。

用户明确要求清理时，直接删除通过用途与安全核验的项目；用途不清、仍在使用、与依赖或验收资料混在一起的内容先保留。只要求检查时，不执行删除。

## 安装 Skill

需要 Git、Python 3.10+；Windows 建议 Python 3.12+，以正确读取文件创建时间。Mole 单独安装，不随本仓库复制其源码或二进制。Windows 使用其[官方 Windows 分支](https://github.com/tw93/Mole/tree/windows)，要求 Windows 10/11 和 PowerShell 5.1+。

macOS：

~~~bash
git clone https://github.com/GoodWay0223/mac-dev-cleanup.git ~/.codex/skills/mac-dev-cleanup
~~~

Windows PowerShell：

~~~powershell
git clone https://github.com/GoodWay0223/mac-dev-cleanup.git "$env:USERPROFILE\.codex\skills\mac-dev-cleanup"
~~~

如果设置了 CODEX_HOME，使用它的 skills/mac-dev-cleanup 路径。已有同名 Skill 时保留本地改动；不要覆盖目录。安装后重新加载 Skill 列表或打开新对话。

在 Codex 中使用：

~~~text
用 $mac-dev-cleanup 检查这台电脑和其他项目的开发缓存，确定无用的直接清掉，不确定的保留。
~~~

Mole 未安装时，这个请求不会自动授权安装。可明确补充“先安装 Mole”。官方安装、版本差异和可用选项见 [Mole 与平台用法](references/mole-platforms.md)。

## 默认边界

| 类别 | 默认规则 |
| --- | --- |
| 构建/索引缓存 | 证明可由现存源码重建、未被 Git 跟踪、目录全部忽略、没有活动使用 |
| iOS 模拟器 | 仅 Mac；可靠最后使用时间超过 72 小时、已关机且没有独有待保留资料 |
| 独立测试影像 | 超过 7 天，核实测试来源及当前用途；以可靠时间中的最新值为准 |
| 源码与 Git | 保留源码、未提交工作、分支、stash、worktree 和可达历史；不因年代久远删除 |
| 依赖与证据 | 保留 node_modules、虚拟环境、Pods、SwiftPM/NuGet 包、结果包、日志、发布和签名产物 |
| 个人和系统资料 | 保留照片、原始素材、数据库、备份、整个临时目录、回收站、WSL/Docker 数据等 |

时间门槛可以由本次指令调整，但年龄和大小本身不能证明无用。Windows 不运行 Xcode 或 simctl，也不默认清理 Windows 系统目录。详细判断依据见 [清理边界](references/cleanup-boundaries.md)。

Mole 的默认 clean/purge 范围可能比这些规则更宽。先 dry-run，再审核具体路径；原生命令无法限定到已审核清单时，保留整组，对已确认的自定义缓存和测试导出逐项补充删除。

## 只读辅助工具

先预览 Mole，保存版本、帮助和扫描限制：

~~~bash
python3 scripts/mole_preview.py clean
python3 scripts/mole_preview.py purge
python3 scripts/mole_preview.py analyze --path /absolute/project/cache
~~~

Windows 用 py -3 替换 python3；analyze 仅包装 Mac JSON 模式。默认私人报告保存在 ~/.codex/attachments，禁止放入 Git 仓库。包装器没有删除入口；Mole 可以写自身的预览清单和配置。退出码 0 也不保证完整扫描。

冻结候选路径 JSON 数组后，审计再复核：

~~~bash
python3 scripts/audit_paths.py snapshot --paths-json /absolute/candidates.json --output /absolute/private-audit.json
python3 scripts/audit_paths.py verify --audit /absolute/private-audit.json
~~~

审计脚本记录树指纹、保护内容、Git 工作区/refs/关联 checkout 和文件打开状态。Windows 用只读排他打开检查文件锁，报告逻辑大小；Mac 用 lsof 和文件分配大小。review_ready 仅表示机械检查通过，**不证明无用，也不授予删除权限**。仍需核实来源、活动任务及本次授权。

## 维护和验证

~~~bash
python3 -B -m unittest discover -s scripts -p 'test_*.py'
~~~

测试只使用隔离临时样本；不清理用户文件。GitHub Actions 在 macOS/Windows 验证脚本边界，并对固定的官方 Mole 版本运行只读帮助检查。CI 不代表所有本机软件、文件锁或实际删除场景已验收。

Mole 验证基线：macOS V1.59.1，Windows V1.32.0-windows。执行时以安装版本及本机帮助为准，不自动升级。维护中发现边界缺口，先复现并增加保留/拒绝测试，再调整规则。不要上传个人清理报告、路径、媒体、凭据或项目 diff。

升级 Skill 前先查看 git status，工作区干净时执行 git pull --ff-only；有本地修改先保留。可通过本仓库 Issues/PR 持续改进。

本仓库原创 Skill、说明和辅助脚本采用 [MIT](LICENSE)。外部依赖 Mole 采用其自身的 GPL-3.0 许可证；本仓库不分发或修改 Mole，许可证互不替代。感谢 [tw93/Mole](https://github.com/tw93/Mole)。
