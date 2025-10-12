# tools/mochi_studio.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import re
import json
import time
import tempfile
from PIL import Image, ImageTk

# Add project root to allow importing core modules
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)

from core.mscript_engine import MscriptScript
from animations import create_animation, list_animation_names
from animations.bitmap_handler import BitmapHandler

# --- Helper Classes ---

class TextLineNumbers(tk.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.textwidget = None

    def attach(self, text_widget):
        self.textwidget = text_widget

    def redraw(self, *args):
        self.delete("all")
        i = self.textwidget.index("@0,0")
        while True:
            dline = self.textwidget.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            linenum = str(i).split(".")[0]
            self.create_text(2, y, anchor="nw", text=linenum, fill="#606366")
            i = self.textwidget.index(f"{i}+1line")

class MscriptTextEditor(tk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = tk.Text(self, wrap="none", undo=True, font=("Courier", 10))
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self.vsb.set)
        self.linenumbers = TextLineNumbers(self, width=30)
        self.linenumbers.attach(self.text)
        self.vsb.pack(side="right", fill="y")
        self.linenumbers.pack(side="left", fill="y")
        self.text.pack(side="right", fill="both", expand=True)
        self.text.bind("<<Change>>", self._on_change)
        self.text.bind("<Configure>", self._on_change)

    def _on_change(self, event):
        self.linenumbers.redraw()

    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)

    def set_text(self, text):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", text)

    def insert_text(self, text):
        self.text.insert(tk.INSERT, text)

class ResourceEditorDialog(simpledialog.Dialog):
    def __init__(self, parent, title=None, resource=None, script_path=None):
        self.resource = resource
        self.script_path = script_path
        super().__init__(parent, title=title)

    def body(self, master):
        ttk.Label(master, text="ID:").grid(row=0, sticky="w")
        ttk.Label(master, text="Path:").grid(row=1, sticky="w")
        self.id_var = tk.StringVar(master)
        self.path_var = tk.StringVar(master)
        self.id_entry = ttk.Entry(master, textvariable=self.id_var)
        self.path_entry = ttk.Entry(master, textvariable=self.path_var)
        self.browse_button = ttk.Button(master, text="Browse...", command=self.browse_path)
        self.id_entry.grid(row=0, column=1, sticky="ew")
        self.path_entry.grid(row=1, column=1, sticky="ew")
        self.browse_button.grid(row=1, column=2, padx=5)
        if self.resource: self.id_var.set(self.resource[0]); self.path_var.set(self.resource[1])
        return self.id_entry

    def browse_path(self):
        initial_dir = os.path.dirname(self.script_path) if self.script_path else "."
        path = filedialog.askopenfilename(initialdir=initial_dir, title="Select Asset File")
        if path:
            rel_path = os.path.relpath(path, PROJECT_ROOT)
            self.path_var.set(rel_path.replace("\\\\", "/"))

    def apply(self):
        self.result = (self.id_var.get(), self.path_var.get())

class AssetPreviewer:
    def __init__(self, thumbnail_size=(128, 128)):
        self.size = thumbnail_size

    def get_preview(self, file_path):
        try:
            if any(file_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".bmp"]):
                img = Image.open(file_path)
            elif file_path.lower().endswith(".gif"):
                img = Image.open(file_path); img.seek(0)
            elif file_path.lower().endswith(".sprite"):
                with open(file_path, 'r') as f: data = json.load(f)
                sprite_image_path = os.path.join(os.path.dirname(file_path), data["image_path"])
                img = Image.open(sprite_image_path)
            elif file_path.lower().endswith(".json"):
                 with open(file_path, 'r') as f: data = json.load(f)
                 if "bitmap_w" in data and "bitmap_h" in data and "bitmap_data" in data:
                    handler = BitmapHandler(data["bitmap_w"], data["bitmap_h"])
                    handler.on_enter(bitmap_data=data["bitmap_data"], bitmap_w=data["bitmap_w"], bitmap_h=data["bitmap_h"])
                    pixel_buf = bytearray(data["bitmap_w"] * data["bitmap_h"] * 3)
                    handler.render_into(0, pixel_buf)
                    img = Image.frombytes('RGB', (data["bitmap_w"], data["bitmap_h"]), bytes(pixel_buf))
                 else: return None
            else: return None
            img.thumbnail(self.size)
            return ImageTk.PhotoImage(img)
        except Exception: return None

# --- Asset Editor Widgets ---

class SpriteEditorWidget(ttk.Frame):
    def __init__(self, parent, studio_app):
        super().__init__(parent)
        self.studio_app = studio_app
        self.image_path, self.image, self.tk_image, self.sprites, self.selected_sprite_index = None, None, None, [], None
        self.state, self.drag_start, self.resize_handle = 'IDLE', None, None

        main_frame = ttk.Frame(self, padding=5); main_frame.pack(fill=tk.BOTH, expand=True)
        top_toolbar = ttk.Frame(main_frame); top_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(top_toolbar, text="Save and Close", command=self.save_and_close).pack(side=tk.RIGHT)
        ttk.Label(top_toolbar, text="Sprite Editor").pack(side=tk.LEFT)

        canvas_frame = ttk.Frame(main_frame); canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#333", cursor="crosshair"); self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sprite_list_frame = ttk.LabelFrame(canvas_frame, text="Sprites"); sprite_list_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,0))
        self.sprite_listbox = tk.Listbox(sprite_list_frame, exportselection=False); self.sprite_listbox.pack(fill=tk.BOTH, expand=True)
        self.sprite_listbox.bind("<<ListboxSelect>>", self.on_sprite_select)
        ttk.Button(sprite_list_frame, text="New Sprite", command=self.create_new_sprite).pack(fill=tk.X)
        ttk.Button(sprite_list_frame, text="Delete Sprite", command=self.delete_sprite).pack(fill=tk.X)

        self.canvas.bind("<Motion>", self.on_canvas_motion); self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag); self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def save_and_close(self): self.studio_app.save_active_asset(); self.studio_app.close_asset_editor()

    def load_data(self, asset_path, asset_data):
        self.sprites = asset_data.get("sprites", [])
        image_path_rel = asset_data.get("image_path")
        if not image_path_rel: messagebox.showerror("Error", "Sprite file missing 'image_path'"); return
        base_dir = os.path.dirname(asset_path)
        self.image_path = os.path.normpath(os.path.join(base_dir, image_path_rel))
        try:
            self.image = Image.open(self.image_path); self.tk_image = ImageTk.PhotoImage(self.image)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL)); self.update_all_views()
        except Exception as e: messagebox.showerror("Error", f"Failed to load sprite image: {e}"); self.studio_app.close_asset_editor()

    def get_data(self):
        if not self.image_path or not self.studio_app.current_script_path: return None
        image_rel_path = os.path.relpath(self.image_path, PROJECT_ROOT)
        return {"image_path": image_rel_path.replace("\\\\", "/"), "sprites": self.sprites}

    def on_canvas_motion(self, event):
        if self.state != 'IDLE': return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.selected_sprite_index is not None:
            x1, y1, w, h = self.sprites[self.selected_sprite_index]
            if abs(x-(x1+w)) < 5 and abs(y-(y1+h)) < 5: self.canvas.config(cursor="sizing"); return
        for i, (sx, sy, sw, sh) in reversed(list(enumerate(self.sprites))):
            if sx <= x <= sx + sw and sy <= y <= sy + sh: self.canvas.config(cursor="fleur"); return
        self.canvas.config(cursor="crosshair")

    def on_canvas_press(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.drag_start = (x, y)
        if self.selected_sprite_index is not None:
            x1, y1, w, h = self.sprites[self.selected_sprite_index]
            if abs(x-(x1+w)) < 5 and abs(y-(y1+h)) < 5: self.state = 'RESIZING'; return
        for i, (sx, sy, sw, sh) in reversed(list(enumerate(self.sprites))):
            if sx <= x <= sx + sw and sy <= y <= sy + sh:
                self.state = 'MOVING'
                if self.selected_sprite_index != i: self.sprite_listbox.selection_set(i); self.on_sprite_select()
                return
        self.sprite_listbox.selection_clear(0, tk.END); self.on_sprite_select()

    def on_canvas_drag(self, event):
        if self.state == 'IDLE' or self.selected_sprite_index is None: return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        dx, dy = x - self.drag_start[0], y - self.drag_start[1]
        if self.state == 'MOVING':
            orig_x, orig_y, w, h = self.sprites[self.selected_sprite_index]
            self.sprites[self.selected_sprite_index] = [int(orig_x + dx), int(orig_y + dy), w, h]
            self.drag_start = (x, y)
        elif self.state == 'RESIZING':
            x1, y1, w, h = self.sprites[self.selected_sprite_index]
            self.sprites[self.selected_sprite_index][2] = max(1, int(w + dx))
            self.sprites[self.selected_sprite_index][3] = max(1, int(h + dy))
            self.drag_start = (x, y)
        self.update_all_views()

    def on_canvas_release(self, event): self.state = 'IDLE'
    def create_new_sprite(self):
        if not self.image: return
        self.sprites.append([10, 10, 50, 50]); self.sprite_listbox.selection_set(len(self.sprites) - 1); self.update_all_views()
    def delete_sprite(self):
        if self.selected_sprite_index is None: return
        del self.sprites[self.selected_sprite_index]; self.update_all_views()
    def update_all_views(self):
        sel = self.sprite_listbox.curselection()
        self.sprite_listbox.delete(0, tk.END)
        for i, (x, y, w, h) in enumerate(self.sprites): self.sprite_listbox.insert(tk.END, f"Sprite {i}: [{x},{y},{w},{h}]")
        if sel: self.sprite_listbox.selection_set(sel[0])
        self.draw_sprite_rects()
    def on_sprite_select(self, event=None):
        indices = self.sprite_listbox.curselection()
        self.selected_sprite_index = indices[0] if indices else None
        self.draw_sprite_rects()
    def draw_sprite_rects(self):
        self.canvas.delete("sprite_rect")
        for i, (x, y, w, h) in enumerate(self.sprites):
            color = "yellow" if i == self.selected_sprite_index else "cyan"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=1, tags="sprite_rect")
            self.canvas.create_text(x + w/2, y + 10, text=str(i), fill=color, tags="sprite_rect")

class BitmapEditorWidget(ttk.Frame):
    def __init__(self, parent, studio_app):
        super().__init__(parent)
        self.studio_app = studio_app

        main_frame = ttk.Frame(self, padding=5); main_frame.pack(fill=tk.BOTH, expand=True)
        top_toolbar = ttk.Frame(main_frame); top_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(top_toolbar, text="Save and Close", command=self.save_and_close).pack(side=tk.RIGHT)
        ttk.Label(top_toolbar, text="Bitmap Editor").pack(side=tk.LEFT)

        data_frame = ttk.LabelFrame(main_frame, text="Bitmap Data (comma-separated hex: 0x00, 0x01, ...)")
        data_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.data_text = tk.Text(data_frame, wrap=tk.WORD, height=10); self.data_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        config_frame = ttk.LabelFrame(main_frame, text="Configuration"); config_frame.pack(fill=tk.X, pady=5)
        ttk.Label(config_frame, text="Bitmap W:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.bitmap_w_var = tk.StringVar(value="8"); ttk.Entry(config_frame, textvariable=self.bitmap_w_var, width=6).grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(config_frame, text="Bitmap H:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.bitmap_h_var = tk.StringVar(value="8"); ttk.Entry(config_frame, textvariable=self.bitmap_h_var, width=6).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(config_frame, text="Update Preview", command=self.update_preview).pack(pady=5)

        preview_frame = ttk.LabelFrame(main_frame, text="Preview"); preview_frame.pack(fill=tk.X, pady=5)
        self.preview_canvas = tk.Canvas(preview_frame, width=128, height=128, bg="#000000"); self.preview_canvas.pack(pady=5)

    def save_and_close(self): self.studio_app.save_active_asset(); self.studio_app.close_asset_editor()

    def load_data(self, asset_path, asset_data):
        self.bitmap_w_var.set(str(asset_data.get("bitmap_w", 8)))
        self.bitmap_h_var.set(str(asset_data.get("bitmap_h", 8)))
        hex_str = ", ".join([f"0x{b:02x}" for b in asset_data.get("bitmap_data", [])])
        self.data_text.delete("1.0", tk.END); self.data_text.insert("1.0", hex_str)
        self.update_preview()

    def get_data(self):
        w = int(self.bitmap_w_var.get())
        h = int(self.bitmap_h_var.get())
        raw_text = self.data_text.get("1.0", tk.END).strip()
        parts = [p.strip() for p in raw_text.split(',')] if raw_text else []
        byte_data = [int(p, 16) for p in parts if p]
        return {"bitmap_w": w, "bitmap_h": h, "bitmap_data": byte_data}

    def update_preview(self):
        try:
            data = self.get_data()
            w, h = data["bitmap_w"], data["bitmap_h"]
            handler = BitmapHandler(w, h); handler.on_enter(**data)
            pixel_buf = bytearray(w * h * 3)
            handler.render_into(0, pixel_buf)
            img = Image.frombytes('RGB', (w, h), bytes(pixel_buf)).resize((128, 128), Image.Resampling.NEAREST)
            self.preview_photo = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor=tk.NW)
        except Exception as e: messagebox.showerror("Preview Error", f"Failed to update preview:\\n{e}")

# --- Main Application Class ---

class MochiStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("Mochi Studio")
        self.root.geometry("1600x900")

        # State variables
        self.current_script_path = None
        self.script_sections = {}
        self.resources = []
        self.active_asset_editor = None
        self.active_asset_path = None
        self.preview_is_running = False
        self.preview_job = None
        self.preview_w, self.preview_h = 64, 64
        self.preview_pixel_buf = bytearray(self.preview_w * self.preview_h * 3)
        self.asset_previewer = AssetPreviewer()
        self.asset_preview_tk_img = None

        # --- Main Layout ---
        main_frame = ttk.Frame(root, padding=10); main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Menu Bar ---
        menu_bar = tk.Menu(root); root.config(menu=menu_bar)
        file_menu = tk.Menu(menu_bar, tearoff=0); menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Script", command=self.new_script)
        file_menu.add_command(label="Load Script...", command=self.load_script)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_active_editor)
        file_menu.add_command(label="Save As...", command=self.save_script_as)
        file_menu.add_separator(); file_menu.add_command(label="Exit", command=root.quit)

        # --- Main 3-Pane Layout ---
        self.paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL); self.paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Left Sidebar (Assets) ---
        left_sidebar = ttk.PanedWindow(self.paned_window, orient=tk.VERTICAL); self.paned_window.add(left_sidebar, weight=1)
        resource_frame = ttk.LabelFrame(left_sidebar, text="Resource Manager"); left_sidebar.add(resource_frame, weight=2)
        self.resource_listbox = tk.Listbox(resource_frame, font=("Courier", 10), exportselection=False); self.resource_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.resource_listbox.bind("<<ListboxSelect>>", self.on_resource_select)
        self.resource_listbox.bind("<Double-1>", self.on_resource_double_click)
        resource_buttons = ttk.Frame(resource_frame); resource_buttons.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(resource_buttons, text="Add...", command=self.add_resource).pack(side=tk.LEFT)
        ttk.Button(resource_buttons, text="Edit...", command=self.edit_resource).pack(side=tk.LEFT)
        ttk.Button(resource_buttons, text="Remove", command=self.remove_resource).pack(side=tk.LEFT)
        asset_preview_frame = ttk.LabelFrame(left_sidebar, text="Asset Preview"); left_sidebar.add(asset_preview_frame, weight=1)
        self.asset_preview_label = ttk.Label(asset_preview_frame, anchor=tk.CENTER); self.asset_preview_label.pack(fill=tk.BOTH, expand=True)

        # --- Center Panel (Editors) ---
        self.center_frame = ttk.Frame(self.paned_window); self.paned_window.add(self.center_frame, weight=3)
        self.text_editor = MscriptTextEditor(self.center_frame); self.text_editor.pack(fill=tk.BOTH, expand=True)

        # --- Right Sidebar (Output & Commands) ---
        right_sidebar = ttk.PanedWindow(self.paned_window, orient=tk.VERTICAL); self.paned_window.add(right_sidebar, weight=1)
        live_preview_frame = ttk.LabelFrame(right_sidebar, text="Live Preview"); right_sidebar.add(live_preview_frame, weight=1)
        preview_controls = ttk.Frame(live_preview_frame); preview_controls.pack(fill=tk.X, padx=5, pady=5)
        self.preview_play_button = ttk.Button(preview_controls, text="Play", command=self.toggle_preview); self.preview_play_button.pack(side=tk.LEFT)
        ttk.Button(preview_controls, text="Stop", command=lambda: self.toggle_preview(force_stop=True)).pack(side=tk.LEFT)
        self.preview_canvas = tk.Canvas(live_preview_frame, width=self.preview_w, height=self.preview_h, bg="black"); self.preview_canvas.pack(pady=10)
        command_palette_frame = ttk.LabelFrame(right_sidebar, text="Command Palette"); right_sidebar.add(command_palette_frame, weight=2)
        self.command_listbox = tk.Listbox(command_palette_frame, font=("Courier", 10)); self.command_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.command_listbox.bind("<Double-1>", lambda e: self.insert_command_from_palette())
        all_commands = sorted(list_animation_names() + ["WAIT"]);
        for cmd in all_commands: self.command_listbox.insert(tk.END, cmd)
        ttk.Button(command_palette_frame, text="Insert Command", command=self.insert_command_from_palette).pack(fill=tk.X, padx=5, pady=5)

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready");
        ttk.Label(main_frame, textvariable=self.status_var, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)

    # --- Editor Management ---
    def on_resource_double_click(self, event):
        if not self.resource_listbox.curselection(): return
        _, res_path = self.resources[self.resource_listbox.curselection()[0]]
        self.open_asset_editor(res_path)

    def open_asset_editor(self, resource_path):
        if self.active_asset_editor: self.close_asset_editor()
        if not self.current_script_path: messagebox.showerror("Error", "Please save the main script first."); return
        full_path = os.path.join(PROJECT_ROOT, resource_path)
        if not os.path.exists(full_path): messagebox.showerror("Error", f"Asset not found: {full_path}"); return

        self.text_editor.pack_forget()
        self.active_asset_path = full_path
        EditorWidget = None
        if resource_path.endswith(".sprite"): EditorWidget = SpriteEditorWidget
        elif resource_path.endswith(".json"): EditorWidget = BitmapEditorWidget

        if EditorWidget:
            try:
                with open(full_path, 'r') as f: data = json.load(f)
                self.active_asset_editor = EditorWidget(self.center_frame, self)
                self.active_asset_editor.pack(fill=tk.BOTH, expand=True)
                self.active_asset_editor.load_data(full_path, data)
                self.status_var.set(f"Editing: {os.path.basename(resource_path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load asset: {e}"); self.close_asset_editor()
        else:
            self.status_var.set(f"This asset type cannot be edited."); self.text_editor.pack(fill=tk.BOTH, expand=True)

    def close_asset_editor(self):
        if not self.active_asset_editor: return
        self.active_asset_editor.destroy()
        self.active_asset_editor = None; self.active_asset_path = None
        self.text_editor.pack(fill=tk.BOTH, expand=True)
        self.status_var.set("Closed asset editor.")

    def save_active_editor(self):
        if self.active_asset_editor: self.save_active_asset()
        else: self.save_script()

    def save_active_asset(self):
        if not self.active_asset_editor or not self.active_asset_path: return
        try:
            data = self.active_asset_editor.get_data()
            if data:
                with open(self.active_asset_path, 'w') as f: json.dump(data, f, indent=2)
                self.status_var.set(f"Saved asset {os.path.basename(self.active_asset_path)}")
        except Exception as e: messagebox.showerror("Save Error", f"Could not save asset: {e}")

    # --- Command & Preview Logic ---
    def insert_command_from_palette(self):
        selected_indices = self.command_listbox.curselection()
        if not selected_indices: return
        command = self.command_listbox.get(selected_indices[0])
        if command == "WAIT": self.text_editor.insert_text("WAIT D[1.0]\\n")
        else: self.text_editor.insert_text(f"{command} K[?]\\n")

    def toggle_preview(self, force_stop=False):
        if self.preview_is_running or force_stop:
            self.preview_is_running = False
            if self.preview_job: self.root.after_cancel(self.preview_job)
            self.preview_job = None; self.preview_play_button.config(text="Play")
        else:
            if not self.current_script_path: messagebox.showerror("Error", "Please save script first."); return
            self.preview_is_running = True; self.preview_play_button.config(text="Pause"); self.start_preview_engine()

    def start_preview_engine(self):
        script_content = self._get_script_content_as_string()
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, dir=os.path.dirname(self.current_script_path), suffix=".mscript") as f:
                temp_script_path = f.name; f.write(script_content)
            self.preview_script_engine = MscriptScript(temp_script_path)
            self.preview_animation = None; self.run_preview_frame()
        finally:
            if 'temp_script_path' in locals() and os.path.exists(temp_script_path): os.remove(temp_script_path)

    def run_preview_frame(self):
        if not self.preview_is_running: return
        try:
            due_commands = self.preview_script_engine.update(time.time())
            for command in due_commands: self._process_preview_command(command)
            if self.preview_animation:
                self.preview_animation.render_into(time.time(), self.preview_pixel_buf)
                img = Image.frombytes('RGB', (self.preview_w, self.preview_h), bytes(self.preview_pixel_buf))
                self.preview_tk_img = ImageTk.PhotoImage(img)
                self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_tk_img)
        except Exception as e: self.status_var.set(f"Preview Error: {e}")
        self.preview_job = self.root.after(16, self.run_preview_frame)

    def _process_preview_command(self, command):
        cmd_name, args = command.name.lower(), command.args.copy()
        if 'asset_path' in args and self.current_script_path:
            if not os.path.isabs(args['asset_path']):
                args['asset_path'] = os.path.abspath(os.path.join(PROJECT_ROOT, args['asset_path']))
        if cmd_name in list_animation_names(): self.preview_animation = create_animation(cmd_name, self.preview_w, self.preview_h, **args)
        elif self.preview_animation and hasattr(self.preview_animation, 'on_event'): self.preview_animation.on_event(command.name, **args)

    # --- File and Script Logic ---
    def _get_script_content_as_string(self):
        main_lines = self.text_editor.get("1.0", tk.END).rstrip('\\n').split('\\n')
        resource_lines = [f"{res[0]}: '{res[1]}'\\n" for res in self.resources]
        return f"[Main start]\\n{'\\n'.join(main_lines)}\\n[Main end]\\n\\n[Resources start]\\n{''.join(resource_lines)}\\n[Resources end]\\n\\n"

    def _ask_to_save_current_work(self):
        """
        Asks the user if they want to save their current work (script or active asset).
        Returns True if the user proceeds (saved or discarded), False if they cancel.
        """
        # Check if an asset editor is active and has unsaved changes
        if self.active_asset_editor and self.active_asset_path:
            response = messagebox.askyesnocancel(
                "Save Asset Changes?",
                f"Do you want to save changes to the current asset '{os.path.basename(self.active_asset_path)}'?"
            )
            if response == True:
                self.save_active_asset()
            elif response == False:
                pass # Discard changes
            else: # Cancel
                return False
            return True # Asset handled, proceed

        # Check for unsaved script changes
        current_script_content = self.text_editor.get("1.0", tk.END).strip()
        if current_script_content: # There's content in the editor
            if not self.current_script_path: # It's a new, unsaved script
                response = messagebox.askyesnocancel(
                    "Save New Script?",
                    "Do you want to save the current new script?"
                )
                if response == True:
                    self.save_script_as() # Force Save As
                    if not self.current_script_path: # User cancelled Save As
                        return False
                elif response == False:
                    pass # Discard changes
                else: # Cancel
                    return False
            else: # An existing script is loaded, might have changes
                response = messagebox.askyesnocancel(
                    "Save Script Changes?",
                    f"Do you want to save changes to '{os.path.basename(self.current_script_path)}'?"
                )
                if response == True:
                    self.save_script()
                elif response == False:
                    pass # Discard changes
                else: # Cancel
                    return False
        return True # No changes to save, or changes handled, proceed

    def new_script(self):
        if not self._ask_to_save_current_work():
            return
        self.close_asset_editor()
        self.current_script_path = None
        self.script_sections = {}
        self.resources = []
        self.text_editor.set_text("")
        self.update_resource_list()
        self.root.title("Mochi Studio - New Script")

    def load_script(self):
        if not self._ask_to_save_current_work():
            return
        self.close_asset_editor()
        script_path = filedialog.askopenfilename(title="Select Mscript File", filetypes=[("Mscript files", "*.mscript")], initialdir="mscripts")
        if not script_path: return
        try:
            with open(script_path, 'r') as f: all_lines = f.readlines()
            self.script_sections = self.parse_sections(all_lines)
            self.text_editor.set_text("".join(self.script_sections.get('main', [])).rstrip('\\n'))
            self.resources = []
            for line in self.script_sections.get('resources', []):
                if ':' in line:
                    parts = line.split(':', 1)
                    res_id = parts[0].strip()
                    path_str = parts[1].strip()
                    if (path_str.startswith("'") and path_str.endswith("'")) or (path_str.startswith('"') and path_str.endswith('"')):
                        path_str = path_str[1:-1]
                    self.resources.append((res_id, path_str))
            self.update_resource_list()
            self.current_script_path = script_path
            self.root.title(f"Mochi Studio - {os.path.basename(script_path)}")
        except Exception as e: messagebox.showerror("Error", f"Failed to load script: {e}")

    def save_script(self):
        if self.current_script_path: self._write_script_to_file(self.current_script_path)
        else: self.save_script_as()

    def save_script_as(self):
        script_path = filedialog.asksaveasfilename(title="Save Mscript As", defaultextension=".mscript", filetypes=[("Mscript files", "*.mscript")], initialdir="mscripts")
        if not script_path: return
        self.current_script_path = script_path
        self.root.title(f"Mochi Studio - {os.path.basename(script_path)}")
        self._write_script_to_file(script_path)

    def _write_script_to_file(self, script_path):
        try:
            with open(script_path, 'w') as f: f.write(self._get_script_content_as_string())
            self.status_var.set(f"Script saved to {script_path}")
        except Exception as e: messagebox.showerror("Error", f"Failed to save file: {e}")

    def parse_sections(self, all_lines):
        sections = {}; current_section = "_header"; sections[current_section] = []
        section_regex = re.compile(r'^\[\s*(\w+)\s*(start|end)\s*\]$', re.IGNORECASE)
        for line in all_lines:
            match = section_regex.match(line.strip())
            if match:
                section_name, status = match.groups()
                current_section = section_name.lower() if status.lower() == 'start' else "_footer"
                sections.setdefault(current_section, [])
            else:
                sections.setdefault(current_section, []).append(line)
        return sections

    def on_resource_select(self, event=None):
        selected_indices = self.resource_listbox.curselection()
        if not selected_indices: return
        _, res_path = self.resources[selected_indices[0]]
        if not self.current_script_path: return
        full_path = os.path.join(PROJECT_ROOT, res_path)
        self.asset_preview_tk_img = self.asset_previewer.get_preview(full_path)
        if self.asset_preview_tk_img:
            self.asset_preview_label.config(image=self.asset_preview_tk_img, text="")
        else:
            self.asset_preview_label.config(image=None, text=f"No preview for\\n{os.path.basename(res_path)}")

    def update_resource_list(self):
        self.resource_listbox.delete(0, tk.END)
        for res_id, res_path in self.resources:
            self.resource_listbox.insert(tk.END, f"{res_id}: '{res_path}'")

    def add_resource(self):
        max_id = 0
        for res_id, _ in self.resources:
            match = re.match(r"K\[(\d+)\]", res_id)
            if match:
                max_id = max(max_id, int(match.group(1)))
        new_id = f"K[{max_id + 1}]"
        dialog = ResourceEditorDialog(self.root, title="Add Resource", resource=(new_id, ''), script_path=self.current_script_path)
        if dialog.result:
            self.resources.append(dialog.result)
            self.update_resource_list()

    def edit_resource(self):
        selected_index = self.resource_listbox.curselection()
        if not selected_index: return
        dialog = ResourceEditorDialog(self.root, title="Edit Resource", resource=self.resources[selected_index[0]], script_path=self.current_script_path)
        if dialog.result: self.resources[selected_index[0]] = dialog.result; self.update_resource_list()

    def remove_resource(self):
        selected_index = self.resource_listbox.curselection()
        if not selected_index: return
        if messagebox.askyesno("Confirm", "Remove this resource?"):
            del self.resources[selected_index[0]]; self.update_resource_list()

if __name__ == "__main__":
    root = tk.Tk()
    app = MochiStudio(root)
    root.mainloop()
