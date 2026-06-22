"""
StudioWindow — Persona editor.

Loads/saves persona JSON files (HEXACO + SPECIAL + Expression + Domains
+ custom_instructions). Edits go through ``PersonaEditor``, a mutable
mirror of the frozen :class:`lilith.core.persona.Persona`. Saves to
``~/.lilith/profiles/active.json`` and publishes ``event/persona/changed``
so the bus adapter rebuilds the system prompt without a restart.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider,
    QPushButton, QComboBox, QPlainTextEdit, QLineEdit, QGroupBox, QFrame,
    QScrollArea, QFileDialog, QMessageBox,
)

# Every persona surface now lives in :mod:`lilith.core.persona`.
# The mutable ``PersonaEditor`` replaces the legacy
# ``CharacterProfile``: same field structure, but Studio mutates the
# editor and ``editor.to_persona()`` collapses to the frozen
# :class:`Persona` for the bus's persona-swap path. As of 2026-05-07
# this file no longer imports anything from the legacy ``lilith_ai``
# package.
from jaeger_os.core.persona import (
    PersonaEditor,
    active_persona_path,
    list_all_personas,
    save_persona,
    user_persona_library_dir,
)

from jaeger_os.instance.lilith.runtime.ui_bus import LilithSessionBus as QtBusClient

from ._brand import lilith_brand_icon


class TraitSlider(QWidget):
    """Slider 0-100 + value label, bound to a float 0.0-1.0."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.title = QLabel(label)
        self.title.setFixedWidth(140)
        self.title.setStyleSheet("font-size: 12px; color: #1F2937;")
        layout.addWidget(self.title)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        layout.addWidget(self.slider, stretch=1)

        self.value = QLabel("0.50")
        self.value.setFixedWidth(40)
        self.value.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(self.value)

        self.slider.valueChanged.connect(self._sync_label)

    def _sync_label(self, v: int):
        self.value.setText(f"{v / 100:.2f}")

    def get(self) -> float:
        return self.slider.value() / 100

    def set(self, v: float):
        self.slider.setValue(int(round(max(0.0, min(1.0, v)) * 100)))
        self._sync_label(self.slider.value())


def _slider_grid(title: str, names: list[str]) -> tuple[QGroupBox, dict[str, TraitSlider]]:
    box = QGroupBox(title)
    box.setStyleSheet(
        """
        QGroupBox {
            font-weight: 600;
            font-size: 12px;
            color: #1F2937;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            margin-top: 14px;
            padding: 10px 8px 8px 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        """
    )
    grid = QVBoxLayout(box)
    grid.setSpacing(2)
    sliders: dict[str, TraitSlider] = {}
    for n in names:
        s = TraitSlider(n)
        sliders[n] = s
        grid.addWidget(s)
    return box, sliders


HEXACO_FIELDS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism", "honesty_humility"]
SPECIAL_FIELDS = ["strength", "perception", "endurance", "charisma", "intelligence", "agility", "luck"]
EXPRESSION_FIELDS = ["sarcasm", "warmth", "verbosity", "formality", "directness", "humor", "empathy", "aggression"]
DOMAIN_FIELDS = ["science", "philosophy", "combat", "art", "politics", "technology", "nature", "psychology"]


class StudioWindow(QWidget):
    def __init__(self, bus: QtBusClient, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.setWindowTitle("Lilith — Persona Studio")
        self.setWindowIcon(lilith_brand_icon())
        self.resize(820, 760)
        self.setStyleSheet("QWidget { background: #FFFFFF; } QLabel { color: #1F2937; }")

        self.profile: PersonaEditor = PersonaEditor()
        self._build_ui()
        self._load_initial_profile()

    # -- UI -----------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header / library picker
        header = QFrame()
        header.setStyleSheet("background: #FAFAFA; border-bottom: 1px solid #E5E7EB;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 10, 16, 10)
        h_layout.setSpacing(8)

        title = QLabel("Persona Studio")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        h_layout.addWidget(QLabel("Library:"))
        self.library_combo = QComboBox()
        self.library_combo.setMinimumWidth(220)
        self._refresh_library()
        h_layout.addWidget(self.library_combo)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_from_library)
        h_layout.addWidget(load_btn)

        open_btn = QPushButton("Open File…")
        open_btn.clicked.connect(self._open_file)
        h_layout.addWidget(open_btn)

        root.addWidget(header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        body_layout.setSpacing(8)

        # Meta: name + description
        meta_box = QGroupBox("Identity")
        meta_box.setStyleSheet(self._group_style())
        meta_layout = QGridLayout(meta_box)
        meta_layout.addWidget(QLabel("Name"), 0, 0)
        self.name_edit = QLineEdit()
        meta_layout.addWidget(self.name_edit, 0, 1)
        meta_layout.addWidget(QLabel("Description"), 1, 0)
        self.desc_edit = QLineEdit()
        meta_layout.addWidget(self.desc_edit, 1, 1)
        body_layout.addWidget(meta_box)

        # Custom instructions
        instr_box = QGroupBox("Custom Instructions (highest-priority guidance)")
        instr_box.setStyleSheet(self._group_style())
        instr_layout = QVBoxLayout(instr_box)
        self.instructions_edit = QPlainTextEdit()
        self.instructions_edit.setPlaceholderText(
            "Override block injected at the bottom of the system prompt. "
            "Use this for explicit behavior rules the slider system can't encode."
        )
        self.instructions_edit.setFixedHeight(120)
        instr_layout.addWidget(self.instructions_edit)
        body_layout.addWidget(instr_box)

        # Slider groups
        hexaco_box, self.hexaco_sliders = _slider_grid("HEXACO", HEXACO_FIELDS)
        special_box, self.special_sliders = _slider_grid("S.P.E.C.I.A.L.", SPECIAL_FIELDS)
        expression_box, self.expression_sliders = _slider_grid("Expression", EXPRESSION_FIELDS)
        domains_box, self.domain_sliders = _slider_grid("Domains", DOMAIN_FIELDS)

        slider_row1 = QHBoxLayout()
        slider_row1.addWidget(hexaco_box, stretch=1)
        slider_row1.addWidget(special_box, stretch=1)
        body_layout.addLayout(slider_row1)

        slider_row2 = QHBoxLayout()
        slider_row2.addWidget(expression_box, stretch=1)
        slider_row2.addWidget(domains_box, stretch=1)
        body_layout.addLayout(slider_row2)

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # Footer / actions
        footer = QFrame()
        footer.setStyleSheet("background: #FAFAFA; border-top: 1px solid #E5E7EB;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(16, 10, 16, 10)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #6B7280; font-size: 11px;")
        f_layout.addWidget(self.status)
        f_layout.addStretch()

        save_as_btn = QPushButton("Save As…")
        save_as_btn.clicked.connect(self._save_as)
        f_layout.addWidget(save_as_btn)

        apply_btn = QPushButton("Save & Apply")
        apply_btn.setStyleSheet(
            """
            QPushButton {
                background: #007AFF;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover { background: #0A84FF; }
            """
        )
        apply_btn.clicked.connect(self._apply)
        f_layout.addWidget(apply_btn)

        root.addWidget(footer)

    def _group_style(self) -> str:
        return """
        QGroupBox {
            font-weight: 600;
            font-size: 12px;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            margin-top: 14px;
            padding: 10px 8px 8px 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 6px;
        }
        QLineEdit, QPlainTextEdit {
            background: #F7F7F8;
            border: 1px solid #E5E7EB;
            border-radius: 6px;
            padding: 6px 8px;
            font-size: 13px;
        }
        """

    # -- profile load/save --------------------------------------------------
    def _refresh_library(self):
        self.library_combo.clear()
        for label, path in list_all_personas():
            self.library_combo.addItem(label, str(path))

    def _load_initial_profile(self):
        self._load_profile_from(str(active_persona_path()))

    def _load_from_library(self):
        path = self.library_combo.currentData()
        if path:
            self._load_profile_from(path)

    def _open_file(self):
        start_dir = str(user_persona_library_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Open profile", start_dir, "JSON (*.json)")
        if path:
            self._load_profile_from(path)

    def _load_profile_from(self, path: str):
        try:
            self.profile = PersonaEditor.from_path(path)
        except Exception as e:
            QMessageBox.warning(self, "Load failed", f"Could not load {path}:\n{e}")
            return
        self._populate_from_profile()
        self._set_status(f"Loaded {os.path.basename(path)}")

    def _populate_from_profile(self):
        m = self.profile.meta
        self.name_edit.setText(m.name or "")
        self.desc_edit.setText(m.description or "")
        self.instructions_edit.setPlainText(m.custom_instructions or "")

        for k, s in self.hexaco_sliders.items():
            s.set(getattr(self.profile.hexaco, k, 0.5))
        for k, s in self.special_sliders.items():
            s.set(getattr(self.profile.special, k, 0.5))
        for k, s in self.expression_sliders.items():
            s.set(getattr(self.profile.expression, k, 0.5))
        for k, s in self.domain_sliders.items():
            s.set(getattr(self.profile.domains, k, 0.5))

    def _harvest_into_profile(self):
        self.profile.meta.name = self.name_edit.text().strip() or "Lilith"
        self.profile.meta.description = self.desc_edit.text().strip()
        self.profile.meta.custom_instructions = self.instructions_edit.toPlainText().strip()
        for k, s in self.hexaco_sliders.items():
            setattr(self.profile.hexaco, k, s.get())
        for k, s in self.special_sliders.items():
            setattr(self.profile.special, k, s.get())
        for k, s in self.expression_sliders.items():
            setattr(self.profile.expression, k, s.get())
        for k, s in self.domain_sliders.items():
            setattr(self.profile.domains, k, s.get())

    def _save_as(self):
        self._harvest_into_profile()
        suggested = str(user_persona_library_dir() / f"{self.profile.meta.name.lower()}.json")
        path, _ = QFileDialog.getSaveFileName(self, "Save profile", suggested, "JSON (*.json)")
        if not path:
            return
        try:
            save_persona(self.profile, path)
            self._refresh_library()
            self._set_status(f"Saved to {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def _apply(self):
        """Save to ~/.lilith/profiles/active.json and tell LLMNode to hot-reload."""
        self._harvest_into_profile()
        active = active_persona_path()
        try:
            save_persona(self.profile, active)
            # LLMNode resolves absolute paths verbatim.
            self.bus.publish("event/persona/changed", {"profile_path": str(active)})
            self._set_status(f"Applied — published event/persona/changed ({active.name})")
        except Exception as e:
            QMessageBox.warning(self, "Apply failed", str(e))

    # -- helpers ------------------------------------------------------------
    def _set_status(self, text: str):
        self.status.setText(text)

    def closeEvent(self, event):
        # Hide instead of destroy so reopening preserves the loaded profile.
        event.ignore()
        self.hide()
