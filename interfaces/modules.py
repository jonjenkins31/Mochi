"""Exact imported-module inventory for the Interface app."""

from __future__ import annotations

import pathlib
from typing import Any

from jaeger_os.core.modules import discover_modules


def _provider_name(factory: str) -> str:
    """Top-level import package named by a ``module:factory`` reference."""
    module_path = (factory or "").partition(":")[0]
    return module_path.split(".")[0] if module_path else ""


def _package_import_name(package: str) -> str:
    """Best import spelling for an install package that is not present yet."""
    return (package or "").strip().replace("-", "_")


def module_inventory(
    app: Any, discovered: dict[str, list[Any]] | None = None,
) -> list[dict[str, Any]]:
    """Describe selected and available slot providers without importing them."""
    if discovered is None:
        discovered = discover_modules(project_dir=getattr(app, "root", None))

    nodes = list(getattr(getattr(app, "spec", None), "nodes", ()) or ())
    by_slot = {node.slot: node for node in nodes if getattr(node, "slot", "")}
    states: dict[str, str] = {}
    supervisor = getattr(app, "supervisor", None)
    if supervisor is not None:
        try:
            states = {row["id"]: row["state"] for row in supervisor.ls()}
        except Exception:  # noqa: BLE001
            states = {}

    rows: list[dict[str, Any]] = []
    all_slots = sorted(set(discovered) | set(by_slot))
    for slot in all_slots:
        node = by_slot.get(slot)
        candidates = list(discovered.get(slot, ()))
        selected = None
        if node is not None and candidates:
            selected = next(
                (candidate for candidate in candidates
                 if candidate.factory == getattr(node, "factory", "")),
                sorted(candidates, key=lambda candidate: candidate.module)[0],
            )

        if not candidates and node is not None:
            rows.append({
                "slot": slot,
                "id": "",
                "name": "",
                "type": "module",
                "implementation": "",
                "provider": (
                    _provider_name(getattr(node, "factory", ""))
                    or _package_import_name(getattr(node, "package", ""))
                    or "not_installed"
                ),
                "module": "",
                "version": "",
                "state": "missing" if getattr(node, "enabled", True) else "unavailable",
                "factory": getattr(node, "factory", ""),
                "source": "",
                "kind": "",
                "selected": True,
                "consumes": [], "produces": [], "tools": [],
            })
            continue

        for candidate in candidates:
            is_selected = candidate is selected
            if is_selected and node is not None:
                state = states.get(node.id)
                if not state:
                    state = "unavailable" if not node.enabled else "declared"
            else:
                state = "available"
            rows.append({
                "slot": slot,
                "id": getattr(candidate, "id", ""),
                "name": getattr(candidate, "name", ""),
                "type": getattr(candidate, "type", "module"),
                "implementation": getattr(candidate, "implementation", ""),
                "provider": _provider_name(candidate.factory),
                "module": candidate.module,
                "version": candidate.version,
                "state": state,
                "factory": candidate.factory,
                "source": str(candidate.source_dir or ""),
                "kind": candidate.kind,
                "selected": is_selected,
                "consumes": list(candidate.consumes),
                "produces": list(candidate.produces),
                "tools": list(candidate.tools),
            })
    return sorted(rows, key=lambda row: (row["slot"], not row["selected"], row["provider"]))


class ModulesTab:
    """Shows which concrete installed package fills every capability slot."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets
        self.app = app
        self._discovered = None
        self._rows: list[dict[str, Any]] = []

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        heading = QtWidgets.QHBoxLayout()
        text = QtWidgets.QLabel(
            "Concrete imported providers selected by JaegerOS module discovery")
        text.setStyleSheet("font-size:14px; color:#e0e0e8;")
        heading.addWidget(text)
        heading.addStretch(1)
        refresh = QtWidgets.QPushButton("Refresh discovery")
        refresh.clicked.connect(self.refresh_discovery)
        heading.addWidget(refresh)
        layout.addLayout(heading)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(
            ["Slot", "Imported provider", "Module", "Version", "State", "Source"])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.currentItemChanged.connect(self._show_details)
        splitter.addWidget(self.table)

        details_group = QtWidgets.QGroupBox("Selected module details")
        details_layout = QtWidgets.QVBoxLayout(details_group)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details)
        splitter.addWidget(details_group)
        splitter.setSizes([430, 210])
        layout.addWidget(splitter, 1)

        self.status = QtWidgets.QLabel()
        self.status.setStyleSheet("color:#777784;")
        layout.addWidget(self.status)

        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self.refresh_runtime)
        self._timer.start(1000)
        self.refresh_discovery()

    def refresh_discovery(self) -> None:
        try:
            self._discovered = discover_modules(
                project_dir=getattr(self.app, "root", pathlib.Path.cwd()))
            self.refresh_runtime()
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Discovery failed: {exc}")

    def refresh_runtime(self) -> None:
        if self._discovered is None:
            return
        selected_key = None
        current = self.table.currentItem()
        if current is not None:
            selected_key = (current.text(0), current.text(1))
        rows = module_inventory(self.app, self._discovered)
        # Only rebuild when the inventory actually changed. Rebuilding
        # starts with clear(), which drops the tree to zero rows, and Qt's
        # accessibility bridge answers an empty model by asking for row 0
        # anyway — once a second, forever:
        #   qt.accessibility.table: Cell requested for row 0 is out of
        #   bounds for table with 0 rows! Resizing table model.
        # Modules change when one is installed or a node changes state,
        # which is not once a second. Not rebuilding also stops the tick
        # from eating the user's selection and scroll position.
        if rows == self._rows and self.table.topLevelItemCount():
            return
        self._rows = rows
        self.table.blockSignals(True)
        self.table.clear()
        selected_item = None
        for index, row in enumerate(self._rows):
            item = self._QtWidgets.QTreeWidgetItem([
                row["slot"], row["provider"], row["module"], row["version"],
                row["state"], row["source"],
            ])
            item.setData(0, self._QtCore.Qt.UserRole, index)
            if row["selected"]:
                font = item.font(1)
                font.setBold(True)
                item.setFont(1, font)
                item.setForeground(4, self._QtGui.QColor("#75d69c"))
            else:
                item.setForeground(4, self._QtGui.QColor("#777784"))
            self.table.addTopLevelItem(item)
            if selected_key == (row["slot"], row["provider"]):
                selected_item = item
        self.table.blockSignals(False)
        for column in range(5):
            self.table.resizeColumnToContents(column)
        if selected_item is None and self.table.topLevelItemCount():
            selected_item = self.table.topLevelItem(0)
        if selected_item is not None:
            self.table.setCurrentItem(selected_item)
            self._show_details(selected_item)
        active = sum(1 for row in self._rows if row["selected"])
        self.status.setText(
            f"{active} selected slot provider{'s' if active != 1 else ''}; "
            f"{len(self._rows)} discovered module{'s' if len(self._rows) != 1 else ''}")

    def _show_details(self, current: Any, _previous: Any = None) -> None:
        if current is None:
            self.details.clear()
            return
        index = current.data(0, self._QtCore.Qt.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self._rows):
            return
        row = self._rows[index]
        lines = [
            f"name: {row['name'] or row['module'] or 'unknown'}",
            f"ecosystem id: {row['id'] or 'unassigned'}",
            f"type: {row['type']}",
            f"implementation: {row['implementation'] or 'unspecified'}",
            f"provider: {row['provider']}",
            f"declared module: {row['module']}",
            f"slot: {row['slot']}",
            f"kind: {row['kind'] or 'unspecified'}",
            f"version: {row['version'] or 'unknown'}",
            f"state: {row['state']}",
            f"factory: {row['factory'] or 'none'}",
            f"source: {row['source'] or 'not installed'}",
            "",
            "consumes:", *[f"  {topic}" for topic in row["consumes"]],
            "produces:", *[f"  {topic}" for topic in row["produces"]],
            "tools:", *[f"  {tool}" for tool in row["tools"]],
        ]
        self.details.setPlainText("\n".join(lines))

    def close(self) -> None:
        self._timer.stop()


__all__ = ["ModulesTab", "module_inventory"]
