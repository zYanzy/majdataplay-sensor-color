# -*- coding: utf-8 -*-
"""
MajdataPlay 传感器高亮配色工具

直接修改运行包 Assembly-CSharp.dll 中 DummyTouchPanelRenderer.OnPreUpdate()
激活态的 Color(R,G,B,A)。补丁引擎为 Mono.Cecil，支持幂等重打：
输入可以是官方原版 DLL，也可以是已改过颜色的 DLL。

引擎只改写这 4 个浮点常量，不注入也不移除任何其他补丁
（例如独立的 Fault 计数器补丁），两者可任意顺序叠加。

依赖：Python 3 (tkinter，标准库) + dotnet 运行时 + engine/patcher.dll
"""

import json
import math
import os
import shutil
import subprocess
import time
import traceback
import tkinter as tk
from datetime import datetime
from tkinter import colorchooser, filedialog, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------- paths ----
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TOOL_DIR)
DEFAULT_GAME_DIR = os.path.join(BASE_DIR, "MajdataPlay_Build-LATEST")
BACKUP_DIR = os.path.join(BASE_DIR, "original_backup")
LEGACY_BACKUP_DIR = os.path.join(BASE_DIR, "fault_patch_backup")
if not os.path.isdir(BACKUP_DIR) and os.path.isdir(LEGACY_BACKUP_DIR):
    BACKUP_DIR = LEGACY_BACKUP_DIR  # keep older installs working
OFFICIAL_DLL = os.path.join(BACKUP_DIR, "Assembly-CSharp.dll")
ENGINE_DIR = os.path.join(TOOL_DIR, "engine")
ENGINE_DLL = os.path.join(ENGINE_DIR, "patcher.dll")
LOCAL_BACKUPS = os.path.join(TOOL_DIR, "backups")
OUTPUT_DIR = os.path.join(TOOL_DIR, "output")
CONFIG_PATH = os.path.join(TOOL_DIR, "config.json")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

# ----------------------------------------------------------------- theme ----
BG = "#f1f3f7"
CARD = "#ffffff"
TEXT = "#1e2430"
SUB = "#6b7280"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
BORDER = "#dfe3ea"
PREVIEW_BG = (28, 31, 40)
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 15, "bold")

PRESETS = [
    ("原版灰", (0.00, 0.00, 0.00, 0.30)),
    ("纯红",   (1.00, 0.00, 0.00, 0.30)),
    ("亮红",   (1.00, 0.15, 0.15, 0.55)),
    ("橙",     (1.00, 0.50, 0.00, 0.50)),
    ("金黄",   (1.00, 0.85, 0.00, 0.50)),
    ("荧光绿", (0.20, 1.00, 0.20, 0.50)),
    ("青",     (0.00, 0.90, 0.90, 0.50)),
    ("天蓝",   (0.20, 0.60, 1.00, 0.50)),
    ("紫",     (0.65, 0.30, 1.00, 0.50)),
    ("粉",     (1.00, 0.40, 0.75, 0.50)),
    ("白",     (1.00, 1.00, 1.00, 0.50)),
    ("柔红",   (1.00, 0.10, 0.10, 0.65)),
]

TRIGGER_SETS = [
    {0, 2, 5},
    {1, 4, 7},
    {0, 3, 6},
    {2, 4, 5, 7},
]


def clamp01(v):
    return max(0.0, min(1.0, float(v)))


def to_hex(rgb):
    return "#%02X%02X%02X" % tuple(int(round(clamp01(c) * 255)) for c in rgb)


def from_hex(text):
    s = text.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError("需要 #RRGGBB 或 RRGGBB 格式的 6 位十六进制")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def blend(rgba, bg=PREVIEW_BG):
    """Simulate alpha compositing: tkinter canvas has no per-shape opacity."""
    r, g, b, a = rgba
    fg = (r * 255, g * 255, b * 255)
    return "#%02X%02X%02X" % tuple(
        int(round(fg[i] * a + bg[i] * (1 - a))) for i in range(3)
    )


def fmt(rgba):
    return "R %.2f  G %.2f  B %.2f  A %.2f" % rgba


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("MajdataPlay 传感器配色工具")
        self.root.geometry("980x730")
        self.root.minsize(900, 660)
        self.root.configure(bg=BG)

        self.rgba = [1.0, 0.0, 0.0, 0.30]
        self.updating = False
        self.busy = False
        self.current_state = None
        self.trigger_index = 0
        self.show_trigger = tk.BooleanVar(value=True)
        self.auto_start = tk.BooleanVar(value=True)

        self.cfg = self.load_config()
        self.auto_start.set(bool(self.cfg.get("auto_start_game", True)))
        self.dotnet = self.find_dotnet()

        self.init_style()
        self.build_ui()
        self.refresh_state()

    # ------------------------------------------------------------ config ----
    def load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        self.cfg["auto_start_game"] = bool(self.auto_start.get())
        self.cfg["game_dir"] = self.game_dir()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log("配置保存失败: %s" % e)

    def game_dir(self):
        return self.cfg.get("game_dir") or DEFAULT_GAME_DIR

    def target_dll(self):
        return os.path.join(self.game_dir(), "MajdataPlay_Data", "Managed", "Assembly-CSharp.dll")

    def game_exe(self):
        return os.path.join(self.game_dir(), "MajdataPlay.exe")

    # ------------------------------------------------------------- style ----
    def init_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", background=BG, foreground=TEXT, font=FONT)
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD, relief="flat")
        st.configure("TLabel", background=BG, foreground=TEXT, font=FONT)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT, font=FONT)
        st.configure("Sub.TLabel", background=CARD, foreground=SUB, font=("Microsoft YaHei UI", 9))
        st.configure("Title.TLabel", background=BG, foreground=TEXT, font=FONT_TITLE)
        st.configure("TLabelframe", background=CARD, foreground=TEXT)
        st.configure("TLabelframe.Label", background=CARD, foreground=TEXT, font=FONT_BOLD)
        st.configure("TButton", font=FONT, padding=(10, 6))
        st.configure("Accent.TButton", font=FONT_BOLD, background=ACCENT, foreground="#ffffff",
                     padding=(14, 8))
        st.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#a9b6d4")])
        st.configure("TCheckbutton", background=CARD, foreground=TEXT, font=FONT)
        st.configure("TEntry", fieldbackground="#ffffff", foreground=TEXT)

    # ---------------------------------------------------------------- UI ----
    def build_ui(self):
        outer = ttk.Frame(self.root, padding=(14, 10, 14, 12))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=0, minsize=396)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(1, weight=1)

        # ---- header ----
        head = ttk.Frame(outer)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(head, text="传感器高亮配色", style="Title.TLabel").pack(side="left")
        self.state_label = ttk.Label(head, text="正在读取程序集…", foreground=SUB)
        self.state_label.pack(side="right")

        # ---- left: color editor ----
        left = ttk.LabelFrame(outer, text=" 颜色设置 ", padding=12, style="TLabelframe")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        inner = ttk.Frame(left, style="Card.TFrame")
        inner.pack(fill="both", expand=True)

        swatch_row = ttk.Frame(inner, style="Card.TFrame")
        swatch_row.pack(fill="x", pady=(0, 10))
        self.swatch = tk.Canvas(swatch_row, width=86, height=64, highlightthickness=1,
                                highlightbackground=BORDER, bg="#ffffff")
        self.swatch.pack(side="left")
        info = ttk.Frame(swatch_row, style="Card.TFrame")
        info.pack(side="left", padx=12, fill="y")
        self.hex_label = ttk.Label(info, text="#FF0000", font=("Consolas", 14, "bold"),
                                   style="Card.TLabel")
        self.hex_label.pack(anchor="w")
        self.rgba_label = ttk.Label(info, text="R 1.00  G 0.00  B 0.00  A 0.30",
                                    style="Sub.TLabel")
        self.rgba_label.pack(anchor="w", pady=(3, 0))
        ttk.Button(info, text="系统取色器…", command=self.pick_system).pack(anchor="w", pady=(8, 0))

        ttk.Label(inner, text="预设色板", style="Card.TLabel", font=FONT_BOLD).pack(anchor="w", pady=(6, 6))
        preset_grid = ttk.Frame(inner, style="Card.TFrame")
        preset_grid.pack(fill="x")
        for i, (name, rgba) in enumerate(PRESETS):
            b = tk.Button(preset_grid, text=name, font=("Microsoft YaHei UI", 9),
                          bg=blend(rgba, (245, 246, 249)), fg=self.readable_fg(rgba),
                          activebackground=blend(rgba, (245, 246, 249)),
                          relief="flat", bd=1, width=9, height=1,
                          command=lambda c=rgba: self.set_color(c))
            b.grid(row=i // 4, column=i % 4, padx=3, pady=3, sticky="ew")
        for c in range(4):
            preset_grid.columnconfigure(c, weight=1)

        ttk.Label(inner, text="精确调整", style="Card.TLabel", font=FONT_BOLD).pack(anchor="w", pady=(14, 6))
        self.scales = {}
        for key, label in (("r", "红 R"), ("g", "绿 G"), ("b", "蓝 B")):
            row = ttk.Frame(inner, style="Card.TFrame")
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=6, style="Card.TLabel").pack(side="left")
            var = tk.IntVar(value=int(round(self.rgba[{"r": 0, "g": 1, "b": 2}[key]] * 255)))
            s = tk.Scale(row, from_=0, to=255, orient="horizontal", variable=var,
                         showvalue=False, length=210, resolution=1,
                         bg=CARD, highlightthickness=0, troughcolor="#e6e9f0",
                         activebackground=ACCENT, command=self.on_scale)
            s.pack(side="left", fill="x", expand=True, padx=6)
            vlabel = ttk.Label(row, text="000", width=3, style="Card.TLabel", font=("Consolas", 10))
            vlabel.pack(side="right")
            self.scales[key] = (var, vlabel)

        row = ttk.Frame(inner, style="Card.TFrame")
        row.pack(fill="x", pady=(6, 2))
        ttk.Label(row, text="透明度", width=6, style="Card.TLabel").pack(side="left")
        self.alpha_var = tk.IntVar(value=30)
        sa = tk.Scale(row, from_=0, to=100, orient="horizontal", variable=self.alpha_var,
                      showvalue=False, length=210, resolution=1,
                      bg=CARD, highlightthickness=0, troughcolor="#e6e9f0",
                      activebackground=ACCENT, command=self.on_scale)
        sa.pack(side="left", fill="x", expand=True, padx=6)
        self.alpha_label = ttk.Label(row, text="30%", width=4, style="Card.TLabel",
                                     font=("Consolas", 10))
        self.alpha_label.pack(side="right")

        hexrow = ttk.Frame(inner, style="Card.TFrame")
        hexrow.pack(fill="x", pady=(14, 2))
        ttk.Label(hexrow, text="HEX", width=6, style="Card.TLabel").pack(side="left")
        self.hex_var = tk.StringVar(value="#FF0000")
        e = ttk.Entry(hexrow, textvariable=self.hex_var, width=14, font=("Consolas", 10))
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda _: self.apply_hex())
        ttk.Button(hexrow, text="应用", width=6, command=self.apply_hex).pack(side="left")
        ttk.Label(inner, text="提示：透明度 A 越高，高亮越不透明；0% 等于完全隐藏。",
                  style="Sub.TLabel", wraplength=340, justify="left").pack(anchor="w", pady=(10, 0))

        # ---- right: preview ----
        right = ttk.LabelFrame(outer, text=" 实时预览（模拟传感器面板） ", padding=12)
        right.grid(row=1, column=1, sticky="nsew")
        rp = ttk.Frame(right, style="Card.TFrame")
        rp.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(rp, bg="#1c1f28", highlightthickness=1,
                                highlightbackground=BORDER)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw_preview())

        ctl = ttk.Frame(rp, style="Card.TFrame")
        ctl.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(ctl, text="显示触发效果", variable=self.show_trigger,
                        command=self.draw_preview).pack(side="left")
        ttk.Button(ctl, text="换一组触发", command=self.cycle_trigger).pack(side="left", padx=10)
        self.compare = tk.Canvas(ctl, width=132, height=26, bg=CARD, highlightthickness=0)
        self.compare.pack(side="right")
        ttk.Label(rp, text="高亮色叠加在深色背景上的实际观感；游戏内需在设置中开启「显示传感器」。",
                  style="Sub.TLabel", wraplength=480, justify="left").pack(anchor="w", pady=(8, 0))

        # ---- actions ----
        act = ttk.LabelFrame(outer, text=" 应用到游戏 ", padding=10)
        act.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Button(act, text="应用到游戏", style="Accent.TButton",
                   command=self.apply_to_game).pack(side="left")
        ttk.Button(act, text="仅生成补丁 DLL", command=self.generate_only).pack(side="left", padx=8)
        ttk.Button(act, text="恢复原版灰", command=self.restore_stock).pack(side="left", padx=4)
        ttk.Button(act, text="回滚官方原版", command=self.rollback_official).pack(side="left", padx=4)
        ttk.Button(act, text="刷新状态", command=self.refresh_state).pack(side="left", padx=4)
        ttk.Checkbutton(act, text="应用后启动游戏", variable=self.auto_start,
                        command=self.save_config).pack(side="right")
        ttk.Label(outer, text="颜色写入程序集后需要重新加载，工具会自动关闭并重启游戏（约 15 秒）；谱面、皮肤、成绩库等个人数据不会触碰。",
                  foreground=SUB, wraplength=940, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.logbox = scrolledtext.ScrolledText(outer, height=7, font=("Consolas", 9),
                                                bg="#111827", fg="#d1d5db",
                                                insertbackground="#d1d5db",
                                                relief="flat", wrap="word")
        self.logbox.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.log("工具已就绪。目录：%s" % TOOL_DIR)
        if not self.dotnet:
            self.log("警告：未找到 dotnet，补丁功能不可用。请安装 .NET 桌面运行时。")

        self.set_color(tuple(self.rgba), silent=True)
        self.draw_preview()

    @staticmethod
    def readable_fg(rgba):
        lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
        return "#111111" if lum > 0.6 else "#ffffff"

    # -------------------------------------------------------------- color ----
    def set_color(self, rgba, silent=False):
        self.rgba = [clamp01(v) for v in rgba]
        self.updating = True
        for i, key in enumerate(("r", "g", "b")):
            var, lbl = self.scales[key]
            n = int(round(self.rgba[i] * 255))
            var.set(n)
            lbl.configure(text="%3d" % n)
        self.alpha_var.set(int(round(self.rgba[3] * 100)))
        self.alpha_label.configure(text="%d%%" % int(round(self.rgba[3] * 100)))
        self.hex_var.set(to_hex(self.rgba[:3]))
        self.updating = False
        self.refresh_color_display()
        if not silent:
            self.log("选择颜色 %s  A=%.2f" % (to_hex(self.rgba[:3]), self.rgba[3]))

    def on_scale(self, _=None):
        if self.updating:
            return
        r = self.scales["r"][0].get() / 255.0
        g = self.scales["g"][0].get() / 255.0
        b = self.scales["b"][0].get() / 255.0
        a = self.alpha_var.get() / 100.0
        for key, n in (("r", self.scales["r"][0].get()),
                       ("g", self.scales["g"][0].get()),
                       ("b", self.scales["b"][0].get())):
            self.scales[key][1].configure(text="%3d" % n)
        self.alpha_label.configure(text="%d%%" % self.alpha_var.get())
        self.rgba = [r, g, b, a]
        self.updating = True
        self.hex_var.set(to_hex(self.rgba[:3]))
        self.updating = False
        self.refresh_color_display()

    def apply_hex(self):
        try:
            rgb = from_hex(self.hex_var.get())
        except ValueError as e:
            messagebox.showwarning("HEX 格式错误", str(e))
            return
        self.set_color((rgb[0], rgb[1], rgb[2], self.rgba[3]))

    def pick_system(self):
        rgb, _ = colorchooser.askcolor(color=to_hex(self.rgba[:3]),
                                       title="选择传感器高亮颜色", parent=self.root)
        if rgb:
            self.set_color((rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, self.rgba[3]))

    def refresh_color_display(self):
        hx = to_hex(self.rgba[:3])
        self.hex_label.configure(text=hx)
        self.rgba_label.configure(text=fmt(tuple(self.rgba)))
        self.swatch.delete("all")
        self.swatch.create_rectangle(0, 0, 86, 32, fill=blend(tuple(self.rgba), (255, 255, 255)),
                                     outline="")
        self.swatch.create_rectangle(0, 32, 86, 64, fill=blend(tuple(self.rgba)), outline="")
        self.swatch.create_text(43, 16, text="浅底", fill="#111111", font=("Microsoft YaHei UI", 8))
        self.swatch.create_text(43, 48, text="游戏深底", fill="#ffffff",
                                font=("Microsoft YaHei UI", 8))
        self.draw_preview()

    def cycle_trigger(self):
        self.trigger_index = (self.trigger_index + 1) % len(TRIGGER_SETS)
        self.draw_preview()

    # ------------------------------------------------------------ preview ----
    def draw_preview(self):
        if not hasattr(self, "compare"):
            return
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 300)
        h = max(c.winfo_height(), 260)
        cx, cy = w // 2, h // 2 + 6
        base = min(w, h)
        r_out = int(base * 0.40)
        r_in = int(r_out * 0.53)
        bg_hex = "#%02X%02X%02X" % PREVIEW_BG
        active = blend(tuple(self.rgba)) if self.show_trigger.get() else bg_hex
        idle = "#%02X%02X%02X" % tuple(int(v * 1.25) for v in PREVIEW_BG)
        triggered = TRIGGER_SETS[self.trigger_index]

        box = (cx - r_out, cy - r_out, cx + r_out, cy + r_out)
        for i in range(8):
            start = i * 45 + 2
            fill = active if (self.show_trigger.get() and i in triggered) else idle
            c.create_arc(box, start=start, extent=41, style=tk.PIESLICE,
                         fill=fill, outline="#3b4150", width=1)
        c.create_oval(cx - r_in, cy - r_in, cx + r_in, cy + r_in,
                      fill=bg_hex, outline="#464c5c", width=2)
        c.create_oval(cx - int(r_in * 0.42), cy - int(r_in * 0.42),
                      cx + int(r_in * 0.42), cy + int(r_in * 0.42),
                      fill="#232733", outline="#4a5060", width=1)

        for i in range(8):
            ang = math.radians(i * 45 + 22.5)
            rr = (r_out + r_in) / 2
            x = cx + rr * math.cos(ang)
            y = cy - rr * math.sin(ang)
            hot = self.show_trigger.get() and i in triggered
            c.create_text(x, y, text="A%d" % (i + 1),
                          fill="#ffffff" if hot else "#8b93a5",
                          font=("Consolas", 9, "bold" if hot else "normal"))
        c.create_text(cx, cy, text="MAIMAI", fill="#6f7789", font=("Consolas", 10, "bold"))
        c.create_text(10, 12, text="触发态演示 · 空闲传感器保持透明",
                      anchor="nw", fill="#8b93a5", font=("Microsoft YaHei UI", 9))

        self.compare.delete("all")
        self.compare.create_rectangle(0, 2, 62, 24, fill=active, outline=BORDER)
        self.compare.create_rectangle(68, 2, 130, 24, fill=idle, outline=BORDER)
        self.compare.create_text(31, 13, text="触发", fill="#ffffff",
                                 font=("Microsoft YaHei UI", 8))
        self.compare.create_text(99, 13, text="空闲", fill="#9aa2b1",
                                 font=("Microsoft YaHei UI", 8))

    # -------------------------------------------------------------- engine ----
    @staticmethod
    def find_dotnet():
        p = shutil.which("dotnet")
        if p:
            return p
        for candidate in (r"C:\Program Files\dotnet\dotnet.exe",
                          r"C:\Program Files (x86)\dotnet\dotnet.exe"):
            if os.path.isfile(candidate):
                return candidate
        return None

    def run_engine(self, args):
        if not self.dotnet:
            raise RuntimeError("未找到 dotnet 运行时")
        if not os.path.isfile(ENGINE_DLL):
            raise RuntimeError("补丁引擎缺失：%s" % ENGINE_DLL)
        cmd = [self.dotnet, ENGINE_DLL] + args
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180,
                           creationflags=CREATE_NO_WINDOW)
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout or "补丁引擎返回 %d" % p.returncode).strip())
        return p.stdout.strip()

    def inspect(self, dll_path):
        out = self.run_engine([dll_path, "--inspect"])
        return json.loads(out.splitlines()[-1])

    # ------------------------------------------------------------- process ----
    def game_running(self):
        try:
            p = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MajdataPlay.exe", "/NH"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", creationflags=CREATE_NO_WINDOW, timeout=20)
            return "MajdataPlay.exe" in p.stdout
        except Exception:
            return False

    def close_game(self):
        p = subprocess.run(["taskkill", "/F", "/IM", "MajdataPlay.exe"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=CREATE_NO_WINDOW, timeout=30)
        self.log("关闭游戏：%s" % (p.stdout.strip() or p.stderr.strip() or "已发送"))

    def start_game(self):
        exe = self.game_exe()
        if not os.path.isfile(exe):
            raise RuntimeError("找不到游戏主程序：%s" % exe)
        subprocess.Popen([exe], cwd=self.game_dir(),
                         creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True)
        self.log("已启动游戏（请等待约 15 秒进入主界面）")

    # --------------------------------------------------------------- state ----
    def refresh_state(self):
        try:
            dll = self.target_dll()
            if not os.path.isfile(dll):
                self.state_label.configure(text="运行包未找到", foreground="#b91c1c")
                self.log("运行包 DLL 不存在：%s" % dll)
                return
            st = self.inspect(dll)
            self.current_state = st
            txt = "当前 DLL：RGBA(%.2f, %.2f, %.2f, %.2f)%s" % (
                st["r"], st["g"], st["b"], st["a"],
                " · 原版默认灰" if (st["r"], st["g"], st["b"], round(st["a"], 2)) == (0.0, 0.0, 0.0, 0.3) else "")
            self.state_label.configure(text=txt, foreground=SUB)
            self.log("读取程序集：%s" % txt)
            self.set_color((st["r"], st["g"], st["b"], st["a"]), silent=True)
        except Exception as e:
            self.state_label.configure(text="读取失败", foreground="#b91c1c")
            self.log("读取程序集失败：%s" % e)

    def log(self, msg):
        line = "[%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), msg)
        self.logbox.insert("end", line)
        self.logbox.see("end")
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    # -------------------------------------------------------------- actions ----
    def guard(self):
        if self.busy:
            return False
        if not self.dotnet:
            messagebox.showerror("缺少依赖", "未找到 dotnet 运行时，无法生成补丁。")
            return False
        if not os.path.isfile(self.target_dll()):
            messagebox.showerror("路径错误", "找不到运行包程序集：\n%s" % self.target_dll())
            return False
        return True

    def color_arg(self):
        return ",".join("%.6g" % clamp01(v) for v in self.rgba)

    def build_patched(self, out_path):
        src = self.target_dll()
        self.run_engine([src, out_path, "--color", self.color_arg()])
        st = self.inspect(out_path)
        want = [clamp01(v) for v in self.rgba]
        got = [st["r"], st["g"], st["b"], st["a"]]
        if any(abs(a - b) > 0.002 for a, b in zip(want, got)):
            raise RuntimeError("生成的程序集颜色校验失败：期望 %s 实际 %s" % (want, got))
        return st

    def backup_current(self):
        os.makedirs(LOCAL_BACKUPS, exist_ok=True)
        name = "Assembly-CSharp_%s.dll" % datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(LOCAL_BACKUPS, name)
        shutil.copy2(self.target_dll(), dst)
        self.log("已备份当前程序集：backups/%s" % name)
        return dst

    def apply_to_game(self):
        if not self.guard():
            return
        running = self.game_running()
        msg = ("将把高亮色设为 %s（A=%.2f）并写入运行包。\n\n" %
               (to_hex(self.rgba[:3]), self.rgba[3]))
        if running:
            msg += "检测到游戏正在运行，工具会先关闭它，替换程序集后自动重启。\n"
        else:
            msg += "游戏当前未运行，替换后%s。\n" % (
                "会自动启动" if self.auto_start.get() else "不会自动启动")
        msg += "\n个人数据（谱面/皮肤/成绩库/设置）不会改动。继续吗？"
        if not messagebox.askyesno("确认应用", msg):
            return

        self.busy = True
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            tmp = os.path.join(OUTPUT_DIR, "Assembly-CSharp.pending.dll")
            self.log("开始生成补丁…")
            if running:
                self.close_game()
                for _ in range(12):
                    if not self.game_running():
                        break
                    time.sleep(0.5)
                    self.root.update()
                if self.game_running():
                    raise RuntimeError("游戏进程仍在运行，程序集被占用，已取消替换")
            st = self.build_patched(tmp)
            self.log("补丁生成并校验通过：%s" % fmt(tuple(self.rgba)))
            self.backup_current()
            shutil.copy2(tmp, self.target_dll())
            check = self.inspect(self.target_dll())
            self.log("替换完成，运行包当前：RGBA(%.2f, %.2f, %.2f, %.2f)" % (
                check["r"], check["g"], check["b"], check["a"]))
            os.remove(tmp)
            self.current_state = check
            self.state_label.configure(
                text="当前 DLL：RGBA(%.2f, %.2f, %.2f, %.2f)" %
                     (check["r"], check["g"], check["b"], check["a"]), foreground=SUB)
            if self.auto_start.get():
                self.start_game()
            self.save_config()
            messagebox.showinfo("完成", "高亮色已应用。\n\n%s\n%s" % (
                fmt(tuple(self.rgba)),
                "游戏正在重新启动，进谱面后开启「显示传感器」即可看到效果。" if self.auto_start.get()
                else "下次启动游戏后生效。"))
        except Exception as e:
            self.log("应用失败：%s" % e)
            messagebox.showerror("应用失败", str(e))
        finally:
            self.busy = False

    def generate_only(self):
        if not self.guard():
            return
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            dst = os.path.join(OUTPUT_DIR, "Assembly-CSharp.dll")
            self.build_patched(dst)
            self.log("已生成补丁 DLL（未替换运行包）：%s" % dst)
            messagebox.showinfo("已生成", "补丁 DLL 已生成，未改动游戏目录：\n%s" % dst)
        except Exception as e:
            self.log("生成失败：%s" % e)
            messagebox.showerror("生成失败", str(e))

    def restore_stock(self):
        self.set_color((0.0, 0.0, 0.0, 0.30))
        self.log("已载入原版灰 (0,0,0,0.3)，点「应用到游戏」写入。")

    def rollback_official(self):
        if not os.path.isfile(OFFICIAL_DLL):
            messagebox.showerror("备份缺失", "找不到官方原版 DLL：\n%s" % OFFICIAL_DLL)
            return
        if not messagebox.askyesno(
                "确认回滚",
                "将用你自备的官方原版 2.0.3 程序集覆盖运行包，所有 IL 补丁"
                "（自定义高亮色，以及可能已单独安装的其他补丁）都会丢失。\n\n"
                "个人数据不会改动，且当前程序集会先备份。继续吗？"):
            return
        running = self.game_running()
        try:
            if running:
                self.close_game()
            self.backup_current()
            shutil.copy2(OFFICIAL_DLL, self.target_dll())
            self.log("已回滚为官方原版程序集")
            self.refresh_state()
            if running and self.auto_start.get():
                self.start_game()
            messagebox.showinfo("完成", "已回滚为官方原版程序集。")
        except Exception as e:
            self.log("回滚失败：%s" % e)
            messagebox.showerror("回滚失败", str(e))


def main():
    root = tk.Tk()
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open(os.path.join(TOOL_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write("[%s]\n%s\n" % (datetime.now().isoformat(), traceback.format_exc()))
        raise
