# 分类依据与保留边界

只阅读本次涉及的类别。下面列出可核实的生成物，不能据此批量删除所有同名目录。

## Xcode、Swift 与项目构建缓存

**常见候选**：已核实 DerivedData 里的 `Build`、`ModuleCache.noindex`、`SDKStatCaches.noindex`、`CompilationCache.noindex`、`Index.noindex`；项目自定义 DerivedData 的对应子目录；SDK 预编译模块和 Clang 模块缓存；Next/Vite/Turbo 等已核实的构建缓存；Python `__pycache__` 中可从仍存在的源码再生成的字节码。

核实方法：

- Xcode 标准位置通常为 `~/Library/Developer/Xcode/DerivedData`。自定义位置必须由 `info.plist`、实际构建命令或工具配置证明；不要仅凭 `dd`、`build`、`.cache` 等名称判断。
- 检查相关 `xcodebuild`、Swift/Clang 编译、索引、测试、开发服务器及 worker 是否在使用。旧文件仍有打开句柄就保留。即使没有打开文件，只要相关任务正在运行，也先跳过该目录。
- 标准 DerivedData 只清理经过审核的构建/索引子目录，保留根目录元数据、日志、结果包和包源码。`XCBuildData` 及 `.xcbuilddata` 中的构建请求、描述和其他记录即使没有数据库文件也保留。整删根目录会混入证据或依赖。
- `.build`、`.next`、自定义输出目录可能混合构建、依赖和测试结果：阅读结构与当前工具配置，选择安全子树。项目缓存的整个待删子树须未被 Git 跟踪、全部被忽略且可由现存源码和配置重建。
- Python 孤立 `.pyc` 可能是唯一可运行副本；没有对应 `.py` 时保留。不清空虚拟环境。

默认排除 DeviceSupport、Archives、Logs、签名/发布产物、dSYM、模拟器 runtimes、包源码和 `node_modules`。浏览器、邮件、聊天、照片、Docker 卷及 Time Machine 不属于开发垃圾；只列占用，不借本 Skill 扩大清理范围。

## Windows 项目缓存

沿用同样的来源、活动任务、Git 和整棵子树核验，不能将 Mac 路径替换为盘符后直接执行。

- 对 Next/Vite/Turbo/Rust/Python 的构建缓存，先读取项目配置确认实际输出。`build`、`dist`、`target`、`bin`、`obj` 的名称本身不构成证据。
- MSBuild/.NET 的 `obj` 子树可能有可再生成的中间文件；仅清理没有配置、唯一编译产物或验收证据的明确子树。默认保留 `.exe`、`.dll`、`.pdb`、`publish`、签名和安装包；若混在父目录里，保留父目录。
- 保留 NuGet 已安装包、SDK、Visual Studio 状态、Gradle 依赖缓存和 Android SDK/虚拟设备。浏览器运行时、模型缓存和离线唯一包也不是普通编译残留。
- 不清空 `%TEMP%`、整个 `%LOCALAPPDATA%`/`%APPDATA%`、Windows 更新缓存、回收站或系统目录。Mole 列出的这些项目不自动获得清理授权。
- 跳过 junction、symlink、其他 reparse point、UNC 网络路径和无法判断文件锁的项。审计锁检查只反映当下；关联编译、开发服务器或测试仍运行时，即使没有锁也要保留。
- 审计脚本在 Windows 返回文件逻辑大小并注明 `allocation_measured=false`，不要称为释放量。以清理前后 `shutil.disk_usage` 记录实际磁盘变化。

## iOS 模拟器

通过本机 `xcrun simctl list devices --json` 和设备 `device.plist` 读取 UUID、状态、运行时、数据路径、`lastUsedAt`。先以本机帮助/实际输出核实字段；字段缺失时保留。

可删必须同时满足：

1. 当前授权覆盖停用模拟器，可靠的 `lastUsedAt` 严格早于当前时刻减 72 小时；这个用户当前指令可改变门槛。
2. 设备当前 `Shutdown`，没有测试进程、Device Hub/Codex 活动任务或持有它的打开句柄。
3. 不是用户指定保留的长期测试设备，没有仍需的独有应用数据、账号状态、付费素材或未完成问题复现资料。
4. 删除前重新读取状态和时间；有变化或无法核实就跳过。

不要用创建时间、目录 mtime、模拟器显示名称或 iOS 版本代替最后使用时间。不要为满足规则先关机。`xcrun simctl delete unavailable` 只删除运行时已不存在、无法启动的设备，可以作为常规项。`delete all` 只在用户明确说模拟器都不要了时使用；删完后项目里记录的 UDID（如 `udid.txt`、脚本、记忆文件）会失效，要一并更新。

通过 `xcrun simctl delete <exact-UUID>` 删除，在新的设备清单中确认 UUID 不存在，并核实实际数据目录已消失。保留运行时；每台设备占用独立数据，运行时可以共享，不能把运行时大小重复计入释放量。APFS 回收可能延迟。

## 独立测试截图、抽帧与录屏

默认超过 7 × 24 小时；用户可调短（多会话并行出图的机器常用 2 天）。最近仍在写入的截图目录说明有会话在用，整个跳过。取文件 mtime、birthtime 和可靠的路径/导出时间中的**最新值**；新复制的旧录像仍保留。Windows 使用支持 `st_birthtime` 的 Python 3.12+ 或 PowerShell `CreationTimeUtc` 读取创建时间；不能把不同平台含义不同的 `ctime` 直接当统一创建时间。无法得到可靠日期时保留。

至少需要一种可信来源：

- XCTest 导出 `manifest.json` 将具体文件映射到明确的测试方法和截图/录屏附件。
- 测试命令、生成脚本或验收文档明确指出该路径是模拟器 UI 截图、测试录屏或从已知测试录像抽出的帧。
- 可追溯到已确认测试导出的逐字节相同副本；先核对哈希，而不是只看相似名称。

目录名 `screenshots`、`frames`、`attachments` 或 `.artifacts` 只用来发现候选。UI 截图也可能是正式设计资料、未完成 PR 的唯一证据；检查当前任务、相关问题和保留标记。内容用途仍不清楚时列为待确认，先保留。

只删未被 Git 跟踪且未打开的独立媒体文件，保留导出 manifest、测试报告、JSON/布局量测数据和 `.xcresult`。不要递归删除结果包的媒体。剪辑、原始录屏和抽帧都要分别通过审核；测试授权不覆盖生成模型输出、照片原图、设计参考或发布展示素材。

扫描用户确认的项目和已知测试输出位置。扩展到 Movies、Desktop、Downloads 或其他工具项目时，沿用同样的来源与年龄核验；不能整删这些目录里的旧视频/图片。

## 包管理器缓存与 Git

- npm/pnpm/pip/Homebrew/SwiftPM 只处理已确认可再下载的缓存，优先本机工具的保守 prune/清理命令。先核实当前版本帮助和配置；不使用 force，不清掉依赖、离线唯一副本或插件。工具可能修改的路径也应预先明确，活动安装期间跳过。
- Git “旧记录”不等于垃圾。允许常规维护：`git gc --prune=2.weeks.ago`，保留默认 reflog/worktree 保留期；若当前配置缩短保留期，跳过或明确使用正常的保守设置。
- 以 `git rev-parse --path-format=absolute --git-common-dir` 对共享对象库去重。清理前后保存关联 checkout 的 HEAD、已跟踪状态、工作/暂存差异摘要及 `git show-ref`；有 Git 写操作或锁文件时跳过。
- 禁止重写历史、强制 prune、到期全部 reflog、删除 stash/tags、删除或改动远端分支。
- 工作树和本地分支只在用户授权清理时处理，且必须逐个通过 [智能体工作树](agent-worktrees.md) 的判定（`scripts/worktree_report.py`）：没人在用、闲置、无未提交改动、无手写未跟踪文件、提交已在远端或 PR 已合并。旧副本可能含未推送工作，判定不过就保留。Codex 托管的 worktree 用 Codex 的归档功能，不手动移除。

## 保存记录

报告放在源码以外的持久附件目录，例如 macOS `~/.codex/attachments/dev-cleanup-<date>-<unique-id>`，Windows `%USERPROFILE%\.codex\attachments\dev-cleanup-<date>-<unique-id>`。不要把新报告放进待清理目录或公开仓库。

记录授权范围、精确截止时刻、候选来源、实际路径、原占用、保留理由、删除/失败/跳过项、核验结果及前后 `df`。隐藏凭据；不把环境变量、媒体内容或完整未提交 diff 复制进报告。

扫描没有报错不代表读到全部资料。权限错误、工具缺失、未知文件时间、Git 状态无法读取、lsof 无法完成时，相关项保持原样并说明限制。
