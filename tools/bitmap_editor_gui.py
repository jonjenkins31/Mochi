# tools/bitmap_editor_gui.py
# A GUI for creating and editing Mochi bitmap animations.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import numpy as np
from PIL import Image, ImageTk

# Add project root to path to allow importing core modules
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from animations.bitmap_handler import BitmapHandler

PREVIEW_SIZE = (128, 64)

class BitmapEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Mochi Bitmap Editor")
        self.current_script_path = None

        # --- Main Layout ---
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Controls ---
        top_controls = ttk.Frame(main_frame)
        top_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(top_controls, text="Load Script...", command=self.load_script).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_controls, text="Save As...", command=self.save_script_as).pack(side=tk.LEFT, padx=(0, 10))

        # --- Left Panel (Editor) ---
        editor_panel = ttk.Frame(main_frame, width=400)
        editor_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # --- Data Entry ---
        data_frame = ttk.LabelFrame(editor_panel, text="Bitmap Data (comma-separated hex: 0x00, 0x01, ...)")
        data_frame.pack(fill=tk.BOTH, expand=True)
        self.data_text = tk.Text(data_frame, wrap=tk.WORD, height=10)
        self.data_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Right Panel (Preview & Config) ---
        preview_panel = ttk.Frame(main_frame, width=250)
        preview_panel.pack(side=tk.RIGHT, fill=tk.Y)
        preview_panel.pack_propagate(False)

        # --- Config ---
        config_frame = ttk.LabelFrame(preview_panel, text="Configuration")
        config_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(config_frame, text="Bitmap W:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.bitmap_w_var = tk.StringVar(value="64")
        ttk.Entry(config_frame, textvariable=self.bitmap_w_var, width=6).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(config_frame, text="Bitmap H:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.bitmap_h_var = tk.StringVar(value="32")
        ttk.Entry(config_frame, textvariable=self.bitmap_h_var, width=6).grid(row=1, column=1, padx=5, pady=2)

        # --- Preview ---
        preview_frame = ttk.LabelFrame(preview_panel, text="Preview")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_canvas = tk.Canvas(preview_frame, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg="#000000")
        self.preview_canvas.pack(pady=5)
        self.preview_image = tk.PhotoImage(width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1])
        self.preview_canvas.create_image(0, 0, image=self.preview_image, anchor=tk.NW)

        ttk.Button(preview_panel, text="Update Preview", command=self.update_preview).pack(fill=tk.X, pady=5)

    def _parse_data_from_text(self):
        """Helper to parse the hex data from the text widget."""
        raw_text = self.data_text.get("1.0", tk.END).strip()
        if not raw_text:
            return []
        parts = [p.strip() for p in raw_text.split(',')]
        return [int(p, 16) for p in parts if p]

    def update_preview(self):
        try:
            w = int(self.bitmap_w_var.get())
            h = int(self.bitmap_h_var.get())
            if w <= 0 or h <= 0:
                raise ValueError("Bitmap dimensions must be positive.")

            byte_data_list = self._parse_data_from_text()

            if not byte_data_list:
                img = Image.new('RGB', PREVIEW_SIZE, (0, 0, 0))
                self.preview_photo = ImageTk.PhotoImage(img)
                self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor=tk.NW)
                return

            handler = BitmapHandler(w, h)
            handler.on_enter(bitmap_data=byte_data_list, bitmap_w=w, bitmap_h=h)
            
            pixel_buf = bytearray(w * h * 3)
            handler.render_into(0, pixel_buf)

            img = Image.frombytes('RGB', (w, h), bytes(pixel_buf))
            img = img.resize(PREVIEW_SIZE, Image.Resampling.NEAREST)

            self.preview_photo = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor=tk.NW)

        except Exception as e:
            messagebox.showerror("Preview Error", f"Failed to update preview:\n{e}")

    def load_script(self):
        path = filedialog.askopenfilename(
            title="Load Bitmap Script",
            filetypes=[("JSON files", "*.json")],
            initialdir="scripts"
        )
        if not path: return

        try:
            with open(path, 'r') as f:
                script_data = json.load(f)
            
            # Find the bitmap_handler mode command
            mode_cmd = next((item for item in script_data.get("timeline", []) 
                             if item.get("cmd") == "mode" and 
                             item.get("args", {}).get("name") == "bitmap_handler"), None)

            if not mode_cmd:
                raise ValueError("Script does not contain a bitmap_handler mode command.")

            args = mode_cmd.get("args", {})
            w = args.get("bitmap_w", 64)
            h = args.get("bitmap_h", 32)
            data = args.get("bitmap_data", [])

            self.bitmap_w_var.set(str(w))
            self.bitmap_h_var.set(str(h))

            # Format data back into a hex string for the text box
            hex_str = ", ".join([f"0x{b:02x}" for b in data])
            self.data_text.delete("1.0", tk.END)
            self.data_text.insert("1.0", hex_str)

            self.current_script_path = path
            self.root.title(f"Mochi Bitmap Editor - {os.path.basename(path)}")
            self.update_preview()

        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load script:\n{e}")

    def save_script_as(self):
        path = filedialog.asksaveasfilename(
            title="Save Bitmap Script As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialdir="scripts"
        )
        if not path: return

        try:
            w = int(self.bitmap_w_var.get())
            h = int(self.bitmap_h_var.get())
            byte_data_list = self._parse_data_from_text()

            script_data = {
                "timeline": [
                    {
                        "at": 0.0,
                        "cmd": "mode",
                        "args": {
                            "name": "bitmap_handler",
                            "bitmap_w": w,
                            "bitmap_h": h,
                            "bitmap_data": byte_data_list,
                            "on_color": [255, 255, 255], # Default colors
                            "off_color": [0, 0, 0]
                        }
                    }
                ]
            }

            with open(path, 'w') as f:
                json.dump(script_data, f, indent=2)
            
            self.current_script_path = path
            self.root.title(f"Mochi Bitmap Editor - {os.path.basename(path)}")
            messagebox.showinfo("Success", f"Script saved to:\n{path}")

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save script:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = BitmapEditor(root)
    root.mainloop()
