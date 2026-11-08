# dev-cleanup：开发电脑安全清理 Skill

给 AI 智能体（Claude Code、Codex 等）用的磁盘清理 Skill。以 [Mole](https://github.com/tw93/Mole) 做通用清理，补充开发场景的判定规则、缓存地图和只读辅助脚本。**macOS 为主，同时支持 Windows**。

覆盖：

- 多个 AI 会话留下的 git 工作树和本地分支（游戏项目每个 2–3 GB，最容易把磁盘占满）
- Xcode DerivedData、iOS 模拟器和多版本 Xcode
- Android 构建输出、Gradle、SDK/NDK 旧版本和模拟器
- Godot、Unity、Blender 的导入缓存、着色器缓存、日志和临时文件
- 智能体测试留下的截图、录屏和 Chrome 测试配置目录
- 构建输出、发布暂存目录和包管理器缓存

用户明确要求清理时，直接删除通过用途与安全核验的项目；用途不清、仍在使用、与依赖或验收资料混在一起的内容先保留。只要求检查时，不执行删除。

## 安装 Skill

需要 Git、Python 3.10+；Windows 建议 Python 3.12+，以正确读取文件创建时间。Mole 单独安装，不随本仓库复制其源码或二进制。Windows 使用其[官方 Windows 分支](https://github.com/tw93/Mole/tree/windows)，要求 Windows 10/11 和 PowerShell 5.1+。

macOS：

~~~bash
git clone https://github.com/GoodWay0223/dev-cleanup.git ~/.codex/skills/dev-cleanup
~~~

Windows PowerShell：

~~~powershell
git clone https://github.com/GoodWay0223/dev-cleanup.git "$env:USERPROFILE\.codex\skills\dev-cleanup"
~~~

Claude Code（命令行或桌面端）：

~~~bash
git clone https://github.com/GoodWay0223/dev-cleanup.git ~/.claude/skills/dev-cleanup
~~~

如果设置了 CODEX_HOME，使用它的 skills/dev-cleanup 路径。已有同名 Skill 时保留本地改动；不要覆盖目录。安装后重新加载 Skill 列表或打开新对话。

原名 mac-dev-cleanup。已有安装请保留本地改动，将 Skill 目录改名为 dev-cleanup，并更新 Git remote；不要保留两份重复安装。旧 GitHub 仓库地址可通过重定向访问，新安装使用本页地址。

使用示例：

~~~text
用 dev-cleanup 清理这台电脑，确定能删的先删，不确定的列出来。
用 dev-cleanup 看看哪些智能体工作树可以删，只出报告。
用 dev-cleanup 设置每天晚上 10 点自动清理。
~~~

Codex 中可写 `$dev-cleanup`，Claude Code 中可写 `/dev-cleanup` 或直接用自然语言描述。

Mole 未安装时，这个请求不会自动授权安装。可明确补充“先安装 Mole”。官方安装、版本差异和可用选项见 [Mole 与平台用法](references/mole-platforms.md)。

## 默认边界

| 类别 | 默认规则 |
| --- | --- |
| 智能体工作树/分支 | 没人在用、闲置 24 小时以上、无未提交改动、无手写未跟踪文件、提交已在远端或 PR 已合并 |
| 引擎导入缓存 | Godot `.godot`、Unity `Library` 等，只对闲置工作树/项目清，代码保留 |
| 构建/索引缓存 | 证明可由现存源码重建、未被 Git 跟踪、目录全部忽略、没有活动使用 |
| iOS 模拟器 | 仅 Mac；可靠最后使用时间超过 72 小时、已关机且没有独有待保留资料 |
| 独立测试影像 | 超过 7 天，核实测试来源及当前用途；以可靠时间中的最新值为准 |
| 源码与 Git | 保留源码、未提交工作、未推送分支、stash、标签和可达历史；不碰远端 |
| 依赖与证据 | 保留 node_modules、虚拟环境、Pods、SwiftPM/NuGet 包、结果包、日志、发布和签名产物 |
| 个人和系统资料 | 保留照片、原始素材、数据库、备份、整个临时目录、回收站、WSL/Docker 数据等 |

完整的工具清单见 [缓存地图](references/cache-map.md)，工作树规则见 [智能体工作树](references/agent-worktrees.md)，告急顺序和定时清理见 [定时与紧急清理](references/routine.md)。

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

检查智能体工作树和本地分支（只读，不 fetch、不删除）：

~~~bash
python3 scripts/worktree_report.py /absolute/main-checkout --gh owner/repo --keep release-tools --asset 'game/data/*'
~~~

每个工作树给出 removable / removable_after_backup / keep（附原因），闲置但有改动的工作树会列出可单独清掉的导入缓存。

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
