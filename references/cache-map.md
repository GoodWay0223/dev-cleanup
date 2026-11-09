# 开发工具缓存地图

按工具列出常见占用、判断方法和清理方式。这张图会持续更新：清到新的大户，就把路径、核验方法和教训补进来；地图上没有的路径，弄清来源之前不动。

标记：✅ 核实条件后可清 · ⚠️ 只清指定子项或需用户点名 · 🚫 不碰
代价：**免重建**（删了不需要再生成）· **用到再建**（下次打开/构建自动生成，第一次慢）· **重下载**（要联网，可能几十分钟）。同样能腾出空间时，先清代价低的。

所有路径先用 `du -sh` / `du -sk` 量，再看最近修改时间和占用进程（`lsof +D <dir>`、`pgrep -fl <tool>`）。可用空间看数据卷：macOS 用 `df -h /System/Volumes/Data`，不要看 `df /`（那是只读系统卷）。

---

## AI 智能体与 harness（Claude Code、Codex 等）

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| 智能体建的 git worktree（`.claude/worktrees/`、自建 `wt/` 目录等） | ⚠️ | 最大的来源，每个带资源的游戏工作树 2–3 GB。按 [智能体工作树](agent-worktrees.md) 逐个判定，用 `scripts/worktree_report.py` 出报告。Codex 托管的 `~/.codex/worktrees` 用 Codex 自己的归档功能，不手动删 |
| 已合并/已推送的本地分支、`prNNN` 之类的 PR 本地副本 | ⚠️ | 同上。`prNNN` 先用 `gh pr view NNN --json state,headRefOid` 对照：已合并且提交相同才删；提交不同（旧版本）就留下并报告 |
| 智能体的临时测试目录：`test-logs-*`、`shots/`、`refs*/`、`review/` 里的截图、录屏、抽帧 | ✅ 免重建 | 只删超过门槛（默认 7 天，用户可调到 2 天）的 png/jpg/webp/gif/mp4/mov/webm；保留同目录的 .md/.sh/.py/.json/.log。最近仍在写入的目录说明有会话在用，整个跳过 |
| 智能体开的 Chrome/Chromium 测试配置目录（`--user-data-dir` 指向的 `profile*/`、`prof_*/`、`ChromeDebug`） | ✅ 用到再建 | 测网页游戏/网页应用时，每个配置目录的 `Default/Service Worker/CacheStorage` 都会存一份完整的资源包（实测每个 530 MB，5 个 2.7 GB）。确认没有 Chrome 进程用它（`lsof +D <profile>` 为空）后整个配置目录可删；测试日志和截图保留 |
| Playwright 浏览器 `~/Library/Caches/ms-playwright`（Win: `%LOCALAPPDATA%\ms-playwright`） | ⚠️ 重下载 | 只删项目锁定版本以外的旧浏览器版本 |
| Claude 桌面端内置 CLI `~/Library/Application Support/Claude/claude-code/<版本>` | ⚠️ | 每个版本约 300 MB。只在 Claude 退出时删除非最新版本 |
| Claude Code `~/.claude/projects/*.jsonl`、`memory/`、`skills/`、`scheduled-tasks/`、`file-history/` | 🚫 | 会话历史、记忆、技能、定时任务、回退记录 |
| Claude Code `~/.claude/shell-snapshots`、`~/.claude/debug`、`~/.claude/cache` | ✅ | 很小；只清 7 天前的 |
| Codex `~/.codex/sessions`、`attachments`、`memories`、`skills` | 🚫 | 历史与附件 |
| Electron 应用（Claude、Cursor、VS Code）`Cache`、`Code Cache`、`GPUCache`、`GraphiteDawnCache` | ✅ 用到再建 | 应用退出后才清；`IndexedDB`、`Local Storage`、`Cookies`、`Partitions` 🚫 |

## Git

- `.git/objects/pack/tmp_pack_*`、`.tmp-*`：fetch/clone 中途失败留下的残包，git 不会引用。磁盘满时多个会话同时 fetch 很容易留下好几 GB（实测 9 个共 2.5 GB）。✅ 免重建：确认没有 git 进程（`pgrep -fl 'git (fetch|clone|index-pack|repack|gc)'`）、没有进程打开它们、文件超过 1 小时未改动后删除；删后 `git count-objects -v` 复核。
- `git worktree prune`：只清理目录已不存在的工作树记录，安全。
- `git gc --prune=2.weeks.ago`：常规维护，允许；不缩短 reflog，不 `--prune=now`。
- 从不删远端分支、不关 PR、不 push。用户说“只删本机”时尤其如此。

## Xcode 与 iOS 模拟器（仅 macOS）

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| `~/Library/Developer/Xcode/DerivedData/<项目-hash>` | ✅ 用到再建 | 只删超过门槛未改动、没有 xcodebuild 在用的项目目录 |
| 模拟器设备 `~/Library/Developer/CoreSimulator/Devices` | ⚠️ | `xcrun simctl delete unavailable` 随时可做；其余按 UUID 删（门槛和条件见 [清理边界](cleanup-boundaries.md)）。用户明确说“模拟器都不要了”时，可 `xcrun simctl shutdown all && xcrun simctl delete all`。删完检查项目里是否记录了 UDID（如 `udid.txt`、脚本、记忆文件），一并标为过期 |
| 模拟器运行时 `xcrun simctl runtime list` | ⚠️ 重下载 | 只删没有设备使用、用户确认不再测试的 beta/旧版本：`xcrun simctl runtime delete <id>` |
| 多个 Xcode（`/Applications/Xcode*.app`） | ⚠️ 重下载 | 先 `xcode-select -p` 和 `xcodebuild -version` 看在用哪个，`mdls -name kMDItemLastUsedDate` 看最后使用时间。删 /Applications 下的应用要 sudo：生成命令让用户自己跑，先 `sudo xcode-select -s` 切到保留的那个 |
| `iOS DeviceSupport` 旧版本 | ⚠️ | 只删用户已不再连接的旧系统版本 |
| `~/Library/Developer/CoreDevice/DeviceFS` | 🚫 | 真机的挂载投影，不是缓存 |
| Archives、`.xcresult`、dSYM、签名包 | 🚫 | 发布与证据 |

## Android

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| 项目 `build/`、`app/build/`、项目内 `.gradle/` | ✅ 用到再建 | 先 `./gradlew --stop`，确认没有 Gradle 进程。最新文件超过门槛才删 |
| Godot 安卓项目的 `android/build/` | ⚠️ | 这是 Godot 安装的 **Gradle 构建模板**，不只是输出。只有它被 git 忽略、且项目导出脚本在缺失时会自动 `--install-android-build-template` 才删；否则只删其中的 `build/`、`.gradle/` 输出子目录 |
| `~/.gradle/caches/build-cache-*`、`~/.gradle/daemon/*/日志` | ✅ 用到再建 | 没有 Gradle 进程时清 |
| `~/.gradle/caches/<旧Gradle版本>`、`~/.gradle/wrapper/dists/<旧版本>` | ⚠️ 重下载 | 保留各项目 `gradle-wrapper.properties` 用到的版本 |
| Android SDK `ndk/<版本>`、`build-tools/<版本>`、`system-images/` | ⚠️ 重下载 | 保留项目 `ndkVersion`、`compileSdk`、导出设置引用的版本；同时装了多个 NDK（每个约 3 GB）时，其余版本可列给用户 |
| 模拟器 AVD `~/.android/avd/*.avd` | ⚠️ | 同 iOS 模拟器：长期不用且用户同意时 `avdmanager delete avd -n <名字>` |
| `~/.android/cache` | ✅ | 可清 |

## Godot

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| 项目 `.godot/`（导入缓存，常见 700–900 MB/个） | ✅ 用到再建 | 主力项目不动；**闲置超过 3 天的工作树**可以只删它的 `.godot`，代码和未提交改动保留。重新打开会重新导入，很慢 |
| `*.import`、`*.uid` 的未提交变化 | — | 是编辑器自动生成的，判定工作树是否“干净”时忽略 |
| 着色器缓存 `$(getconf DARWIN_USER_CACHE_DIR)org.godotengine.godot`（实测 1.1 GB）、`.../clang` | ✅ 用到再建 | 只在 `pgrep -i godot` 为空时删 |
| `~/Library/Application Support/Godot/app_userdata/<项目>/logs`、各游戏 user 目录的 `logs/` | ✅ | 只删超过 2 天的日志 |
| 游戏 user 目录里的 `shader_cache/`、下载的资源包 | ⚠️ | 游戏不运行时可删，下次运行重建/重下载 |
| `export_templates/`、`editor_settings-*.tres`、`projects.cfg` | 🚫 | 导出模板与编辑器设置 |
| 导出产物（`.pck`、网页导出目录、`simbuild` 等） | ⚠️ | 区分“发布用的”与“临时测试的”。打包后上传到 CDN 的包，用 `curl -sI` 对比 CDN 上同名文件的 `Content-Length`（或 sha256）一致后才删本地副本；文件名带内容哈希时最可靠 |

## Unity

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| 项目 `Library/`、`Temp/`、`obj/`、`Logs/` | ✅ 用到再建 | Unity 编辑器关闭、项目闲置超过门槛时可删；`Library/` 重建要很久（大项目数十分钟），优先只对闲置项目做 |
| `Builds/` 等构建输出 | ⚠️ | 区分发布包和临时构建 |
| `~/Library/Unity/cache`（Win: `%LOCALAPPDATA%\Unity\cache`）包缓存 | ✅ 重下载 | 可清 |
| Unity Hub 下载缓存 `~/Library/Application Support/UnityHub` 下的安装包 | ✅ | 已安装的编辑器版本不动 |
| 编辑器版本 `/Applications/Unity/Hub/Editor/<版本>` | ⚠️ 重下载 | 保留各项目 `ProjectSettings/ProjectVersion.txt` 用到的版本，其余让用户在 Hub 里卸载 |
| `Assets/`、`Packages/`、`ProjectSettings/`、`UserSettings/` | 🚫 | 源码与配置 |

## Blender

| 路径 | 标记 | 说明 |
| --- | --- | --- |
| `*.blend1`、`*.blend2` 自动备份 | ⚠️ | 是上一版存档；只在同名 `.blend` 存在、备份超过门槛且用户同意时清 |
| 渲染输出目录（默认 `/tmp/` 或项目 `render/`） | ⚠️ | 区分成品与测试帧 |
| `~/Library/Application Support/Blender/<旧版本>/` | ⚠️ | 新版本已迁移设置后，旧版本目录可列给用户 |
| 物理/流体烘焙缓存（`blendcache_*`、`cache_fluid_*`） | ✅ 用到再建 | 可重新烘焙，但可能很慢 |
| 临时文件 `$TMPDIR/*.blend@`、`quit.blend`、崩溃恢复文件 | ⚠️ | 可能是唯一的恢复副本，先问 |

## 包管理器与构建工具

- npm `npm cache clean --force`；pnpm `pnpm store prune`；yarn `yarn cache clean`；pip `pip cache purge`；uv `uv cache clean`；Homebrew `brew cleanup --prune=all`；Go `go clean -cache`；CocoaPods `pod cache clean --all`。都是 ✅ 重下载，且工具会自己判断，优先用它们，不直接删目录。
- `node_modules`、`.venv`、`Pods`、SwiftPM `SourcePackages`：🚫（默认）。只有用户点名某个闲置项目时才清。
- 各项目的 `build/`、`dist/`、`.next/`、`target/`：✅ 用到再建，前提是被 git 忽略、最新文件超过门槛、没有构建进程在跑。
- 发布暂存目录（如 `web/.deploy-staging`、`.vercel/output`）：git 忽略、超过门槛、发布流程会重新生成时 ✅。

## Mole（系统和应用的通用垃圾）

- 非交互运行：`mo clean < /dev/null`。stdin 不是终端时 Mole 跳过需要 sudo 的系统缓存，只清用户级，不会卡在密码提示。
- 加超时：`timeout 600 mo clean < /dev/null`。它可能卡在扫描 `~/Movies` 等受隐私保护的目录（macOS 权限弹窗）或“应用缓存”一步，超时后 `pkill -f "mole/.*/clean.sh"`，已完成的部分有效。
- 日志在 `~/Library/Logs/mole/operations.log`，汇报时可引用实际删除项。

## 🚫 一律不碰

钥匙串、各应用的登录态/Cookies/Local Storage/IndexedDB、消息数据库、照片库、`~/Documents`、`~/Desktop`、`~/Downloads` 中的个人文件、废纸篓（不替用户清空）、`/System`、需要 sudo 的系统目录、Docker 卷、Time Machine 快照。
