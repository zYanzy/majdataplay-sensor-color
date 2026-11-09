# MajdataPlay 传感器配色工具

针对 [MajdataPlay](https://github.com/LingFeng-bbben/MajdataPlay) **Windows 运行包 2.0.3 `20260917-637bba0`（Mono 后端）** 的非官方外置工具：直接修改「调试 → 显示传感器」触发态的高亮颜色。

**本仓库只做这一件事。** 它与独立的 [Fault 计数器补丁](https://github.com/zYanzy/majdataplay-center-display) 互不依赖：可以只装本工具、只装 Fault 补丁，或两个都装（顺序随意）。本引擎只改 `DummyTouchPanelRenderer.OnPreUpdate()` 里 `Color(R,G,B,A)` 的 4 个浮点常量，**不注入也不移除**任何其他补丁。

仓库不含游戏本体、官方二进制、谱面、皮肤、成绩库或个人设置。

## 功能

- 官方原版触发态为灰色 `Color(0, 0, 0, 0.3)`，工具可改成任意 RGBA（示例红色 `Color(1, 0, 0, 0.3)`）；空闲态保持全透明。
- **GUI**：预设色板 / RGBA 滑块 / HEX 输入 / 系统取色器 / 传感器面板实时预览 / 一键应用 / 仅生成补丁 DLL / 恢复原版灰 / 回滚官方原版 / 日志。
- **幂等引擎**：定位颜色不依赖 `0.3f` 常量，而用 `brtrue.s` 的跳转目标作语义锚点，因此改过 alpha 后仍能再次改色；输入官方原版或已改色的 DLL 都可以。
- 应用前自动备份当前 DLL 到 `backups/`，生成后二次 `--inspect` 校验才替换。

## 目录

| 路径 | 说明 |
| --- | --- |
| `sensor_color_tool.py` | tkinter GUI 主程序 |
| `engine-src/` | C# 补丁引擎源码（Mono.Cecil 0.11.6，只改颜色） |
| `start.bat` / `启动配色工具.bat` | 启动脚本，自动探测带 tkinter 的 Python |
| `config.example.json` | 配置模板 |
| `restore.py` | 用自备的官方原版 DLL 回滚（只换 DLL） |
| `INSTALL.md` | 在另一台同版本客户端部署的完整指南，供 AI Agent 阅读执行 |
| `LICENSE` | GPLv3 全文，来自官方仓库 |

引擎命令行：

```bat
dotnet engine\patcher.dll <input.dll> --inspect                          :: {"r":..,"g":..,"b":..,"a":..}
dotnet engine\patcher.dll <input.dll> <output.dll> --color R,G,B,A      :: 只改颜色，幂等
```

`--inspect` 会校验颜色 IL 锚点，因此同时充当**版本兼容性检查**；输出不了 JSON 就说明程序集版本不对，必须停止。

## 环境与首次构建

- Windows + Python 3（**必须带 tkinter**，安装时勾选 *tcl/tk and IDLE*）
- .NET 10 **SDK**（clone 路线需要 `dotnet build`；拿到已含 `engine/` 的离线包则只需 .NET 10 **运行时**）

```bat
dotnet build engine-src\patcher.csproj -c Release -o engine
copy config.example.json config.json
```

编辑 `config.json`，把 `game_dir` 指向含 `MajdataPlay.exe` 的目录（JSON 里反斜杠写成 `\\`），然后双击 `启动配色工具.bat`。Git Bash 下把 `copy` 换成 `cp`。

> 必须用 bat 启动：部分便携 Python 不带 tkinter，bat 会逐个探测 `py -3.10 / 3.12 / 3.11 / 3.13 / 3` 找到可用的解释器并以 `pyw` 无控制台启动。

> 「回滚官方原版」按钮需要自备官方原版 `Assembly-CSharp.dll`，放到仓库上一级的 `original_backup\Assembly-CSharp.dll`（也兼容旧目录 `fault_patch_backup\`）。本仓库不分发任何游戏二进制。

## 让高亮显示出来（改 `settings.json`）

只需 `Debug.DisplaySensor` = `true`（或在游戏内「调试 → 显示传感器」打开）。本工具**不需要**改 `Game.*` 相关键。

## 注意事项

- **MajdataHub 官方增量更新会覆盖 `Assembly-CSharp.dll`，补丁会丢失**；更新后打开工具点一次「应用到游戏」即可。
- 工具只替换 `Assembly-CSharp.dll`，绝不覆盖 `MaiCharts/`、`Skins/`、`*.db`、`settings.json`。
- 颜色改动需重新加载程序集，工具会关闭并重启游戏；Agent 环境下建议 `config.json` 里设 `"auto_start_game": false`，由用户手动双击 `MajdataPlay.exe`。
- 若同时装了 Fault 补丁：本工具不会清掉它；但用官方原版 DLL「回滚」会**同时**清掉两个补丁，需要各自重新应用。
- 用 `brtrue.s` 跳转目标定位颜色时，4 个 `ldc.r4` 必须原地改 `Operand`（R 指令是分支目标），不能用 `ILProcessor.Replace`。

## 许可与声明

本项目是对 GPLv3 项目 MajdataPlay 的非官方修改。`LICENSE` 为官方 GPLv3 全文，本仓库原创内容同样按 GPLv3 发布。第三方依赖 [Mono.Cecil](https://github.com/jbevain/cecil) 为 MIT。

本仓库与 MajdataPlay 官方无关联。以 IL 补丁修改游戏程序集可能不符合相关使用条款，请自行评估；使用前请备份，作者不对数据丢失或账号问题负责。
