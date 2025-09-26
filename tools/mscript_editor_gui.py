
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import re

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

        if self.resource:
            self.id_var.set(self.resource[0])
            self.path_var.set(self.resource[1])

        return self.id_entry # initial focus

    def browse_path(self):
        initial_dir = os.path.dirname(self.script_path) if self.script_path else "."
        path = filedialog.askopenfilename(initialdir=initial_dir, title="Select Asset File")
        if path and self.script_path:
            # Make path relative to the script
            rel_path = os.path.relpath(path, os.path.dirname(self.script_path))
            self.path_var.set(rel_path.replace("\\", "/")) # Use forward slashes
        elif path:
            self.path_var.set(path)

    def apply(self):
        self.result = (self.id_var.get(), self.path_var.get())

class MscriptEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Mscript Editor")
        self.root.geometry("1000x700")

        self.current_script_path = None
        self.script_sections = {}
        self.resources = []

        # --- Main Layout ---
        main_frame = ttk.Frame(root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Top Controls ---
        top_controls = ttk.Frame(main_frame)
        top_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(top_controls, text="Load Script...", command=self.load_script).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_controls, text="Save", command=self.save_script).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(top_controls, text="Save As...", command=self.save_script_as).pack(side=tk.LEFT, padx=(0, 10))

        # --- Paned Window for Script and Resources ---
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Script Frame (Left) ---
        script_frame = ttk.LabelFrame(paned_window, text="Script")
        self.text_editor = MscriptTextEditor(script_frame)
        self.text_editor.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        paned_window.add(script_frame, weight=3)

        # --- Resource Frame (Right) ---
        resource_frame = ttk.LabelFrame(paned_window, text="Resources")
        self.resource_listbox = tk.Listbox(resource_frame, font=("Courier", 10))
        self.resource_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        resource_buttons = ttk.Frame(resource_frame)
        resource_buttons.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(resource_buttons, text="Add...", command=self.add_resource).pack(side=tk.LEFT)
        ttk.Button(resource_buttons, text="Edit...", command=self.edit_resource).pack(side=tk.LEFT)
        ttk.Button(resource_buttons, text="Remove", command=self.remove_resource).pack(side=tk.LEFT)
        paned_window.add(resource_frame, weight=1)

    def parse_sections(self, all_lines):
        sections = {}
        current_section = "_header"
        sections[current_section] = []
        section_regex = re.compile(r'^\[\s*(\w+)\s*(start|end)\s*\]$', re.IGNORECASE)

        for line in all_lines:
            match = section_regex.match(line.strip())
            if match:
                section_name, status = match.groups()
                section_name = section_name.lower()
                if status.lower() == 'start':
                    current_section = section_name
                    if current_section not in sections:
                        sections[current_section] = []
                elif status.lower() == 'end':
                    current_section = "_footer"
                    if current_section not in sections:
                        sections[current_section] = []
            else:
                sections.setdefault(current_section, []).append(line)
        return sections

    def load_script(self):
        script_path = filedialog.askopenfilename(title="Select Mscript File", filetypes=[("Mscript files", "*.mscript")], initialdir="mscripts")
        if not script_path: return
        try:
            with open(script_path, 'r') as f:
                all_lines = f.readlines()
            
            self.script_sections = self.parse_sections(all_lines)

            main_content = "".join(self.script_sections.get('main', [])).rstrip('\n')
            self.text_editor.set_text(main_content)

            self.resources = []
            resource_lines = self.script_sections.get('resources', [])
            for line in resource_lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    self.resources.append((parts[0].strip(), parts[1].strip().strip("'")))
            self.update_resource_list()

            self.current_script_path = script_path
            self.root.title(f"Mscript Editor - {os.path.basename(script_path)}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load script: {e}")

    def save_script(self):
        if self.current_script_path:
            self._write_script_to_file(self.current_script_path)
        else:
            self.save_script_as()

    def save_script_as(self):
        script_path = filedialog.asksaveasfilename(title="Save Mscript As", defaultextension=".mscript", filetypes=[("Mscript files", "*.mscript")], initialdir="mscripts")
        if not script_path: return
        self.current_script_path = script_path
        self.root.title(f"Mscript Editor - {os.path.basename(script_path)}")
        self._write_script_to_file(script_path)

    def _write_script_to_file(self, script_path):
        try:
            edited_main = self.text_editor.get("1.0", tk.END).rstrip('\n')
            self.script_sections['main'] = [l + '\n' for l in edited_main.split('\n')]

            resource_lines = [f"{res[0]}: '{res[1]}'\n" for res in self.resources]
            self.script_sections['resources'] = resource_lines

            with open(script_path, 'w') as f:
                if '_header' in self.script_sections:
                    f.writelines(self.script_sections['_header'])
                
                order = ['main', 'resources'] # Define section order
                for section_name in order:
                    if section_name in self.script_sections:
                        f.write(f"[{section_name.capitalize()} start]\n")
                        f.writelines(self.script_sections[section_name])
                        f.write(f"[{section_name.capitalize()} end]\n\n")

                if '_footer' in self.script_sections:
                    f.writelines(self.script_sections['_footer'])

            messagebox.showinfo("Success", f"Script saved to:\n{script_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def update_resource_list(self):
        self.resource_listbox.delete(0, tk.END)
        for res_id, res_path in self.resources:
            self.resource_listbox.insert(tk.END, f"{res_id}: '{res_path}'")

    def add_resource(self):
        dialog = ResourceEditorDialog(self.root, title="Add Resource", script_path=self.current_script_path)
        if dialog.result:
            self.resources.append(dialog.result)
            self.update_resource_list()

    def edit_resource(self):
        selected_index = self.resource_listbox.curselection()
        if not selected_index: return
        selected_resource = self.resources[selected_index[0]]
        
        dialog = ResourceEditorDialog(self.root, title="Edit Resource", resource=selected_resource, script_path=self.current_script_path)
        if dialog.result:
            self.resources[selected_index[0]] = dialog.result
            self.update_resource_list()

    def remove_resource(self):
        selected_index = self.resource_listbox.curselection()
        if not selected_index: return
        if messagebox.askyesno("Confirm", "Are you sure you want to remove this resource?"):
            del self.resources[selected_index[0]]
            self.update_resource_list()

if __name__ == "__main__":
    root = tk.Tk()
    app = MscriptEditor(root)
    root.mainloop()
