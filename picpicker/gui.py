#!/usr/bin/env python3
"""比卡拾图 PicPicker GUI 界面"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from urllib.parse import unquote
from PIL import Image, ImageTk
import os
import csv
import random
import zipfile
import shutil
import subprocess
import platform
import sys
import tempfile
from io import StringIO

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
    _DND_AVAILABLE = True
except ImportError:
    COPY = "copy"
    DND_FILES = "DND_Files"
    _DND_AVAILABLE = False


def _app_icon_path() -> Path | None:
    """返回开发环境、wheel 或 PyInstaller 包中的应用图标路径。"""
    candidates: list[Path] = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / "logo.png")

    module_dir = Path(__file__).resolve().parent
    candidates.extend((module_dir / "logo.png", module_dir.parent / "logo.png"))
    return next((path for path in candidates if path.is_file()), None)


class PicPickerApp:
    """PicPicker 比卡拾图 应用主类"""

    APP_TITLE = "PicPicker - 比卡拾图"
    
    # 支持的图片格式
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif', '.webp'}
    
    # 文件夹名称映射
    FOLDER_NAMES = ["原图文件夹", "图1文件夹", "图2文件夹"]
    
    def __init__(self):
        self.root = (TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk())
        self.current_csv_path: str | None = None
        self.is_dirty = False
        self._pending_dropped_csv_path: str | None = None
        self.root.title(self.APP_TITLE)
        self._set_app_icon()
        self.root.geometry("1400x950")
        
        # 存储文件夹路径和图片列表
        self.folder_paths = [None, None, None]  # 最多3个文件夹
        self.image_lists = [[], [], []]  # 每个文件夹的图片列表
        self.current_indices = [0, 0, 0]  # 当前显示的图片索引
        # 存储共享的上次选择目录（三个按钮共享）
        self.last_selected_dir = None
        # 存储选中状态（只针对图1文件夹和图2文件夹，索引1和2）
        self.selected_states = [{}, {}]  # [{图片索引: bool}, {图片索引: bool}]
        # 存储文字备注（只针对图1文件夹和图2文件夹，key 为图片在各自列表里的索引）
        self.notes = [{}, {}]  # [{图片索引: str}, {图片索引: str}]
        # 存储遮罩文件夹路径和图片列表（只针对图1和图2，索引1和2）
        self.mask_folder_paths = [None, None]  # 图1遮罩文件夹、图2遮罩文件夹
        self.mask_image_lists = [[], []]  # 图1遮罩图片列表、图2遮罩图片列表
        # 切换状态：False显示图片，True显示遮罩（只针对图1和图2）
        self.show_mask_mode = [False, False]  # 图1切换状态、图2切换状态
        # 全局遮罩显示状态：False 显示原图，True 显示遮罩（前提是对应侧有遮罩）
        self.mask_mode_enabled = False
        # 信息隐藏状态：False显示信息，True隐藏信息（只针对图1和图2）
        self.hide_info_mode = False  # 是否隐藏图1和图2的信息
        # 备注上屏状态：默认显示，只针对图1和图2
        self.show_note_overlay = True
        # 放大镜功能
        self.magnifier_enabled = False  # 放大镜是否启用
        self.magnifier_size = 200  # 放大镜窗口大小（像素）
        self.magnifier_zoom = 3  # 放大倍数
        self.magnifier_labels = []  # 三个放大镜标签
        self.current_mouse_preview = None  # 当前鼠标所在的预览图索引（0, 1, 2或None）
        self.magnifier_offset_x = 20  # 主镜相对鼠标的X偏移
        self.magnifier_offset_y = 20  # 主镜相对鼠标的Y偏移
        self.magnifier_update_id = None  # 放大镜更新任务的ID
        # 背景颜色选项（按顺序：默认、黑、白、红、绿、蓝；红绿蓝为偏暗色）
        self.bg_colors = {
            "默认": "#e0e0e0",
            "黑": "#000000",
            "白": "#FFFFFF",
            "红": "#990000",
            "绿": "#006400",
            "蓝": "#0000AA"
        }
        self.bg_color_order = ["默认", "黑", "白", "红", "绿", "蓝"]  # 颜色顺序
        self.current_bg_color = "默认"  # 当前选择的背景颜色
        # 背景颜色变量（需要在创建界面之前初始化，因为菜单需要使用）
        self.bg_color_var = tk.StringVar(value="默认")
        # 图片在预览框留白方向上的对齐方式：头部、居中、尾部
        self.image_position_var = tk.StringVar(value="居中")
        # 过滤：所有 / 有标记 / 有未标记 / 无标记（仅在菜单更改时刷新列表）
        self.filter_mode = "所有"
        self.filter_var = tk.StringVar(value="所有")
        self.filtered_indices = []  # 通过过滤的图片索引列表（当 filter_mode != 所有 时使用）
        self.current_filtered_index = 0  # 在过滤列表中的当前位置

        # 文件名搜索：保留当前关键词和命中位置，便于循环查找
        self._filename_search_dialog: tk.Toplevel | None = None
        self._filename_search_query = ""
        self._filename_search_results: list[int] = []
        self._filename_search_position = -1

        # 原图列表窗口（非模态）：横向缩略图列表，最多同时展示10张，支持滚动
        self.image_list_menu_var = tk.BooleanVar(value=False)
        self._image_list_window: tk.Toplevel | None = None
        self._image_list_canvas: tk.Canvas | None = None
        self._image_list_inner: tk.Frame | None = None
        self._image_list_scrollbar: tk.Scrollbar | None = None
        self._image_list_inner_window_id: int | None = None
        self._image_list_items: list[tk.Label] = []
        self._image_list_containers: list[tk.Frame] = []
        self._image_list_thumb_cache: dict[int, ImageTk.PhotoImage] = {}
        self._image_list_source_key: tuple[str, int] | None = None  # (folder_path_str, count)
        # 原图列表缩略图最长边 80，对应预览框约 80x80
        self._image_list_thumb_size = 80
        # 由原图列表点击触发跳转时，抑制一次自动滚动（因为点击处必然可见）
        self._suppress_image_list_auto_scroll_once: bool = False
        self._image_list_load_job: str | None = None  # after id
        # 盲选模式：对调图1/图2的展示（图片、文件名、路径与尺寸），标记以实际选择为准
        self.blind_mode = False
        self.blind_swap_indices: set[int] = set()  # 对调展示的图片索引（每次开启时随机 20%～80%）
        
        # 创建界面
        self._create_widgets()
        
        # 整个窗口支持拖入 .csv，按「打开标记文件」处理
        if _DND_AVAILABLE:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_root_drop)

        self._bind_keyboard_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

        # 启动后最大化窗口（非全屏）
        self._maximize_window()

    def _bind_keyboard_shortcuts(self):
        """注册键盘快捷键。

        键盘绑定必须独立于窗口最大化逻辑：Windows 上
        ``state("zoomed")`` 成功后会直接返回，不应因此跳过快捷键注册。
        """
        self.root.bind('<Up>', self._on_arrow_up)
        self.root.bind('<Down>', self._on_arrow_down)
        self.root.bind('<KeyPress-Up>', self._on_arrow_up)
        self.root.bind('<KeyPress-Down>', self._on_arrow_down)
        self.root.bind('<Left>', self._on_arrow_left)
        self.root.bind('<Right>', self._on_arrow_right)
        self.root.bind('<KeyPress-Left>', self._on_arrow_left)
        self.root.bind('<KeyPress-Right>', self._on_arrow_right)
        self.root.bind('<KeyPress-m>', self._on_key_m)
        self.root.bind('<KeyPress-M>', self._on_key_m)
        self.root.bind('<KeyPress-i>', self._on_key_i)
        self.root.bind('<KeyPress-I>', self._on_key_i)
        self.root.bind('<KeyPress-c>', self._on_key_c)
        self.root.bind('<KeyPress-C>', self._on_key_c)
        # 备注编辑快捷键：[ 图1备注；] 图2备注
        self.root.bind('<KeyPress>', self._on_keypress_for_note)

        # 文件名搜索快捷键
        if platform.system() == "Darwin":
            self.root.bind('<Command-f>', self._on_key_f)
            self.root.bind('<Command-F>', self._on_key_f)
        else:
            self.root.bind('<Control-f>', self._on_key_f)
            self.root.bind('<Control-F>', self._on_key_f)

        self.root.bind('<KeyPress-a>', self._on_key_a)
        self.root.bind('<KeyPress-A>', self._on_key_a)
        self.root.bind('<KeyPress-s>', self._on_key_s)
        self.root.bind('<KeyPress-S>', self._on_key_s)
        self.root.bind('<KeyPress-g>', self._on_key_g)
        self.root.bind('<KeyPress-G>', self._on_key_g)

        # 绑定 Command 或 Control 组合键。
        system = platform.system()
        if system == "Darwin":
            self.root.bind('<Command-o>', lambda e: self._import_from_csv())
            self.root.bind('<Command-O>', lambda e: self._import_from_csv())
            # 原图列表是独立 Toplevel，因此使用 bind_all。
            self.root.bind_all('<Command-l>', self._on_key_l)
            self.root.bind_all('<Command-L>', self._on_key_l)
            self.root.bind('<Command-b>', self._on_key_b)
            self.root.bind('<Command-B>', self._on_key_b)
            self.root.bind('<Command-s>', lambda e: self._export_to_csv())
            self.root.bind('<Command-Shift-s>', lambda e: self._save_csv_as())
            self.root.bind('<Command-Shift-S>', lambda e: self._save_csv_as())
            self.root.bind('<Command-Shift-e>', lambda e: self._export_marked_images())
            self.root.bind('<Command-Shift-E>', lambda e: self._export_marked_images())
            self.root.bind('<Command-r>', lambda e: self._invert_selections())
            self.root.bind('<Command-Shift-r>', lambda e: self._reset_selections())
            self.root.bind('<Command-Shift-R>', lambda e: self._reset_selections())
            self.root.bind('<Command-R>', lambda e: self._reset_selections())
            self.root.bind('<Command-w>', lambda e: self._close_folders())
            self.root.bind('<Command-W>', lambda e: self._close_folders())
            self.root.bind('<Command-q>', lambda e: self._quit_app())
            self.root.bind('<Command-Q>', lambda e: self._quit_app())
        else:
            self.root.bind('<Control-o>', lambda e: self._import_from_csv())
            self.root.bind('<Control-O>', lambda e: self._import_from_csv())
            self.root.bind_all('<Control-l>', self._on_key_l)
            self.root.bind_all('<Control-L>', self._on_key_l)
            self.root.bind('<Control-b>', self._on_key_b)
            self.root.bind('<Control-B>', self._on_key_b)
            self.root.bind('<Control-s>', lambda e: self._export_to_csv())
            self.root.bind('<Control-Shift-s>', lambda e: self._save_csv_as())
            self.root.bind('<Control-Shift-S>', lambda e: self._save_csv_as())
            self.root.bind('<Control-Shift-e>', lambda e: self._export_marked_images())
            self.root.bind('<Control-Shift-E>', lambda e: self._export_marked_images())
            self.root.bind('<Control-r>', lambda e: self._invert_selections())
            self.root.bind('<Control-Shift-r>', lambda e: self._reset_selections())
            self.root.bind('<Control-Shift-R>', lambda e: self._reset_selections())
            self.root.bind('<Control-R>', lambda e: self._reset_selections())
            self.root.bind('<Control-w>', lambda e: self._close_folders())
            self.root.bind('<Control-W>', lambda e: self._close_folders())
            self.root.bind('<Control-q>', lambda e: self._quit_app())
            self.root.bind('<Control-Q>', lambda e: self._quit_app())

        # 主键盘和数字小键盘的 1-6 均可切换背景色。
        for i in range(1, 7):
            idx = i - 1
            self.root.bind(f'<KeyPress-{i}>', lambda e, idx=idx: self._on_bg_color_key(idx))
            self.root.bind(f'<KeyPress-KP_{i}>', lambda e, idx=idx: self._on_bg_color_key(idx))

        self.root.focus_set()

    def _set_app_icon(self) -> None:
        """设置源码运行时的窗口图标；打包应用图标由 PyInstaller 设置。"""
        icon_path = _app_icon_path()
        if icon_path is None:
            return

        try:
            # 保存引用，避免 Tk 图片对象被回收后图标失效。
            self._app_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._app_icon)
        except tk.TclError:
            # 图标加载失败不应阻止主程序启动。
            self._app_icon = None

    def _maximize_window(self):
        """启动后最大化窗口（不是全屏）。"""
        # 先让Tk完成一次布局计算，避免拿到0尺寸
        try:
            self.root.update_idletasks()
        except Exception:
            pass

        system = platform.system()

        # Windows / Linux: Tk 通常支持 zoomed
        if system in ("Windows", "Linux"):
            try:
                self.root.state("zoomed")
                return
            except Exception:
                pass

        # macOS: 某些Tk版本不支持 state('zoomed')，尝试 -zoomed，再退回到屏幕尺寸
        try:
            self.root.attributes("-zoomed", True)
            return
        except Exception:
            pass

        try:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+0+0")
        except Exception:
            # 最后兜底：不影响启动
            pass
    
    def _create_widgets(self):
        """创建界面组件"""
        # 创建菜单栏
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 创建"文件"菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        
        # 添加打开文件夹的菜单项
        file_menu.add_command(label="打开原图文件夹…", command=lambda: self._select_folder(0))
        file_menu.add_separator()
        file_menu.add_command(label="打开图1文件夹…", command=lambda: self._select_folder(1))
        file_menu.add_command(label="打开图2文件夹…", command=lambda: self._select_folder(2))
        file_menu.add_separator()
        file_menu.add_command(label="打开图1遮罩文件夹…", command=lambda: self._select_mask_folder(1))
        file_menu.add_command(label="打开图2遮罩文件夹…", command=lambda: self._select_mask_folder(2))
        file_menu.add_separator()
        # 检测操作系统以确定快捷键显示
        system = platform.system()
        if system == "Darwin":  # macOS
            open_accelerator = "Cmd+O"
        else:  # Windows/Linux
            open_accelerator = "Ctrl+O"
        
        file_menu.add_command(
            label="打开标记文件…",
            command=self._import_from_csv,
            accelerator=open_accelerator
        )
        file_menu.add_separator()
        save_mark_acc = "Cmd+S" if system == "Darwin" else "Ctrl+S"
        save_as_acc = "Cmd+Shift+S" if system == "Darwin" else "Ctrl+Shift+S"
        save_mark_images_acc = "Cmd+Shift+E" if system == "Darwin" else "Ctrl+Shift+E"
        file_menu.add_command(
            label="保存标记",
            command=self._export_to_csv,
            accelerator=save_mark_acc
        )
        file_menu.add_command(
            label="另存为标记…",
            command=self._save_csv_as,
            accelerator=save_as_acc
        )
        file_menu.add_command(
            label="导出标记与图片…",
            command=self._export_marked_images,
            accelerator=save_mark_images_acc
        )
        file_menu.add_separator()
        close_acc = "Cmd+W" if system == "Darwin" else "Ctrl+W"
        quit_acc = "Cmd+Q" if system == "Darwin" else "Ctrl+Q"
        file_menu.add_command(
            label="关闭所有文件夹",
            command=self._close_folders,
            accelerator=close_acc
        )
        file_menu.add_command(
            label="退出",
            command=self._quit_app,
            accelerator=quit_acc
        )
        
        # 创建“导航”菜单：集中图片定位、切换和同步操作。
        navigation_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="导航", menu=navigation_menu)

        navigation_menu.add_command(
            label="上一张图片",
            command=lambda: self._navigate_images(-1),
            accelerator="↑"
        )
        navigation_menu.add_command(
            label="下一张图片",
            command=lambda: self._navigate_images(1),
            accelerator="↓"
        )
        navigation_menu.add_command(
            label="跳转到…",
            command=self._jump_to_image,
            accelerator="G"
        )
        search_accelerator = "Cmd+F" if platform.system() == "Darwin" else "Ctrl+F"
        navigation_menu.add_command(
            label="搜索原图…",
            command=self._show_filename_search,
            accelerator=search_accelerator
        )
        # 原图列表（非模态窗口，显示原图文件夹的缩略图列表）
        navigation_menu.add_checkbutton(
            label="原图列表",
            command=self._toggle_image_list_window,
            variable=self.image_list_menu_var,
            accelerator="Cmd+L" if platform.system() == "Darwin" else "Ctrl+L"
        )
        navigation_menu.add_separator()
        navigation_menu.add_command(
            label="对齐到原图",
            command=self._align_to_original,
            accelerator="A"
        )

        # 创建“显示”菜单：集中图片呈现方式和查看状态。
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="显示", menu=view_menu)

        # 切换遮罩/图片：根据当前全局遮罩状态切换，文案随之更新
        view_menu.add_command(
            label="切换遮罩",
            command=self._toggle_mask_mode,
            accelerator="M"
        )
        # 记录切换遮罩菜单项索引，便于后续更新文案
        self.toggle_mask_menu_index = view_menu.index(tk.END)
        view_menu.add_separator()

        # 查看状态统一使用勾选项，勾选表示该功能当前已启用或内容可见。
        self.blind_mode_var = tk.BooleanVar(value=False)
        blind_accelerator = "Cmd+B" if platform.system() == "Darwin" else "Ctrl+B"
        view_menu.add_checkbutton(
            label="盲选模式",
            command=self._toggle_blind_mode,
            variable=self.blind_mode_var,
            accelerator=blind_accelerator
        )

        self.show_info_menu_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="显示图片信息",
            command=self._toggle_info_visibility,
            variable=self.show_info_menu_var,
            accelerator="I"
        )

        # 备注上屏开关（默认显示）
        self.show_note_menu_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="显示备注",
            command=self._toggle_note_visibility,
            variable=self.show_note_menu_var,
            accelerator="C"
        )
        self.view_menu = view_menu

        # 添加放大镜开关
        self.magnifier_menu_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(
            label="放大镜",
            command=self._toggle_magnifier,
            variable=self.magnifier_menu_var,
            accelerator="S"
        )
        view_menu.add_separator()
        
        # 添加"图片背景"子菜单
        bg_color_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="图片背景", menu=bg_color_menu)
        
        # 添加颜色选项到子菜单（使用单选按钮显示当前选中状态）
        for idx, color_option in enumerate(self.bg_color_order):
            accelerator = str(idx + 1)  # 快捷键1-6
            bg_color_menu.add_radiobutton(
                label=color_option,
                variable=self.bg_color_var,
                value=color_option,
                command=self._change_bg_color,
                accelerator=accelerator
            )

        # 图片位置：横向存在留白时对应左/中/右，纵向存在留白时对应上/中/下。
        image_position_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="图片位置", menu=image_position_menu)
        for position in ("头部", "居中", "尾部"):
            image_position_menu.add_radiobutton(
                label=position,
                variable=self.image_position_var,
                value=position,
                command=self._change_image_position,
            )
        
        # 创建"标记"菜单
        mark_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="标记", menu=mark_menu)

        # 添加"过滤"子菜单（所有 / 有标记 / 有未标记 / 无标记 | 图1标记/图1未标记/图2标记/图2未标记）
        filter_menu = tk.Menu(mark_menu, tearoff=0)
        mark_menu.add_cascade(label="过滤", menu=filter_menu)
        for opt in ("所有", "有标记", "有未标记", "无标记"):
            filter_menu.add_radiobutton(
                label=opt,
                variable=self.filter_var,
                value=opt,
                command=self._apply_filter
            )
        filter_menu.add_separator()
        for opt in ("相同", "异同"):
            filter_menu.add_radiobutton(
                label=opt,
                variable=self.filter_var,
                value=opt,
                command=self._apply_filter
            )
        filter_menu.add_separator()
        for opt in ("图1标记", "图1未标记", "图2标记", "图2未标记"):
            filter_menu.add_radiobutton(
                label=opt,
                variable=self.filter_var,
                value=opt,
                command=self._apply_filter
            )
        mark_menu.add_separator()

        # 添加标记相关的菜单项
        mark_menu.add_command(
            label="标记图1",
            command=lambda: self._toggle_selection(1),
            accelerator="←"
        )
        mark_menu.add_command(
            label="标记图2",
            command=lambda: self._toggle_selection(2),
            accelerator="→"
        )
        invert_acc = "Cmd+R" if platform.system() == "Darwin" else "Ctrl+R"
        mark_menu.add_command(
            label="反转标记…",
            command=self._invert_selections,
            accelerator=invert_acc
        )
        reset_acc = "Cmd+Shift+R" if platform.system() == "Darwin" else "Ctrl+Shift+R"
        mark_menu.add_command(
            label="重置标记…",
            command=self._reset_selections,
            accelerator=reset_acc
        )
        mark_menu.add_separator()
        mark_menu.add_command(
            label="备注图1…",
            command=lambda: self._edit_note(1),
            accelerator="["
        )
        mark_menu.add_command(
            label="备注图2…",
            command=lambda: self._edit_note(2),
            accelerator="]"
        )

        # 创建"关于"菜单
        about_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="关于", menu=about_menu)
        about_menu.add_command(
            label="关于 PicPicker",
            command=self._show_about
        )
        
        # 使用grid布局管理主窗口，确保状态栏不会被挤压
        # 主容器使用grid布局
        main_container = tk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        main_container.grid_rowconfigure(1, weight=1)  # 预览区域可扩展
        main_container.grid_columnconfigure(0, weight=1)
        
        # 顶部区域：左（操作提示）、中（过滤条件）、右（图片背景）
        button_frame = tk.Frame(main_container)
        button_frame.grid(row=0, column=0, sticky="ew", pady=10, padx=10)
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        
        # 左侧提示（将底部操作键提示移到顶部）
        left_hint_frame = tk.Frame(button_frame)
        left_hint_frame.grid(row=0, column=0, sticky="ew")
        left_hint_frame.grid_columnconfigure(0, weight=1)
        self.key_hint_label = tk.Label(
            left_hint_frame,
            text="↑↓ 切换图片 | ←→ 标记图1/图2 | M 切换遮罩 | S 放大镜 | 双击打开原图",
            font=("Arial", 9),
            fg="#000000",
            anchor=tk.W
        )
        self.key_hint_label.grid(row=0, column=0, sticky="w")
        
        # 居中：当前过滤条件 + 盲选状态（盲选开启时在右侧显示「盲选模式：开」）
        center_status_frame = tk.Frame(button_frame)
        center_status_frame.grid(row=0, column=1, padx=15)
        self.filter_condition_label = tk.Label(
            center_status_frame,
            text="过滤: 所有",
            font=("Arial", 9),
            fg="#000000",
            anchor=tk.CENTER
        )
        self.filter_condition_label.pack(side=tk.LEFT)
        self.blind_mode_status_label = tk.Label(
            center_status_frame,
            text="",
            font=("Arial", 9),
            fg="#000000",
            anchor=tk.W
        )
        # 未开启盲选时不 pack，开启时再 pack(side=tk.LEFT, padx=(15, 0))
        
        # 右侧容器（图片背景选择靠右）
        right_button_frame = tk.Frame(button_frame)
        right_button_frame.grid(row=0, column=2, sticky="e")
        
        # 图片背景标签
        bg_color_label = tk.Label(
            right_button_frame,
            text="图片背景:",
            font=("Arial", 9)
        )
        bg_color_label.pack(side=tk.LEFT, padx=5)
        
        # 背景颜色单选按钮组（使用色块显示）
        for shortcut_number, color_option in enumerate(self.bg_color_order, start=1):
            bg_color = self.bg_colors[color_option]
            fg_color = self._get_contrasting_text_color(bg_color)
            # 创建单选按钮（使用indicatoron=0显示为色块）
            bg_radio = tk.Radiobutton(
                right_button_frame,
                text=str(shortcut_number),
                variable=self.bg_color_var,
                value=color_option,
                command=self._change_bg_color,
                indicatoron=0,  # 隐藏单选按钮的圆圈，显示为按钮样式
                width=3,
                height=1,
                bg=bg_color,
                fg=fg_color,
                selectcolor=bg_color,  # 选中时的颜色
                activebackground=bg_color,  # 鼠标悬停时的颜色
                activeforeground=fg_color,
                relief=tk.RAISED,
                borderwidth=2
            )
            bg_radio.pack(side=tk.LEFT, padx=2)
        
        # 图片预览区域
        preview_frame = tk.Frame(main_container)
        preview_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        # 使用grid布局，让预览图父容器撑满剩余空间
        preview_frame.grid_rowconfigure(1, weight=1)  # 预览图父容器行可扩展
        preview_frame.grid_columnconfigure(0, weight=1)  # 列可扩展
        
        # 创建3个预览框
        self.preview_labels = []
        self.filename_labels = []  # 文件名只读文本框（用于复制）
        self.folder_path_entries = []  # 文件夹路径只读文本框（用于复制）
        self.check_labels = []  # 选中标志标签（只用于图1文件夹和图2文件夹）
        self.selection_status_labels = []  # 选中状态显示标签（只用于图1文件夹和图2文件夹）
        self.path_status_labels = []  # 路径状态显示标签（显示图片路径和遮罩路径）
        self.note_overlay_labels = [None, None, None]  # 图1/图2预览框底部的备注上屏标签
        self.preview_context_menus = []  # 三个图片预览区域共用全局状态的右键菜单
        
        # 创建信息栏区域（上方，三个信息栏并排）
        info_frame = tk.Frame(preview_frame)
        info_frame.grid(row=0, column=0, sticky="ew", padx=3)
        # 使用grid布局确保三个信息栏均分宽度
        info_frame.grid_columnconfigure(0, weight=1, uniform="info_cols")
        info_frame.grid_columnconfigure(1, weight=1, uniform="info_cols")
        info_frame.grid_columnconfigure(2, weight=1, uniform="info_cols")
        
        # 创建统一的预览图父容器（确保三个预览图高度一致，宽度均分，高度撑满剩余空间）
        preview_images_frame = tk.Frame(preview_frame)
        preview_images_frame.grid(row=1, column=0, sticky="nsew", padx=3)
        # 使用grid布局确保三个预览图均分宽度和高度
        preview_images_frame.grid_columnconfigure(0, weight=1, uniform="preview_cols")
        preview_images_frame.grid_columnconfigure(1, weight=1, uniform="preview_cols")
        preview_images_frame.grid_columnconfigure(2, weight=1, uniform="preview_cols")
        preview_images_frame.grid_rowconfigure(0, weight=1)  # 行可扩展，撑满高度
        
        for i in range(3):
            # 每个预览框的信息栏容器（放在上方信息栏区域）
            # 原图、图1、图2使用统一的样式和字体大小
            container = tk.Frame(info_frame)
            container.grid(row=0, column=i, sticky="ew", padx=3)
            
            # 文件夹名称和路径放在同一行
            folder_path_frame = tk.Frame(container)
            folder_path_frame.pack(pady=1, fill=tk.X, anchor="w")
            
            # 文件夹名称标签
            folder_name_label = tk.Label(
                folder_path_frame,
                text=f"{self.FOLDER_NAMES[i]}:",
                font=("Arial", 9)
            )
            folder_name_label.pack(side=tk.LEFT, padx=(0, 5))  # 左侧，右边距5像素
            
            # 文件夹路径只读文本框（用于复制）
            folder_path_entry = tk.Entry(
                folder_path_frame,
                font=("Arial", 9),
                state="readonly",
                fg="#000000"
            )
            folder_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)  # 左侧，填充剩余空间
            # 双击路径框：打开对应目录
            folder_path_entry.bind("<Double-Button-1>", lambda e, idx=i: self._open_folder_path(idx))
            # 初始化显示"未选择"
            folder_path_entry.config(state="normal")
            folder_path_entry.insert(0, "未选择")
            folder_path_entry.config(state="readonly")
            self.folder_path_entries.append(folder_path_entry)
            
            # 文件名只读文本框（用于复制）
            filename_entry = tk.Entry(
                container,
                font=("Arial", 16),
                state="readonly",
                fg="#000000",
                justify="center",
                readonlybackground=container.cget("bg"),
                relief=tk.FLAT,
                highlightthickness=0,
            )
            filename_entry.pack(pady=1, fill=tk.X)  # 缩小行间距
            # 初始化为空（readonly 下需切到 normal 写入）
            filename_entry.config(state="normal")
            filename_entry.insert(0, "")
            filename_entry.config(state="readonly")
            self.filename_labels.append(filename_entry)
            
            # 状态信息显示标签（在预览图上方）
            # 统一字体：Arial 9
            # 原图文件夹显示"当前第n/m张"，图1/2文件夹显示"已标记 n/m percent%"
            selection_status_label = tk.Label(
                container,
                text="",
                font=("Arial", 9),
                fg="#006600",
                height=1  # 固定高度，确保对齐
            )
            selection_status_label.pack(pady=1, fill=tk.X)  # 缩小行间距
            self.selection_status_labels.append(selection_status_label)
            
            # 预览图容器（用于在预览图右上角放置选中标志）
            # 放在统一的预览图父容器中，确保高度一致，宽度均分
            preview_container = tk.Frame(preview_images_frame)
            preview_container.grid(row=0, column=i, sticky="nsew", padx=2)
            preview_container.grid_rowconfigure(0, weight=1)  # 预览图行可扩展
            preview_container.grid_columnconfigure(0, weight=1)  # 预览图列可扩展
            
            # 图片预览框（统一高度，使用grid确保填充整个容器）
            folder_name = self.FOLDER_NAMES[i]
            preview_label = tk.Label(
                preview_container,
                text=f"打开{folder_name}",
                bg=self.bg_colors[self.current_bg_color],  # 使用当前选择的背景颜色
                relief=tk.SUNKEN,
                borderwidth=2,
            )
            preview_label.grid(row=0, column=0, sticky="nsew")
            context_menu_widgets = [preview_container, preview_label]
            # 绑定单击事件，选择文件夹（当未选择文件夹时）
            preview_label.bind("<Button-1>", lambda e, idx=i: self._on_preview_click(idx))
            # 绑定双击事件，打开原文件（当已选择文件夹时）
            preview_label.bind("<Double-Button-1>", lambda e, idx=i: self._open_image_file(idx))
            # 绑定鼠标移动事件，用于放大镜功能
            preview_label.bind("<Motion>", lambda e, idx=i: self._on_preview_mouse_move(e, idx))
            preview_label.bind("<Leave>", lambda e, idx=i: self._on_preview_mouse_leave(e, idx))
            if _DND_AVAILABLE:
                preview_label.drop_target_register(DND_FILES)
                preview_label.dnd_bind("<<Drop>>", lambda e, idx=i: self._on_preview_drop(e, idx))
            self.preview_labels.append(preview_label)

            # 图1、图2备注上屏标签：独立于图片层，显隐时无需重新绘制图片。
            if i >= 1:
                note_overlay_label = tk.Label(
                    preview_container,
                    text="",
                    font=("Arial", 12),
                    fg=self._get_contrasting_text_color(
                        self.bg_colors[self.current_bg_color]
                    ),
                    # Tk Label 不支持真正透明；与勾选标志相同，通过同步
                    # 预览背景色实现视觉上的透明底色。
                    bg=self.bg_colors[self.current_bg_color],
                    justify=tk.LEFT,
                    anchor="w",
                    padx=8,
                    pady=6,
                )
                note_overlay_label.place_forget()
                preview_container.bind(
                    "<Configure>",
                    lambda e, label=note_overlay_label: label.config(
                        wraplength=max(1, e.width - 16)
                    ),
                    add="+",
                )
                self.note_overlay_labels[i] = note_overlay_label
                context_menu_widgets.append(note_overlay_label)
            
            # 创建放大镜标签（初始隐藏，放在预览图容器中）
            magnifier_label = tk.Label(
                preview_container,
                relief=tk.RAISED,
                borderwidth=2,
                bg="white"
            )
            magnifier_label.place_forget()  # 初始隐藏
            self.magnifier_labels.append(magnifier_label)
            context_menu_widgets.append(magnifier_label)
            
            # 选中标志标签（只用于图1文件夹和图2文件夹，索引1和2）
            # 放置在预览图右上角，字体再放大2倍（从32到64）
            if i >= 1:  # 只对图1文件夹和图2文件夹添加选中标志
                check_label = tk.Label(
                    preview_container,
                    text="",
                    font=("Arial", 64),  # 再放大2倍（从32到64）
                    fg="#00AA00",
                    bg="#e0e0e0"  # 与预览图背景色一致
                )
                # 使用place布局放置在右上角
                check_label.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)
                self.check_labels.append(check_label)
                context_menu_widgets.append(check_label)
            else:
                self.check_labels.append(None)  # 原图文件夹不需要选中标志

            preview_context_menu = tk.Menu(preview_container, tearoff=0)
            self.preview_context_menus.append(preview_context_menu)
            for widget in context_menu_widgets:
                self._bind_preview_context_menu(widget, preview_context_menu, i)
        
        # 预览图下方的路径状态显示区域
        path_status_frame = tk.Frame(preview_frame)
        path_status_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        # 使用uniform确保三个状态信息均分宽度
        path_status_frame.grid_columnconfigure(0, weight=1, uniform="path_cols")
        path_status_frame.grid_columnconfigure(1, weight=1, uniform="path_cols")
        path_status_frame.grid_columnconfigure(2, weight=1, uniform="path_cols")
        
        # 为每个预览图创建路径状态显示标签
        for i in range(3):
            path_status_label = tk.Label(
                path_status_frame,
                text="",
                font=("Arial", 9),
                fg="#666666",
                wraplength=0,  # 设置为0表示不限制换行，让文本自然显示
                justify=tk.LEFT,
                anchor="w"
            )
            path_status_label.grid(row=0, column=i, sticky="ew", padx=5)
            self.path_status_labels.append(path_status_label)
        
        # 状态栏（使用grid布局放在主容器的独立行，不会被挤压）
        self.status_label = tk.Label(
            main_container,
            text="",
            font=("Arial", 9),
            bg="#f0f0f0",
            anchor=tk.W
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
    
    def _build_filtered_indices(self):
        """根据当前 filter_mode 和 selected_states 构建过滤后的索引列表（仅当 filter_mode 不为 所有 时有效）"""
        lengths = [len(self.image_lists[i]) for i in range(3) if self.image_lists[i]]
        n = min(lengths) if lengths else 0
        if n == 0:
            self.filtered_indices = []
            return
        if self.filter_mode == "有标记":
            self.filtered_indices = [
                k for k in range(n)
                if self.selected_states[0].get(k, False) or self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "有未标记":
            # 图1或图2有其一未标记即列出
            self.filtered_indices = [
                k for k in range(n)
                if not self.selected_states[0].get(k, False) or not self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "无标记":
            # 图1和图2均未标记才列出
            self.filtered_indices = [
                k for k in range(n)
                if not self.selected_states[0].get(k, False) and not self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "相同":
            # 图1与图2标记状态相同（同为标记 or 同为未标记）
            self.filtered_indices = [
                k for k in range(n)
                if self.selected_states[0].get(k, False) == self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "异同":
            # 图1与图2标记状态不同（一边标记另一边未标记）
            self.filtered_indices = [
                k for k in range(n)
                if self.selected_states[0].get(k, False) != self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "图1标记":
            self.filtered_indices = [
                k for k in range(n)
                if self.selected_states[0].get(k, False)
            ]
        elif self.filter_mode == "图1未标记":
            self.filtered_indices = [
                k for k in range(n)
                if not self.selected_states[0].get(k, False)
            ]
        elif self.filter_mode == "图2标记":
            self.filtered_indices = [
                k for k in range(n)
                if self.selected_states[1].get(k, False)
            ]
        elif self.filter_mode == "图2未标记":
            self.filtered_indices = [
                k for k in range(n)
                if not self.selected_states[1].get(k, False)
            ]
        else:
            self.filtered_indices = list(range(n))

    def _get_original_list_indices(self) -> list[int]:
        """返回原图列表窗口应显示的原图索引序列：受当前过滤模式控制。"""
        if self.filter_mode != "所有" and self.filtered_indices:
            # 过滤模式下，仅显示通过过滤的索引
            return list(self.filtered_indices)
        # 否则显示原图文件夹中的全部图片
        return list(range(len(self.image_lists[0]) if self.image_lists and self.image_lists[0] else 0))
    
    def _sync_indices_from_filtered(self):
        """根据 current_filtered_index 和 filtered_indices 同步 current_indices（仅当过滤列表非空时调用）"""
        if not self.filtered_indices:
            return
        self.current_filtered_index = max(0, min(self.current_filtered_index, len(self.filtered_indices) - 1))
        k = self.filtered_indices[self.current_filtered_index]
        for i in range(3):
            if self.image_lists[i]:
                self.current_indices[i] = min(k, len(self.image_lists[i]) - 1)
    
    def _apply_filter(self):
        """菜单中更改过滤条件时刷新过滤列表并更新显示（浏览过程中改标记不动态刷新）"""
        self._reset_filename_search(close_dialog=True)
        self.filter_mode = self.filter_var.get()
        self.filter_condition_label.config(text=f"过滤: {self.filter_mode}")
        # 与左侧操作信息栏同字体；有标记/无标记时加粗
        if self.filter_mode != "所有":
            self.filter_condition_label.config(font=("Arial", 9, "bold"))
        else:
            self.filter_condition_label.config(font=("Arial", 9))
        if self.filter_mode == "所有":
            self._update_all_previews()
            # 过滤恢复为“所有”：原图列表显示全部原图
            self._refresh_image_list_window()
            self._highlight_current_in_image_list()
            return
        self._build_filtered_indices()
        self.current_filtered_index = 0
        if self.filtered_indices:
            self._sync_indices_from_filtered()
        self._update_all_previews()
        if self.hide_info_mode:
            for index in [1, 2]:
                if self.image_lists[index]:
                    self._update_info_visibility(index)
        self._refresh_magnifier_if_needed()
        # 过滤列表变化时刷新原图列表内容与高亮
        self._refresh_image_list_window()
        self._highlight_current_in_image_list()
    
    def _apply_folder_to_index(self, index, folder_path):
        """将指定文件夹路径应用到某预览框（原图/图1/图2）。供选择文件夹与拖拽放入共用。"""
        if not folder_path or not os.path.isdir(folder_path):
            return
        self._reset_filename_search(close_dialog=True)
        self.folder_paths[index] = folder_path
        self.image_lists[index] = self._load_images(folder_path)
        self.current_indices[index] = 0
        self.last_selected_dir = folder_path
        if index >= 1:
            self.selected_states[index - 1] = {i: False for i in range(len(self.image_lists[index]))}
            # 切换图1/图2文件夹时清空对应备注
            self.notes[index - 1] = {}
        if not self.hide_info_mode or index == 0:
            self.folder_path_entries[index].config(state="normal")
            self.folder_path_entries[index].delete(0, tk.END)
            self.folder_path_entries[index].insert(0, folder_path)
            self.folder_path_entries[index].config(state="readonly")
        if index >= 1:
            self._update_info_visibility(index)
        self._update_preview(index)
        if index >= 1:
            self._update_info_visibility(index)
        image_count = len(self.image_lists[index])
        self.status_label.config(
            text=f"{self.FOLDER_NAMES[index]} 已加载 {image_count} 张图片"
        )
        # 原图文件夹变化时刷新原图列表窗口
        if index == 0:
            self._refresh_image_list_window()
        if self.filter_mode != "所有":
            self._build_filtered_indices()
            self.current_filtered_index = 0
            if self.filtered_indices:
                self._sync_indices_from_filtered()
            self._update_all_previews()
        self._set_dirty(True)

    def _show_image_or_mask_choice(self, path_str, index):
        """弹出非模态对话框：将文件夹作为图片还是遮罩？用户点击后再执行，不阻塞拖放返回。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("选择用途")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        tk.Label(dlg, text="将文件夹作为图片还是遮罩？", font=("Arial", 11)).pack(pady=15, padx=20)
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(0, 15))

        def as_image():
            dlg.destroy()
            self._apply_folder_to_index(index, path_str)

        def as_mask():
            dlg.destroy()
            self._apply_mask_folder_to_index(index, path_str)

        tk.Button(btn_frame, text="图片", width=10, command=as_image).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="遮罩", width=10, command=as_mask).pack(side=tk.LEFT, padx=5)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.lift(self.root)
        dlg.focus_force()
        # 不调用 wait_window / grab_set，拖放处理立即返回，UI 不卡住；用户点击按钮时再执行逻辑

    def _apply_mask_folder_to_index(self, index, folder_path):
        """将指定路径设为某预览框的遮罩文件夹（index: 1 为图1，2 为图2）。"""
        if not folder_path or not os.path.isdir(folder_path):
            return
        mask_index = index - 1
        self.mask_folder_paths[mask_index] = folder_path
        self.mask_image_lists[mask_index] = self._load_images(folder_path)
        self.last_selected_dir = folder_path
        self._update_preview(index)
        if not self.hide_info_mode:
            self._update_path_status(index)
        else:
            self.path_status_labels[index].config(text="该信息已隐藏")
        if index >= 1:
            self._update_info_visibility(index)
        mask_count = len(self.mask_image_lists[mask_index])
        self.status_label.config(
            text=f"{self.FOLDER_NAMES[index]}遮罩文件夹已加载，共 {mask_count} 张图片"
        )
        self._set_dirty(True)

    def _on_preview_drop(self, event, index):
        """拖拽放入：.csv 按「打开标记文件」处理；文件夹则设该预览框路径或弹出图片/遮罩选择。"""
        if not _DND_AVAILABLE or not getattr(event, "data", None):
            return
        try:
            for raw in self.root.tk.splitlist(event.data):
                s = str(raw).strip()
                if s.startswith("file://"):
                    s = unquote(s[7:].lstrip("/"))
                p = Path(s)
                if p.is_file() and p.suffix.lower() == ".csv":
                    self._queue_dropped_csv_import(str(p))
                    return COPY
                if p.is_dir():
                    path_str = str(p)
                    if index in (1, 2) and self.folder_paths[index]:
                        self._show_image_or_mask_choice(path_str, index)
                    else:
                        self._apply_folder_to_index(index, path_str)
                    return
        except Exception:
            pass

    def _select_folder(self, index):
        """选择文件夹"""
        initial_dir = None
        if self.last_selected_dir and os.path.exists(self.last_selected_dir):
            initial_dir = self.last_selected_dir
        else:
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                initial_dir = downloads_dir
            else:
                initial_dir = os.path.expanduser("~")
        folder_path = filedialog.askdirectory(
            title=f"选择{self.FOLDER_NAMES[index]}",
            initialdir=initial_dir
        )
        self.root.focus_force()
        if folder_path:
            self._apply_folder_to_index(index, folder_path)
    
    def _load_images(self, folder_path):
        """加载文件夹中的所有图片"""
        image_files = []
        folder = Path(folder_path)
        
        if not folder.exists():
            return []
        
        # 遍历文件夹，查找所有图片文件
        for file_path in folder.iterdir():
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in self.IMAGE_EXTENSIONS:
                    image_files.append(file_path)
        
        # 按文件名排序
        image_files.sort(key=lambda x: x.name)
        
        return image_files
    
    def _select_mask_folder(self, index):
        """选择遮罩文件夹（index: 1为图1，2为图2）"""
        # 确定初始目录：优先使用共享的上次选择的目录，否则使用下载目录
        initial_dir = None
        
        # 如果有共享的上次选择的目录，且目录存在，使用它
        if self.last_selected_dir and os.path.exists(self.last_selected_dir):
            initial_dir = self.last_selected_dir
        else:
            # 否则使用下载目录
            downloads_dir = os.path.expanduser("~/Downloads")
            if os.path.exists(downloads_dir):
                initial_dir = downloads_dir
            else:
                initial_dir = os.path.expanduser("~")
        
        folder_path = filedialog.askdirectory(
            title=f"选择{self.FOLDER_NAMES[index]}遮罩文件夹",
            initialdir=initial_dir
        )
        self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
        if folder_path:
            self._apply_mask_folder_to_index(index, folder_path)
    
    def _toggle_mask_mode(self):
        """切换遮罩/图片显示模式：全局开关，图1/图2 始终同步。"""
        # 检查是否至少有一个遮罩文件夹已选择
        has_mask = False
        for i in range(2):
            if self.mask_folder_paths[i] and self.mask_image_lists[i]:
                has_mask = True
                break
        
        if not has_mask:
            messagebox.showwarning("警告", "请先选择遮罩文件夹！")
            return
        
        # 全局遮罩状态取反
        self.mask_mode_enabled = not self.mask_mode_enabled
        # 图1/图2 的显示模式始终跟随全局状态
        self.show_mask_mode[0] = self.mask_mode_enabled
        self.show_mask_mode[1] = self.mask_mode_enabled
        
        # 根据当前状态更新菜单文案：显示原图时提供「切换遮罩」，显示遮罩时提供「切换图片」
        if hasattr(self, "view_menu") and hasattr(self, "toggle_mask_menu_index"):
            if self.mask_mode_enabled:
                self.view_menu.entryconfig(self.toggle_mask_menu_index, label="切换图片")
            else:
                self.view_menu.entryconfig(self.toggle_mask_menu_index, label="切换遮罩")
        
        # 刷新图1和图2 预览与路径状态
        for idx in (1, 2):
            if self.image_lists[idx]:
                self._update_preview(idx)
                if not self.hide_info_mode:
                    self._update_path_status(idx)
                else:
                    self.path_status_labels[idx].config(text="该信息已隐藏")
        
        # 如果放大镜启用且鼠标在预览图上，刷新放大镜（遮罩切换）
        self._refresh_magnifier_if_needed()
    
    def _update_preview(self, index):
        """更新指定索引的预览图"""
        if index < 0 or index >= 3:
            return
        self._update_note_overlay(index)
        # 盲选模式：图1/图2 位置可能显示对调（图片、文件名、路径以实际显示的数据源为准）
        display_data_index = self._get_blind_display_data_index(index) if index >= 1 else index
        
        # 确定使用哪个图片列表（原始图片或遮罩图片）
        # 对于图1和图2，如果切换模式为True，使用遮罩图片列表
        if index >= 1 and self.show_mask_mode[display_data_index - 1]:
            # 使用遮罩图片
            mask_index = display_data_index - 1  # mask_image_lists的索引（0或1）
            image_list = self.mask_image_lists[mask_index]
            # 如果遮罩列表为空，回退到原始图片列表
            if not image_list:
                image_list = self.image_lists[display_data_index]
        else:
            # 使用原始图片
            image_list = self.image_lists[display_data_index] if index >= 1 else self.image_lists[index]
        
        current_idx = self.current_indices[display_data_index] if index >= 1 else self.current_indices[index]
        
        if not image_list or current_idx < 0 or current_idx >= len(image_list):
            # 没有图片或索引无效
            if not self.folder_paths[index] or not self.image_lists[index]:
                # 未选择文件夹，显示提示文字
                folder_name = self.FOLDER_NAMES[index]
                self.preview_labels[index].config(
                    image='', text=f"打开{folder_name}", cursor="hand2", anchor=tk.CENTER
                )
                self.preview_labels[index].image = None
            else:
                # 已选择文件夹但没有图片或索引无效
                self.preview_labels[index].config(
                    image='', text="暂无图片", cursor="", anchor=tk.CENTER
                )
                self.preview_labels[index].image = None
            # 如果图1或图2在隐藏模式下，显示"该信息已隐藏"
            if self.hide_info_mode and index >= 1:
                self._set_filename_text(index, "该信息已隐藏")
                self.path_status_labels[index].config(text="该信息已隐藏")
            else:
                self._set_filename_text(index, "")
                # 清空路径状态显示
                self._update_path_status(index)
            # 清空选中标志和状态显示（只针对图1文件夹和图2文件夹）
            self._update_selection_display(index)
            return
        
        image_path = image_list[current_idx]
        
        try:
            # 加载图片
            img = Image.open(image_path)
            
            # 获取预览框容器大小（容器高度固定，由父容器决定）
            preview_label = self.preview_labels[index]
            preview_container = preview_label.master
            
            # 等待布局完成，获取容器实际大小
            preview_container.update_idletasks()
            container_width = preview_container.winfo_width()
            container_height = preview_container.winfo_height()
            
            # 如果容器还没有大小，使用默认值
            if container_width <= 1 or container_height <= 1:
                container_width, container_height = 350, 400
            
            # 计算缩放比例，保持宽高比，填充容器
            img_width, img_height = img.size
            scale_w = container_width / img_width
            scale_h = container_height / img_height
            scale = min(scale_w, scale_h)  # 选择较小的缩放比例，确保图片完全显示在容器内
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # 调整图片大小
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 转换为Tkinter可用的格式
            photo = ImageTk.PhotoImage(img_resized)
            
            # 更新预览框
            self.preview_labels[index].config(
                image=photo,
                text="",
                cursor="",
                anchor=self._get_preview_image_anchor(),
            )
            self.preview_labels[index].image = photo  # 保持引用
            
            # 更新文件名显示（含后缀，不含目录）
            filename = image_path.name
            if not self.hide_info_mode or index == 0:  # 原图不受隐藏模式影响
                self._set_filename_text(index, filename)
            else:
                # 图1或图2在隐藏模式下，显示"该信息已隐藏"
                self._set_filename_text(index, "该信息已隐藏")
            
            # 更新选中标志和状态显示（只针对图1文件夹和图2文件夹）
            self._update_selection_display(index)
            
            # 更新路径状态显示
            if not self.hide_info_mode or index == 0:  # 原图不受隐藏模式影响
                self._update_path_status(index)
            else:
                # 图1或图2在隐藏模式下，显示"该信息已隐藏"
                self.path_status_labels[index].config(text="该信息已隐藏")
            
        except Exception as e:
            messagebox.showerror("错误", f"无法加载图片: {image_path}\n{str(e)}")
            self.preview_labels[index].config(
                image='', text="加载失败", anchor=tk.CENTER
            )
            self.preview_labels[index].image = None
            self._set_filename_text(index, image_path.name)
            # 更新选中标志和状态显示（只针对图1文件夹和图2文件夹）
            self._update_selection_display(index)
            # 更新路径状态显示
            self._update_path_status(index)
    
    def _update_all_previews(self):
        """更新所有预览图"""
        for i in range(3):
            self._update_preview(i)
    
    def _on_bg_color_key(self, index):
        """处理数字键1-6切换背景颜色"""
        if 0 <= index < len(self.bg_color_order):
            color_option = self.bg_color_order[index]
            self.bg_color_var.set(color_option)
            self._change_bg_color()
    
    def _change_bg_color(self):
        """更改预览图容器的背景颜色"""
        self.current_bg_color = self.bg_color_var.get()
        bg_color = self.bg_colors[self.current_bg_color]
        note_fg = self._get_contrasting_text_color(bg_color)
        
        # 更新所有预览图的背景颜色
        for preview_label in self.preview_labels:
            preview_label.config(bg=bg_color)
        
        # 更新选中标志的背景颜色（如果存在）
        for i in range(2):
            if self.check_labels[i + 1]:  # 图1和图2的选中标志
                self.check_labels[i + 1].config(bg=bg_color)

        # 备注标签与勾选标志采用相同方式模拟透明背景。
        for note_label in getattr(self, "note_overlay_labels", []):
            if note_label is not None:
                note_label.config(bg=bg_color, fg=note_fg)
        
        # 如果放大镜启用且鼠标在预览图上，刷新放大镜（背景色改变）
        self._refresh_magnifier_if_needed()

    def _get_preview_image_anchor(self):
        """返回当前图片位置对应的 Tk Label 锚点。"""
        return {
            "头部": tk.NW,
            "居中": tk.CENTER,
            "尾部": tk.SE,
        }.get(self.image_position_var.get(), tk.CENTER)

    def _change_image_position(self):
        """更新三个预览框内图片的对齐位置，不重新缩放图片。"""
        anchor = self._get_preview_image_anchor()
        for preview_label in self.preview_labels:
            if getattr(preview_label, "image", None) is not None:
                preview_label.config(anchor=anchor)
            else:
                preview_label.config(anchor=tk.CENTER)
        self._refresh_magnifier_if_needed()

    def _get_preview_image_offsets(
        self,
        preview_width: int,
        preview_height: int,
        display_width: int,
        display_height: int,
    ) -> tuple[int, int]:
        """返回缩放图片在预览框中的偏移，供放大镜坐标换算使用。"""
        free_width = max(0, preview_width - display_width)
        free_height = max(0, preview_height - display_height)
        position = self.image_position_var.get()
        if position == "头部":
            return 0, 0
        if position == "尾部":
            return free_width, free_height
        return free_width // 2, free_height // 2

    @staticmethod
    def _get_contrasting_text_color(bg_color: str) -> str:
        """为十六进制背景色选择对比度更高的黑色或白色文字。"""
        hex_color = bg_color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(channel * 2 for channel in hex_color)
        if len(hex_color) != 6:
            return "#000000"

        try:
            rgb = [int(hex_color[index:index + 2], 16) / 255 for index in (0, 2, 4)]
        except ValueError:
            return "#000000"

        linear_rgb = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in rgb
        ]
        luminance = (
            0.2126 * linear_rgb[0]
            + 0.7152 * linear_rgb[1]
            + 0.0722 * linear_rgb[2]
        )
        contrast_with_black = (luminance + 0.05) / 0.05
        contrast_with_white = 1.05 / (luminance + 0.05)
        return "#000000" if contrast_with_black >= contrast_with_white else "#FFFFFF"

    # ===================== 原图列表窗口（原图缩略图） =====================

    def _toggle_image_list_window(self):
        """菜单：原图列表 开关。"""
        if self.image_list_menu_var.get():
            self._open_image_list_window()
        else:
            self._close_image_list_window()

    def _close_image_list_window(self):
        """关闭原图列表窗口并重置菜单勾选。"""
        if self._image_list_window is not None:
            try:
                self._image_list_window.destroy()
            except Exception:
                pass
        self._image_list_window = None
        self._image_list_canvas = None
        self._image_list_inner = None
        self._image_list_scrollbar = None
        self._image_list_inner_window_id = None
        self._image_list_items = []
        self._image_list_containers = []
        self._image_list_thumb_cache.clear()
        self._image_list_source_key = None
        self._image_list_load_job = None
        self._suppress_image_list_auto_scroll_once = False
        # 解除菜单勾选（避免递归调用时再次进来）
        if self.image_list_menu_var.get():
            self.image_list_menu_var.set(False)

    def _open_image_list_window(self):
        """打开（或刷新）原图列表窗口：显示原图文件夹的缩略图。"""
        # 无原图文件夹或无图片时直接关闭窗口
        if not self.image_lists[0]:
            self._close_image_list_window()
            messagebox.showinfo("原图列表", "请先打开原图文件夹。", parent=self.root)
            try:
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass
            return

        if self._image_list_window is None or not self._image_list_window.winfo_exists():
            win = tk.Toplevel(self.root)
            self._image_list_window = win
            # 标题会在 _refresh_image_list_window 中根据 n/m 统一更新
            win.title("原图列表 0/0")
            win.resizable(True, False)
            # 允许悬浮在主窗口之上
            try:
                win.attributes("-topmost", True)
            except Exception:
                pass
            # 默认宽度与主窗口一致，并与主窗口左上角对齐
            try:
                self.root.update_idletasks()
                main_w = max(200, int(self.root.winfo_width()))
                main_x = int(self.root.winfo_x())
                main_y = int(self.root.winfo_y())
                win.geometry(f"{main_w}x{self._image_list_thumb_size + 60}+{main_x}+{main_y}")
            except Exception:
                pass
            # 关闭窗口时同步取消菜单勾选
            def on_close() -> None:
                self._close_image_list_window()
            win.protocol("WM_DELETE_WINDOW", on_close)

            container = tk.Frame(win)
            container.pack(fill=tk.BOTH, expand=True)

            # 预览框高度约为缩略图边长（100）再加上一些上下内边距
            canvas = tk.Canvas(container, height=self._image_list_thumb_size + 40, highlightthickness=0)
            hbar = tk.Scrollbar(container, orient="horizontal", command=canvas.xview)
            canvas.configure(xscrollcommand=hbar.set)

            canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            hbar.pack(side=tk.BOTTOM, fill=tk.X)

            inner = tk.Frame(canvas)
            self._image_list_canvas = canvas
            self._image_list_inner = inner
            self._image_list_scrollbar = hbar
            self._image_list_items = []
            self._image_list_containers = []
            self._image_list_thumb_cache.clear()

            self._image_list_inner_window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_config(_event: tk.Event) -> None:
                canvas.configure(scrollregion=canvas.bbox("all"))

            inner.bind("<Configure>", _on_config)

            # 在整个图片列表窗口范围内支持滚轮/触控板滚动（水平滚动）
            def _in_this_window(evt: tk.Event) -> bool:
                try:
                    w = evt.widget
                    return bool(w) and w.winfo_toplevel() == win
                except Exception:
                    return False

            def _scroll_h(delta_units: int) -> None:
                try:
                    canvas.xview_scroll(delta_units, "units")
                except Exception:
                    pass

            def _on_mousewheel(evt: tk.Event) -> str:
                if not _in_this_window(evt):
                    return ""
                # Windows: delta = ±120; macOS: delta 通常较小
                d = getattr(evt, "delta", 0) or 0
                if d == 0:
                    return "break"
                units = -1 if d > 0 else 1
                # 加速一点：大滚动按比例多走几格（避免触控板太慢）
                steps = max(1, int(abs(d) / 120)) if abs(d) >= 120 else 1
                _scroll_h(units * steps)
                return "break"

            def _on_linux_wheel(evt: tk.Event) -> str:
                if not _in_this_window(evt):
                    return ""
                # Button-4 上滚，Button-5 下滚
                num = getattr(evt, "num", 0)
                if num == 4:
                    _scroll_h(-1)
                elif num == 5:
                    _scroll_h(1)
                return "break"

            # 绑定到整个应用，但只在事件发生于该窗口时生效
            system = platform.system()
            if system == "Linux":
                self.root.bind_all("<Button-4>", _on_linux_wheel, add="+")
                self.root.bind_all("<Button-5>", _on_linux_wheel, add="+")
            else:
                self.root.bind_all("<MouseWheel>", _on_mousewheel, add="+")

        # 标记菜单勾选为打开状态
        if not self.image_list_menu_var.get():
            self.image_list_menu_var.set(True)

        # 刷新/重建列表内容
        self._refresh_image_list_window()

    def _refresh_image_list_window(self):
        """根据当前原图文件夹和索引刷新原图列表窗口内容与高亮，并更新标题「原图列表 n/m」。"""
        if self._image_list_window is None or not self._image_list_window.winfo_exists():
            return
        if not self.image_lists[0]:
            self._close_image_list_window()
            return

        indices = self._get_original_list_indices()
        if not indices:
            self._close_image_list_window()
            return

        folder_path = self.folder_paths[0] or ""
        key = (str(folder_path), tuple(indices), self.filter_mode)

        # 更新窗口标题：原图列表 n/m（受过滤模式控制）
        total = len(indices)
        if self.filter_mode != "所有" and self.filtered_indices:
            cur_pos = max(0, min(self.current_filtered_index, total - 1))
        else:
            try:
                cur_pos = indices.index(self.current_indices[0])
            except ValueError:
                cur_pos = 0
        current = cur_pos + 1 if total > 0 else 0
        try:
            self._image_list_window.title(f"原图列表 {current}/{total}")
        except Exception:
            pass

        # 判断是否需要重建所有缩略图（文件夹或数量/过滤变化）
        need_rebuild = key != self._image_list_source_key

        if need_rebuild:
            inner = self._image_list_inner
            if inner is None:
                return

            # 清理旧内容（包括每个 item_frame 以及其子控件），避免留下空预览框
            for child in list(inner.winfo_children()):
                try:
                    child.destroy()
                except Exception:
                    pass
            self._image_list_items = []
            self._image_list_containers = []
            self._image_list_thumb_cache.clear()
            self._image_list_source_key = key

            # 每张图片一个垂直小单元：上方缩略图（固定约 80x80），下方序号
            for idx, img_idx in enumerate(indices):
                if img_idx < 0 or img_idx >= len(self.image_lists[0]):
                    continue
                image_path = self.image_lists[0][img_idx]
                item_frame = tk.Frame(inner, padx=0, pady=4)
                item_frame.grid(row=0, column=idx, sticky="n")

                # 固定大小的缩略图容器，防止布局后高度被压缩
                thumb_container = tk.Frame(
                    item_frame,
                    width=self._image_list_thumb_size,
                    height=self._image_list_thumb_size,
                    bg="#dddddd",
                    bd=0,
                    highlightthickness=0,
                    highlightbackground="#dddddd",
                    highlightcolor="#dddddd",
                )
                thumb_container.pack(side=tk.TOP)
                thumb_container.pack_propagate(False)  # 内部控件不影响容器尺寸

                thumb_label = tk.Label(thumb_container, text=str(idx + 1), bg="#dddddd")
                thumb_label.pack(expand=True)

                index_label = tk.Label(
                    item_frame,
                    text=str(idx + 1),
                    font=("Arial", 8),
                )
                index_label.pack(side=tk.TOP, pady=(2, 0))

                # 点击：跳转主窗口到该图片序号
                def _on_click(_e, k=idx + 1) -> None:
                    self._jump_to_image_via_list(k)

                # 点击容器边框/空白也可选中
                thumb_container.bind("<Button-1>", _on_click)
                thumb_label.bind("<Button-1>", _on_click)
                index_label.bind("<Button-1>", _on_click)
                self._image_list_items.append(thumb_label)
                self._image_list_containers.append(thumb_container)

            # 让 Canvas 更新 scrollregion
            if self._image_list_canvas is not None:
                self._image_list_canvas.update_idletasks()
                self._image_list_canvas.configure(scrollregion=self._image_list_canvas.bbox("all"))

            # 启动缩略图延迟加载
            self._schedule_image_list_thumbnails()

        # 更新高亮和滚动到当前图片
        self._highlight_current_in_image_list()

    def _schedule_image_list_thumbnails(self):
        """分批加载缩略图，避免一次性阻塞 UI。"""
        if self._image_list_canvas is None or not self.image_lists[0]:
            return

        # 取消上一次任务
        if self._image_list_load_job is not None:
            try:
                self.root.after_cancel(self._image_list_load_job)
            except Exception:
                pass
            self._image_list_load_job = None

        def _load_batch(start: int = 0) -> None:
            batch_size = 10  # 每批加载10张，刚好覆盖“最多同时显示10张”的宽度需求
            indices = self._get_original_list_indices()
            end = min(len(indices), start + batch_size)
            size = self._image_list_thumb_size
            for idx in range(start, end):
                if idx in self._image_list_thumb_cache:
                    continue
                if idx >= len(self._image_list_items):
                    break
                try:
                    img_idx = indices[idx]
                    if img_idx < 0 or img_idx >= len(self.image_lists[0]):
                        continue
                    img_path = self.image_lists[0][img_idx]
                    img = Image.open(img_path)
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._image_list_thumb_cache[idx] = photo
                    self._image_list_items[idx].config(image=photo, text="")
                except Exception:
                    # 加载失败则保持文字占位
                    pass

            if end < len(indices):
                self._image_list_load_job = self.root.after(50, lambda: _load_batch(end))
            else:
                self._image_list_load_job = None

        self._image_list_load_job = self.root.after(0, lambda: _load_batch(0))

    def _highlight_current_in_image_list(self):
        """根据 current_indices[0] 在原图列表中高亮当前原图，并自动滚动到可见位置。"""
        if not self.image_lists[0]:
            return
        if not self._image_list_items:
            return
        indices = self._get_original_list_indices()
        if not indices:
            return
        # 当前高亮位置：过滤模式下用 current_filtered_index，否则在 indices 中查找 current_indices[0]
        if self.filter_mode != "所有" and self.filtered_indices:
            cur = max(0, min(self.current_filtered_index, len(indices) - 1))
        else:
            try:
                cur = indices.index(self.current_indices[0])
            except ValueError:
                cur = 0
        cur = max(0, min(cur, len(self._image_list_items) - 1))

        # 同步更新窗口标题中的 n/m（不重建列表）
        if self._image_list_window is not None and self._image_list_window.winfo_exists():
            total = len(indices)
            current = cur + 1 if total > 0 else 0
            try:
                self._image_list_window.title(f"原图列表 {current}/{total}")
            except Exception:
                pass

        # 高亮：背景不变，使用边框深蓝色提示当前项
        for idx, lbl in enumerate(self._image_list_items):
            if idx < len(self._image_list_containers):
                cont = self._image_list_containers[idx]
                if idx == cur:
                    cont.config(highlightthickness=4, highlightbackground="#0044aa", highlightcolor="#0044aa")
                else:
                    cont.config(highlightthickness=1, highlightbackground="#cccccc", highlightcolor="#cccccc")
            # 图片/文本区域背景保持灰色
            lbl.config(bg="#dddddd")

        # 若本次高亮是由图片列表自身点击触发，则不做任何滚动，只更新高亮一次
        if getattr(self, "_suppress_image_list_auto_scroll_once", False):
            self._suppress_image_list_auto_scroll_once = False
            return

        # 水平滚动：仅当当前项不在图片列表窗口的可视范围内时才滚动（避免“跳动”）
        canvas = self._image_list_canvas
        if canvas is None or canvas.winfo_width() <= 0 or not self._image_list_items:
            return

        try:
            canvas.update_idletasks()
        except Exception:
            pass

        n = len(self._image_list_items)
        unit_w = max(1, int(self._image_list_thumb_size))  # 单个缩略图大致宽度（80）
        total_w = unit_w * n
        view_w = float(max(1, canvas.winfo_width()))

        # 当前位置的可视起始索引和可视容量（按缩略图个数估算）
        try:
            left_frac = float(canvas.xview()[0])
        except Exception:
            left_frac = 0.0
        left_pixel = left_frac * total_w
        left_index = int(left_pixel / unit_w)
        visible_count = max(1, int(view_w / unit_w))
        right_index = left_index + visible_count - 1

        # 当前项在可视范围内：不滚动
        if left_index <= cur <= right_index:
            return

        # 不在可视范围：最小幅度滚动，使当前项刚好进入可视区
        if cur < left_index:
            new_left_index = cur
        else:  # cur > right_index
            new_left_index = cur - visible_count + 1

        # Clamp 到合法范围
        max_left_index = max(0, n - visible_count)
        new_left_index = max(0, min(new_left_index, max_left_index))

        new_left_pixel = new_left_index * unit_w
        new_frac = new_left_pixel / float(max(1, total_w))
        new_frac = min(1.0, max(0.0, new_frac))
        canvas.xview_moveto(new_frac)

    def _jump_to_image_via_list(self, index1_based: int) -> None:
        """由原图列表窗口点击触发的跳转：index1_based 为 1 基序号（受过滤控制）。"""
        if not self.image_lists[0]:
            return

        indices = self._get_original_list_indices()
        if not indices:
            return
        if index1_based < 1 or index1_based > len(indices):
            return

        # 可见列表中的位置 -> 全量原图索引
        target_global_index = indices[index1_based - 1]

        # 更新所有已加载文件夹的索引
        for i in range(3):
            image_list = self.image_lists[i]
            if image_list:
                if target_global_index < len(image_list):
                    self.current_indices[i] = target_global_index
                else:
                    self.current_indices[i] = len(image_list) - 1

        # 过滤模式下同步更新 current_filtered_index
        if self.filter_mode != "所有" and self.filtered_indices:
            self.current_filtered_index = index1_based - 1

        self._update_all_previews()

        if self.hide_info_mode:
            for idx in [1, 2]:
                if self.image_lists[idx]:
                    self._update_info_visibility(idx)

        self._refresh_magnifier_if_needed()
        # 由列表点击触发：只高亮，不自动滚动（点击点必然可见）
        self._suppress_image_list_auto_scroll_once = True
        self._highlight_current_in_image_list()
    
    def _get_image_size(self, image_path):
        """获取图片尺寸"""
        try:
            img = Image.open(image_path)
            return img.size  # 返回 (width, height)
        except Exception:
            return None
    
    def _refresh_magnifier_if_needed(self):
        """如果放大镜启用且鼠标在预览图上，刷新放大镜"""
        if not self.magnifier_enabled:
            return
        
        if self.current_mouse_preview is None:
            return
        
        # 获取当前鼠标位置
        try:
            mouse_x_root = self.root.winfo_pointerx()
            mouse_y_root = self.root.winfo_pointery()
            
            # 检查鼠标是否在预览图上
            index = self.current_mouse_preview
            preview_label = self.preview_labels[index]
            
            # 获取预览图在屏幕上的位置
            preview_x_root = preview_label.winfo_rootx()
            preview_y_root = preview_label.winfo_rooty()
            preview_width = preview_label.winfo_width()
            preview_height = preview_label.winfo_height()
            
            # 检查鼠标是否在预览图范围内
            if (preview_x_root <= mouse_x_root <= preview_x_root + preview_width and
                preview_y_root <= mouse_y_root <= preview_y_root + preview_height):
                
                # 计算鼠标在预览图上的相对坐标
                preview_x = mouse_x_root - preview_x_root
                preview_y = mouse_y_root - preview_y_root
                
                # 获取当前显示的图像
                image_list = self.image_lists[index]
                if index >= 1 and self.show_mask_mode[index - 1]:
                    mask_index = index - 1
                    if self.mask_image_lists[mask_index]:
                        image_list = self.mask_image_lists[mask_index]
                
                if image_list and self.current_indices[index] < len(image_list):
                    current_image_path = image_list[self.current_indices[index]]
                    
                    try:
                        img = Image.open(current_image_path)
                        img_width, img_height = img.size
                        
                        # 计算预览图的缩放比例
                        scale_x = preview_width / img_width
                        scale_y = preview_height / img_height
                        scale = min(scale_x, scale_y)
                        
                        # 计算实际显示的图像尺寸
                        display_width = int(img_width * scale)
                        display_height = int(img_height * scale)
                        
                        # 计算图像按当前位置设置显示时的偏移
                        offset_x, offset_y = self._get_preview_image_offsets(
                            preview_width,
                            preview_height,
                            display_width,
                            display_height,
                        )
                        
                        # 将鼠标坐标转换为图像坐标
                        if (offset_x <= preview_x <= offset_x + display_width and
                            offset_y <= preview_y <= offset_y + display_height):
                            
                            img_x = int((preview_x - offset_x) / scale)
                            img_y = int((preview_y - offset_y) / scale)
                            
                            # 确保坐标在图像范围内
                            img_x = max(0, min(img_width - 1, img_x))
                            img_y = max(0, min(img_height - 1, img_y))
                            
                            # 立即更新放大镜位置和图像
                            self._update_magnifier_positions(index, mouse_x_root, mouse_y_root, preview_label)
                            self._schedule_magnifier_update(index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label)
                    except Exception:
                        pass
        except Exception:
            pass
    
    def _toggle_magnifier(self):
        """切换放大镜功能"""
        self.magnifier_enabled = self.magnifier_menu_var.get()
        if not self.magnifier_enabled:
            # 隐藏所有放大镜
            for magnifier_label in self.magnifier_labels:
                magnifier_label.place_forget()
            self.current_mouse_preview = None
            # 取消待处理的更新
            if self.magnifier_update_id:
                self.root.after_cancel(self.magnifier_update_id)
                self.magnifier_update_id = None
        else:
            # 如果启用放大镜，检查鼠标是否在任何预览图上
            try:
                mouse_x_root = self.root.winfo_pointerx()
                mouse_y_root = self.root.winfo_pointery()
                
                # 检查鼠标是否在任何一个预览图上
                for index in range(3):
                    preview_label = self.preview_labels[index]
                    
                    # 获取预览图在屏幕上的位置
                    preview_x_root = preview_label.winfo_rootx()
                    preview_y_root = preview_label.winfo_rooty()
                    preview_width = preview_label.winfo_width()
                    preview_height = preview_label.winfo_height()
                    
                    # 检查鼠标是否在预览图范围内
                    if (preview_width > 1 and preview_height > 1 and
                        preview_x_root <= mouse_x_root <= preview_x_root + preview_width and
                        preview_y_root <= mouse_y_root <= preview_y_root + preview_height):
                        
                        # 设置当前鼠标所在的预览图索引
                        self.current_mouse_preview = index
                        
                        # 计算鼠标在预览图上的相对坐标
                        preview_x = mouse_x_root - preview_x_root
                        preview_y = mouse_y_root - preview_y_root
                        
                        # 获取当前显示的图像
                        image_list = self.image_lists[index]
                        if index >= 1 and self.show_mask_mode[index - 1]:
                            mask_index = index - 1
                            if self.mask_image_lists[mask_index]:
                                image_list = self.mask_image_lists[mask_index]
                        
                        if image_list and self.current_indices[index] < len(image_list):
                            current_image_path = image_list[self.current_indices[index]]
                            
                            try:
                                img = Image.open(current_image_path)
                                img_width, img_height = img.size
                                
                                # 计算预览图的缩放比例
                                scale_x = preview_width / img_width
                                scale_y = preview_height / img_height
                                scale = min(scale_x, scale_y)
                                
                                # 计算实际显示的图像尺寸
                                display_width = int(img_width * scale)
                                display_height = int(img_height * scale)
                                
                                # 计算图像按当前位置设置显示时的偏移
                                offset_x, offset_y = self._get_preview_image_offsets(
                                    preview_width,
                                    preview_height,
                                    display_width,
                                    display_height,
                                )
                                
                                # 将鼠标坐标转换为图像坐标
                                if (offset_x <= preview_x <= offset_x + display_width and
                                    offset_y <= preview_y <= offset_y + display_height):
                                    
                                    img_x = int((preview_x - offset_x) / scale)
                                    img_y = int((preview_y - offset_y) / scale)
                                    
                                    # 确保坐标在图像范围内
                                    img_x = max(0, min(img_width - 1, img_x))
                                    img_y = max(0, min(img_height - 1, img_y))
                                    
                                    # 立即更新放大镜位置和图像
                                    self._update_magnifier_positions(index, mouse_x_root, mouse_y_root, preview_label)
                                    self._schedule_magnifier_update(index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label)
                                    break  # 找到鼠标所在的预览图，退出循环
                            except Exception:
                                pass
            except Exception:
                pass
    
    def _on_preview_mouse_move(self, event, index):
        """处理预览图上的鼠标移动事件"""
        if not self.magnifier_enabled:
            return
        
        self.current_mouse_preview = index
        
        # 获取鼠标在预览图上的相对坐标
        preview_label = self.preview_labels[index]
        preview_x = event.x
        preview_y = event.y
        
        # 获取预览图的尺寸
        preview_width = preview_label.winfo_width()
        preview_height = preview_label.winfo_height()
        
        if preview_width <= 1 or preview_height <= 1:
            return  # 预览图还未渲染完成
        
        # 获取当前显示的图像
        image_list = self.image_lists[index]
        if index >= 1 and self.show_mask_mode[index - 1]:
            mask_index = index - 1
            if self.mask_image_lists[mask_index]:
                image_list = self.mask_image_lists[mask_index]
        
        if not image_list or self.current_indices[index] >= len(image_list):
            return
        
        current_image_path = image_list[self.current_indices[index]]
        
        # 计算图像坐标（考虑图像缩放）
        try:
            img = Image.open(current_image_path)
            img_width, img_height = img.size
            
            # 计算预览图的缩放比例
            scale_x = preview_width / img_width
            scale_y = preview_height / img_height
            scale = min(scale_x, scale_y)  # 保持宽高比
            
            # 计算实际显示的图像尺寸
            display_width = int(img_width * scale)
            display_height = int(img_height * scale)
            
            # 计算图像按当前位置设置显示时的偏移
            offset_x, offset_y = self._get_preview_image_offsets(
                preview_width,
                preview_height,
                display_width,
                display_height,
            )
            
            # 将鼠标坐标转换为图像坐标
            if preview_x < offset_x or preview_x > offset_x + display_width:
                return
            if preview_y < offset_y or preview_y > offset_y + display_height:
                return
            
            img_x = int((preview_x - offset_x) / scale)
            img_y = int((preview_y - offset_y) / scale)
            
            # 确保坐标在图像范围内
            img_x = max(0, min(img_width - 1, img_x))
            img_y = max(0, min(img_height - 1, img_y))
            
            # 立即更新放大镜位置（提升跟手性），延迟更新图像内容
            self._update_magnifier_positions(index, event.x_root, event.y_root, preview_label)
            # 延迟更新放大镜图像内容（优化性能）
            self._schedule_magnifier_update(index, img_x, img_y, event.x_root, event.y_root, preview_label)
            
        except Exception as e:
            pass
    
    def _on_preview_mouse_leave(self, event, index):
        """处理鼠标离开预览图事件"""
        if not self.magnifier_enabled:
            return
        
        # 取消待处理的放大镜更新
        if self.magnifier_update_id:
            self.root.after_cancel(self.magnifier_update_id)
            self.magnifier_update_id = None
        
        # 检查鼠标是否移动到其他预览图上
        widget_under = event.widget.winfo_containing(event.x_root, event.y_root)
        
        # 如果鼠标移动到其他预览图或放大镜上，不隐藏
        is_on_preview = False
        is_on_magnifier = False
        
        for i, preview_label in enumerate(self.preview_labels):
            if widget_under == preview_label:
                is_on_preview = True
                break

        for magnifier_label in self.magnifier_labels:
            if widget_under == magnifier_label:
                is_on_magnifier = True
                break
        
        # 如果鼠标不在任何预览图或放大镜上，隐藏所有放大镜
        if not is_on_preview and not is_on_magnifier:
            for magnifier_label in self.magnifier_labels:
                magnifier_label.place_forget()
            self.current_mouse_preview = None
    
    def _update_magnifier_positions(self, main_index, mouse_x_root, mouse_y_root, main_preview_label):
        """立即更新放大镜位置（提升跟手性，智能选择位置避免遮挡）"""
        # 计算主镜位置（鼠标附近）
        main_preview_x = main_preview_label.winfo_rootx()
        main_preview_y = main_preview_label.winfo_rooty()
        
        # 计算鼠标在预览图中的相对坐标
        mouse_x_in_preview = mouse_x_root - main_preview_x
        mouse_y_in_preview = mouse_y_root - main_preview_y
        
        main_preview_width = main_preview_label.winfo_width()
        main_preview_height = main_preview_label.winfo_height()
        
        if main_preview_width <= 1 or main_preview_height <= 1:
            return
        
        # 智能选择放大镜位置，避免遮挡原图
        offset = 20  # 基础偏移量
        margin = 10  # 边界边距
        
        # 判断鼠标是否靠近右边界
        near_right = mouse_x_in_preview > main_preview_width - self.magnifier_size - margin
        # 判断鼠标是否靠近下边界
        near_bottom = mouse_y_in_preview > main_preview_height - self.magnifier_size - margin
        # 判断鼠标是否靠近左边界
        near_left = mouse_x_in_preview < self.magnifier_size + margin
        # 判断鼠标是否靠近上边界
        near_top = mouse_y_in_preview < self.magnifier_size + margin
        
        # 根据鼠标位置选择放大镜位置
        if near_right:
            # 鼠标靠近右边界，放大镜放在左侧
            main_magnifier_x = mouse_x_in_preview - self.magnifier_size - offset
        elif near_left:
            # 鼠标靠近左边界，放大镜放在右侧
            main_magnifier_x = mouse_x_in_preview + offset
        else:
            # 默认放在右侧
            main_magnifier_x = mouse_x_in_preview + offset
        
        if near_bottom:
            # 鼠标靠近下边界，放大镜放在上方
            main_magnifier_y = mouse_y_in_preview - self.magnifier_size - offset
        elif near_top:
            # 鼠标靠近上边界，放大镜放在下方
            main_magnifier_y = mouse_y_in_preview + offset
        else:
            # 默认放在下方
            main_magnifier_y = mouse_y_in_preview + offset
        
        # 更新三个放大镜的位置
        for i in range(3):
            magnifier_label = self.magnifier_labels[i]
            preview_label = self.preview_labels[i]
            
            if not self.image_lists[i] or self.current_indices[i] >= len(self.image_lists[i]):
                continue
            
            preview_width = preview_label.winfo_width()
            preview_height = preview_label.winfo_height()
            
            if preview_width <= 1 or preview_height <= 1:
                continue
            
            if i == main_index:
                # 主镜：使用计算好的位置
                magnifier_x = main_magnifier_x
                magnifier_y = main_magnifier_y
            else:
                # 从镜：同步主镜的相对位置
                if main_preview_width > 0 and main_preview_height > 0:
                    main_rel_x = main_magnifier_x / main_preview_width
                    main_rel_y = main_magnifier_y / main_preview_height
                else:
                    main_rel_x = 0.5
                    main_rel_y = 0.5
                
                # 计算从镜的鼠标相对位置
                mouse_rel_x = mouse_x_in_preview / main_preview_width
                mouse_rel_y = mouse_y_in_preview / main_preview_height
                
                # 在从镜中应用相同的智能位置选择逻辑
                mouse_x_in_other = mouse_rel_x * preview_width
                mouse_y_in_other = mouse_rel_y * preview_height
                
                # 判断从镜中鼠标是否靠近边界
                near_right_other = mouse_x_in_other > preview_width - self.magnifier_size - margin
                near_bottom_other = mouse_y_in_other > preview_height - self.magnifier_size - margin
                near_left_other = mouse_x_in_other < self.magnifier_size + margin
                near_top_other = mouse_y_in_other < self.magnifier_size + margin
                
                if near_right_other:
                    magnifier_x = mouse_x_in_other - self.magnifier_size - offset
                elif near_left_other:
                    magnifier_x = mouse_x_in_other + offset
                else:
                    magnifier_x = mouse_x_in_other + offset
                
                if near_bottom_other:
                    magnifier_y = mouse_y_in_other - self.magnifier_size - offset
                elif near_top_other:
                    magnifier_y = mouse_y_in_other + offset
                else:
                    magnifier_y = mouse_y_in_other + offset
            
            # 确保放大镜不超出预览图边界
            magnifier_x = max(0, min(preview_width - self.magnifier_size, magnifier_x))
            magnifier_y = max(0, min(preview_height - self.magnifier_size, magnifier_y))
            
            # 立即更新位置（如果放大镜已显示）
            if magnifier_label.winfo_viewable():
                magnifier_label.place(x=int(magnifier_x), y=int(magnifier_y))
    
    def _schedule_magnifier_update(self, index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label):
        """调度放大镜图像内容更新（延迟更新以优化性能）"""
        # 保存最新的更新参数
        self._pending_magnifier_update = (index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label)
        
        # 如果已有待处理的更新，取消它
        if self.magnifier_update_id:
            self.root.after_cancel(self.magnifier_update_id)
        
        # 延迟8ms更新图像内容（约120fps，提升跟手性）
        self.magnifier_update_id = self.root.after(8, self._execute_magnifier_update)
    
    def _execute_magnifier_update(self):
        """执行放大镜更新"""
        if hasattr(self, '_pending_magnifier_update'):
            index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label = self._pending_magnifier_update
            self._update_magnifiers(index, img_x, img_y, mouse_x_root, mouse_y_root, preview_label)
            self.magnifier_update_id = None
    
    def _update_magnifiers(self, main_index, img_x, img_y, mouse_x_root, mouse_y_root, main_preview_label):
        """更新所有放大镜显示"""
        # 计算主镜位置（使用智能位置选择，避免遮挡）
        main_preview_x = main_preview_label.winfo_rootx()
        main_preview_y = main_preview_label.winfo_rooty()
        
        # 计算鼠标在预览图中的相对坐标
        mouse_x_in_preview = mouse_x_root - main_preview_x
        mouse_y_in_preview = mouse_y_root - main_preview_y
        
        main_preview_width = main_preview_label.winfo_width()
        main_preview_height = main_preview_label.winfo_height()
        
        if main_preview_width <= 1 or main_preview_height <= 1:
            return
        
        # 智能选择放大镜位置，避免遮挡原图
        offset = 20  # 基础偏移量
        margin = 10  # 边界边距
        
        # 判断鼠标是否靠近边界
        near_right = mouse_x_in_preview > main_preview_width - self.magnifier_size - margin
        near_bottom = mouse_y_in_preview > main_preview_height - self.magnifier_size - margin
        near_left = mouse_x_in_preview < self.magnifier_size + margin
        near_top = mouse_y_in_preview < self.magnifier_size + margin
        
        # 根据鼠标位置选择放大镜位置
        if near_right:
            main_magnifier_x = mouse_x_in_preview - self.magnifier_size - offset
        elif near_left:
            main_magnifier_x = mouse_x_in_preview + offset
        else:
            main_magnifier_x = mouse_x_in_preview + offset
        
        if near_bottom:
            main_magnifier_y = mouse_y_in_preview - self.magnifier_size - offset
        elif near_top:
            main_magnifier_y = mouse_y_in_preview + offset
        else:
            main_magnifier_y = mouse_y_in_preview + offset
        
        # 更新三个放大镜（盲选时图1/图2使用实际显示的数据源）
        for i in range(3):
            magnifier_label = self.magnifier_labels[i]
            preview_label = self.preview_labels[i]
            display_i = self._get_blind_display_data_index(i) if i >= 1 else i
            
            # 获取当前显示的图像
            image_list = self.image_lists[display_i]
            if i >= 1 and self.show_mask_mode[display_i - 1]:
                mask_index = display_i - 1
                if self.mask_image_lists[mask_index]:
                    image_list = self.mask_image_lists[mask_index]
            
            if not image_list or self.current_indices[display_i] >= len(image_list):
                magnifier_label.place_forget()
                continue
            
            try:
                current_image_path = image_list[self.current_indices[display_i]]
                img = Image.open(current_image_path)
                img_width, img_height = img.size
                
                # 计算裁剪区域（以img_x, img_y为中心）
                crop_size = self.magnifier_size // self.magnifier_zoom
                left = max(0, img_x - crop_size // 2)
                top = max(0, img_y - crop_size // 2)
                right = min(img_width, left + crop_size)
                bottom = min(img_height, top + crop_size)
                
                # 调整边界
                if right - left < crop_size:
                    left = max(0, right - crop_size)
                if bottom - top < crop_size:
                    top = max(0, bottom - crop_size)
                
                # 裁剪图像
                cropped = img.crop((left, top, right, bottom))
                
                # 放大图像
                magnified = cropped.resize((self.magnifier_size, self.magnifier_size), Image.Resampling.LANCZOS)
                
                # 创建背景色图像（使用当前选择的背景颜色）
                bg_color_hex = self.bg_colors[self.current_bg_color]
                # 将十六进制颜色转换为RGB
                bg_color_rgb = tuple(int(bg_color_hex[j:j+2], 16) for j in (1, 3, 5))
                # 创建背景色图像
                bg_image = Image.new('RGB', (self.magnifier_size, self.magnifier_size), bg_color_rgb)
                
                # 将放大后的图像叠加在背景色图像上
                # 如果放大后的图像有透明通道，使用alpha_composite；否则直接paste
                if magnified.mode == 'RGBA':
                    bg_image = bg_image.convert('RGBA')
                    final_image = Image.alpha_composite(bg_image, magnified)
                else:
                    # 如果图像没有透明通道，直接paste（假设图像是RGB模式）
                    if magnified.mode != 'RGB':
                        magnified = magnified.convert('RGB')
                    bg_image.paste(magnified, (0, 0))
                    final_image = bg_image
                
                # 在合成图像上绘制黄色十字准星
                from PIL import ImageDraw
                draw = ImageDraw.Draw(final_image)
                center_x = self.magnifier_size // 2
                center_y = self.magnifier_size // 2
                # 绘制垂直线（黄色）
                draw.line([(center_x, 0), (center_x, self.magnifier_size)], fill="#FFFF00", width=1)
                # 绘制水平线（黄色）
                draw.line([(0, center_y), (self.magnifier_size, center_y)], fill="#FFFF00", width=1)
                
                # 转换为PhotoImage
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(final_image)
                magnifier_label.config(image=photo)
                magnifier_label.image = photo  # 保持引用
                
                # 计算放大镜位置
                preview_width = preview_label.winfo_width()
                preview_height = preview_label.winfo_height()
                
                if i == main_index:
                    # 主镜：使用计算好的位置
                    magnifier_x = main_magnifier_x
                    magnifier_y = main_magnifier_y
                else:
                    # 从镜：同步主镜的相对位置，并应用智能位置选择
                    # 计算从镜中鼠标的相对位置
                    if main_preview_width > 0 and main_preview_height > 0:
                        mouse_rel_x = mouse_x_in_preview / main_preview_width
                        mouse_rel_y = mouse_y_in_preview / main_preview_height
                    else:
                        mouse_rel_x = 0.5
                        mouse_rel_y = 0.5
                    
                    # 在从镜中计算鼠标位置
                    mouse_x_in_other = mouse_rel_x * preview_width
                    mouse_y_in_other = mouse_rel_y * preview_height
                    
                    # 判断从镜中鼠标是否靠近边界
                    near_right_other = mouse_x_in_other > preview_width - self.magnifier_size - margin
                    near_bottom_other = mouse_y_in_other > preview_height - self.magnifier_size - margin
                    near_left_other = mouse_x_in_other < self.magnifier_size + margin
                    near_top_other = mouse_y_in_other < self.magnifier_size + margin
                    
                    # 根据鼠标位置选择从镜位置
                    if near_right_other:
                        magnifier_x = mouse_x_in_other - self.magnifier_size - offset
                    elif near_left_other:
                        magnifier_x = mouse_x_in_other + offset
                    else:
                        magnifier_x = mouse_x_in_other + offset
                    
                    if near_bottom_other:
                        magnifier_y = mouse_y_in_other - self.magnifier_size - offset
                    elif near_top_other:
                        magnifier_y = mouse_y_in_other + offset
                    else:
                        magnifier_y = mouse_y_in_other + offset
                
                # 确保放大镜不超出预览图边界
                magnifier_x = max(0, min(preview_width - self.magnifier_size, magnifier_x))
                magnifier_y = max(0, min(preview_height - self.magnifier_size, magnifier_y))
                
                # 显示放大镜
                magnifier_label.place(x=int(magnifier_x), y=int(magnifier_y))
                
            except Exception as e:
                magnifier_label.place_forget()
    
    def _on_preview_click(self, index):
        """单击预览图时，如果未选择文件夹，则打开文件夹选择对话框"""
        # 检查是否已选择文件夹
        if not self.folder_paths[index] or not self.image_lists[index]:
            # 未选择文件夹，打开文件夹选择对话框
            self._select_folder(index)
        # 如果已选择文件夹，单击不做任何操作（双击会打开文件）

    def _bind_preview_context_menu(self, widget, menu, index: int) -> None:
        """为预览区域控件绑定跨平台右键菜单事件。"""
        sequences = ["<Button-3>"]
        if platform.system() == "Darwin":
            sequences.extend(("<Button-2>", "<Control-Button-1>"))
        for sequence in sequences:
            widget.bind(
                sequence,
                lambda event, context_menu=menu, idx=index: self._show_preview_context_menu(
                    event, context_menu, idx
                ),
                add="+",
            )

    def _populate_preview_context_menu(self, menu, index: int) -> None:
        """根据对应图片文件夹是否已打开，动态生成右键菜单。"""
        menu.delete(0, tk.END)
        if not self.folder_paths[index]:
            menu.add_command(
                label=f"打开{self.FOLDER_NAMES[index]}",
                command=lambda idx=index: self._select_folder(idx),
            )
            return

        menu.add_command(
            label="打开",
            command=lambda idx=index: self._open_image_file(idx),
        )
        menu.add_command(
            label="打开方式",
            command=lambda idx=index: self._open_image_with(idx),
        )
        menu.add_command(
            label="拷贝",
            command=lambda idx=index: self._copy_image_file(idx),
        )
        menu.add_command(
            label="拷贝路径",
            command=lambda idx=index: self._copy_image_path(idx),
        )

    def _show_preview_context_menu(self, event, menu, index: int):
        """在鼠标位置显示图片预览区域的右键菜单。"""
        self._populate_preview_context_menu(menu, index)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _get_displayed_image_path(self, index):
        """返回指定预览栏当前实际显示的图片路径（含盲选与遮罩）。"""
        if index < 0 or index >= 3:
            return None

        display_index = self._get_blind_display_data_index(index) if index >= 1 else index
        image_list = self.image_lists[display_index]
        if not image_list:
            return None

        current_index = self.current_indices[display_index]
        if current_index < 0:
            return None

        if index >= 1 and self.show_mask_mode[display_index - 1]:
            mask_list = self.mask_image_lists[display_index - 1]
            if current_index < len(mask_list):
                return Path(mask_list[current_index])

        if current_index < len(image_list):
            return Path(image_list[current_index])
        return None

    def _open_image_file(self, index):
        """双击预览图时，使用系统默认应用打开原文件（盲选时打开当前该位置实际显示的文件）"""
        file_path = self._get_displayed_image_path(index)
        if file_path is None:
            return
        
        # 使用系统默认应用打开文件
        try:
            file_path_str = str(file_path.absolute())
            system = platform.system()
            
            if system == "Windows":
                os.startfile(file_path_str)
            elif system == "Darwin":  # macOS
                subprocess.run(["open", file_path_str])
            else:  # Linux
                subprocess.run(["xdg-open", file_path_str])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件：\n{str(e)}")

    def _open_image_with(self, index):
        """调用系统“打开方式”，让用户选择应用打开当前实际显示的文件。"""
        file_path = self._get_displayed_image_path(index)
        if file_path is None:
            return

        file_path_str = str(file_path.absolute())
        system = platform.system()
        try:
            if system == "Darwin":
                script = (
                    "on run argv\n"
                    "set targetFile to POSIX file (item 1 of argv)\n"
                    "set chosenApp to choose application with prompt "
                    '"选择用于打开图片的应用"\n'
                    "tell chosenApp to open targetFile\n"
                    "end run"
                )
                result = subprocess.run(
                    ["osascript", "-e", script, "--", file_path_str],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0 and "-128" not in result.stderr:
                    raise RuntimeError(result.stderr.strip() or "无法选择应用")
            elif system == "Windows":
                subprocess.Popen(
                    ["rundll32.exe", "shell32.dll,OpenAs_RunDLL", file_path_str]
                )
            else:
                messagebox.showinfo(
                    "打开方式",
                    "当前系统暂不支持调用系统应用选择器。",
                    parent=self.root,
                )
        except Exception as e:
            messagebox.showerror("错误", f"无法选择打开方式：\n{str(e)}")

    def _copy_image_file(self, index):
        """将当前实际显示的图片文件作为文件对象写入系统剪贴板。"""
        file_path = self._get_displayed_image_path(index)
        if file_path is None:
            return

        file_path = file_path.absolute()
        system = platform.system()
        try:
            if system == "Darwin":
                script = (
                    'ObjC.import("AppKit");\n'
                    'ObjC.import("Foundation");\n'
                    "function run(argv) {\n"
                    "  const fileURL = $.NSURL.fileURLWithPath($(argv[0]));\n"
                    "  const pasteboard = $.NSPasteboard.generalPasteboard;\n"
                    "  pasteboard.clearContents;\n"
                    "  const files = $.NSArray.arrayWithObject(fileURL);\n"
                    "  if (!pasteboard.writeObjects(files)) {\n"
                    '    throw new Error("无法向剪贴板写入文件 URL");\n'
                    "  }\n"
                    "}\n"
                )
                result = subprocess.run(
                    [
                        "osascript",
                        "-l",
                        "JavaScript",
                        "-e",
                        script,
                        str(file_path),
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "无法拷贝文件")
            elif system == "Windows":
                script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$files = New-Object System.Collections.Specialized.StringCollection; "
                    "[void]$files.Add($args[0]); "
                    "[System.Windows.Forms.Clipboard]::SetFileDropList($files)"
                )
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-STA",
                        "-NoProfile",
                        "-Command",
                        script,
                        str(file_path),
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "无法拷贝文件")
            elif shutil.which("wl-copy"):
                subprocess.run(
                    ["wl-copy", "--type", "text/uri-list"],
                    input=file_path.as_uri(),
                    text=True,
                    check=True,
                )
            elif shutil.which("xclip"):
                subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "text/uri-list"],
                    input=file_path.as_uri(),
                    text=True,
                    check=True,
                )
            else:
                raise RuntimeError("当前系统缺少可写入文件剪贴板的工具")

            self.status_label.config(text=f"已拷贝图片文件：{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"无法拷贝图片文件：\n{str(e)}")

    def _copy_image_path(self, index):
        """将当前实际显示图片的绝对路径作为纯文本写入剪贴板。"""
        file_path = self._get_displayed_image_path(index)
        if file_path is None:
            return

        absolute_path = str(file_path.absolute())
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(absolute_path)
            self.root.update_idletasks()
            self.status_label.config(text=f"已拷贝图片路径：{absolute_path}")
        except Exception as e:
            messagebox.showerror("错误", f"无法拷贝图片路径：\n{str(e)}")
    
    def _update_path_status(self, index):
        """更新路径状态显示（显示图片路径和遮罩路径，以及对应的像素尺寸）"""
        if index < 0 or index >= 3:
            return
        
        # 如果图1或图2在隐藏模式下，不更新路径状态
        if self.hide_info_mode and index >= 1:
            return
        
        path_status_label = self.path_status_labels[index]
        # 盲选模式：图1/图2 位置显示对调后的路径与尺寸
        display_data_index = self._get_blind_display_data_index(index) if index >= 1 else index
        
        if not self.image_lists[display_data_index] if index >= 1 else not self.image_lists[index]:
            # 没有图片
            path_status_label.config(text="")
            return
        
        current_idx = self.current_indices[display_data_index] if index >= 1 else self.current_indices[index]
        
        # 对于图1和图2，显示原始图片路径和遮罩路径信息
        if index >= 1:
            mask_index = display_data_index - 1
            path_parts = []
            
            # 原始图片路径和尺寸
            if current_idx < len(self.image_lists[display_data_index]):
                original_image_path = self.image_lists[display_data_index][current_idx]
                original_path_text = f"图片: {str(original_image_path.absolute())}"
                # 获取图片尺寸
                img_size = self._get_image_size(original_image_path)
                if img_size:
                    original_path_text += f" ({img_size[0]}x{img_size[1]})"
                path_parts.append(original_path_text)
            
            # 遮罩路径和尺寸（使用 display_data_index 对应的遮罩）
            if self.mask_folder_paths[mask_index]:
                if self.mask_image_lists[mask_index] and current_idx < len(self.mask_image_lists[mask_index]):
                    mask_image_path = self.mask_image_lists[mask_index][current_idx]
                    mask_path_text = f"遮罩: {str(mask_image_path.absolute())}"
                    # 获取遮罩尺寸
                    mask_size = self._get_image_size(mask_image_path)
                    if mask_size:
                        mask_path_text += f" ({mask_size[0]}x{mask_size[1]})"
                    path_parts.append(mask_path_text)
                else:
                    mask_path_text = f"遮罩文件夹: {self.mask_folder_paths[mask_index]}"
                    path_parts.append(mask_path_text)

            # 组合路径文本
            path_status_text = "\n".join(path_parts) if path_parts else ""
        else:
            # 原图只显示图片路径和尺寸
            if current_idx < len(self.image_lists[index]):
                current_display_path = self.image_lists[index][current_idx]
                path_status_text = f"图片: {str(current_display_path.absolute())}"
                # 获取图片尺寸
                img_size = self._get_image_size(current_display_path)
                if img_size:
                    path_status_text += f" ({img_size[0]}x{img_size[1]})"
            else:
                path_status_text = ""
        
        path_status_label.config(text=path_status_text)
    
    def _update_selection_display(self, index):
        """更新状态显示（原图文件夹显示"当前第n/m张"，图1/2文件夹显示选中状态）；过滤模式下 m 使用过滤后的数量"""
        status_label = self.selection_status_labels[index]
        
        if not self.image_lists[index]:
            # 没有图片
            if status_label:
                status_label.config(text="")
            # 如果是图1/2文件夹，清空选中标志
            if index >= 1 and self.check_labels[index]:
                preview_bg = self.bg_colors[self.current_bg_color]
                self.check_labels[index].config(text="", bg=preview_bg)
            return
        
        current_idx = self.current_indices[index]
        # 过滤模式下：n、m 使用当前过滤列表（仅切换过滤条件时刷新，不随标记变化）
        if self.filter_mode != "所有" and self.filtered_indices:
            total = len(self.filtered_indices)
            current_num = self.current_filtered_index + 1
        else:
            total = len(self.image_lists[index])
            current_num = current_idx + 1
        
        # 更新状态显示
        if status_label:
            if index == 0:
                # 原图文件夹：显示"当前第n/m张"，过滤时追加 (有标记/无标记)
                if total > 0:
                    suffix = f" ({self.filter_mode})" if self.filter_mode != "所有" else ""
                    status_label.config(text=f"当前第 {current_num}/{total} 张{suffix}")
                else:
                    status_label.config(text="")
            else:
                # 图1文件夹和图2文件夹：显示当前序号和选中状态，m 使用过滤后的值
                state_index = index - 1  # selected_states的索引（0或1）
                selected_count = sum(1 for v in self.selected_states[state_index].values() if v)
                total_full = len(self.image_lists[index])  # 百分比仍按全量计算
                if total > 0:
                    percent = int((selected_count / total_full) * 100) if total_full else 0
                    # 与原图一致，在过滤模式下追加过滤条件说明，但不改变已标记统计
                    suffix = f" ({self.filter_mode})" if self.filter_mode != "所有" else ""
                    status_label.config(
                        text=f"当前第 {current_num}/{total} 张{suffix}, 已标记 {selected_count}/{total_full} ({percent}%)"
                    )
                else:
                    status_label.config(text="")
        
        # 更新选中标志（只针对图1文件夹和图2文件夹）；盲选时显示当前槽位「实际显示内容」的标记状态
        if index >= 1:
            check_label = self.check_labels[index]
            if check_label:
                display_data_index = self._get_blind_display_data_index(index)
                state_index = display_data_index - 1  # 该槽位当前显示的是图1还是图2
                check_idx = self.current_indices[display_data_index]
                preview_bg = self.bg_colors[self.current_bg_color]
                if self.selected_states[state_index].get(check_idx, False):
                    check_label.config(text="✓", fg="#00AA00", bg=preview_bg)  # 绿色打勾，背景色与预览图一致
                else:
                    check_label.config(text="", fg="#00AA00", bg=preview_bg)
    
    def _toggle_selection(self, index):
        """切换指定文件夹的当前图片的选中状态（只针对图1文件夹和图2文件夹）。
        盲选模式下以实际显示为准：若图1位置显示的是图2，则「标记图1」记在图2上。"""
        if index < 1 or index > 2:
            return  # 只处理图1文件夹和图2文件夹
        
        if not self.image_lists[index]:
            return  # 没有图片
        
        current_idx = self.current_indices[0]
        # 盲选且当前行对调时：图1位置显示的是图2，故标记图1 -> 记图2；标记图2 -> 记图1
        if self.blind_mode and current_idx in self.blind_swap_indices:
            state_index = 1 if index == 1 else 0
        else:
            state_index = index - 1
        if not self.image_lists[state_index + 1]:
            return
        # 切换选中状态
        self.selected_states[state_index][current_idx] = not self.selected_states[state_index].get(current_idx, False)
        self._set_dirty(True)
        
        # 更新显示（两个槽位都刷新，因勾选可能显示在任一侧）
        self._update_selection_display(1)
        self._update_selection_display(2)
    
    def _on_arrow_up(self, event):
        """处理向上箭头键"""
        self._navigate_images(-1)
    
    def _on_arrow_down(self, event):
        """处理向下箭头键"""
        self._navigate_images(1)
    
    def _on_arrow_left(self, event):
        """处理向左箭头键 - 切换图1文件夹的选中状态"""
        self._toggle_selection(1)
    
    def _on_arrow_right(self, event):
        """处理向右箭头键 - 切换图2文件夹的选中状态"""
        self._toggle_selection(2)
    
    def _on_key_m(self, event):
        """处理M键 - 切换遮罩/图片显示模式"""
        self._toggle_mask_mode()
    
    def _on_key_a(self, event):
        """处理A键 - 对齐到原图"""
        self._align_to_original()
    
    def _on_key_s(self, event):
        """处理S键 - 切换放大镜"""
        # 切换放大镜状态
        self.magnifier_menu_var.set(not self.magnifier_menu_var.get())
        self._toggle_magnifier()
    
    def _on_key_g(self, event):
        """处理G键 - 跳转到指定图片"""
        self._jump_to_image()

    def _on_key_f(self, event):
        """处理 Cmd+F / Ctrl+F - 搜索原图文件名。"""
        self._show_filename_search()
        return "break"

    @staticmethod
    def _find_filename_matches(image_paths, query, candidate_indices=None):
        """返回候选范围内文件名包含 query 的原图索引（忽略大小写）。"""
        normalized_query = query.casefold()
        if candidate_indices is None:
            candidate_indices = range(len(image_paths))
        return [
            index
            for index in candidate_indices
            if normalized_query in Path(image_paths[index]).name.casefold()
        ]

    def _reset_filename_search(self, close_dialog=False):
        """清空文件名搜索状态；可选关闭已打开的搜索框。"""
        self._filename_search_query = ""
        self._filename_search_results = []
        self._filename_search_position = -1
        if close_dialog and self._filename_search_dialog is not None:
            try:
                self._filename_search_dialog.destroy()
            except tk.TclError:
                pass
            self._filename_search_dialog = None

    def _jump_to_original_index(self, target_index):
        """按原图的绝对索引同步跳转所有已加载的图片列表。"""
        for index, image_list in enumerate(self.image_lists):
            if image_list:
                self.current_indices[index] = min(target_index, len(image_list) - 1)

        if self.filter_mode != "所有" and target_index in self.filtered_indices:
            self.current_filtered_index = self.filtered_indices.index(target_index)

        self._update_all_previews()
        if self.hide_info_mode:
            for index in (1, 2):
                if self.image_lists[index]:
                    self._update_info_visibility(index)
        self._refresh_magnifier_if_needed()
        self._highlight_current_in_image_list()

    def _show_filename_search(self):
        """显示文件名搜索框，同一关键词可连续循环查找。"""
        if not self.image_lists[0]:
            messagebox.showwarning("警告", "请先打开原图文件夹。", parent=self.root)
            return

        if self._filename_search_dialog is not None:
            try:
                if self._filename_search_dialog.winfo_exists():
                    self._filename_search_dialog.lift()
                    self._filename_search_dialog.focus_force()
                    return
            except tk.TclError:
                pass
            self._filename_search_dialog = None

        dlg = tk.Toplevel(self.root)
        self._filename_search_dialog = dlg
        dlg.title("搜索原图")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        tk.Label(dlg, text="请输入原图文件名：", font=("Arial", 11)).pack(
            pady=(12, 6), padx=12, anchor="w"
        )

        entry = tk.Entry(dlg, width=60, font=("Arial", 11))
        entry.pack(pady=(0, 12), padx=12, fill=tk.X)
        entry.insert(0, self._filename_search_query)
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        entry.focus_set()

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(0, 12))

        def on_search():
            query = entry.get().strip()
            if not query:
                messagebox.showwarning("搜索原图", "请输入要搜索的文件名。", parent=dlg)
                entry.focus_set()
                return

            if query != self._filename_search_query:
                self._filename_search_query = query
                candidate_indices = (
                    self.filtered_indices
                    if self.filter_mode != "所有"
                    else range(len(self.image_lists[0]))
                )
                self._filename_search_results = self._find_filename_matches(
                    self.image_lists[0], query, candidate_indices
                )
                self._filename_search_position = -1

            if not self._filename_search_results:
                messagebox.showinfo(
                    "搜索原图",
                    f"没有找到文件名包含“{query}”的原图。",
                    parent=dlg,
                )
                entry.focus_set()
                return

            wrapped_to_first = (
                self._filename_search_position == len(self._filename_search_results) - 1
            )
            self._filename_search_position = (
                self._filename_search_position + 1
            ) % len(self._filename_search_results)
            target_index = self._filename_search_results[self._filename_search_position]
            self._jump_to_original_index(target_index)
            self.status_label.config(
                text=(
                    f"搜索“{query}”：第 {self._filename_search_position + 1}/"
                    f"{len(self._filename_search_results)} 个结果，原图第 {target_index + 1} 张"
                )
            )
            if wrapped_to_first:
                messagebox.showinfo(
                    "搜索原图",
                    "已到达最后一项搜索结果，现已回到第一项结果。",
                    parent=dlg,
                )
            entry.focus_set()

        def on_cancel():
            self._filename_search_dialog = None
            dlg.destroy()
            self.root.focus_force()

        tk.Button(btn_frame, text="搜索", width=10, command=on_search).pack(
            side=tk.LEFT, padx=8
        )
        tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(
            side=tk.LEFT, padx=8
        )

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        entry.bind("<Return>", lambda event: on_search())
        entry.bind("<Escape>", lambda event: on_cancel())
        dlg.grab_set()
        dlg.wait_window(dlg)

    def _on_key_l(self, event):
        """处理L键 - 原图列表（Cmd/Ctrl+L）"""
        # 先切换勾选状态，再调用统一开关逻辑
        self.image_list_menu_var.set(not self.image_list_menu_var.get())
        self._toggle_image_list_window()
        return "break"

    def _jump_to_image(self):
        """跳转到指定序号的图片"""
        # 检查是否有至少一个文件夹已加载
        has_images = False
        max_images = 0
        for i in range(3):
            if self.image_lists[i]:
                has_images = True
                max_images = max(max_images, len(self.image_lists[i]))
        
        if not has_images:
            messagebox.showwarning("警告", "请先选择文件夹！")
            return
        
        # 过滤模式下按过滤列表序号跳转（使用当前过滤列表，不随标记刷新）
        if self.filter_mode != "所有":
            if not self.filtered_indices:
                messagebox.showwarning("警告", "当前过滤条件下没有图片。")
                return
            max_images = len(self.filtered_indices)
            prompt = f"请输入要跳转的图片序号（1-{max_images}，过滤后）："
            result = simpledialog.askinteger(
                "跳转到图片",
                prompt,
                minvalue=1,
                maxvalue=max_images,
                initialvalue=self.current_filtered_index + 1
            )
            self.root.focus_force()
            if result is None:
                return
            self.current_filtered_index = result - 1
            self._sync_indices_from_filtered()
            self._update_all_previews()
            if self.hide_info_mode:
                for index in [1, 2]:
                    if self.image_lists[index]:
                        self._update_info_visibility(index)
            self._refresh_magnifier_if_needed()
            self.status_label.config(text=f"已跳转到第 {result} 张图片")
            self._highlight_current_in_image_list()
            return
        
        # 弹出输入框，让用户输入序号（从1开始）
        prompt = f"请输入要跳转的图片序号（1-{max_images}）："
        result = simpledialog.askinteger(
            "跳转到图片",
            prompt,
            minvalue=1,
            maxvalue=max_images,
            initialvalue=self.current_indices[0] + 1 if self.image_lists[0] else 1
        )
        self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
        
        if result is None:
            return  # 用户取消
        
        # 将序号转换为索引（n-1）
        target_index = result - 1
        
        # 更新所有已加载文件夹的索引
        for i in range(3):
            image_list = self.image_lists[i]
            if image_list:
                # 确保索引在有效范围内
                if target_index < len(image_list):
                    self.current_indices[i] = target_index
                else:
                    # 如果目标索引超出范围，使用最后一个索引
                    self.current_indices[i] = len(image_list) - 1
        
        # 更新所有预览
        self._update_all_previews()
        
        # 如果图1或图2在隐藏模式下，更新信息显示状态
        if self.hide_info_mode:
            for index in [1, 2]:
                if self.image_lists[index]:
                    self._update_info_visibility(index)
        
        # 如果放大镜启用且鼠标在预览图上，刷新放大镜（图片切换）
        self._refresh_magnifier_if_needed()
        # 同步更新图片列表中的高亮项
        self._highlight_current_in_image_list()
        
        # 更新状态栏
        total_images = sum(len(img_list) for img_list in self.image_lists)
        if total_images > 0:
            self.status_label.config(
                text=f"已跳转到第 {result} 张图片"
            )
    
    def _navigate_images(self, direction):
        """导航图片（direction: -1 上一张, 1 下一张）"""
        # 检查是否有至少一个文件夹已加载
        has_images = False
        for i in range(3):
            if self.image_lists[i]:
                has_images = True
                break
        
        if not has_images:
            return

        # 过滤模式：在过滤后的列表上浏览（使用当前过滤列表，不随标记刷新）
        if self.filter_mode != "所有":
            if not self.filtered_indices:
                return
            nf = len(self.filtered_indices)
            if nf > 1:
                cur = self.current_filtered_index
                if direction > 0 and cur >= nf - 1:
                    msg = "当前已是最后一张图片，将回到第一张图片"
                    ok = messagebox.askokcancel("提示", msg, parent=self.root)
                    try:
                        self.root.lift()
                        self.root.focus_force()
                    except Exception:
                        pass
                    if not ok:
                        return
                elif direction < 0 and cur <= 0:
                    msg = "当前已是第一张图片，将回到最后一张图片"
                    ok = messagebox.askokcancel("提示", msg, parent=self.root)
                    try:
                        self.root.lift()
                        self.root.focus_force()
                    except Exception:
                        pass
                    if not ok:
                        return
            self.current_filtered_index = (self.current_filtered_index + direction) % nf
            if self.current_filtered_index < 0:
                self.current_filtered_index += nf
            self._sync_indices_from_filtered()
            self._update_all_previews()
            if self.hide_info_mode:
                for index in [1, 2]:
                    if self.image_lists[index]:
                        self._update_info_visibility(index)
            self._refresh_magnifier_if_needed()
            total_images = sum(len(img_list) for img_list in self.image_lists)
            if total_images > 0:
                self.status_label.config(text=f"已加载 {total_images} 张图片")
            # 同步更新图片列表中的高亮项
            self._highlight_current_in_image_list()
            return

        # 原图（index=0）到边界时提示确认后再循环
        # 仅在原图数量 > 1 时启用该提示
        original_list = self.image_lists[0]
        if original_list and len(original_list) > 1:
            original_idx = self.current_indices[0]
            if direction > 0 and original_idx >= len(original_list) - 1:
                msg = "当前已是最后一张图片，将回到第一张图片"
                ok = messagebox.askokcancel("提示", msg, parent=self.root)
                # 避免弹窗导致主窗口失去焦点（macOS 上更常见）
                try:
                    self.root.lift()
                    self.root.focus_force()
                except Exception:
                    pass
                if not ok:
                    return
            elif direction < 0 and original_idx <= 0:
                msg = "当前已是第一张图片，将回到最后一张图片"
                ok = messagebox.askokcancel("提示", msg, parent=self.root)
                # 避免弹窗导致主窗口失去焦点（macOS 上更常见）
                try:
                    self.root.lift()
                    self.root.focus_force()
                except Exception:
                    pass
                if not ok:
                    return
        
        # 更新所有已加载文件夹的索引
        for i in range(3):
            image_list = self.image_lists[i]
            if image_list:
                current_idx = self.current_indices[i]
                new_idx = current_idx + direction
                
                # 限制索引范围
                if new_idx < 0:
                    new_idx = len(image_list) - 1  # 循环到末尾
                elif new_idx >= len(image_list):
                    new_idx = 0  # 循环到开头
                
                self.current_indices[i] = new_idx
        
        # 更新所有预览
        self._update_all_previews()
        
        # 如果图1或图2在隐藏模式下，更新信息显示状态
        if self.hide_info_mode:
            for index in [1, 2]:
                if self.image_lists[index]:
                    self._update_info_visibility(index)
        
        # 如果放大镜启用且鼠标在预览图上，刷新放大镜（图片切换）
        self._refresh_magnifier_if_needed()
        
        # 更新状态
        total_images = sum(len(img_list) for img_list in self.image_lists)
        if total_images > 0:
            # 检查是否有图1/2文件夹已加载
            has_compare_folders = len(self.image_lists[1]) > 0 or len(self.image_lists[2]) > 0
            if has_compare_folders:
                self.status_label.config(
                    text=f"已加载 {total_images} 张图片"
                )
            else:
                self.status_label.config(
                    text=f"已加载 {total_images} 张图片"
                )
        # 同步更新图片列表中的高亮项
        self._highlight_current_in_image_list()

    def _align_to_original(self):
        """对齐到原图：将图1和图2当前显示图片的序号修改为原图文件夹显示的序号"""
        # 检查是否有原图文件夹
        if not self.image_lists[0]:
            messagebox.showwarning("警告", "请先选择原图文件夹！")
            return
        
        # 获取原图当前显示的序号
        original_index = self.current_indices[0]
        
        # 对齐图1
        if self.image_lists[1]:
            # 确保索引在有效范围内
            if original_index < len(self.image_lists[1]):
                self.current_indices[1] = original_index
                self._update_preview(1)
            else:
                # 如果原图序号超出图1范围，设置为图1的最后一张
                if len(self.image_lists[1]) > 0:
                    self.current_indices[1] = len(self.image_lists[1]) - 1
                    self._update_preview(1)
        
        # 对齐图2
        if self.image_lists[2]:
            # 确保索引在有效范围内
            if original_index < len(self.image_lists[2]):
                self.current_indices[2] = original_index
                self._update_preview(2)
            else:
                # 如果原图序号超出图2范围，设置为图2的最后一张
                if len(self.image_lists[2]) > 0:
                    self.current_indices[2] = len(self.image_lists[2]) - 1
                    self._update_preview(2)
    
    def _get_blind_display_data_index(self, slot_index: int) -> int:
        """盲选模式下，slot_index 位置（1=图1 或 2=图2）实际应显示的数据源。返回 1 或 2。不对调时返回 slot_index。"""
        if not self.blind_mode or slot_index not in (1, 2):
            return slot_index
        k = self.current_indices[0]
        if k not in self.blind_swap_indices:
            return slot_index
        return 2 if slot_index == 1 else 1

    def _get_note_overlay_text(self, slot_index: int) -> str:
        """返回图1/图2预览位置当前实际展示内容的备注。"""
        if slot_index not in (1, 2):
            return ""
        display_data_index = self._get_blind_display_data_index(slot_index)
        image_list = self.image_lists[display_data_index]
        current_idx = self.current_indices[display_data_index]
        if not image_list or current_idx < 0 or current_idx >= len(image_list):
            return ""
        return self.notes[display_data_index - 1].get(current_idx, "")

    def _update_note_overlay(self, slot_index: int) -> None:
        """刷新指定预览位置的备注上屏标签，不重绘底层图片。"""
        if slot_index not in (1, 2):
            return
        if not hasattr(self, "note_overlay_labels"):
            return
        label = self.note_overlay_labels[slot_index]
        if label is None:
            return

        note_text = self._get_note_overlay_text(slot_index)
        if not self.show_note_overlay or not note_text.strip():
            label.place_forget()
            label.config(text="")
            return

        preview_container = self.preview_labels[slot_index].master
        wraplength = max(1, preview_container.winfo_width() - 16)
        preview_bg = self.bg_colors[self.current_bg_color]
        note_fg = self._get_contrasting_text_color(preview_bg)
        label.config(
            text=note_text,
            wraplength=wraplength,
            bg=preview_bg,
            fg=note_fg,
        )
        label.place(x=0, rely=1.0, relwidth=1.0, anchor="sw")
        # macOS 下菜单命令执行期间需要明确提升并刷新控件，否则文字可能要等到
        # 窗口焦点变化后才绘制出来。
        label.lift()
        label.update_idletasks()
        if slot_index < len(self.check_labels) and self.check_labels[slot_index] is not None:
            self.check_labels[slot_index].lift()

    def _refresh_note_overlays(self) -> None:
        """在当前 Tk 事件结束后再次刷新备注，确保覆盖控件完成绘制。"""
        for index in (1, 2):
            self._update_note_overlay(index)

    def _rebuild_blind_swap_indices(self):
        """根据当前图片列表重新生成盲选对调索引（20%～80%），仅在图1和图2均存在时生效。"""
        # 仅当图1与图2均加载时才对调
        if not self.image_lists[1] or not self.image_lists[2]:
            self.blind_swap_indices = set()
            return
        lengths = [len(self.image_lists[i]) for i in range(3) if self.image_lists[i]]
        n = min(lengths) if lengths else 0
        if n == 0:
            self.blind_swap_indices = set()
            return
        ratio = random.uniform(0.2, 0.8)
        count = max(1, min(n, int(round(n * ratio))))
        self.blind_swap_indices = set(random.sample(range(n), count))

    def _toggle_blind_mode(self):
        """切换盲选模式：开启时随机 20%～80% 的图片对调图1/图2 的展示；退出时恢复。"""
        self.blind_mode = self.blind_mode_var.get()
        if self.blind_mode:
            # 开启盲选时根据当前图片重新生成对调索引
            self._rebuild_blind_swap_indices()
            # 开启盲选时自动启用「隐藏图片信息」
            if not self.hide_info_mode:
                self.hide_info_mode = True
                if hasattr(self, "toggle_info_btn"):
                    self.toggle_info_btn.config(text="显示图片信息(I)")
                if hasattr(self, "show_info_menu_var"):
                    self.show_info_menu_var.set(False)
                for index in [1, 2]:
                    self._update_info_visibility(index)
                messagebox.showinfo("盲选模式", "盲选模式下已自动隐藏图片信息")
            # 顶部显示「盲选模式：开」
            self.blind_mode_status_label.config(text="盲选模式：开")
            self.blind_mode_status_label.pack(side=tk.LEFT, padx=(15, 0))
        else:
            self.blind_swap_indices = set()
            # 顶部隐藏盲选状态
            self.blind_mode_status_label.pack_forget()
            self.blind_mode_status_label.config(text="")
            # 退出盲选时自动恢复「显示图片信息」
            if self.hide_info_mode:
                self.hide_info_mode = False
                if hasattr(self, "toggle_info_btn"):
                    self.toggle_info_btn.config(text="隐藏图片信息(I)")
                if hasattr(self, "show_info_menu_var"):
                    self.show_info_menu_var.set(True)
                for index in [1, 2]:
                    self._update_info_visibility(index)
            messagebox.showinfo("盲选模式", "已退出盲选模式")
        self._update_preview(1)
        self._update_preview(2)
        if self.magnifier_enabled:
            self._refresh_magnifier_if_needed()

    def _toggle_info_visibility(self):
        """切换图1和图2的信息显示/隐藏"""
        self.hide_info_mode = not self.hide_info_mode
        
        # 更新顶部按钮文本（顶部按钮可能已被移除）
        if hasattr(self, "toggle_info_btn"):
            if self.hide_info_mode:
                self.toggle_info_btn.config(text="显示图片信息(I)")
            else:
                self.toggle_info_btn.config(text="隐藏图片信息(I)")
        
        if hasattr(self, "show_info_menu_var"):
            self.show_info_menu_var.set(not self.hide_info_mode)
        
        # 更新图1和图2的信息显示
        for index in [1, 2]:
            self._update_info_visibility(index)

    def _toggle_note_visibility(self):
        """切换图1和图2预览框内的备注上屏显示。"""
        self.show_note_overlay = not self.show_note_overlay
        if hasattr(self, "show_note_menu_var"):
            self.show_note_menu_var.set(self.show_note_overlay)
        self._refresh_note_overlays()
        # 菜单关闭发生在 command 返回之后；idle 阶段再刷新一次可规避 macOS Tk
        # 在菜单仍处于激活状态时不重绘覆盖 Label 的问题。
        self.root.after_idle(self._refresh_note_overlays)

    def _on_key_c(self, event):
        """处理C键 - 隐藏/显示备注。"""
        self._toggle_note_visibility()

    def _on_key_i(self, event):
        """处理I键 - 隐藏/显示图片信息"""
        self._toggle_info_visibility()

    def _on_keypress_for_note(self, event):
        """处理全局按键： [ 备注图1； ] 备注图2。"""
        try:
            ch = getattr(event, "char", "") or ""
            keysym = getattr(event, "keysym", "") or ""
            if ch == "[" or keysym == "bracketleft":
                self._edit_note(1)
            elif ch == "]" or keysym == "bracketright":
                self._edit_note(2)
        except Exception:
            # 避免键盘事件干扰其它交互
            pass

    def _edit_note(self, slot_index: int):
        """为指定槽位（1=图1，2=图2）编辑当前图片的文字备注。"""
        if slot_index not in (1, 2):
            return
        if not self.image_lists[slot_index]:
            messagebox.showwarning("警告", f"请先打开图{slot_index}文件夹。", parent=self.root)
            return
        current_idx = self.current_indices[slot_index]
        if current_idx < 0 or current_idx >= len(self.image_lists[slot_index]):
            messagebox.showwarning("警告", f"当前图{slot_index}序号无效，无法编辑备注。", parent=self.root)
            return

        existing_note = self.notes[slot_index - 1].get(current_idx, "")

        dlg = tk.Toplevel(self.root)
        dlg.title(f"备注图{slot_index}")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        tk.Label(dlg, text=f"图{slot_index}备注：", font=("Arial", 11)).pack(pady=(12, 6), padx=12, anchor="w")

        entry = tk.Entry(dlg, width=60, font=("Arial", 11))
        entry.pack(pady=(0, 12), padx=12, fill=tk.X)
        entry.insert(0, existing_note)
        entry.config(state="normal")
        entry.select_range(0, tk.END)  # 便于直接覆盖
        entry.icursor(tk.END)
        entry.focus_set()

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(0, 12))

        def on_ok():
            text = entry.get()
            new_note = text if text.strip() else ""
            if new_note == "":
                self.notes[slot_index - 1].pop(current_idx, None)
            else:
                self.notes[slot_index - 1][current_idx] = new_note
            if new_note != existing_note:
                self._set_dirty(True)
            dlg.destroy()

            self._refresh_note_overlays()

        def on_cancel():
            dlg.destroy()

        tk.Button(btn_frame, text="确定", width=10, command=on_ok).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(side=tk.LEFT, padx=8)

        dlg.protocol("WM_DELETE_WINDOW", on_cancel)
        entry.bind("<Return>", lambda e: on_ok())
        entry.bind("<Escape>", lambda e: on_cancel())

        dlg.grab_set()
        dlg.wait_window(dlg)

    def _on_key_b(self, event):
        """处理 Cmd+B / Ctrl+B - 盲选模式"""
        self.blind_mode_var.set(not self.blind_mode_var.get())
        self._toggle_blind_mode()
    
    def _update_info_visibility(self, index):
        """更新图1或图2的信息显示/隐藏状态（index: 1为图1，2为图2）"""
        if index < 1 or index > 2:
            return
        
        if self.hide_info_mode:
            # 隐藏模式：显示"该信息已隐藏"
            # 隐藏文件夹路径文本框
            self.folder_path_entries[index].config(state="normal")
            self.folder_path_entries[index].delete(0, tk.END)
            self.folder_path_entries[index].insert(0, "该信息已隐藏")
            self.folder_path_entries[index].config(state="readonly")
            
            # 隐藏文件名
            self._set_filename_text(index, "该信息已隐藏")
            
            # 隐藏底部路径状态
            self.path_status_labels[index].config(text="该信息已隐藏")
        else:
            # 显示模式：恢复正常显示
            # 恢复文件夹路径显示
            if self.folder_paths[index]:
                self.folder_path_entries[index].config(state="normal")
                self.folder_path_entries[index].delete(0, tk.END)
                self.folder_path_entries[index].insert(0, self.folder_paths[index])
                self.folder_path_entries[index].config(state="readonly")
            else:
                self.folder_path_entries[index].config(state="normal")
                self.folder_path_entries[index].delete(0, tk.END)
                self.folder_path_entries[index].insert(0, "未选择")
                self.folder_path_entries[index].config(state="readonly")
            
            # 恢复文件名显示（盲选时显示当前该槽位实际展示的数据源文件名）
            display_data_index = self._get_blind_display_data_index(index)
            if self.image_lists[display_data_index] and self.current_indices[display_data_index] < len(self.image_lists[display_data_index]):
                current_idx = self.current_indices[display_data_index]
                image_path = self.image_lists[display_data_index][current_idx]
                self._set_filename_text(index, image_path.name)
            else:
                self._set_filename_text(index, "")
            
            # 恢复底部路径状态显示（需要重新计算路径和尺寸）
            self._update_path_status(index)
    
    def _reset_selections(self):
        """重置所有标记（取消所有图片的选中状态）"""
        has_compare_images = bool(self.image_lists[1] or self.image_lists[2])
        if not has_compare_images:
            messagebox.showwarning("警告", "请先打开图1或图2文件夹。", parent=self.root)
            return

        ok = messagebox.askokcancel(
            "重置标记",
            "确定要重置图1和图2的所有标记吗？\n\n所有已标记图片都会变为未标记。",
            parent=self.root,
        )
        if not ok:
            try:
                self.root.focus_force()
            except Exception:
                pass
            return

        changed = False
        # 重置图1文件夹的选中状态
        if self.image_lists[1]:
            changed = changed or any(self.selected_states[0].values())
            self.selected_states[0] = {i: False for i in range(len(self.image_lists[1]))}
            self._update_selection_display(1)
        
        # 重置图2文件夹的选中状态
        if self.image_lists[2]:
            changed = changed or any(self.selected_states[1].values())
            self.selected_states[1] = {i: False for i in range(len(self.image_lists[2]))}
            self._update_selection_display(2)

        if changed:
            self._set_dirty(True)
        self.status_label.config(text="所有标记已重置")
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _invert_selections(self):
        """反转图1和图2的所有标记状态。"""
        has_compare_images = bool(self.image_lists[1] or self.image_lists[2])
        if not has_compare_images:
            messagebox.showwarning("警告", "请先打开图1或图2文件夹。", parent=self.root)
            return

        ok = messagebox.askokcancel(
            "反转标记",
            "确定要反转图1和图2的所有标记吗？\n\n已标记会变为未标记，未标记会变为已标记。",
            parent=self.root,
        )
        if not ok:
            try:
                self.root.focus_force()
            except Exception:
                pass
            return

        if self.image_lists[1]:
            self.selected_states[0] = {
                i: not self.selected_states[0].get(i, False)
                for i in range(len(self.image_lists[1]))
            }
            self._update_selection_display(1)

        if self.image_lists[2]:
            self.selected_states[1] = {
                i: not self.selected_states[1].get(i, False)
                for i in range(len(self.image_lists[2]))
            }
            self._update_selection_display(2)

        self._set_dirty(True)
        self._refresh_magnifier_if_needed()
        self.status_label.config(text="已反转图1和图2的所有标记")
        try:
            self.root.focus_force()
        except Exception:
            pass
    
    def _open_file_with_default_app(self, file_path):
        """使用系统默认应用打开文件"""
        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            elif system == "Windows":  # Windows
                os.startfile(file_path)
            else:  # Linux和其他Unix系统
                subprocess.run(["xdg-open", file_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件：\n{str(e)}")

    def _set_dirty(self, dirty: bool) -> None:
        """更新当前文档的未保存状态及窗口标题。"""
        self.is_dirty = bool(dirty)
        title = self.APP_TITLE
        if self.current_csv_path:
            title += f" — {os.path.abspath(self.current_csv_path)}"
        if self.is_dirty:
            title += " *"
        try:
            self.root.title(title)
        except Exception:
            pass

    def _prompt_unsaved_changes(self, pending_action: str) -> str:
        """提示处理未保存内容，返回 save、discard 或 cancel。"""
        result = {"action": "cancel"}
        dlg = tk.Toplevel(self.root)
        dlg.title("未保存的更改")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        tk.Label(
            dlg,
            text=f"当前标记信息尚未保存。\n是否先保存再{pending_action}？",
            font=("Arial", 11),
            justify=tk.LEFT,
        ).pack(padx=24, pady=(20, 16))

        button_frame = tk.Frame(dlg)
        button_frame.pack(padx=16, pady=(0, 18))

        def choose(action: str) -> None:
            result["action"] = action
            dlg.destroy()

        save_button = tk.Button(
            button_frame,
            text="保存",
            width=10,
            command=lambda: choose("save"),
            default=tk.ACTIVE,
        )
        save_button.pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame,
            text="不保存",
            width=10,
            command=lambda: choose("discard"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame,
            text="取消",
            width=10,
            command=lambda: choose("cancel"),
        ).pack(side=tk.LEFT, padx=5)

        dlg.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        dlg.bind("<Return>", lambda event: choose("save"))
        dlg.bind("<Escape>", lambda event: choose("cancel"))
        dlg.grab_set()
        save_button.focus_set()
        dlg.wait_window(dlg)
        try:
            self.root.focus_force()
        except Exception:
            pass
        return result["action"]

    def _confirm_unsaved_changes(self, pending_action: str) -> bool:
        """处理未保存状态；仅在允许继续后返回 True。"""
        if not self.is_dirty:
            return True
        action = self._prompt_unsaved_changes(pending_action)
        if action == "save":
            return self._export_to_csv()
        return action == "discard"

    def _close_folders(self):
        """关闭所有已打开文件夹，清空标记/列表/预览，回到初始状态。"""
        if self.is_dirty:
            if not self._confirm_unsaved_changes("关闭文件夹"):
                return
        else:
            try:
                ok = messagebox.askokcancel(
                    "关闭文件夹",
                    "确定要关闭所有文件夹并清空标记与预览吗？",
                    parent=self.root,
                )
            except Exception:
                ok = True
            if not ok:
                return
        # 停止放大镜任务并隐藏放大镜
        try:
            if self.magnifier_update_id:
                self.root.after_cancel(self.magnifier_update_id)
        except Exception:
            pass
        self.magnifier_update_id = None
        self.magnifier_enabled = False
        if hasattr(self, "magnifier_menu_var"):
            try:
                self.magnifier_menu_var.set(False)
            except Exception:
                pass
        for magnifier_label in getattr(self, "magnifier_labels", []):
            try:
                magnifier_label.place_forget()
            except Exception:
                pass
        self.current_mouse_preview = None

        # 关闭原图列表窗口（若打开）
        try:
            self._close_image_list_window()
        except Exception:
            pass
        self._reset_filename_search(close_dialog=True)

        # 重置核心数据
        self.folder_paths = [None, None, None]
        self.image_lists = [[], [], []]
        self.current_indices = [0, 0, 0]
        self.last_selected_dir = None
        self.selected_states = [{}, {}]
        self.notes = [{}, {}]
        self.mask_folder_paths = [None, None]
        self.mask_image_lists = [[], []]
        self.show_mask_mode = [False, False]
        self.mask_mode_enabled = False

        # 退出盲选/隐藏信息并清理状态展示
        self.blind_mode = False
        self.blind_swap_indices = set()
        if hasattr(self, "blind_mode_var"):
            try:
                self.blind_mode_var.set(False)
            except Exception:
                pass
        if hasattr(self, "blind_mode_status_label"):
            try:
                self.blind_mode_status_label.pack_forget()
                self.blind_mode_status_label.config(text="")
            except Exception:
                pass
        self.hide_info_mode = False
        if hasattr(self, "toggle_info_btn"):
            try:
                self.toggle_info_btn.config(text="隐藏图片信息(I)")
            except Exception:
                pass
        if hasattr(self, "show_info_menu_var"):
            try:
                self.show_info_menu_var.set(True)
            except Exception:
                pass

        # 备注上屏恢复默认显示状态
        self.show_note_overlay = True
        if hasattr(self, "show_note_menu_var"):
            try:
                self.show_note_menu_var.set(True)
            except Exception:
                pass
        for note_label in getattr(self, "note_overlay_labels", []):
            if note_label is not None:
                try:
                    note_label.place_forget()
                    note_label.config(text="")
                except Exception:
                    pass

        # 重置过滤
        self.filter_mode = "所有"
        try:
            self.filter_var.set("所有")
        except Exception:
            pass
        self.filtered_indices = []
        self.current_filtered_index = 0
        if hasattr(self, "filter_condition_label"):
            try:
                self.filter_condition_label.config(text="过滤: 所有", font=("Arial", 9))
            except Exception:
                pass

        # 重置 UI 文本/预览
        for i in range(3):
            # 顶部文件夹路径
            if i < len(getattr(self, "folder_path_entries", [])):
                try:
                    self.folder_path_entries[i].config(state="normal")
                    self.folder_path_entries[i].delete(0, tk.END)
                    self.folder_path_entries[i].insert(0, "未选择")
                    self.folder_path_entries[i].config(state="readonly")
                except Exception:
                    pass

            # 顶部文件名
            try:
                self._set_filename_text(i, "")
            except Exception:
                pass

            # 底部路径状态
            if i < len(getattr(self, "path_status_labels", [])):
                try:
                    self.path_status_labels[i].config(text="")
                except Exception:
                    pass

            # 状态栏（当前第n/m张 / 已标记...）
            if i < len(getattr(self, "selection_status_labels", [])):
                try:
                    self.selection_status_labels[i].config(text="")
                except Exception:
                    pass

            # 预览图框：回到“打开xxx”
            if i < len(getattr(self, "preview_labels", [])):
                try:
                    folder_name = self.FOLDER_NAMES[i]
                    self.preview_labels[i].config(
                        image="",
                        text=f"打开{folder_name}",
                        cursor="hand2",
                        anchor=tk.CENTER,
                    )
                    self.preview_labels[i].image = None
                except Exception:
                    pass

            # 右上角选中标志清空（图1/图2）
            if i >= 1 and i < len(getattr(self, "check_labels", [])) and self.check_labels[i]:
                try:
                    preview_bg = self.bg_colors[self.current_bg_color]
                    self.check_labels[i].config(text="", bg=preview_bg)
                except Exception:
                    pass

        # 刷新遮罩切换菜单文案（如果存在）
        try:
            if hasattr(self, "view_menu") and hasattr(self, "toggle_mask_menu_index"):
                self.view_menu.entryconfig(self.toggle_mask_menu_index, label="切换遮罩")
        except Exception:
            pass

        # 收尾：让主窗口获得焦点
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

        self.current_csv_path = None
        self._set_dirty(False)

    def _quit_app(self):
        """彻底退出应用。"""
        if self.is_dirty:
            if not self._confirm_unsaved_changes("退出"):
                return
        else:
            try:
                ok = messagebox.askokcancel(
                    "退出",
                    "确定要退出 PicPicker 吗？",
                    parent=self.root,
                )
            except Exception:
                ok = True
            if not ok:
                return
        try:
            self._close_image_list_window()
        except Exception:
            pass
        self._reset_filename_search(close_dialog=True)
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def _show_about(self) -> None:
        """显示关于信息，包括作者与 GitHub 地址。"""
        message = (
            "PicPicker 比卡拾图\n\n"
            "作者：wkw\n"
            "GitHub：https://github.com/wkw1125/picpicker"
        )
        messagebox.showinfo("关于 PicPicker", message, parent=self.root)

    def _set_filename_text(self, index: int, text: str):
        """设置顶部文件名只读文本框内容（用于复制）。"""
        try:
            entry = self.filename_labels[index]
        except Exception:
            return
        try:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, text or "")
        finally:
            entry.config(state="readonly")

    def _open_folder_path(self, index: int):
        """双击路径框时：打开对应目录（原图/图1/图2）。"""
        try:
            folder_path = self.folder_paths[index] if 0 <= index < len(self.folder_paths) else None
            if not folder_path:
                messagebox.showwarning("提示", "尚未选择该文件夹。")
                return
            if not os.path.isdir(folder_path):
                messagebox.showwarning("提示", f"目录不存在：\n{folder_path}")
                return
            self._open_file_with_default_app(folder_path)
        finally:
            # 弹窗关闭后让主窗口获得焦点
            self.root.focus_force()
    
    def _export_marked_images(self):
        """导出标记图片到zip文件"""
        # 检查是否有原图文件夹
        if not self.folder_paths[0] or not self.image_lists[0]:
            messagebox.showwarning("警告", "请先选择原图文件夹！")
            return
        
        # 收集已标记的图片索引（无标记时也可保存，仅导出 CSV 或空图片目录）
        selected_indices_1 = []
        selected_indices_2 = []
        if self.image_lists[1]:
            selected_indices_1 = [idx for idx, selected in self.selected_states[0].items() if selected]
        if self.image_lists[2]:
            selected_indices_2 = [idx for idx, selected in self.selected_states[1].items() if selected]
        
        # 选择保存位置（默认保存至下载目录）
        downloads_dir = os.path.expanduser("~/Downloads")
        default_filename = os.path.join(downloads_dir, "picpicker.zip")
        
        zip_path = filedialog.asksaveasfilename(
            title="保存标记图片zip文件",
            defaultextension=".zip",
            filetypes=[("ZIP文件", "*.zip"), ("所有文件", "*.*")],
            initialdir=downloads_dir,
            initialfile="picpicker.zip"
        )
        self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
        
        if not zip_path:
            return  # 用户取消保存
        
        try:
            # 创建临时目录用于组织文件
            import tempfile
            temp_dir = tempfile.mkdtemp()
            
            try:
                # 收集需要打包的原图索引（图1或图2被选中时，对应的原图需要打包）
                original_indices_to_pack = set()
                
                # 图1：始终保留 img1 目录结构，有标记时复制图片
                if self.image_lists[1]:
                    img1_dir = os.path.join(temp_dir, "img1")
                    os.makedirs(img1_dir, exist_ok=True)
                    for idx in selected_indices_1:
                        if idx < len(self.image_lists[1]):
                            src_file = self.image_lists[1][idx]
                            dst_file = os.path.join(img1_dir, src_file.name)
                            shutil.copy2(src_file, dst_file)
                            original_indices_to_pack.add(idx)
                    if self.mask_folder_paths[0] and self.mask_image_lists[0]:
                        mask1_dir = os.path.join(temp_dir, "mask1")
                        os.makedirs(mask1_dir, exist_ok=True)
                        for idx in selected_indices_1:
                            if idx < len(self.mask_image_lists[0]):
                                src_file = self.mask_image_lists[0][idx]
                                dst_file = os.path.join(mask1_dir, src_file.name)
                                shutil.copy2(src_file, dst_file)
                
                # 图2：始终保留 img2 目录结构，有标记时复制图片
                if self.image_lists[2]:
                    img2_dir = os.path.join(temp_dir, "img2")
                    os.makedirs(img2_dir, exist_ok=True)
                    for idx in selected_indices_2:
                        if idx < len(self.image_lists[2]):
                            src_file = self.image_lists[2][idx]
                            dst_file = os.path.join(img2_dir, src_file.name)
                            shutil.copy2(src_file, dst_file)
                            original_indices_to_pack.add(idx)
                    if self.mask_folder_paths[1] and self.mask_image_lists[1]:
                        mask2_dir = os.path.join(temp_dir, "mask2")
                        os.makedirs(mask2_dir, exist_ok=True)
                        for idx in selected_indices_2:
                            if idx < len(self.mask_image_lists[1]):
                                src_file = self.mask_image_lists[1][idx]
                                dst_file = os.path.join(mask2_dir, src_file.name)
                                shutil.copy2(src_file, dst_file)
                
                # 原图：始终保留 img 目录结构，有标记时复制对应原图
                if self.image_lists[0]:
                    img_dir = os.path.join(temp_dir, "img")
                    os.makedirs(img_dir, exist_ok=True)
                    for idx in original_indices_to_pack:
                        if idx < len(self.image_lists[0]):
                            src_file = self.image_lists[0][idx]
                            dst_file = os.path.join(img_dir, src_file.name)
                            if not os.path.exists(dst_file):
                                shutil.copy2(src_file, dst_file)
                
                # 生成CSV数据并添加到zip文件
                csv_data = self._generate_csv_data()
                
                # 创建zip文件
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 先写入空目录条目，保证无标记时也保留目录结构
                    if self.image_lists[0]:
                        zipf.writestr("img/", "")
                    if self.image_lists[1]:
                        zipf.writestr("img1/", "")
                    if self.image_lists[2]:
                        zipf.writestr("img2/", "")
                    if self.mask_folder_paths[0] and self.mask_image_lists[0]:
                        zipf.writestr("mask1/", "")
                    if self.mask_folder_paths[1] and self.mask_image_lists[1]:
                        zipf.writestr("mask2/", "")
                    # 遍历临时目录，将所有文件添加到zip
                    for root, dirs, files in os.walk(temp_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            zipf.write(file_path, arcname)
                    # 将CSV数据添加到zip文件的根目录
                    if csv_data:
                        zipf.writestr("picpicker.csv", csv_data.encode('gbk'))
                
                # 询问用户是否打开导出的文件
                if messagebox.askyesno("成功", f"标记图片和CSV已导出到：\n{zip_path}\n\n是否打开该文件？"):
                    self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
                    self._open_file_with_default_app(zip_path)
                else:
                    self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
                
            finally:
                # 清理临时目录
                shutil.rmtree(temp_dir, ignore_errors=True)
                
        except Exception as e:
            messagebox.showerror("错误", f"导出标记图片失败：\n{str(e)}")
    
    def _generate_csv_data(self):
        """生成CSV数据（返回字符串，不保存到文件）。
        新格式在原有基础上增加列：
        图1遮罩、图2遮罩（目录路径 + 文件名），以及图1备注、图2备注。"""
        # 检查是否有原图文件夹
        if not self.folder_paths[0] or not self.image_lists[0]:
            return None
        
        # 检查是否有至少一个图1/2文件夹
        if not self.folder_paths[1] and not self.folder_paths[2]:
            return None
        
        try:
            # 按序号对应：行数 = 原图/图1/图2 最大长度，第 i 行 = 第 i 张原图、第 i 张图1、第 i 张图2，标记按序号取
            n0 = len(self.image_lists[0])
            n1 = len(self.image_lists[1]) if self.image_lists[1] else 0
            n2 = len(self.image_lists[2]) if self.image_lists[2] else 0
            m1 = len(self.mask_image_lists[0]) if self.mask_image_lists[0] else 0
            m2 = len(self.mask_image_lists[1]) if self.mask_image_lists[1] else 0
            row_count = max(n0, n1, n2)
            if row_count == 0:
                return None

            from io import StringIO
            csv_buffer = StringIO()
            writer = csv.writer(csv_buffer)
            # 表头：增加 图1遮罩、图2遮罩 两列，以及图1备注、图2备注
            writer.writerow(['原图', '图1', '图1标记', '图2', '图2标记', '图1遮罩', '图2遮罩', '图1备注', '图2备注'])
            dir_0 = self.folder_paths[0] if self.folder_paths[0] else ''
            dir_1 = self.folder_paths[1] if self.folder_paths[1] else ''
            dir_2 = self.folder_paths[2] if self.folder_paths[2] else ''
            mask_dir_1 = self.mask_folder_paths[0] if self.mask_folder_paths[0] else ''
            mask_dir_2 = self.mask_folder_paths[1] if self.mask_folder_paths[1] else ''
            # 目录行：原图/图1/图2 路径 + 图1遮罩/图2遮罩 目录路径
            writer.writerow([dir_0, dir_1, '-', dir_2, '-', mask_dir_1, mask_dir_2, '-', '-'])

            total_count = n0
            p1 = int((sum(1 for v in self.selected_states[0].values() if v) / n1) * 100) if n1 else 0
            p2 = int((sum(1 for v in self.selected_states[1].values() if v) / n2) * 100) if n2 else 0
            writer.writerow([
                f'共{total_count}张',
                '图1标记率', f'{p1}%',
                '图2标记率', f'{p2}%',
                '-',  # 图1遮罩（统计行占位）
                '-',  # 图2遮罩（统计行占位）
                '-',  # 图1备注（统计行占位）
                '-',  # 图2备注（统计行占位）
            ])

            for i in range(row_count):
                file_0 = Path(self.image_lists[0][i]).name if i < n0 else ''
                file_1 = Path(self.image_lists[1][i]).name if i < n1 else ''
                selected_1 = '1' if self.selected_states[0].get(i, False) else '0'
                file_2 = Path(self.image_lists[2][i]).name if i < n2 else ''
                selected_2 = '1' if self.selected_states[1].get(i, False) else '0'
                # 遮罩文件名（仅文件名，路径由目录行给出）
                mask_1 = Path(self.mask_image_lists[0][i]).name if m1 and i < m1 else ''
                mask_2 = Path(self.mask_image_lists[1][i]).name if m2 and i < m2 else ''
                note_1 = self.notes[0].get(i, "") if i < n1 else ''
                note_2 = self.notes[1].get(i, "") if i < n2 else ''
                writer.writerow([file_0, file_1, selected_1, file_2, selected_2, mask_1, mask_2, note_1, note_2])

            return csv_buffer.getvalue()
            
        except Exception:
            return None
    
    def _on_root_drop(self, event):
        """整个窗口拖入：若为 .csv 文件则按「打开标记文件」处理。"""
        if not _DND_AVAILABLE or not getattr(event, "data", None):
            return
        try:
            for raw in self.root.tk.splitlist(event.data):
                s = str(raw).strip()
                if s.startswith("file://"):
                    s = unquote(s[7:].lstrip("/"))
                p = Path(s)
                if p.is_file() and p.suffix.lower() == ".csv":
                    self._queue_dropped_csv_import(str(p))
                    return COPY
        except Exception:
            pass

    def _import_from_csv(self):
        """从CSV标记文件导入并打开（菜单/快捷键：弹出文件选择框）。"""
        if not self._confirm_unsaved_changes("打开其他 CSV"):
            return False
        downloads_dir = os.path.expanduser("~/Downloads")
        csv_path = filedialog.askopenfilename(
            title="选择CSV标记文件",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialdir=downloads_dir
        )
        self.root.focus_force()
        if csv_path:
            return self._import_from_csv_file(csv_path)
        return False

    def _request_import_from_csv_file(self, csv_path: str) -> bool:
        """处理未保存状态后，导入菜单或拖拽指定的 CSV。"""
        if not self._confirm_unsaved_changes("打开其他 CSV"):
            return False
        return self._import_from_csv_file(csv_path)

    def _queue_dropped_csv_import(self, csv_path: str) -> None:
        """让原生 DnD 回调先返回，再执行可能弹出模态窗口的导入流程。"""
        if getattr(self, "_pending_dropped_csv_path", None) is not None:
            return
        self._pending_dropped_csv_path = csv_path
        self.root.after(
            100,
            lambda path=csv_path: self._run_queued_csv_import(path),
        )

    def _run_queued_csv_import(self, csv_path: str) -> None:
        """在原生拖放会话结束后处理拖入的 CSV。"""
        if getattr(self, "_pending_dropped_csv_path", None) != csv_path:
            return
        self._pending_dropped_csv_path = None
        self._request_import_from_csv_file(csv_path)

    def _validate_csv_format(self, csv_path):
        """检查 CSV 是否符合当前导出的格式规则。返回 (True, None) 或 (False, 错误提示)。"""
        try:
            with open(csv_path, 'r', encoding='gbk') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
        except Exception as e:
            return (False, f"无法读取文件或编码不正确：{e}")
        if len(rows) < 3:
            return (False, "CSV 格式不正确：至少需要 3 行（表头、目录、统计）")
        header = rows[0]
        # 兼容旧格式：前 5 列必须匹配，后续列（图1遮罩/图2遮罩）可选
        if len(header) < 5 or header[0].strip() != '原图' or header[1].strip() != '图1' or header[2].strip() != '图1标记' or header[3].strip() != '图2' or header[4].strip() != '图2标记':
            return (False, "CSV 格式不正确：表头应为「原图, 图1, 图1标记, 图2, 图2标记」开头")
        dir_row = rows[1]
        if len(dir_row) < 5:
            return (False, "CSV 格式不正确：目录行至少需要 5 列")
        if not (dir_row[0].strip() or dir_row[1].strip() or dir_row[3].strip()):
            return (False, "CSV 格式不正确：目录行中未填写原图或图1/图2路径")
        data_rows = rows[3:] if len(rows) > 3 else []
        if not data_rows:
            return (False, "CSV 格式不正确：没有数据行")
        return (True, None)

    def _import_from_csv_file(self, csv_path):
        """从指定 CSV 文件路径导入标记并打开（与「打开标记文件」相同逻辑）。"""
        ok, err = self._validate_csv_format(csv_path)
        if not ok:
            messagebox.showerror("CSV 格式错误", err)
            return False
        try:
            # 读取并解析CSV文件
            with open(csv_path, 'r', encoding='gbk') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
            
            # 解析第1行：表头（已校验）
            header = rows[0]
            # 解析第2行：目录路径
            dir_row = rows[1]
            folder_path_0 = dir_row[0].strip() if dir_row[0].strip() else None
            folder_path_1 = dir_row[1].strip() if len(dir_row) > 1 and dir_row[1].strip() else None
            folder_path_2 = dir_row[3].strip() if len(dir_row) > 3 and dir_row[3].strip() else None
            # 解析遮罩目录路径（新格式中为可选第 6/7 列）
            mask_folder_path_1 = None
            mask_folder_path_2 = None
            try:
                if len(header) >= 7:
                    for idx, name in enumerate(header):
                        name = name.strip()
                        if name == '图1遮罩' and len(dir_row) > idx and dir_row[idx].strip():
                            mask_folder_path_1 = dir_row[idx].strip()
                        if name == '图2遮罩' and len(dir_row) > idx and dir_row[idx].strip():
                            mask_folder_path_2 = dir_row[idx].strip()
            except Exception:
                mask_folder_path_1 = None
                mask_folder_path_2 = None

            # 备注列索引（新格式可选）
            note_col_1 = None
            note_col_2 = None
            try:
                note_col_1 = next((i for i, name in enumerate(header) if name.strip() == '图1备注'), None)
                note_col_2 = next((i for i, name in enumerate(header) if name.strip() == '图2备注'), None)
            except Exception:
                note_col_1 = None
                note_col_2 = None
            
            if not folder_path_0:
                messagebox.showerror("错误", "CSV文件中未找到原图文件夹路径")
                return False
            
            if not folder_path_1 and not folder_path_2:
                messagebox.showerror("错误", "CSV文件中未找到图1或图2文件夹路径")
                return False
            
            # 解析第3行：统计信息（可选，用于验证）
            stats_row = rows[2] if len(rows) > 2 else None
            
            # 解析数据行（从第4行开始）
            data_rows = rows[3:] if len(rows) > 3 else []
            
            # 提取文件名和标记状态
            csv_filenames_0 = []  # 原图文件名列表（按CSV顺序）
            csv_filenames_1 = []  # 图1文件名列表（按CSV顺序）
            csv_filenames_2 = []  # 图2文件名列表（按CSV顺序）
            csv_selected_1 = {}  # 图1标记状态 {文件名: bool}
            csv_selected_2 = {}  # 图2标记状态 {文件名: bool}
            csv_notes_1 = {}  # 图1备注 {文件名: str}
            csv_notes_2 = {}  # 图2备注 {文件名: str}
            
            for row in data_rows:
                if len(row) < 5:
                    continue
                
                filename_0 = row[0].strip()
                filename_1 = row[1].strip()
                filename_2 = row[3].strip()
                selected_1 = row[2].strip() == '1'
                selected_2 = row[4].strip() == '1'
                
                note_1_text = row[note_col_1].strip() if note_col_1 is not None and note_col_1 < len(row) else ''
                note_2_text = row[note_col_2].strip() if note_col_2 is not None and note_col_2 < len(row) else ''
                
                if filename_0:
                    csv_filenames_0.append(filename_0)
                    if filename_1:
                        csv_filenames_1.append(filename_1)
                        csv_selected_1[filename_1] = selected_1
                        csv_notes_1[filename_1] = note_1_text
                    if filename_2:
                        csv_filenames_2.append(filename_2)
                        csv_selected_2[filename_2] = selected_2
                        csv_notes_2[filename_2] = note_2_text
            
            # 验证文件夹路径是否存在
            if not os.path.exists(folder_path_0):
                messagebox.showerror("错误", f"原图文件夹路径不存在：\n{folder_path_0}")
                return False
            
            if folder_path_1 and not os.path.exists(folder_path_1):
                messagebox.showerror("错误", f"图1文件夹路径不存在：\n{folder_path_1}")
                return False
            
            if folder_path_2 and not os.path.exists(folder_path_2):
                messagebox.showerror("错误", f"图2文件夹路径不存在：\n{folder_path_2}")
                return False
            # 遮罩目录存在性（若填写了路径，则要求存在；否则忽略）
            if mask_folder_path_1 and not os.path.exists(mask_folder_path_1):
                messagebox.showerror("错误", f"图1遮罩文件夹路径不存在：\n{mask_folder_path_1}")
                return False
            if mask_folder_path_2 and not os.path.exists(mask_folder_path_2):
                messagebox.showerror("错误", f"图2遮罩文件夹路径不存在：\n{mask_folder_path_2}")
                return False
            
            # 加载实际文件夹中的图片
            actual_images_0 = self._load_images(folder_path_0)
            actual_images_1 = self._load_images(folder_path_1) if folder_path_1 else []
            actual_images_2 = self._load_images(folder_path_2) if folder_path_2 else []
            
            # 获取实际文件名列表（按文件系统顺序）
            actual_filenames_0 = [Path(f).name for f in actual_images_0]
            actual_filenames_1 = [Path(f).name for f in actual_images_1]
            actual_filenames_2 = [Path(f).name for f in actual_images_2]
            
            # 验证图片数量一致性
            warnings = []
            if len(actual_filenames_0) != len(csv_filenames_0):
                warnings.append(f"原图文件夹：CSV记录 {len(csv_filenames_0)} 张，实际 {len(actual_filenames_0)} 张")
            
            if folder_path_1 and len(actual_filenames_1) != len(csv_filenames_1):
                warnings.append(f"图1文件夹：CSV记录 {len(csv_filenames_1)} 张，实际 {len(actual_filenames_1)} 张")
            
            if folder_path_2 and len(actual_filenames_2) != len(csv_filenames_2):
                warnings.append(f"图2文件夹：CSV记录 {len(csv_filenames_2)} 张，实际 {len(actual_filenames_2)} 张")
            
            # 验证文件顺序一致性
            if actual_filenames_0 != csv_filenames_0:
                warnings.append("原图文件夹：文件顺序与CSV记录不一致")
            
            if folder_path_1 and actual_filenames_1 != csv_filenames_1:
                warnings.append("图1文件夹：文件顺序与CSV记录不一致")
            
            if folder_path_2 and actual_filenames_2 != csv_filenames_2:
                warnings.append("图2文件夹：文件顺序与CSV记录不一致")
            
            # 如果有警告，显示警告对话框
            if warnings:
                warning_msg = "检测到以下不一致：\n\n" + "\n".join(warnings) + "\n\n是否继续导入？"
                if not messagebox.askyesno("警告", warning_msg):
                    self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
                    return False
                self.root.focus_force()  # 弹窗关闭后让主窗口获得焦点
            
            # 设置文件夹路径和图片列表
            self._reset_filename_search(close_dialog=True)
            self.folder_paths[0] = folder_path_0
            self.image_lists[0] = actual_images_0
            self.current_indices[0] = 0
            
            if folder_path_1:
                self.folder_paths[1] = folder_path_1
                self.image_lists[1] = actual_images_1
                self.current_indices[1] = 0
                # 初始化图1的选中状态
                self.selected_states[0] = {}
                self.notes[0] = {}
                for idx, img_path in enumerate(actual_images_1):
                    filename = Path(img_path).name
                    self.selected_states[0][idx] = csv_selected_1.get(filename, False)
                    self.notes[0][idx] = csv_notes_1.get(filename, "")
            else:
                self.folder_paths[1] = None
                self.image_lists[1] = []
                self.current_indices[1] = 0
                self.selected_states[0] = {}
                self.notes[0] = {}
            
            if folder_path_2:
                self.folder_paths[2] = folder_path_2
                self.image_lists[2] = actual_images_2
                self.current_indices[2] = 0
                # 初始化图2的选中状态
                self.selected_states[1] = {}
                self.notes[1] = {}
                for idx, img_path in enumerate(actual_images_2):
                    filename = Path(img_path).name
                    self.selected_states[1][idx] = csv_selected_2.get(filename, False)
                    self.notes[1][idx] = csv_notes_2.get(filename, "")
            else:
                self.folder_paths[2] = None
                self.image_lists[2] = []
                self.current_indices[2] = 0
                self.selected_states[1] = {}
                self.notes[1] = {}

            # 设置遮罩文件夹路径和图片列表（新格式），旧格式下 mask_folder_path_* 均为 None
            if mask_folder_path_1:
                self.mask_folder_paths[0] = mask_folder_path_1
                self.mask_image_lists[0] = self._load_images(mask_folder_path_1)
            else:
                self.mask_folder_paths[0] = None
                self.mask_image_lists[0] = []
            if mask_folder_path_2:
                self.mask_folder_paths[1] = mask_folder_path_2
                self.mask_image_lists[1] = self._load_images(mask_folder_path_2)
            else:
                self.mask_folder_paths[1] = None
                self.mask_image_lists[1] = []
            
            # 当前为过滤模式时，根据导入的标记刷新过滤列表并同步索引
            if self.filter_mode != "所有":
                self._build_filtered_indices()
                self.current_filtered_index = 0
                if self.filtered_indices:
                    self._sync_indices_from_filtered()

            # 若当前处于盲选模式，则基于新的图片列表重新生成对调索引
            if self.blind_mode:
                self._rebuild_blind_swap_indices()
            
            # 更新文件夹路径文本框
            self.folder_path_entries[0].config(state="normal")
            self.folder_path_entries[0].delete(0, tk.END)
            self.folder_path_entries[0].insert(0, folder_path_0)
            self.folder_path_entries[0].config(state="readonly")
            
            if folder_path_1:
                if not self.hide_info_mode:
                    self.folder_path_entries[1].config(state="normal")
                    self.folder_path_entries[1].delete(0, tk.END)
                    self.folder_path_entries[1].insert(0, folder_path_1)
                    self.folder_path_entries[1].config(state="readonly")
            else:
                # 兼容旧格式或缺失图1路径的情况
                self.folder_path_entries[1].config(state="normal")
                self.folder_path_entries[1].delete(0, tk.END)
                self.folder_path_entries[1].insert(0, "未选择")
                self.folder_path_entries[1].config(state="readonly")
            
            if folder_path_2:
                if not self.hide_info_mode:
                    self.folder_path_entries[2].config(state="normal")
                    self.folder_path_entries[2].delete(0, tk.END)
                    self.folder_path_entries[2].insert(0, folder_path_2)
                    self.folder_path_entries[2].config(state="readonly")
            else:
                self.folder_path_entries[2].config(state="normal")
                self.folder_path_entries[2].delete(0, tk.END)
                self.folder_path_entries[2].insert(0, "未选择")
                self.folder_path_entries[2].config(state="readonly")
            
            # 刷新所有预览
            for i in range(3):
                if self.image_lists[i]:
                    self._update_preview(i)
                    self._update_selection_display(i)
                    if not self.hide_info_mode or i == 0:
                        self._update_path_status(i)
            
            # 更新状态栏
            total_images = sum(len(img_list) for img_list in self.image_lists)
            csv_filename = os.path.basename(csv_path) if csv_path else "CSV文件"
            self.status_label.config(
                text=f"已成功从CSV文件导入标记信息：{csv_filename}，共 {total_images} 张图片"
            )
            self.current_csv_path = os.path.abspath(csv_path)
            self._set_dirty(False)
            return True
            
        except Exception as e:
            messagebox.showerror("错误", f"导入CSV文件失败：\n{str(e)}")
            return False
    
    def _can_generate_csv(self) -> bool:
        """检查当前内容是否满足 CSV 生成条件。"""
        if not self.folder_paths[0] or not self.image_lists[0]:
            messagebox.showwarning("警告", "请先选择原图文件夹！")
            return False
        if not self.folder_paths[1] and not self.folder_paths[2]:
            messagebox.showwarning("警告", "请至少选择一个图1/2文件夹！")
            return False
        return True

    def _choose_csv_save_path(self) -> str | None:
        """显示 CSV 保存对话框并返回用户选择的路径。"""
        downloads_dir = os.path.expanduser("~/Downloads")
        csv_path = filedialog.asksaveasfilename(
            title="保存CSV文件",
            defaultextension=".csv",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")],
            initialdir=downloads_dir,
            initialfile="picpicker.csv"
        )
        try:
            self.root.focus_force()
        except Exception:
            pass
        return csv_path or None

    def _write_csv_atomically(self, csv_path: str, csv_data: str) -> None:
        """在目标目录完整写入临时文件后，原子替换 CSV。"""
        target = Path(csv_path).absolute()
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="gbk",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(csv_data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, target)
        except Exception as e:
            cleanup_error = None
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as cleanup_exception:
                    cleanup_error = cleanup_exception
            message = str(e)
            if cleanup_error is not None:
                message += f"\n临时文件无法删除：{temp_path}\n{cleanup_error}"
            raise RuntimeError(message) from e

    def _save_csv_to_path(self, csv_path: str) -> bool:
        """将当前数据保存至指定 CSV；成功后更新文档状态。"""
        if not self._can_generate_csv():
            return False
        csv_data = self._generate_csv_data()
        if not csv_data:
            messagebox.showerror("错误", "生成CSV数据失败")
            return False
        try:
            self._write_csv_atomically(csv_path, csv_data)
        except Exception as e:
            messagebox.showerror("错误", f"保存CSV文件失败：\n{e}")
            return False

        self.current_csv_path = os.path.abspath(csv_path)
        self._set_dirty(False)
        try:
            self.status_label.config(text=f"标记信息已保存到：{self.current_csv_path}")
        except Exception:
            pass
        return True

    def _export_to_csv(self) -> bool:
        """保存标记信息；已有当前 CSV 时直接覆盖。"""
        if self.current_csv_path and not self.is_dirty:
            return True
        if not self._can_generate_csv():
            return False
        csv_path = self.current_csv_path or self._choose_csv_save_path()
        if not csv_path:
            return False
        return self._save_csv_to_path(csv_path)

    def _save_csv_as(self) -> bool:
        """将标记信息另存为新的当前 CSV。"""
        if not self._can_generate_csv():
            return False
        csv_path = self._choose_csv_save_path()
        if not csv_path:
            return False
        return self._save_csv_to_path(csv_path)
    
    def run(self):
        """运行应用"""
        self.root.mainloop()


if __name__ == "__main__":
    app = PicPickerApp()
    app.run()
