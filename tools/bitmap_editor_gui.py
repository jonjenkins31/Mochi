# tools/bitmap_editor_gui.py
# A GUI for viewing Mochi bitmap animations.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import time
from PIL import Image, ImageTk
import os
import sys

# Add project root to path to allow importing core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from animations.bitmap_handler import BitmapHandler

PREVIEW_SIZE = (128, 64)
WINDOW_SIZE = (600, 400)

class BitmapAnimationViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("Mochi Bitmap Animation Viewer")
        self.root.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}")

        self.frame_paths = []
        self.handler = BitmapHandler(PREVIEW_SIZE[0], PREVIEW_SIZE[1])

        # Animation state
        self.is_playing = False
        self.animation_time = 0.0
        self.last_update_time = None
        self.animation_job = None

        # --- Main Layout ---
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Left Panel (Frame List) ---
        list_panel = ttk.Frame(main_frame, width=250)
        list_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        ttk.Button(list_panel, text="Load Frame(s)...", command=self.load_frames).pack(fill=tk.X, pady=(0, 5))
        
        self.frame_listbox = tk.Listbox(list_panel)
        self.frame_listbox.pack(fill=tk.BOTH, expand=True)
        self.frame_listbox.bind('<<ListboxSelect>>', self.on_frame_select)

        # --- Right Panel (Preview & Controls) ---
        preview_panel = ttk.Frame(main_frame, width=300)
        preview_panel.pack(side=tk.RIGHT, fill=tk.Y)
        preview_panel.pack_propagate(False)

        # --- Preview ---
        preview_frame = ttk.LabelFrame(preview_panel, text="Preview")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_canvas = tk.Canvas(preview_frame, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg="#000000")
        self.preview_canvas.pack(pady=5, padx=5, expand=True)

        # --- Controls ---
        controls_frame = ttk.LabelFrame(preview_panel, text="Controls")
        controls_frame.pack(fill=tk.X)

        # FPS Control
        fps_frame = ttk.Frame(controls_frame, padding=5)
        fps_frame.pack(fill=tk.X)
        ttk.Label(fps_frame, text="FPS:").pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value="10.0")
        ttk.Entry(fps_frame, textvariable=self.fps_var, width=6).pack(side=tk.LEFT, padx=5)

        # Play/Pause Buttons
        buttons_frame = ttk.Frame(controls_frame, padding=(5, 0, 5, 5))
        buttons_frame.pack(fill=tk.X, expand=True)
        self.play_button = ttk.Button(buttons_frame, text="Play", command=self.play, state=tk.DISABLED)
        self.play_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        self.pause_button = ttk.Button(buttons_frame, text="Pause", command=self.pause, state=tk.DISABLED)
        self.pause_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

    def load_frames(self):
        self.pause()
        paths = filedialog.askopenfilenames(
            title="Select Bitmap JSON Frame(s)",
            filetypes=[("JSON files", "*.json")],
            initialdir=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'bitmaps'))
        )
        if not paths:
            return

        self.frame_paths = list(paths)
        self.frame_listbox.delete(0, tk.END)
        for path in self.frame_paths:
            self.frame_listbox.insert(tk.END, os.path.basename(path))
        
        if self.frame_paths:
            self.frame_listbox.selection_set(0)
            self.on_frame_select(None) # Manually trigger update for the first frame
            self.play_button.config(state=tk.NORMAL if len(self.frame_paths) > 1 else tk.DISABLED)

    def on_frame_select(self, event):
        self.pause()
        selection_indices = self.frame_listbox.curselection()
        if not selection_indices:
            return
        
        selected_index = selection_indices[0]
        self.animation_time = selected_index / float(self.fps_var.get())
        self.update_preview()

    def update_preview(self):
        if not self.frame_paths:
            return

        try:
            fps = float(self.fps_var.get())
            if fps <= 0:
                fps = 1.0
        except ValueError:
            fps = 1.0
        
        num_frames = len(self.frame_paths)
        frame_index = int(self.animation_time * fps) % num_frames
        
        current_path = self.frame_paths[frame_index]
        
        # Use the handler as intended by the core system
        self.handler.on_enter(asset_path=current_path)
        
        pixel_buf = bytearray(PREVIEW_SIZE[0] * PREVIEW_SIZE[1] * 3)
        self.handler.render_into(0, pixel_buf) # Time is not used by the original handler

        img = Image.frombytes('RGB', (self.handler.bitmap_w, self.handler.bitmap_h), bytes(pixel_buf))
        img = img.resize(PREVIEW_SIZE, Image.Resampling.NEAREST)

        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor=tk.NW)

        # Update listbox selection to match current frame
        if not self.is_playing:
             self.frame_listbox.selection_clear(0, tk.END)
        self.frame_listbox.selection_set(frame_index)


    def _animate(self):
        if self.is_playing:
            now = time.monotonic()
            delta_t = now - self.last_update_time
            self.last_update_time = now
            self.animation_time += delta_t

            self.update_preview()
            
            self.animation_job = self.root.after(33, self._animate) # ~30 FPS GUI update

    def play(self):
        if not self.is_playing and len(self.frame_paths) > 1:
            self.is_playing = True
            self.last_update_time = time.monotonic()
            self.play_button.config(state=tk.DISABLED)
            self.pause_button.config(state=tk.NORMAL)
            self._animate()

    def pause(self):
        if self.is_playing:
            self.is_playing = False
            if self.animation_job:
                self.root.after_cancel(self.animation_job)
                self.animation_job = None
            self.play_button.config(state=tk.NORMAL)
            self.pause_button.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = BitmapAnimationViewer(root)
    root.mainloop()
