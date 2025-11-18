import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import zipfile
from collections import defaultdict

# =============================
# Data structures
# =============================

@dataclass
class EnumDef:
    name: str
    values: List[str] = field(default_factory=list)

@dataclass
class FieldDef:
    name: str
    type_name: str       # Base type (sin ?, sin [])
    is_optional: bool
    is_list: bool
    raw_line: str

@dataclass
class ModelDef:
    name: str
    fields: List[FieldDef] = field(default_factory=list)
    schema: Optional[str] = None

# =============================
# Parsing helpers
# =============================

SCALAR_TS_MAP: Dict[str, str] = {
    "String": "string",
    "Int": "number",
    "Float": "number",
    "Boolean": "boolean",
    "DateTime": "DateTimeString",
    "Json": "JsonValue",
    "BigInt": "number",
    "Decimal": "number",
}

def strip_line_comments(schema: str) -> str:
    lines = []
    for line in schema.splitlines():
        if "//" in line:
            line = line.split("//", 1)[0]
        lines.append(line)
    return "\n".join(lines)

def parse_prisma(schema: str):
    schema_no_comments = strip_line_comments(schema)
    lines = schema_no_comments.splitlines()

    enums: Dict[str, EnumDef] = {}
    models: Dict[str, ModelDef] = {}

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("model ") or line.startswith("enum "):
            parts = line.split()
            if len(parts) < 2:
                i += 1
                continue
            kind = parts[0]
            name = parts[1]

            # buscar '{'
            if "{" not in line:
                i += 1
                while i < len(lines) and "{" not in lines[i]:
                    i += 1
                i += 1
            else:
                i += 1

            body_lines = []
            while i < len(lines):
                current = lines[i]
                if current.strip() == "}":
                    break
                body_lines.append(current)
                i += 1

            if kind == "enum":
                enum = EnumDef(name=name)
                for raw in body_lines:
                    l = raw.strip()
                    if not l:
                        continue
                    if l.startswith("@@schema"):
                        # Podrías parsear el schema del enum si lo necesitas
                        continue
                    if l.startswith("@") or l.startswith("@@"):
                        continue
                    token = l.split()[0]
                    if token:
                        enum.values.append(token)
                enums[name] = enum

            elif kind == "model":
                model = ModelDef(name=name)
                schema_name: Optional[str] = None
                for raw in body_lines:
                    l = raw.strip()
                    if not l:
                        continue
                    if l.startswith("@@schema"):
                        m = re.search(r'@@schema\("([^"]+)"\)', l)
                        if m:
                            schema_name = m.group(1)
                        continue
                    if l.startswith("@") or l.startswith("@@"):
                        continue
                    parts_f = l.split()
                    if len(parts_f) < 2:
                        continue
                    field_name = parts_f[0]
                    type_token = parts_f[1]

                    is_optional = type_token.endswith("?")
                    raw_type = type_token[:-1] if is_optional else type_token
                    is_list = raw_type.endswith("[]")
                    base_type = raw_type[:-2] if is_list else raw_type

                    field_def = FieldDef(
                        name=field_name,
                        type_name=base_type,
                        is_optional=is_optional,
                        is_list=is_list,
                        raw_line=l,
                    )
                    model.fields.append(field_def)
                model.schema = schema_name
                models[name] = model

        i += 1

    return enums, models

# =============================
# TS generation helpers
# =============================

def prisma_field_to_ts(
    field: FieldDef,
    model_names: set,
    enum_names: set,
) -> str:
    base = field.type_name

    is_model = base in model_names
    is_enum = base in enum_names
    is_scalar = base in SCALAR_TS_MAP

    if is_scalar:
        ts_base = SCALAR_TS_MAP[base]
    elif is_enum:
        ts_base = base
    else:
        ts_base = base

    # Listas
    if field.is_list:
        ts_base_list = f"{ts_base}[]"
        # Arrays de modelos como Model[] | null
        if is_model:
            return f"{ts_base_list} | null"
        else:
            return ts_base_list

    # Escalares/enums opcionales
    if not is_model and field.is_optional:
        return f"{ts_base} | null"

    # Relaciones: siempre Model | null
    if is_model:
        return f"{ts_base} | null"

    # Escalar/enum requerido
    return ts_base

def prisma_field_to_ts_flat(
    field: FieldDef,
    enum_names: set,
) -> str:
    base = field.type_name

    is_enum = base in enum_names
    is_scalar = base in SCALAR_TS_MAP

    if is_scalar:
        ts_base = SCALAR_TS_MAP[base]
    elif is_enum:
        ts_base = base
    else:
        ts_base = "any"

    if field.is_list:
        ts_base_list = f"{ts_base}[]"
        if field.is_optional:
            return f"{ts_base_list} | null"
        return ts_base_list

    if field.is_optional:
        return f"{ts_base} | null"

    return ts_base

def generate_single_file(enums: Dict[str, EnumDef], models: Dict[str, ModelDef], generate_flat: bool) -> str:
    model_names = set(models.keys())
    enum_names = set(enums.keys())

    lines = []

    lines.append("// Auto-generated from Prisma schema.")
    lines.append("// Generated by Prisma TypeTags (single file).")
    lines.append("")
    lines.append("export type DateTimeString = string;")
    lines.append("export type JsonValue = any;")
    lines.append("")

    if enums:
        lines.append("// =========================")
        lines.append("// ENUM TYPES")
        lines.append("// =========================")
        lines.append("")
        for enum in enums.values():
            if not enum.values:
                continue
            values_union = " | ".join(f'"{v}"' for v in enum.values)
            lines.append(f"export type {enum.name} = {values_union};")
            lines.append("")

    # Forward declarations
    lines.append("// =========================")
    lines.append("// FORWARD DECLARATIONS")
    lines.append("// =========================")
    lines.append("")
    for model_name in models.keys():
        lines.append(f"export interface {model_name} {{}}")
    lines.append("")

    # Models
    lines.append("// =========================")
    lines.append("// MODELS")
    lines.append("// =========================")
    lines.append("")

    for model in models.values():
        lines.append(f"export interface {model.name} " + "{")
        for field in model.fields:
            ts_type = prisma_field_to_ts(field, model_names, enum_names)
            lines.append(f"  {field.name}: {ts_type};")
        lines.append("}")
        lines.append("")
        if generate_flat:
            lines.append(f"export interface {model.name}Flat " + "{")
            for field in model.fields:
                # solo campos no-relacionales
                if field.type_name in model_names:
                    continue
                ts_type_flat = prisma_field_to_ts_flat(field, enum_names)
                lines.append(f"  {field.name}: {ts_type_flat};")
            lines.append("}")
            lines.append("")
    return "\n".join(lines)

def generate_split_files(enums: Dict[str, EnumDef], models: Dict[str, ModelDef], generate_flat: bool, generate_index: bool) -> Dict[str, str]:
    files: Dict[str, str] = {}
    model_names = set(models.keys())
    enum_names = set(enums.keys())

    # common/base.ts
    base_lines = []
    base_lines.append("// Auto-generated by Prisma TypeTags")
    base_lines.append("// Common base types")
    base_lines.append("export type DateTimeString = string;")
    base_lines.append("export type JsonValue = any;")
    base_lines.append("")
    files["common/base.ts"] = "\n".join(base_lines)

    # common/enums.ts
    enums_lines = []
    enums_lines.append("// Auto-generated by Prisma TypeTags")
    enums_lines.append("// Enums for the whole schema")
    if enums:
        enums_lines.append("")
        for enum in enums.values():
            if not enum.values:
                continue
            values_union = " | ".join(f'"{v}"' for v in enum.values)
            enums_lines.append(f"export type {enum.name} = {values_union};")
            enums_lines.append("")
    files["common/enums.ts"] = "\n".join(enums_lines)

    # Partition models by schema
    models_by_schema: Dict[str, List[ModelDef]] = defaultdict(list)
    for m in models.values():
        key = m.schema or "default"
        models_by_schema[key].append(m)

    # Map model -> schema
    model_to_schema: Dict[str, str] = {}
    for schema_name, lst in models_by_schema.items():
        for m in lst:
            model_to_schema[m.name] = schema_name

    # Generate per-schema files
    for schema_name, schema_models in models_by_schema.items():
        lines: List[str] = []
        lines.append("// Auto-generated by Prisma TypeTags")
        lines.append("// Types for schema: " + schema_name)
        lines.append('import type { DateTimeString, JsonValue } from "../common/base";')
        if enums:
            # import all enums (más simple)
            enum_imports = ", ".join(sorted(enum_names))
            lines.append(f'import type {{ {enum_imports} }} from "../common/enums";')
        lines.append("")

        # Cross-schema model imports
        cross_imports: Dict[str, set] = defaultdict(set)
        for m in schema_models:
            for field in m.fields:
                if field.type_name in model_names:
                    other_schema = model_to_schema.get(field.type_name, schema_name)
                    if other_schema != schema_name:
                        cross_imports[other_schema].add(field.type_name)
        for other_schema, names in cross_imports.items():
            if not names:
                continue
            imported_names = ", ".join(sorted(names))
            lines.append(f'import type {{ {imported_names} }} from "../{other_schema}/models";')
        if cross_imports:
            lines.append("")

        # Models
        for m in schema_models:
            lines.append(f"export interface {m.name} " + "{")
            for field in m.fields:
                ts_type = prisma_field_to_ts(field, model_names, enum_names)
                lines.append(f"  {field.name}: {ts_type};")
            lines.append("}")
            lines.append("")
            if generate_flat:
                lines.append(f"export interface {m.name}Flat " + "{")
                for field in m.fields:
                    if field.type_name in model_names:
                        continue
                    ts_type_flat = prisma_field_to_ts_flat(field, enum_names)
                    lines.append(f"  {field.name}: {ts_type_flat};")
                lines.append("}")
                lines.append("")

        files[f"{schema_name}/models.ts"] = "\n".join(lines)

    # index.ts
    if generate_index:
        idx_lines: List[str] = []
        idx_lines.append('export * from "./common/base";')
        idx_lines.append('export * from "./common/enums";')
        for schema_name in sorted(models_by_schema.keys()):
            idx_lines.append(f'export * from "./{schema_name}/models";')
        idx_lines.append("")
        files["index.ts"] = "\n".join(idx_lines)

    return files

def prisma_to_ts(schema: str) -> str:
    enums, models = parse_prisma(schema)
    return generate_single_file(enums, models, generate_flat=False)

# =============================
# GUI
# =============================

class PrismaToTSApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Prisma → TypeScript (Tkinter GUI)")
        self.root.geometry("1200x750")

        self.generated_files: Dict[str, str] = {}
        self.preview_file: Optional[str] = None

        top_frame = tk.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.load_button = tk.Button(top_frame, text="Cargar schema.prisma", command=self.load_schema)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.generate_button = tk.Button(top_frame, text="Generar TypeScript", command=self.generate_ts)
        self.generate_button.pack(side=tk.LEFT, padx=5)

        self.save_ts_button = tk.Button(top_frame, text="Guardar archivo actual", command=self.save_ts)
        self.save_ts_button.pack(side=tk.LEFT, padx=5)

        self.save_zip_button = tk.Button(top_frame, text="Guardar ZIP", command=self.save_zip)
        self.save_zip_button.pack(side=tk.LEFT, padx=5)

        # Selects (OptionMenu) para opciones
        self.split_var = tk.StringVar(value="No")
        self.flat_var = tk.StringVar(value="No")
        self.index_var = tk.StringVar(value="No")

        tk.Label(top_frame, text="Dividir por schema:").pack(side=tk.LEFT, padx=(20, 2))
        tk.OptionMenu(top_frame, self.split_var, "No", "Sí").pack(side=tk.LEFT)

        tk.Label(top_frame, text="Tipos planos:").pack(side=tk.LEFT, padx=(10, 2))
        tk.OptionMenu(top_frame, self.flat_var, "No", "Sí").pack(side=tk.LEFT)

        tk.Label(top_frame, text="Generar index.ts:").pack(side=tk.LEFT, padx=(10, 2))
        tk.OptionMenu(top_frame, self.index_var, "No", "Sí").pack(side=tk.LEFT)

        self.status_label = tk.Label(top_frame, text="Listo.", anchor="w")
        self.status_label.pack(side=tk.LEFT, padx=20)

        paned = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_frame = tk.Frame(paned)
        right_frame = tk.Frame(paned)

        paned.add(left_frame, stretch="always")
        paned.add(right_frame, stretch="always")

        tk.Label(left_frame, text="Schema Prisma", anchor="w").pack(anchor="w")
        self.schema_text = ScrolledText(left_frame, wrap=tk.NONE)
        self.schema_text.pack(fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="TypeScript generado (preview)", anchor="w").pack(anchor="w")
        self.ts_text = ScrolledText(right_frame, wrap=tk.NONE)
        self.ts_text.pack(fill=tk.BOTH, expand=True)

    def load_schema(self):
        path = filedialog.askopenfilename(
            title="Selecciona el archivo schema.prisma",
            filetypes=[("Prisma schema", "*.prisma"), ("Todos los archivos", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.schema_text.delete("1.0", tk.END)
            self.schema_text.insert(tk.END, content)
            self.status_label.config(text=f"Schema cargado: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")

    def generate_ts(self):
        schema = self.schema_text.get("1.0", tk.END)
        if not schema.strip():
            messagebox.showwarning("Atención", "El área de schema Prisma está vacía.")
            return

        split_by_schema = self.split_var.get() == "Sí"
        generate_flat = self.flat_var.get() == "Sí"
        generate_index = self.index_var.get() == "Sí"

        try:
            enums, models = parse_prisma(schema)
            if split_by_schema:
                files = generate_split_files(enums, models, generate_flat, generate_index)
            else:
                main_ts = generate_single_file(enums, models, generate_flat)
                files = {"models.ts": main_ts}
                if generate_index:
                    files["index.ts"] = 'export * from "./models";\n'

            self.generated_files = files

            # elegir archivo de preview
            if "models.ts" in files:
                preview_name = "models.ts"
            elif "index.ts" in files:
                preview_name = "index.ts"
            else:
                preview_name = sorted(files.keys())[0]

            self.preview_file = preview_name

            header = "// Archivos generados:\n"
            for name in sorted(files.keys()):
                header += f"// - {name}\n"
            header += "\n"

            self.ts_text.delete("1.0", tk.END)
            self.ts_text.insert(tk.END, header + files[preview_name])
            self.status_label.config(text=f"TypeScript generado. Archivos: {len(files)}")
        except Exception as e:
            messagebox.showerror("Error", f"Ocurrió un problema al generar TS:\n{e}")

    def save_ts(self):
        if not self.generated_files or not self.preview_file:
            messagebox.showwarning("Atención", "No hay código TypeScript generado aún.")
            return
        ts_code = self.generated_files.get(self.preview_file, "")
        if not ts_code.strip():
            messagebox.showwarning("Atención", "El archivo de preview está vacío.")
            return
        path = filedialog.asksaveasfilename(
            title=f"Guardar {self.preview_file}",
            defaultextension=".ts",
            initialfile=self.preview_file,
            filetypes=[("TypeScript", "*.ts"), ("Todos los archivos", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(ts_code)
            self.status_label.config(text=f"{self.preview_file} guardado en: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el archivo:\n{e}")

    def save_zip(self):
        if not self.generated_files:
            messagebox.showwarning("Atención", "No hay archivos generados para guardar en ZIP.")
            return

        path = filedialog.asksaveasfilename(
            title="Guardar ZIP con archivos TS",
            defaultextension=".zip",
            filetypes=[("ZIP", "*.zip"), ("Todos los archivos", "*.*")]
        )
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, content in self.generated_files.items():
                    zf.writestr(name, content)
            self.status_label.config(text=f"ZIP guardado en: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar el ZIP:\n{e}")

def run_app():
    root = tk.Tk()
    app = PrismaToTSApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_app()
