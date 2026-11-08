---
name: dev-cleanup
description: 安全清理开发电脑的磁盘空间（macOS 为主，兼容 Windows）：AI 智能体（Claude Code、Codex）留下的旧 git 工作树和分支、Xcode/iOS 模拟器、Android SDK/Gradle/模拟器、Godot/Unity/Blender 缓存、测试截图录屏、构建输出和包管理器缓存，以 Mole 为通用清理工具。用于磁盘快满、清理垃圾、盘点占用或设置定时清理；保留源码、未提交工作、依赖、历史和个人资料。
---

# 开发电脑安全清理

适用于任何智能体 harness（Claude Code、Codex 等）。以 [Mole](https://github.com/tw93/Mole) 做通用清理，本 Skill 补充开发场景的判定规则、缓存地图和只读辅助脚本。

## 授权与范围

- 用户说“清理 / 删除 / 照常清理”：直接完成能确认安全的项，不逐项再问；不确定的列出来。用户说“检查 / 看占用 / 建议”：只盘点。
- 用户说“确定能删的先删”：按本文件和参考文档的条件执行，条件不满足的一律保留并报告。
- 用户的本次指令可以调整门槛（如截图 2 天、工作树闲置 24 小时）和范围（如“只删本机，不碰 GitHub”）。
- 年龄、大小、目录名、被 git 忽略，都不能单独证明无用。

## 不跨越的边界

- 不碰 GitHub 等远端：不删远端分支、不关 PR、不 push。
- 保留源码、配置、密钥、数据库、个人文件、原始或付费生成素材、设计参考、发布包和备份。
- 保留未提交的改动、未推送的提交、stash、标签、Codex/Claude 的会话历史、记忆、技能、定时任务。
- 默认保留 `node_modules`、虚拟环境、Pods、SwiftPM 包、SDK、导出模板；只清理它们的工具自带缓存。
- 保留 `.xcresult`、`.xcarchive`、dSYM、签名包、Xcode `Logs`、DeviceSupport（除非用户点名）。
- 不用 sudo、不清空废纸篓、不为清理而杀进程或关闭模拟器、不改系统设置。需要 sudo 的删除（如 /Applications 下的旧 Xcode）生成命令让用户自己跑。

## 执行流程

1. **量空间**：macOS `df -h /System/Volumes/Data`（不是 `df /`），Windows `shutil.disk_usage`。低于 5 GB 先按 [定时与紧急清理](references/routine.md) 的告急顺序腾空间。
2. **找大户**：在用户的项目根、主目录和 `~/Library` 下用 `du -sh <dir>/* | sort -rh | head` 逐层下钻，不扫整个磁盘。对照 [缓存地图](references/cache-map.md) 认出每个大户属于哪个工具、能清什么、代价多大。地图上没有的路径先查清来源。
3. **按类别判定**：
   - 智能体工作树和本地分支：运行 `scripts/worktree_report.py`，规则见 [智能体工作树](references/agent-worktrees.md)。
   - Xcode、模拟器、截图录屏、包缓存、Git：见 [清理边界](references/cleanup-boundaries.md)。
   - Android、Godot、Unity、Blender、浏览器测试配置、harness 自身：见 [缓存地图](references/cache-map.md)。
   - 每项检查：是否有进程在用（`lsof`/`pgrep`）、最近是否有人改、能否重建、被 git 跟踪与否。
4. **先清代价低的**：免重建 → 用到再建 → 重下载。工具自带的清理命令（`npm cache clean`、`pnpm store prune`、`brew cleanup`、`simctl delete unavailable`、`gradlew --stop` 后清输出）优先于直接删目录。
5. **Mole**：先读 [Mole 与平台用法](references/mole-platforms.md)。用户级常规清理用 `timeout 900 mo clean < /dev/null`（非交互，跳过需要 sudo 的系统项）；要先看范围时用 `mo clean --dry-run` 或 `scripts/mole_preview.py`。`mo purge` 会碰依赖目录，默认不执行。
6. **需要留痕时冻结清单再删**：对一批自定义缓存或媒体，可先用 `scripts/audit_paths.py snapshot` 冻结，删除前 `verify`，变化的跳过：

   ```bash
   python3 <skill-dir>/scripts/audit_paths.py snapshot --paths-json <candidates.json> --output <audit.json>
   python3 <skill-dir>/scripts/audit_paths.py verify --audit <audit.json>
   ```

   报告放在源码仓库和候选目录之外。删除时逐个路径精确删除，变量加引号，不用未审核的通配符或 `git clean`。
7. **复核与汇报**：再量一次空间。简短说明删了哪些类别、多少项、依据（PR 已合并 / 已推送 / 已在 CDN）、实际增加的可用空间；列出保留的大项和原因，让用户决定。APFS 释放有延迟，删除量与实际变化分开写。

## 定时清理

用户要求定时自动清理时，按 [定时与紧急清理](references/routine.md) 写一个自包含的定时任务提示词（本机路径、保留名单、门槛、不碰清单、汇报格式）。没被要求就不要创建。

## 维护这份 Skill

每次清到地图上没有的新大户，或踩到新坑，把路径、核验方法和教训补进 [缓存地图](references/cache-map.md) 或对应参考文档。不要写入用户的私人路径、项目名或凭据。
