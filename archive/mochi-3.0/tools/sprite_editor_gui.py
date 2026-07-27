
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import json
import os
import re

RESIZE_HANDLE_SIZE = 4
PREVIEW_SIZE = (64, 64)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class SpriteEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Sprite Script Editor")

        self.image_path = None
        self.image_resource_id = "K[1]" # Hardcoded for simplicity
        self.current_script_path = None
        self.image = None
        self.tk_image = None
        self.sprites = []
        self.timeline = []
        self.timeline_clipboard = []
        
        self.selected_sprite_index = None
        self.selected_timeline_index = None

        # --- Interaction & Preview State ---
        self.state = 'IDLE' # IDLE, MOVING, RESIZING
        self.drag_start = None
        self.resize_handle = None
        self.is_playing_preview = False
        self.preview_timeline_index = 0
        self.preview_job = None

        # --- Main Layout ---
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Controls ---
        top_controls = ttk.Frame(main_frame)
        top_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(top_controls, text="Load Script...", command=self.load_script).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_controls, text="Save", command=self.save_script).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_controls, text="Save As...", command=self.save_script_as).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(top_controls, text="Load Asset...", command=self.load_image).pack(side=tk.LEFT, padx=(10, 0))

        # --- Asset Panel (Left) ---
        asset_panel = ttk.Frame(main_frame, width=250)
        asset_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        asset_panel.pack_propagate(False)

        # --- New Sprite Panel ---
        new_sprite_frame = ttk.LabelFrame(asset_panel, text="New Sprite")
        new_sprite_frame.pack(fill=tk.X, pady=(0, 10))
        size_entries_frame = ttk.Frame(new_sprite_frame)
        size_entries_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(size_entries_frame, text="W:").pack(side=tk.LEFT)
        self.sprite_w_var = tk.StringVar(value="64")
        ttk.Entry(size_entries_frame, textvariable=self.sprite_w_var, width=4).pack(side=tk.LEFT)
        ttk.Label(size_entries_frame, text="H:").pack(side=tk.LEFT, padx=(5,0))
        self.sprite_h_var = tk.StringVar(value="64")
        ttk.Entry(size_entries_frame, textvariable=self.sprite_h_var, width=4).pack(side=tk.LEFT)
        ttk.Button(new_sprite_frame, text="Create New Sprite", command=self.create_new_sprite).pack(fill=tk.X, padx=5, pady=5)
        self.lock_aspect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(new_sprite_frame, text="Lock Aspect Ratio on Resize", variable=self.lock_aspect_var).pack(anchor="w", padx=5)

        # --- Sprite List ---
        sprite_list_frame = ttk.LabelFrame(asset_panel, text="Assets")
        sprite_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.sprite_listbox = tk.Listbox(sprite_list_frame, height=6, exportselection=False)
        self.sprite_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.sprite_listbox.bind("<<ListboxSelect>>", self.on_sprite_select)
        sprite_buttons_frame = ttk.Frame(sprite_list_frame)
        sprite_buttons_frame.pack(fill=tk.X, padx=5, pady=(0,5))
        ttk.Button(sprite_buttons_frame, text="Duplicate", command=self.duplicate_sprite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,2))
        ttk.Button(sprite_buttons_frame, text="Delete", command=self.delete_sprite).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2,0))

        # --- Animation Panel (Right) ---
        animation_panel = ttk.Frame(main_frame, width=300)
        animation_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        animation_panel.pack_propagate(False)

        # --- Preview Panel ---
        preview_frame = ttk.LabelFrame(animation_panel, text="Animation Preview")
        preview_frame.pack(fill=tk.X, pady=(0, 10))
        self.preview_canvas = tk.Canvas(preview_frame, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg="#000")
        self.preview_canvas.pack(pady=5)
        self.preview_button = ttk.Button(preview_frame, text="Play", command=self.toggle_preview)
        self.preview_button.pack(fill=tk.X, padx=5, pady=5)

        # --- Timeline ---
        timeline_frame = ttk.LabelFrame(animation_panel, text="Animation Script")
        timeline_frame.pack(fill=tk.BOTH, expand=True)
        self.timeline_listbox = tk.Listbox(timeline_frame, height=8, exportselection=False)
        self.timeline_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.timeline_listbox.bind("<<ListboxSelect>>", self.on_timeline_select)
        
        # --- Timeline Toolbar ---
        timeline_toolbar = ttk.Frame(timeline_frame)
        timeline_toolbar.pack(fill=tk.X, pady=5)
        ttk.Button(timeline_toolbar, text="Add Sprite", command=self.add_sprite_to_timeline).pack(side=tk.LEFT, padx=2)
        self.duration_var = tk.StringVar(value="0.5")
        self.duration_entry = ttk.Entry(timeline_toolbar, textvariable=self.duration_var, width=5)
        self.duration_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(timeline_toolbar, text="Add Delay", command=self.add_delay_to_timeline).pack(side=tk.LEFT, padx=2)

        # --- Timeline Edit Controls ---
        edit_controls = ttk.Frame(timeline_frame)
        edit_controls.pack(fill=tk.X, padx=5, pady=(0,5))
        ttk.Button(edit_controls, text="Cut", command=self.cut_timeline_item).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(edit_controls, text="Copy", command=self.copy_timeline_item).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        self.paste_button = ttk.Button(edit_controls, text="Paste", command=self.paste_timeline_item, state=tk.DISABLED)
        self.paste_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(edit_controls, text="Del", command=self.remove_from_timeline).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(edit_controls, text="Up", command=lambda: self.move_timeline_item(-1)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(edit_controls, text="Down", command=lambda: self.move_timeline_item(1)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # --- Canvas (Center) ---
        self.canvas = tk.Canvas(main_frame, background="#333", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def get_resize_handle(self, x, y, sprite_index):
        if sprite_index != self.selected_sprite_index: return None
        x1, y1, w, h = self.sprites[sprite_index]
        x2, y2 = x1 + w, y1 + h
        s = RESIZE_HANDLE_SIZE
        if abs(x - x1) < s and abs(y - y1) < s: return "nw"
        if abs(x - x2) < s and abs(y - y1) < s: return "ne"
        if abs(x - x1) < s and abs(y - y2) < s: return "sw"
        if abs(x - x2) < s and abs(y - y2) < s: return "se"
        if abs(x - x1) < s: return "w"
        if abs(x - x2) < s: return "e"
        if abs(y - y1) < s: return "n"
        if abs(y - y2) < s: return "s"
        return None

    def on_canvas_motion(self, event):
        if self.state != 'IDLE': return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        if self.selected_sprite_index is not None:
            handle = self.get_resize_handle(x, y, self.selected_sprite_index)
            if handle:
                if handle in ["nw", "se"]: self.canvas.config(cursor="sizing")
                elif handle in ["ne", "sw"]: self.canvas.config(cursor="sizing")
                elif handle in ["n", "s"]: self.canvas.config(cursor="sb_v_double_arrow")
                elif handle in ["e", "w"]: self.canvas.config(cursor="sb_h_double_arrow")
                return

        for i, (sx, sy, sw, sh) in reversed(list(enumerate(self.sprites))):
            if sx <= x <= sx + sw and sy <= y <= sy + sh:
                self.canvas.config(cursor="fleur")
                return
        
        self.canvas.config(cursor="crosshair")

    def on_canvas_press(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.drag_start = (x, y)

        if self.selected_sprite_index is not None:
            self.resize_handle = self.get_resize_handle(x, y, self.selected_sprite_index)
            if self.resize_handle:
                self.state = 'RESIZING'
                return

        for i, (sx, sy, sw, sh) in reversed(list(enumerate(self.sprites))):
            if sx <= x <= sx + sw and sy <= y <= sy + sh:
                self.state = 'MOVING'
                if self.selected_sprite_index != i:
                    self.sprite_listbox.selection_clear(0, tk.END)
                    self.sprite_listbox.selection_set(i)
                    self.on_sprite_select(None)
                return
        
        self.sprite_listbox.selection_clear(0, tk.END)
        self.on_sprite_select(None)
        self.state = 'IDLE'

    def on_canvas_drag(self, event):
        if self.state == 'IDLE': return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        dx, dy = x - self.drag_start[0], y - self.drag_start[1]

        if self.state == 'MOVING' and self.selected_sprite_index is not None:
            orig_x, orig_y, w, h = self.sprites[self.selected_sprite_index]
            new_x, new_y = orig_x + dx, orig_y + dy
            self.sprites[self.selected_sprite_index] = [int(new_x), int(new_y), w, h]
            self.drag_start = (x, y)
            self.update_sprite_list()
            self.draw_sprite_rects()

        elif self.state == 'RESIZING' and self.selected_sprite_index is not None:
            x1_orig, y1_orig, w_orig, h_orig = self.sprites[self.selected_sprite_index]
            aspect_ratio = w_orig / h_orig if h_orig != 0 else 1
            x1, y1, x2, y2 = x1_orig, y1_orig, x1_orig + w_orig, y1_orig + h_orig

            if 'e' in self.resize_handle: x2 = x
            if 'w' in self.resize_handle: x1 = x
            if 's' in self.resize_handle: y2 = y
            if 'n' in self.resize_handle: y1 = y

            if self.lock_aspect_var.get():
                if self.resize_handle in ['n', 's']:
                    new_h = abs(y1 - y2)
                    new_w = new_h * aspect_ratio
                    if 'w' in self.resize_handle: x1 = x2 - new_w
                    else: x2 = x1 + new_w
                else:
                    new_w = abs(x1 - x2)
                    new_h = new_w / aspect_ratio
                    if 'n' in self.resize_handle: y1 = y2 - new_h
                    else: y2 = y1 + new_h

            self.sprites[self.selected_sprite_index] = [int(min(x1,x2)), int(min(y1,y2)), int(abs(x1-x2)), int(abs(y1-y2))]
            self.update_sprite_list()
            self.draw_sprite_rects()

    def on_canvas_release(self, event):
        self.state = 'IDLE'
        self.resize_handle = None
        self.on_canvas_motion(event)

    def create_new_sprite(self):
        if not self.image: messagebox.showerror("Error", "Load an image first."); return
        try:
            w, h = int(self.sprite_w_var.get()), int(self.sprite_h_var.get())
            if w <= 0 or h <= 0: raise ValueError("Size must be positive")
            x = self.canvas.canvasx(0) + (self.canvas.winfo_width() / 2) - (w / 2)
            y = self.canvas.canvasy(0) + (self.canvas.winfo_height() / 2) - (h / 2)
            self.sprites.append([int(x), int(y), w, h])
            self.sprite_listbox.selection_clear(0, tk.END)
            self.sprite_listbox.selection_set(len(self.sprites) - 1)
            self.update_all_views()
        except ValueError as e: messagebox.showerror("Error", f"Invalid sprite size: {e}")

    def duplicate_sprite(self):
        if self.selected_sprite_index is None: messagebox.showerror("Error", "Select a sprite to duplicate."); return
        x, y, w, h = self.sprites[self.selected_sprite_index]
        self.sprites.append([int(x + 10), int(y + 10), w, h])
        self.sprite_listbox.selection_clear(0, tk.END)
        self.sprite_listbox.selection_set(len(self.sprites) - 1)
        self.update_all_views()

    def _load_image_from_path(self, path):
        try:
            full_path = path if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"Image file not found at: {full_path}")
            
            self.image_path = os.path.relpath(full_path, PROJECT_ROOT).replace('\\', '/')
            self.image = Image.open(full_path)
            self.tk_image = ImageTk.PhotoImage(self.image)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
            self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
            return True
        except Exception as e:
            messagebox.showerror("Image Load Error", str(e))
            return False

    def _parse_sections(self, all_lines):
        sections = {}
        current_section = None
        section_regex = re.compile(r'^\[\s*(\w+)\s*(start|end)\s*\]$', re.IGNORECASE)
        for line in all_lines:
            match = section_regex.match(line.strip())
            if match:
                section_name, status = match.groups()
                if status.lower() == 'start':
                    current_section = section_name.lower()
                    sections[current_section] = []
                elif status.lower() == 'end':
                    current_section = None
            elif current_section:
                sections[current_section].append(line.strip())
        return sections

    def load_script(self):
        script_path = filedialog.askopenfilename(title="Select MochiScript File", filetypes=[("MochiScript files", "*.mscript")], initialdir=os.path.join(PROJECT_ROOT, "assets", "mscripts"))
        if not script_path: return
        
        try:
            with open(script_path, 'r') as f:
                all_lines = f.readlines()
            
            sections = self._parse_sections(all_lines)

            # -- Reset state --
            self.sprites = []
            self.timeline = []
            
            # -- Parse Resources --
            resource_lines = sections.get('resources', [])
            if not resource_lines: raise ValueError("No [Resources] section found.")
            
            res_match = re.match(r"(K\[\d+\]):\s*'(.*)'", resource_lines[0])
            if not res_match: raise ValueError("Could not parse resource line.")
            
            self.image_resource_id, image_path_rel = res_match.groups()
            if not self._load_image_from_path(image_path_rel):
                return

            # -- Parse Main --
            main_lines = sections.get('main', [])
            if not main_lines: raise ValueError("No [Main] section found.")

            sprite_cmd_re = re.compile(r"SPRITE\s+K\[\d+\](?:\s+D\[([\d\.]+)\])?\s+SRC\[(\d+),(\d+),(\d+),(\d+)\]")
            wait_cmd_re = re.compile(r"WAIT\s+D\[([\d\.]+)\]")

            for line in main_lines:
                sprite_match = sprite_cmd_re.match(line)
                wait_match = wait_cmd_re.match(line)

                if sprite_match:
                    duration, x, y, w, h = sprite_match.groups()
                    sprite_rect = [int(v) for v in (x, y, w, h)]
                    
                    if sprite_rect not in self.sprites:
                        self.sprites.append(sprite_rect)
                    sprite_index = self.sprites.index(sprite_rect)
                    
                    self.timeline.append({"cmd": "show_sprite", "index": sprite_index})
                    if duration:
                        self.timeline.append({"cmd": "delay", "duration": float(duration)})

                elif wait_match:
                    duration = wait_match.groups()[0]
                    self.timeline.append({"cmd": "delay", "duration": float(duration)})

            self.current_script_path = script_path
            self.root.title(f"Sprite Script Editor - {os.path.basename(script_path)}")
            self.update_all_views()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load script: {e}")
            # Reset on failure
            self.image_path = None
            self.current_script_path = None
            self.sprites = []
            self.timeline = []
            self.update_all_views()


    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.bmp *.jpg"), ("All files", "*.*")] )
        if not path: return
        
        if self._load_image_from_path(path):
            self.sprites, self.timeline, self.selected_sprite_index = [], [], None
            self.current_script_path = None # New image means new script
            self.root.title("Sprite Script Editor")
            self.update_all_views()

    def update_all_views(self):
        sprite_sel = self.sprite_listbox.curselection()
        timeline_sel = self.timeline_listbox.curselection()
        self.update_sprite_list()
        self.update_timeline_list()
        if sprite_sel: self.sprite_listbox.selection_set(sprite_sel[0])
        if timeline_sel: self.timeline_listbox.selection_set(timeline_sel[0])
        self.draw_sprite_rects()

    def update_sprite_list(self):
        sel = self.sprite_listbox.curselection()
        self.sprite_listbox.delete(0, tk.END)
        for i, (x, y, w, h) in enumerate(self.sprites):
            self.sprite_listbox.insert(tk.END, f"Asset {i}: [{x}, {y}, {w}, {h}]")
        if sel: self.sprite_listbox.selection_set(sel[0])

    def on_sprite_select(self, event=None):
        indices = self.sprite_listbox.curselection()
        self.selected_sprite_index = indices[0] if indices else None
        self.draw_sprite_rects()

    def delete_sprite(self):
        if self.selected_sprite_index is None: return
        
        deleted_idx = self.selected_sprite_index
        del self.sprites[deleted_idx]
        
        # Filter timeline and remap indices
        new_timeline = []
        for item in self.timeline:
            if item.get('cmd') == 'show_sprite':
                if item['index'] == deleted_idx:
                    continue # Skip items that used the deleted sprite
                elif item['index'] > deleted_idx:
                    item['index'] -= 1 # Decrement indices of sprites that came after
            new_timeline.append(item)
        self.timeline = new_timeline

        self.selected_sprite_index = None
        self.sprite_listbox.selection_clear(0, tk.END)
        self.update_all_views()

    def draw_sprite_rects(self):
        self.canvas.delete("sprite_rect")
        if not self.image: return
        for i, (x, y, w, h) in enumerate(self.sprites):
            color = "yellow" if i == self.selected_sprite_index else "cyan"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=1, tags="sprite_rect")
            self.canvas.create_text(x + w/2, y + 10, text=str(i), fill=color, tags="sprite_rect", font=("TkDefaultFont", 10, "bold"))
            if i == self.selected_sprite_index:
                s = RESIZE_HANDLE_SIZE
                self.canvas.create_rectangle(x-s, y-s, x+s, y+s, fill=color, outline="black", tags="sprite_rect")
                self.canvas.create_rectangle(x+w-s, y-s, x+w+s, y+s, fill=color, outline="black", tags="sprite_rect")
                self.canvas.create_rectangle(x-s, y+h-s, x+s, y+h+s, fill=color, outline="black", tags="sprite_rect")
                self.canvas.create_rectangle(x+w-s, y+h-s, x+w+s, y+h+s, fill=color, outline="black", tags="sprite_rect")

    def add_sprite_to_timeline(self):
        if self.selected_sprite_index is None: messagebox.showerror("Error", "Select an asset first."); return
        self.timeline.append({"cmd": "show_sprite", "index": self.selected_sprite_index})
        self.update_timeline_list()
        self.timeline_listbox.selection_set(len(self.timeline) - 1)

    def add_delay_to_timeline(self):
        try:
            duration = float(self.duration_var.get())
            if duration <= 0: raise ValueError("Duration must be positive")
            self.timeline.append({"cmd": "delay", "duration": duration})
            self.update_timeline_list()
            self.timeline_listbox.selection_set(len(self.timeline) - 1)
        except ValueError as e: messagebox.showerror("Error", f"Invalid duration: {e}")

    def remove_from_timeline(self):
        if self.selected_timeline_index is None: return
        del self.timeline[self.selected_timeline_index]
        self.selected_timeline_index = None
        self.timeline_listbox.selection_clear(0, tk.END)
        self.update_timeline_list()
        self.on_timeline_select(None)

    def on_timeline_select(self, event=None):
        indices = self.timeline_listbox.curselection()
        self.selected_timeline_index = indices[0] if indices else None

    def update_timeline_list(self):
        sel = self.timeline_listbox.curselection()
        self.timeline_listbox.delete(0, tk.END)
        for i, item in enumerate(self.timeline):
            if item["cmd"] == "show_sprite": self.timeline_listbox.insert(tk.END, f"{i}: SHOW Asset {item['index']}")
            elif item["cmd"] == "delay": self.timeline_listbox.insert(tk.END, f"{i}: DELAY {item['duration']}s")
        if sel: self.timeline_listbox.selection_set(sel[0])

    def cut_timeline_item(self):
        self.copy_timeline_item()
        self.remove_from_timeline()

    def copy_timeline_item(self):
        if self.selected_timeline_index is None: return
        self.timeline_clipboard = [self.timeline[self.selected_timeline_index]]
        self.paste_button.config(state=tk.NORMAL)

    def paste_timeline_item(self):
        if not self.timeline_clipboard: return
        
        paste_item = self.timeline_clipboard[0].copy()

        if self.selected_timeline_index is None:
            insert_at = len(self.timeline)
        else:
            insert_at = self.selected_timeline_index + 1

        self.timeline.insert(insert_at, paste_item)
        self.update_timeline_list()
        self.timeline_listbox.selection_clear(0, tk.END)
        self.timeline_listbox.selection_set(insert_at)
        self.on_timeline_select()

    def move_timeline_item(self, direction):
        if self.selected_timeline_index is None: return
        
        idx = self.selected_timeline_index
        new_idx = idx + direction

        if 0 <= new_idx < len(self.timeline):
            self.timeline.insert(new_idx, self.timeline.pop(idx))
            self.update_timeline_list()
            self.timeline_listbox.selection_set(new_idx)
            self.on_timeline_select()

    def save_script(self):
        if self.current_script_path:
            self._write_script_to_file(self.current_script_path)
        else:
            self.save_script_as()

    def save_script_as(self):
        script_path = filedialog.asksaveasfilename(
            title="Save MochiScript As",
            defaultextension=".mscript",
            filetypes=[("MochiScript files", "*.mscript")],
            initialdir=os.path.join(PROJECT_ROOT, "assets", "mscripts")
        )
        if not script_path: return
        self.current_script_path = script_path
        self.root.title(f"Sprite Script Editor - {os.path.basename(script_path)}")
        self._write_script_to_file(script_path)

    def _write_script_to_file(self, script_path):
        if not self.image_path:
            messagebox.showerror("Error", "Please load an asset image first.")
            return

        # Ensure image path is relative to project root for consistency
        image_path_rel = self.image_path
        if os.path.isabs(image_path_rel):
             image_path_rel = os.path.relpath(image_path_rel, PROJECT_ROOT).replace('\\', '/')

        # --- Build Script Content ---
        output = []
        output.append("[Header start]")
        output.append(f"! Generated by Mochi Sprite Editor")
        output.append("[Header end]\n")

        output.append("[Resources start]")
        output.append(f"{self.image_resource_id}: '{image_path_rel}'")
        output.append("[Resources end]\n")

        output.append("[Main start]")
        
        i = 0
        while i < len(self.timeline):
            item = self.timeline[i]
            if item['cmd'] == 'show_sprite':
                sprite_idx = item['index']
                x, y, w, h = self.sprites[sprite_idx]
                
                # Look ahead for a delay to use as duration
                duration = 0.0
                if i + 1 < len(self.timeline) and self.timeline[i+1]['cmd'] == 'delay':
                    duration = self.timeline[i+1]['duration']
                    i += 1 # Consume the delay
                
                output.append(f"SPRITE {self.image_resource_id} D[{duration}] SRC[{x},{y},{w},{h}]")

            elif item['cmd'] == 'delay':
                # This is a standalone delay
                output.append(f"WAIT D[{item['duration']}]")
            
            i += 1
        
        output.append("[Main end]")

        try:
            with open(script_path, 'w') as f:
                f.write('\n'.join(output))
            messagebox.showinfo("Success", f"Script saved to:\n{script_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def toggle_preview(self):
        if self.is_playing_preview:
            self.is_playing_preview = False
            if self.preview_job: self.root.after_cancel(self.preview_job); self.preview_job = None
            self.preview_button.config(text="Play")
            self.timeline_listbox.selection_clear(0, tk.END)
            self.on_timeline_select()
        else:
            if not self.timeline: messagebox.showinfo("Info", "Timeline is empty."); return
            self.is_playing_preview = True
            self.preview_timeline_index = 0
            self.preview_button.config(text="Stop")
            self.run_preview_frame()

    def run_preview_frame(self):
        if not self.is_playing_preview: return

        if self.preview_timeline_index >= len(self.timeline):
            self.preview_timeline_index = 0 # Loop

        self.timeline_listbox.selection_clear(0, tk.END)
        self.timeline_listbox.selection_set(self.preview_timeline_index)
        self.on_timeline_select()

        item = self.timeline[self.preview_timeline_index]
        delay_ms = 1 # Default delay for show commands

        if item["cmd"] == "show_sprite":
            sprite_index = item["index"]
            if 0 <= sprite_index < len(self.sprites):
                x, y, w, h = self.sprites[sprite_index]
                sprite_img = self.image.crop((x, y, x + w, y + h))
                sprite_img = sprite_img.resize(PREVIEW_SIZE, Image.Resampling.NEAREST)
                self.preview_tk_image = ImageTk.PhotoImage(sprite_img)
                self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.preview_tk_image)
            self.preview_timeline_index += 1

        elif item["cmd"] == "delay":
            delay_ms = int(item["duration"] * 1000)
            self.preview_timeline_index += 1

        self.preview_job = self.root.after(delay_ms, self.run_preview_frame)

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteEditor(root)
    root.mainloop()
