# 部署指南：在另一台电脑上只安装传感器配色工具

> 本文件供 AI Agent 阅读执行。请严格按顺序操作，**任何一步校验失败就停止并向用户报告**，不要猜测、不要跳过、不要强行写入程序集。
>
> 本指南**只改传感器高亮颜色**，不会注入 Fault 计数器。若用户还要 Fault 计数器，另见 `majdataplay-center-display` 仓库的 INSTALL.md；两份补丁可任意顺序叠加。

## 1. 适用范围（硬性前提）

| 项目 | 要求 |
| --- | --- |
| 游戏 | MajdataPlay **Windows 运行包 2.0.3 `20260917-637bba0`，Mono 后端** |
| 目标文件 | `<GAME_DIR>\MajdataPlay_Data\Managed\Assembly-CSharp.dll` |
| 官方原版指纹 | SHA256 `139817f1e0147f8fe21fdc6c0a24303f3a93c98a7fd049c4eebf54a09c875ad9`，大小 `1,241,600` 字节 |
| 版本标识 | `<GAME_DIR>\MajdataPlay_Data\app.info` |

**版本不匹配必须停止。** IL 锚点（`DummyTouchPanelRenderer.OnPreUpdate()` 中 `brtrue.s` 的跳转目标、紧随其后的 4 个 `ldc.r4` 与 `Color::.ctor`）绑定这一版程序集；其他版本（含 dev 分支 2.1.0）结构不同，强行注入会损坏程序集。

指纹不同**不一定**是版本不对：DLL 可能已被改过颜色，或已装了 Fault 补丁。此时以第 5 节 `--inspect` 的结果为准，能正常输出 JSON 就说明锚点兼容。

## 2. 依赖

- Windows
- Python 3（**必须带 tkinter**，用于 GUI）
- .NET 10 **SDK**（clone 路线需要 `dotnet build`）；若拿到已含 `engine/` 编译产物的离线目录，只需 .NET 10 **运行时**
- git（可选）

## 3. 获取代码

**方式 A — 公开仓库（推荐）**

```bash
git clone https://github.com/zYanzy/majdataplay-sensor-color.git
```

仓库**不含** `engine/`（编译产物被 `.gitignore` 排除），必须执行第 4 步构建。

**方式 B — 离线拷贝**

让用户把整个仓库目录拷过来（含 `engine/patcher.dll` 与 Mono.Cecil 的 DLL），可跳过第 4 步。

下文用 `<TOOL_DIR>` 表示该目录。

## 4. 构建补丁引擎（方式 A 必做）

```bat
dotnet build "<TOOL_DIR>\engine-src\patcher.csproj" -c Release -o "<TOOL_DIR>\engine"
```

依赖 NuGet 包 `Mono.Cecil 0.11.6`。若因无 SDK / 无网络构建失败，改用方式 B 获取已编译的 `engine/`，**不要**自行改写 csproj 的目标框架，也不要编译游戏根目录的 `.sln`。

## 5. 兼容性校验（写入前必做）

1. 找到含 `MajdataPlay.exe` 的目录，记为 `<GAME_DIR>`。**向用户确认，不要猜**。
2. 确认游戏已完全退出；DLL 被占用时不能替换。
3. 先做一份带时间戳的备份，例如 `<TOOL_DIR>\backups\Assembly-CSharp_<日期>.dll`。
4. 执行：

```bat
set "DLL=<GAME_DIR>\MajdataPlay_Data\Managed\Assembly-CSharp.dll"
dotnet "<TOOL_DIR>\engine\patcher.dll" "%DLL%" --inspect
```

期望输出**一行 JSON**，例如官方原版 `{"r":0,"g":0,"b":0,"a":0.3}`，已改色则可能是 `{"r":1,"g":0,"b":0,"a":0.3}`。

**只有成功输出 JSON 才能继续**。抛异常（找不到 `DummyTouchPanelRenderer` / `brtrue` 锚点 / `Color::.ctor`）、返回码非 0 → 版本不兼容，立即停止并报告。

## 6. 生成并写入补丁

颜色为 `R,G,B,A`，各分量 0..1；默认红色 `1,0,0,0.3`。

```bat
mkdir "<TOOL_DIR>\output" 2>nul
dotnet "<TOOL_DIR>\engine\patcher.dll" "%DLL%" "<TOOL_DIR>\output\Assembly-CSharp.patched.dll" --color 1,0,0,0.3
```

预期输出 `OK color=1,0,0,0.3`。引擎**只**改写这 4 个常量，不会注入或移除 Fault 计数器等其他补丁。

二次校验生成物，要求 RGBA 与目标一致：

```bat
dotnet "<TOOL_DIR>\engine\patcher.dll" "<TOOL_DIR>\output\Assembly-CSharp.patched.dll" --inspect
```

然后**只替换这一个文件**：

```bat
copy /Y "<TOOL_DIR>\output\Assembly-CSharp.patched.dll" "%DLL%"
```

（Git Bash 下用 `cp -f`。）最后再对 `%DLL%` 执行一次 `--inspect` 确认。

> 也可以跳过手工命令，直接用 GUI：完成第 7 步配置后双击 `启动配色工具.bat`，选好颜色点「应用到游戏」。GUI 会自动备份、生成、二次校验、替换，并在需要时关闭/重启游戏。

## 7. 写工具配置

把 `config.example.json` 复制为 `config.json` 并编辑：

```json
{
  "auto_start_game": false,
  "game_dir": "<GAME_DIR>"
}
```

`game_dir` 中 Windows 反斜杠在 JSON 里要写成 `\\`。**Agent 环境下建议 `auto_start_game: false`** —— 由命令会话启动的游戏进程常被系统回收，让用户手动双击 `MajdataPlay.exe` 最可靠。

## 8. 让功能在游戏里可见（改 `settings.json`，改前先备份）

只改这一个键，其余内容一律保留：

| 路径 | 值 | 说明 |
| --- | --- | --- |
| `Debug.DisplaySensor` | `true` | 否则看不到传感器高亮；也可在游戏内「调试 → 显示传感器」打开 |

**不需要**改 `Game.BGInfo` / `SecondaryBGInfo` / `EnableJudgeTimingGauge` —— 那些属于另一个独立的 Fault 补丁。

## 9. 验收

1. 手动双击 `MajdataPlay.exe` 启动游戏，进入任意谱面、开启「调试 → 显示传感器」：触发时高亮为目标色，空闲时全透明。
2. 游戏日志中无 `InvalidProgramException` / `BadImageFormatException` / 程序集加载失败。
3. `MaiCharts/`、`Skins/`、`MajScores.db` 未被改动。
4. 若此前已单独装了 Fault 计数器，它应当仍然有效；若从未装过，设置里不应出现 `Fault` 选项 —— 这正好证明两个功能彼此独立。

## 10. 禁止事项

- **只替换 `Assembly-CSharp.dll`**，绝不整目录覆盖；不要动 `MaiCharts/`、`Skins/`、`MajScores.db`、`Logs/` 及 `settings.json` 的其他键。
- 不要用 `dotnet build` / VS / MSBuild 编译游戏根目录的 `.sln` / `.csproj`（那些只给 IDE 提示用）。
- 不要在游戏运行时替换 DLL。
- 不要把任何游戏二进制、谱面、成绩库、个人设置上传或提交到版本库。
- **MajdataHub 官方增量更新会覆盖 `Assembly-CSharp.dll` 导致补丁丢失**；更新后重跑第 5–6 步，或打开 GUI 点一次「应用到游戏」。
- 如果之后还要装 Fault 补丁，不要为了"恢复"而用官方原版 DLL 整体覆盖——那会清掉已装好的配色；Fault 引擎本身是叠加式的。

## 11. 回滚

用第 5 步的备份覆盖回 `%DLL%`，或：

```bat
py -3 "<TOOL_DIR>\restore.py" "<GAME_DIR>" --dll "<你的官方原版 Assembly-CSharp.dll>"
```

也可在 GUI 点「回滚官方原版」（需自备原版 DLL，放到 `<TOOL_DIR>\..\original_backup\Assembly-CSharp.dll`；旧目录 `fault_patch_backup\` 也兼容）。注意：**用官方原版 DLL 整体回滚会同时清掉其他已安装的 IL 补丁**，需要各自重新应用。`restore.py` 只替换 DLL，不动谱面/皮肤/成绩库/设置。

## 12. 日常使用

双击 `启动配色工具.bat`（或 `start.bat`）打开 GUI 换色。颜色改动需重新加载程序集，工具会关闭并重启游戏（可用 `auto_start_game` 控制）。GUI 必须用 bat 启动，直接双击 `.py` 可能落到不带 tkinter 的解释器。
