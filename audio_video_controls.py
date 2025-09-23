from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, QColorDialog, QTextEdit, QDialog, QComboBox, QHBoxLayout
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, QTimer
from PIL import Image , ImageSequence
import os
import time
import random

class AudioVideoManager(QWidget):
    def __init__(self, main_controller=None):
        super().__init__()
        self.main_controller = main_controller
        self.matrix_streaming = False
        self.streaming = False
        self.eye_animation = "assets/Eyes_Gif.gif"
        eye_frame_map = {
            "sad": (0, 79),
            "happy": (80, 159),
            "blink": (160, 239),
            "look_left": (240, 319),
            "look_right": (320, 399),
            "idle": (400, 479)
        }

        layout = QVBoxLayout()
        
        # --- Matrix Color Picker ---
        self.matrix_label = QLabel("Set LED Matrix to Solid Color:")
        self.matrix_color_btn = QPushButton("Pick Matrix Color")
        self.matrix_color_btn.clicked.connect(self.pick_matrix_color)
        layout.addWidget(self.matrix_label)
        layout.addWidget(self.matrix_color_btn)

        # --- Matrix Animation Mode Selector ---
        self.matrix_anim_label = QLabel("Matrix Animation Mode:")
        self.matrix_anim_dropdown = QComboBox()
        self.matrix_anim_dropdown.addItems([
            "Animation 1",  # MODE_MATRIX_ANIMATION_1 = 1
            "Animation 2",  # MODE_MATRIX_ANIMATION_2 = 2
            "Animation 3",  # MODE_MATRIX_ANIMATION_3 = 3
        ])
        self.matrix_anim_dropdown.setCurrentIndex(0)  # Default to Animation 1
        self.matrix_anim_send_btn = QPushButton("Send Matrix Animation")
        self.matrix_anim_send_btn.clicked.connect(self.send_matrix_animation_mode)
        layout.addWidget(self.matrix_anim_label)
        layout.addWidget(self.matrix_anim_dropdown)
        layout.addWidget(self.matrix_anim_send_btn)

        # --- Upload Image to Matrix ---
        self.led_label = QLabel("Upload Image for LED Matrix:")
        self.upload_btn = QPushButton("Browse Image")
        self.upload_btn.clicked.connect(self.upload_image_matrix)
        layout.addWidget(self.led_label)
        layout.addWidget(self.upload_btn)

        # --- Icon Send ---
        self.icon_label = QLabel("Send Icon to LED Matrix:")
        self.icon_dropdown = QComboBox()
        self.icon_dropdown.addItems(self.load_icon_list())
        self.icon_send_btn = QPushButton("Send Icon to Matrix")
        self.icon_send_btn.clicked.connect(self.send_selected_icon_to_matrix)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon_dropdown)
        icon_row.addWidget(self.icon_send_btn)
        layout.addWidget(self.icon_label)
        layout.addLayout(icon_row)


        # --- Matrix Live Stream Toggle ---
        self.matrix_live_btn = QPushButton("Start Matrix Live Stream")
        self.matrix_live_btn.setCheckable(True)
        self.matrix_live_btn.clicked.connect(self.toggle_matrix_live_stream)
        layout.addWidget(self.matrix_live_btn)

        # --- NeoPixel Color Picker ---
        self.neopixel_label = QLabel("Select Color for NeoPixel:")
        self.color_btn = QPushButton("Choose Color")
        self.color_btn.clicked.connect(self.pick_neopixel_color)
        layout.addWidget(self.neopixel_label)
        layout.addWidget(self.color_btn)

        # --- NeoPixel Animation Selector ---
        self.anim_mode_label = QLabel("Select NeoPixel Animation:")
        self.anim_dropdown = QComboBox()
        self.anim_dropdown.addItems([
            "Red-Green-Blue Wipe",       # 1
            "Percentage Bar",            # 2
            "Theater Chase",             # 3
            "Rainbow",                   # 4
            "Rainbow + White Overlay",   # 5
            "Pulse White",               # 6
            "Rainbow Cycle",             # 7
            "Set All LEDs to Color",     # 8
            "Pulse Custom Color",        # 9
            "Theater Chase Rainbow",     # 10
        ])
        self.anim_send_btn = QPushButton("Send Animation Mode")
        self.anim_send_btn.clicked.connect(self.send_neopixel_animation_mode)

        anim_layout = QHBoxLayout()
        anim_layout.addWidget(self.anim_dropdown)
        anim_layout.addWidget(self.anim_send_btn)
        layout.addWidget(self.anim_mode_label)
        layout.addLayout(anim_layout)

        # --- NeoPixel Live Stream ---
        self.live_stream_btn = QPushButton("Start Live Stream")
        self.live_stream_btn.setCheckable(True)
        self.live_stream_btn.clicked.connect(self.toogle_neopixel_live_stream)
        layout.addWidget(self.live_stream_btn)

        self.setLayout(layout)

    # -----------Shared Functions---------------

    def send_command(self, command):
        if self.main_controller:
            self.main_controller.send_avc_command(command)

    def load_icon_list(self):
        folder = "assets/icons"
        os.makedirs(folder, exist_ok=True)
        return sorted([f[:-4] for f in os.listdir(folder) if f.endswith(".png")])


    #------------------ Matrix Functions----------------------

    def pick_matrix_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            r, g, b = color.red(), color.green(), color.blue()
            self.send_matrix_color(r, g, b)

    def send_matrix_color(self, r, g, b):
        hex_frame = "".join(f"{r:02X}{g:02X}{b:02X}" for _ in range(64 * 64))
        self.send_command(f"FM[{hex_frame}]")

    def send_matrix_rgb_frame(self, rgb_matrix):
        hex_data = "".join(f"{r:02X}{g:02X}{b:02X}" for row in rgb_matrix for r, g, b in row)
        self.send_command(f"FM[{hex_data}]")

    def send_matrix_animation_mode(self):
        index = self.matrix_anim_dropdown.currentIndex() + 1
        self.send_command(f"MM[{index}]")

    def upload_image_matrix(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.bmp)")
        if file_path:
            image = Image.open(file_path).convert("RGB").resize((64, 64))
            hex_data = "".join(f"{r:02X}{g:02X}{b:02X}" for y in range(64) for x in range(64) for r, g, b in [image.getpixel((x, y))])
            self.send_command(f"FM[{hex_data}]")

    def send_selected_icon_to_matrix(self):
        icon_name = self.icon_dropdown.currentText()
        icon_path = os.path.join("assets/icons", f"{icon_name}.png")
        if not os.path.exists(icon_path):
            print(f"[!] Icon '{icon_name}.png' not found.")
            return
        rgb_matrix = self.convert_image_to_rgb_matrix(icon_path)
        self.send_matrix_rgb_frame(rgb_matrix)

    def convert_image_to_rgb_matrix(self, path, width=64, height=64):
        img = Image.open(path).convert("RGB").resize((width, height))
        return [[img.getpixel((x, y)) for x in range(width)] for y in range(height)]

    def toggle_matrix_live_stream(self):
        if self.matrix_live_btn.isChecked():
            self.matrix_live_btn.setText("Stop Matrix Live Stream")
            self.start_matrix_stream()
        else:
            self.matrix_live_btn.setText("Start Matrix Live Stream")
            self.stop_matrix_stream()

    def start_matrix_stream(self):
        self.matrix_streaming = True
        self.matrix_frame_index = 0
        self.current_matrix_color = self.generate_random_color()
        self.matrix_timer = QTimer()
        self.matrix_timer.timeout.connect(self.send_matrix_stream_frame)
        self.matrix_timer.start(5)

    def stop_matrix_stream(self):
        self.matrix_streaming = False
        if hasattr(self, 'matrix_timer'):
            self.matrix_timer.stop()

    def send_matrix_stream_frame(self):
        if not self.matrix_streaming:
            return
        matrix = self.generate_matrix_frame()
        self.send_matrix_rgb_frame(matrix)
        self.matrix_frame_index += 1
        if self.matrix_frame_index >= 64 * 64:
            self.matrix_frame_index = 0
            self.current_matrix_color = self.generate_random_color()

    def generate_matrix_frame(self):
        matrix = [[(0, 0, 0) for _ in range(64)] for _ in range(64)]
        row = self.matrix_frame_index // 64
        col = self.matrix_frame_index % 64
        matrix[row][col] = self.current_matrix_color
        return matrix

    def generate_random_color(self):
        return random.choice([
            (255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0),
            (0, 255, 255), (0, 0, 255), (139, 0, 255)
        ])
    

    def play_gif_animation(self, gif_path, animation_name, x_offset=0, y_offset=0, frame_map=None):
        try:
            if frame_map is None:
                frame_map = {
                    "wake_up": (30, 43),
                    "idle": (65, 70),
                    "look_left": (75, 94),
                    "look_right": (95, 112),
                    "look around": (241, 300),
                    "sad": (0, 79),
                    "happy": (80, 159),
                    "blink": (160, 239),
                    "what": (431, 450),
                    "bye": (451, 479),
                    "center": (78, 78),
                    "left": (81, 81),
                    "right": (105, 105),

                }

            if animation_name not in frame_map:
                print(f"[Eyes] Animation '{animation_name}' not found in frame map.")
                return

            start_frame, end_frame = frame_map[animation_name]
            gif = Image.open(gif_path)
            full_matrix_width = 64
            full_matrix_height = 64

            for frame_index, frame in enumerate(ImageSequence.Iterator(gif)):
                if frame_index < start_frame:
                    continue
                if frame_index > end_frame:
                    break

                # Resize from 128x64 to 64x32
                frame = frame.convert("RGB").resize((64, 32))

                # Create black canvas and center the 64x32 frame
                full_matrix = [[(0, 0, 0) for _ in range(full_matrix_width)] for _ in range(full_matrix_height)]

                for y in range(32):
                    for x in range(64):
                        r, g, b = frame.getpixel((x, y))
                        target_y = y + y_offset
                        target_x = x + x_offset
                        if 0 <= target_x < full_matrix_width and 0 <= target_y < full_matrix_height:
                            full_matrix[target_y][target_x] = (r, g, b)

                # Convert to hex string and send to LED matrix
                hex_frame = "".join(f"{r:02X}{g:02X}{b:02X}" for row in full_matrix for (r, g, b) in row)
                self.send_command(f"FM[{hex_frame}]")

                # Frame delay (fallback = 50ms)
                delay_ms = frame.info.get("duration", 50)
                time.sleep(delay_ms / 1000.0)

        except Exception as e:
            print(f"[Eyes] Failed to play animation '{animation_name}': {e}")

    #------------------- NeoPixel Functions------------------

    def pick_neopixel_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            r, g, b, _ = color.getRgb()
            self.send_neopixel_color(r, g, b)

    def send_neopixel_color(self, r, g, b):
        frame = ""
        for _ in range(24):
            if abs(r - g) < 15 and abs(g - b) < 15:
                w = min(r, g, b)
                r, g, b = r - w, g - w, b - w
            else:
                w = 0
            frame += f"{w:02X}{r:02X}{g:02X}{b:02X}"
        self.send_command(f"FN[{frame}]")

    def send_neopixel_animation_mode(self):
        mode = self.anim_dropdown.currentIndex() + 1
        self.send_command(f"MN[{mode}]")

    def toogle_neopixel_live_stream(self):
        if self.live_stream_btn.isChecked():
            self.live_stream_btn.setText("Stop Live Stream")
            self.send_command("MN[0]")  # stream mode
            self.start_live_stream()
        else:
            self.live_stream_btn.setText("Start Live Stream")
            self.stop_live_stream()

    def start_live_stream(self):
        self.streaming = True
        self.pixel_buffer = [(0, 0, 0)] * 24
        self.falling_block = None
        self.last_fall_time = time.time()
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.send_stream_frame)
        self.stream_timer.start(16)

    def stop_live_stream(self):
        self.streaming = False
        if hasattr(self, 'stream_timer'):
            self.stream_timer.stop()

    def send_stream_frame(self):
        if not self.streaming:
            return
        filled = sum(1 for c in self.pixel_buffer if c != (0, 0, 0))
        normalized = 1 / 100.0  # Range: 0.01 to 1.0 n   # 1 = fastest, 100 = slowest
        fall_delay = max(0.02, 0.25 * normalized - (filled * 0.007))
        if time.time() - self.last_fall_time < fall_delay:
            return
        self.last_fall_time = time.time()

        if self.falling_block is None:
            if filled >= 24:
                self.pixel_buffer = [(0, 0, 0)] * 24
            self.falling_block = {
                "color": self.generate_random_color(),
                "position": 0
            }

        pos = self.falling_block["position"]
        while pos < 23 and self.pixel_buffer[pos + 1] == (0, 0, 0):
            pos += 1

        if pos > self.falling_block["position"]:
            self.falling_block["position"] += 1
        else:
            self.pixel_buffer[pos] = self.falling_block["color"]
            self.falling_block = None

        temp_buffer = self.pixel_buffer.copy()
        if self.falling_block:
            temp_buffer[self.falling_block["position"]] = self.falling_block["color"]

        frame = ""
        for r, g, b in temp_buffer:
            if abs(r - g) < 15 and abs(g - b) < 15:
                w = min(r, g, b)
                r, g, b = r - w, g - w, b - w
            else:
                w = 0
            frame += f"{w:02X}{r:02X}{g:02X}{b:02X}"

        self.send_command(f"FN[{frame}]")

    def generate_random_color(self):
        rainbow_palette = [
            (255, 0, 0),      # Red
            (255, 127, 0),    # Orange
            (255, 255, 0),    # Yellow
            (0, 255, 0),      # Green
            (0, 255, 255),    # Cyan
            (0, 0, 255),      # Blue
            (139, 0, 255),    # Violet
        ]
        return random.choice(rainbow_palette)