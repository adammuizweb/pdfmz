import io
import os
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter


# =========================
# Konfigurasi aplikasi
# =========================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_NAME = "PDFMZ"
APP_VERSION = "v1.2.0 Preview Select"

CUT_OUTPUT_MODE_MAP = {
    "Gabung jadi 1 PDF": "merge",
    "Pisah per halaman": "split",
    "Auto group berurutan": "auto_group",
}

MODE_THEMES = {
    "cut": {
        "name": "Potong PDF",
        "emoji": "✂️",
        "primary": "#ef4444",
        "hover": "#dc2626",
        "main_bg": "#241717",
        "main_card": "#321d1d",
        "main_card_soft": "#3a1f1f",
        "border": "#7f1d1d",
        "text": "#fecaca",
        "muted": "#fca5a5",
        "status": "#f87171",
    },
    "image": {
        "name": "Convert ke Gambar",
        "emoji": "🖼️",
        "primary": "#22c55e",
        "hover": "#16a34a",
        "main_bg": "#16251a",
        "main_card": "#1d3525",
        "main_card_soft": "#24412e",
        "border": "#166534",
        "text": "#bbf7d0",
        "muted": "#86efac",
        "status": "#4ade80",
    },
}

NEUTRAL = {
    "app_bg": "#101010",
    "header_bg": "#171717",
    "panel_bg": "#262626",
    "card_bg": "#202020",
    "card_soft": "#2b2b2b",
    "soft": "#3f3f46",
    "soft_hover": "#52525b",
    "text": "#f4f4f5",
    "muted": "#a3a3a3",
    "line": "#3f3f46",
    "blue": "#2563eb",
    "blue_hover": "#1d4ed8",
}


# =========================
# Helper umum
# =========================

def parse_page_ranges(text: str, total_pages: int) -> list[int]:
    """
    Input contoh:
    - "1-3"     -> halaman 1 sampai 3
    - "1,3,5"   -> halaman 1, 3, dan 5
    - "1-3,7"   -> halaman 1, 2, 3, dan 7

    Output berupa index halaman mulai dari 0.
    """
    pages = []
    text = text.replace(" ", "")

    if not text:
        raise ValueError("Masukkan halaman yang ingin diproses.")

    for part in text.split(","):
        if not part:
            continue

        if "-" in part:
            start, end = part.split("-", 1)

            if not start.isdigit() or not end.isdigit():
                raise ValueError(f"Format halaman tidak valid: {part}")

            start = int(start)
            end = int(end)

            if start > end:
                raise ValueError(f"Range tidak valid: {part}")

            pages.extend(range(start, end + 1))
        else:
            if not part.isdigit():
                raise ValueError(f"Format halaman tidak valid: {part}")

            pages.append(int(part))

    if not pages:
        raise ValueError("Masukkan minimal satu halaman.")

    for page in pages:
        if page < 1 or page > total_pages:
            raise ValueError(
                f"Halaman {page} di luar batas. PDF ini hanya punya {total_pages} halaman."
            )

    unique_pages = []
    for page in pages:
        if page not in unique_pages:
            unique_pages.append(page)

    return [page - 1 for page in unique_pages]


def indices_to_page_range_text(indices: list[int]) -> str:
    """Ubah index 0-based menjadi teks halaman seperti: 1,3-6,8-9."""
    if not indices:
        return ""

    pages = sorted(set(index + 1 for index in indices))
    ranges = []
    start = pages[0]
    prev = pages[0]

    for page in pages[1:]:
        if page == prev + 1:
            prev = page
        else:
            ranges.append(str(start) if start == prev else f"{start}-{prev}")
            start = page
            prev = page

    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(ranges)


def group_consecutive_indices(indices: list[int]) -> list[list[int]]:
    """Group halaman berurutan. Input dan output menggunakan index 0-based."""
    if not indices:
        return []

    sorted_indices = sorted(set(indices))
    groups = [[sorted_indices[0]]]

    for index in sorted_indices[1:]:
        if index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])

    return groups


def page_group_label(indices: list[int]) -> str:
    pages = [index + 1 for index in indices]
    if len(pages) == 1:
        return str(pages[0])
    return f"{pages[0]}-{pages[-1]}"


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def safe_filename(name: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "_")
    return name.strip() or "output"


def open_folder(path: str):
    if not path:
        return

    path = os.path.abspath(path)

    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


# =========================
# Core PDF logic
# =========================

def read_pdf_info(pdf_path: str) -> tuple[int, int]:
    with open(pdf_path, "rb") as file:
        pdf_bytes = file.read()

    reader = PdfReader(io.BytesIO(pdf_bytes))

    if reader.is_encrypted:
        raise ValueError("PDF terenkripsi/password protected belum didukung.")

    return len(reader.pages), len(pdf_bytes)


def write_selected_pdf(
    reader: PdfReader,
    page_indices: list[int],
    output_path: str,
    compress: bool = True,
) -> None:
    writer = PdfWriter()

    for page_index in page_indices:
        writer.add_page(reader.pages[page_index])

    if compress:
        for page in writer.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass

    with open(output_path, "wb") as output_file:
        writer.write(output_file)


def cut_pdf_outputs(
    pdf_path: str,
    output_folder: str,
    output_name: str,
    page_range_text: str,
    compress: bool,
    output_mode: str,
) -> tuple[int, int, list[str]]:
    with open(pdf_path, "rb") as file:
        pdf_bytes = file.read()

    reader = PdfReader(io.BytesIO(pdf_bytes))

    if reader.is_encrypted:
        raise ValueError("PDF terenkripsi/password protected belum didukung.")

    selected_pages = parse_page_ranges(page_range_text, len(reader.pages))

    if not output_name.lower().endswith(".pdf"):
        output_name += ".pdf"

    output_name = safe_filename(output_name)
    base_name = safe_filename(Path(output_name).stem)
    output_paths = []

    if output_mode == "merge":
        output_path = os.path.join(output_folder, output_name)
        write_selected_pdf(reader, selected_pages, output_path, compress)
        output_paths.append(output_path)

    elif output_mode == "split":
        for page_index in selected_pages:
            label = page_index + 1
            output_path = os.path.join(output_folder, f"{base_name}_halaman_{label}.pdf")
            write_selected_pdf(reader, [page_index], output_path, compress)
            output_paths.append(output_path)

    elif output_mode == "auto_group":
        groups = group_consecutive_indices(selected_pages)

        for group in groups:
            label = page_group_label(group)
            output_path = os.path.join(output_folder, f"{base_name}_halaman_{label}.pdf")
            write_selected_pdf(reader, group, output_path, compress)
            output_paths.append(output_path)

    else:
        raise ValueError("Mode hasil potong PDF tidak valid.")

    total_output_size = sum(os.path.getsize(path) for path in output_paths)
    return len(pdf_bytes), total_output_size, output_paths


def pdf_page_to_image(
    doc: fitz.Document,
    page_index: int,
    image_format: str,
    zoom: float,
    compress_image: bool,
    image_quality: int,
    resize_image: bool,
    max_width: int,
) -> bytes:
    page = doc.load_page(page_index)
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    if resize_image and image.width > max_width:
        ratio = max_width / image.width
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height), Image.LANCZOS)

    output = io.BytesIO()
    image_format = image_format.upper()

    if image_format == "JPG":
        image.save(
            output,
            format="JPEG",
            quality=image_quality if compress_image else 95,
            optimize=True,
        )
    elif image_format == "PNG":
        image.save(
            output,
            format="PNG",
            optimize=compress_image,
            compress_level=9 if compress_image else 6,
        )
    elif image_format == "WEBP":
        image.save(
            output,
            format="WEBP",
            quality=image_quality if compress_image else 95,
            method=6 if compress_image else 4,
        )
    else:
        raise ValueError("Format gambar tidak didukung.")

    output.seek(0)
    return output.read()


def render_pdf_thumbnail(doc: fitz.Document, page_index: int, max_width: int = 132, max_height: int = 178) -> Image.Image:
    page = doc.load_page(page_index)
    rect = page.rect
    zoom = min(max_width / rect.width, max_height / rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def convert_pdf_to_images_file(
    pdf_path: str,
    output_folder: str,
    page_range_text: str,
    image_format: str,
    zoom: float,
    compress_image: bool,
    image_quality: int,
    resize_image: bool,
    max_width: int,
    zip_result: bool,
) -> tuple[int, list[str]]:
    doc = fitz.open(pdf_path)

    selected_pages = parse_page_ranges(page_range_text, len(doc))
    image_format = image_format.upper()

    extension_map = {
        "JPG": "jpg",
        "PNG": "png",
        "WEBP": "webp",
    }

    extension = extension_map[image_format]
    output_paths = []
    base_name = safe_filename(Path(pdf_path).stem)

    for page_index in selected_pages:
        image_bytes = pdf_page_to_image(
            doc=doc,
            page_index=page_index,
            image_format=image_format,
            zoom=zoom,
            compress_image=compress_image,
            image_quality=image_quality,
            resize_image=resize_image,
            max_width=max_width,
        )

        image_name = f"{base_name}_halaman_{page_index + 1}.{extension}"
        image_path = os.path.join(output_folder, image_name)

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        output_paths.append(image_path)

    doc.close()

    if zip_result and output_paths:
        zip_path = os.path.join(output_folder, f"{base_name}_gambar.zip")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for image_path in output_paths:
                zip_file.write(image_path, arcname=os.path.basename(image_path))

        return os.path.getsize(zip_path), [zip_path]

    total_size = sum(os.path.getsize(path) for path in output_paths)
    return total_size, output_paths


# =========================
# UI Desktop App
# =========================

class PDFMZApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PDFMZ - Desktop PDF Tool")
        self.geometry("1100x760")
        self.minsize(960, 680)
        self.configure(fg_color=NEUTRAL["app_bg"])

        self.pdf_path = ctk.StringVar(value="")
        self.output_folder = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.mode = ctk.StringVar(value="cut")
        self.cut_output_mode = ctk.StringVar(value="Gabung jadi 1 PDF")

        self.total_pages = 0
        self.original_size = 0
        self.last_output_folder = self.output_folder.get()

        self.quality_slider = None
        self.quality_label = None
        self.zoom_label = None

        self._build_ui()
        self._update_mode_ui()

    # ---------- UI building blocks ----------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_main_area()

    def _build_header(self):
        self.header = ctk.CTkFrame(self, corner_radius=0, fg_color=NEUTRAL["header_bg"])
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.grid_columnconfigure(1, weight=1)

        self.header_icon = ctk.CTkLabel(
            self.header,
            text="📄",
            font=ctk.CTkFont(size=42),
            width=72,
            text_color=NEUTRAL["text"],
        )
        self.header_icon.grid(row=0, column=0, rowspan=2, padx=(24, 10), pady=22, sticky="w")

        self.header_title = ctk.CTkLabel(
            self.header,
            text=APP_NAME,
            font=ctk.CTkFont(size=38, weight="bold"),
            anchor="w",
            text_color=NEUTRAL["text"],
        )
        self.header_title.grid(row=0, column=1, padx=(0, 24), pady=(24, 0), sticky="ew")

        self.header_subtitle = ctk.CTkLabel(
            self.header,
            text="Potong PDF dan ubah PDF ke gambar dengan mudah.",
            font=ctk.CTkFont(size=15),
            anchor="w",
            text_color=NEUTRAL["muted"],
        )
        self.header_subtitle.grid(row=1, column=1, padx=(0, 24), pady=(0, 24), sticky="ew")

        self.version_label = ctk.CTkLabel(
            self.header,
            text=APP_VERSION,
            font=ctk.CTkFont(size=13),
            text_color=NEUTRAL["muted"],
        )
        self.version_label.grid(row=0, column=2, padx=24, pady=(28, 0), sticky="ne")

    def _build_main_area(self):
        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=1, column=0, padx=24, pady=20, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=0)
        self.main_area.grid_columnconfigure(1, weight=1)
        self.main_area.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(
            self.main_area,
            width=360,
            corner_radius=18,
            fg_color=NEUTRAL["panel_bg"],
        )
        self.left_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        self.left_panel.grid_propagate(False)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.right_panel = ctk.CTkFrame(self.main_area, corner_radius=18)
        self.right_panel.grid(row=0, column=1, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=0)
        self.right_panel.grid_rowconfigure(1, weight=0)
        self.right_panel.grid_rowconfigure(2, weight=1)
        self.right_panel.grid_rowconfigure(3, weight=0)

        self._build_left_panel(self.left_panel)
        self._build_right_panel(self.right_panel)

    def _build_left_panel(self, parent):
        self.step1_badge, self.step1_label = self._section_title(parent, "1", "Pilih file PDF", 0)

        self.choose_pdf_btn = ctk.CTkButton(
            parent,
            text="📄  Pilih File PDF",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.select_pdf,
        )
        self.choose_pdf_btn.grid(row=1, column=0, padx=16, pady=(8, 8), sticky="ew")

        self.file_card = ctk.CTkFrame(parent, corner_radius=14, fg_color=NEUTRAL["card_bg"])
        self.file_card.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="ew")
        self.file_card.grid_columnconfigure(0, weight=1)

        self.file_name_label = ctk.CTkLabel(
            self.file_card,
            text="Belum ada PDF dipilih",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=285,
            text_color=NEUTRAL["text"],
        )
        self.file_name_label.grid(row=0, column=0, padx=14, pady=(12, 3), sticky="ew")

        self.file_info_label = ctk.CTkLabel(
            self.file_card,
            text="Pilih PDF untuk mulai memproses file.",
            anchor="w",
            justify="left",
            wraplength=285,
            text_color=NEUTRAL["muted"],
        )
        self.file_info_label.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")

        self.step2_badge, self.step2_label = self._section_title(parent, "2", "Pilih fitur", 3)

        self.feature_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.feature_frame.grid(row=4, column=0, padx=16, pady=(8, 14), sticky="ew")
        self.feature_frame.grid_columnconfigure(0, weight=1)

        self.cut_mode_btn = ctk.CTkButton(
            self.feature_frame,
            text="✂️  Potong PDF\nAmbil halaman tertentu",
            height=66,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.set_mode("cut"),
        )
        self.cut_mode_btn.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.image_mode_btn = ctk.CTkButton(
            self.feature_frame,
            text="🖼️  Convert ke Gambar\nJPG, PNG, atau WEBP",
            height=66,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda: self.set_mode("image"),
        )
        self.image_mode_btn.grid(row=1, column=0, sticky="ew")

        self.step3_badge, self.step3_label = self._section_title(parent, "3", "Folder hasil", 5)

        self.folder_card = ctk.CTkFrame(parent, corner_radius=14, fg_color=NEUTRAL["card_bg"])
        self.folder_card.grid(row=6, column=0, padx=16, pady=(8, 14), sticky="ew")
        self.folder_card.grid_columnconfigure(0, weight=1)

        self.folder_label = ctk.CTkLabel(
            self.folder_card,
            text=self.output_folder.get(),
            anchor="w",
            justify="left",
            wraplength=285,
            text_color=NEUTRAL["text"],
        )
        self.folder_label.grid(row=0, column=0, padx=14, pady=(12, 8), sticky="ew")

        self.change_folder_btn = ctk.CTkButton(
            self.folder_card,
            text="📁  Ganti Folder Output",
            command=self.select_output_folder,
            height=36,
        )
        self.change_folder_btn.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")

        self.tips_card = ctk.CTkFrame(parent, corner_radius=14, fg_color=NEUTRAL["card_soft"])
        self.tips_card.grid(row=7, column=0, padx=16, pady=(0, 14), sticky="ew")
        self.tips_card.grid_columnconfigure(0, weight=1)

        self.tips_label = ctk.CTkLabel(
            self.tips_card,
            text="Tips: gunakan 1-3 untuk range, atau 1,3,5 untuk halaman pilihan.",
            text_color=NEUTRAL["muted"],
            anchor="w",
            justify="left",
            wraplength=285,
        )
        self.tips_label.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

    def _section_title(self, parent, step_number: str, text: str, row: int):
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=row, column=0, padx=16, pady=(14, 0), sticky="ew")
        section.grid_columnconfigure(1, weight=1)

        badge = ctk.CTkLabel(
            section,
            text=step_number,
            width=28,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        badge.grid(row=0, column=0, padx=(0, 10), sticky="w")

        label = ctk.CTkLabel(
            section,
            text=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        )
        label.grid(row=0, column=1, sticky="ew")

        return badge, label

    def _build_right_panel(self, parent):
        self.mode_title_label = ctk.CTkLabel(
            parent,
            text="✂️ Potong PDF",
            font=ctk.CTkFont(size=26, weight="bold"),
            anchor="w",
        )
        self.mode_title_label.grid(row=0, column=0, padx=26, pady=(26, 4), sticky="ew")

        self.mode_desc_label = ctk.CTkLabel(
            parent,
            text="Ambil halaman tertentu dari PDF dan simpan sebagai file baru.",
            font=ctk.CTkFont(size=14),
            anchor="w",
        )
        self.mode_desc_label.grid(row=1, column=0, padx=26, pady=(0, 18), sticky="ew")

        self.settings_container = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        self.settings_container.grid(row=2, column=0, padx=26, pady=(0, 14), sticky="nsew")
        self.settings_container.grid_columnconfigure(0, weight=1)
        self.settings_container.grid_rowconfigure(0, weight=1)

        self.cut_panel = ctk.CTkFrame(
            self.settings_container,
            corner_radius=16,
            border_width=1,
        )
        self.image_panel = ctk.CTkFrame(
            self.settings_container,
            corner_radius=16,
            border_width=1,
        )

        self.cut_panel.grid(row=0, column=0, sticky="new")
        self.image_panel.grid(row=0, column=0, sticky="new")

        self._build_cut_settings(self.cut_panel)
        self._build_image_settings(self.image_panel)
        self._build_action_bar(parent)

    def _build_cut_settings(self, parent):
        parent.grid_columnconfigure(1, weight=1)

        self.cut_settings_title = ctk.CTkLabel(
            parent,
            text="Pengaturan Potong PDF",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.cut_settings_title.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 4), sticky="ew")

        self.cut_settings_desc = ctk.CTkLabel(
            parent,
            text="Pilih halaman yang ingin disimpan ke file PDF baru.",
            anchor="w",
        )
        self.cut_settings_desc.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

        self.cut_page_range = ctk.StringVar(value="1")
        self._field_label(parent, "Halaman", "Contoh: 1-3, 5, 7-9", 2)
        cut_page_row = ctk.CTkFrame(parent, fg_color="transparent")
        cut_page_row.grid(row=2, column=1, padx=20, pady=10, sticky="ew")
        cut_page_row.grid_columnconfigure(0, weight=1)

        self.cut_page_entry = ctk.CTkEntry(
            cut_page_row,
            textvariable=self.cut_page_range,
            height=42,
            placeholder_text="Contoh: 1-3, 5, 7-9",
        )
        self.cut_page_entry.grid(row=0, column=0, sticky="ew")

        self.cut_preview_button = ctk.CTkButton(
            cut_page_row,
            text="Preview & Pilih",
            width=145,
            height=42,
            command=self.open_cut_preview_modal,
        )
        self.cut_preview_button.grid(row=0, column=1, padx=(12, 0))

        self.cut_output_name = ctk.StringVar(value="hasil_potong.pdf")
        self._field_label(parent, "Nama file hasil", "File akan disimpan di folder output", 3)
        self.cut_output_entry = ctk.CTkEntry(
            parent,
            textvariable=self.cut_output_name,
            height=42,
        )
        self.cut_output_entry.grid(row=3, column=1, padx=20, pady=10, sticky="ew")

        self.cut_output_mode_label = ctk.CTkLabel(
            parent,
            text="Mode hasil: Gabung jadi 1 PDF",
            anchor="w",
            justify="left",
        )
        self.cut_output_mode_label.grid(row=4, column=1, padx=20, pady=(2, 8), sticky="ew")

        self.compress_pdf = ctk.BooleanVar(value=True)
        self.compress_pdf_check = ctk.CTkCheckBox(
            parent,
            text="Perkecil ukuran file hasil",
            variable=self.compress_pdf,
            font=ctk.CTkFont(size=14),
        )
        self.compress_pdf_check.grid(row=5, column=1, padx=20, pady=(8, 6), sticky="w")

        self.cut_note = ctk.CTkLabel(
            parent,
            text="Catatan: Preview & Pilih bisa digunakan untuk memilih halaman dengan checkbox dan menentukan mode hasil.",
            wraplength=650,
            justify="left",
            anchor="w",
        )
        self.cut_note.grid(row=6, column=0, columnspan=2, padx=20, pady=(4, 22), sticky="ew")

    def _build_image_settings(self, parent):
        parent.grid_columnconfigure(1, weight=1)

        self.image_settings_title = ctk.CTkLabel(
            parent,
            text="Pengaturan Convert ke Gambar",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.image_settings_title.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 4), sticky="ew")

        self.image_settings_desc = ctk.CTkLabel(
            parent,
            text="Ubah halaman PDF menjadi gambar JPG, PNG, atau WEBP.",
            anchor="w",
        )
        self.image_settings_desc.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")

        self.convert_page_range = ctk.StringVar(value="1")
        self._field_label(parent, "Halaman", "Contoh: 1-3, 5, 7-9", 2)
        image_page_row = ctk.CTkFrame(parent, fg_color="transparent")
        image_page_row.grid(row=2, column=1, padx=20, pady=10, sticky="ew")
        image_page_row.grid_columnconfigure(0, weight=1)

        self.convert_page_entry = ctk.CTkEntry(
            image_page_row,
            textvariable=self.convert_page_range,
            height=42,
            placeholder_text="Contoh: 1-3, 5, 7-9",
        )
        self.convert_page_entry.grid(row=0, column=0, sticky="ew")

        self.image_preview_button = ctk.CTkButton(
            image_page_row,
            text="Preview & Pilih",
            width=145,
            height=42,
            command=self.open_image_preview_modal,
        )
        self.image_preview_button.grid(row=0, column=1, padx=(12, 0))

        self.image_format = ctk.StringVar(value="JPG")
        self.zoom = ctk.DoubleVar(value=2.0)
        self.image_quality = ctk.IntVar(value=80)
        self.resize_image = ctk.BooleanVar(value=False)
        self.max_width = ctk.StringVar(value="1200")

        self._field_label(parent, "Format gambar", "Pilih format hasil convert", 3)
        self.format_row = ctk.CTkFrame(parent, fg_color="transparent")
        self.format_row.grid(row=3, column=1, padx=20, pady=10, sticky="ew")
        self.format_row.grid_columnconfigure(0, weight=0)
        self.format_row.grid_columnconfigure(1, weight=0)
        self.format_row.grid_columnconfigure(2, weight=1)

        self.image_format_segment = ctk.CTkSegmentedButton(
            self.format_row,
            values=["JPG", "PNG", "WEBP"],
            variable=self.image_format,
            command=lambda _: self.update_quality_state(),
            height=38,
        )
        self.image_format_segment.grid(row=0, column=0, sticky="w")

        self.image_advanced_button = ctk.CTkButton(
            self.format_row,
            text="⚙️ Opsi Lanjutan",
            height=38,
            width=150,
            command=self.open_image_advanced_modal,
        )
        self.image_advanced_button.grid(row=0, column=1, padx=(12, 0), sticky="w")

        self.compress_image = ctk.BooleanVar(value=True)
        self.compress_image_check = ctk.CTkCheckBox(
            parent,
            text="Perkecil ukuran gambar hasil convert",
            variable=self.compress_image,
            font=ctk.CTkFont(size=14),
        )
        self.compress_image_check.grid(row=4, column=1, padx=20, pady=(14, 6), sticky="w")

        self.zip_result = ctk.BooleanVar(value=True)
        self.zip_result_check = ctk.CTkCheckBox(
            parent,
            text="Gabungkan banyak gambar ke 1 file ZIP",
            variable=self.zip_result,
            font=ctk.CTkFont(size=14),
        )
        self.zip_result_check.grid(row=5, column=1, padx=20, pady=(6, 12), sticky="w")

        self.image_note = ctk.CTkLabel(
            parent,
            text="Preview & Pilih bisa digunakan untuk memilih halaman yang ingin diubah menjadi gambar.",
            wraplength=680,
            justify="left",
            anchor="w",
        )
        self.image_note.grid(row=6, column=0, columnspan=2, padx=20, pady=(4, 22), sticky="ew")

    def _field_label(self, parent, title: str, desc: str, row: int):
        label_frame = ctk.CTkFrame(parent, fg_color="transparent")
        label_frame.grid(row=row, column=0, padx=20, pady=10, sticky="nw")
        label_frame.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            label_frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew")

        desc_label = ctk.CTkLabel(
            label_frame,
            text=desc,
            anchor="w",
            wraplength=190,
        )
        desc_label.grid(row=1, column=0, sticky="ew")

    def _build_action_bar(self, parent):
        self.action_bar = ctk.CTkFrame(parent, corner_radius=16, border_width=1)
        self.action_bar.grid(row=3, column=0, padx=26, pady=(0, 18), sticky="ew")
        self.action_bar.grid_columnconfigure(0, weight=1)

        status_row = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        status_row.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_row,
            text="Siap. Pilih PDF untuk mulai.",
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.reset_button = ctk.CTkButton(
            status_row,
            text="Reset",
            width=90,
            command=self.reset_form,
        )
        self.reset_button.grid(row=0, column=1, padx=(12, 8))

        self.open_folder_button = ctk.CTkButton(
            status_row,
            text="Buka Folder Output",
            width=150,
            command=self.open_output_folder_action,
        )
        self.open_folder_button.grid(row=0, column=2, padx=(0, 8))

        self.process_button = ctk.CTkButton(
            status_row,
            text="Proses Sekarang",
            width=170,
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_process,
        )
        self.process_button.grid(row=0, column=3)

        self.progress = ctk.CTkProgressBar(self.action_bar)
        self.progress.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")
        self.progress.set(0)

    # ---------- UI state ----------

    def set_mode(self, mode: str):
        self.mode.set(mode)
        self._update_mode_ui()

    def _update_mode_ui(self):
        mode = self.mode.get()
        theme = MODE_THEMES[mode]

        self.configure(fg_color=NEUTRAL["app_bg"])
        self.header.configure(fg_color=NEUTRAL["header_bg"])
        self.header_icon.configure(text="📄", text_color=NEUTRAL["text"])
        self.header_title.configure(text_color=NEUTRAL["text"])
        self.header_subtitle.configure(text_color=NEUTRAL["muted"])
        self.version_label.configure(text_color=NEUTRAL["muted"])

        self.left_panel.configure(fg_color=NEUTRAL["panel_bg"])
        self.right_panel.configure(fg_color=theme["main_bg"])

        self.step1_badge.configure(fg_color=NEUTRAL["blue"], text_color="white")
        self.step2_badge.configure(fg_color=theme["primary"], text_color="white")
        self.step3_badge.configure(fg_color=NEUTRAL["blue"], text_color="white")

        self.step1_label.configure(text_color=NEUTRAL["text"])
        self.step2_label.configure(text_color=theme["text"])
        self.step3_label.configure(text_color=NEUTRAL["text"])

        self.file_card.configure(fg_color=NEUTRAL["card_bg"])
        self.folder_card.configure(fg_color=NEUTRAL["card_bg"])
        self.tips_card.configure(fg_color=NEUTRAL["card_soft"])
        self.file_name_label.configure(text_color=NEUTRAL["text"])
        self.folder_label.configure(text_color=NEUTRAL["text"])
        self.tips_label.configure(text_color=NEUTRAL["muted"])

        self.choose_pdf_btn.configure(fg_color=NEUTRAL["blue"], hover_color=NEUTRAL["blue_hover"], text_color="white")
        self.change_folder_btn.configure(fg_color=NEUTRAL["blue"], hover_color=NEUTRAL["blue_hover"], text_color="white")

        self.cut_mode_btn.configure(
            fg_color=MODE_THEMES["cut"]["primary"] if mode == "cut" else NEUTRAL["soft"],
            hover_color=MODE_THEMES["cut"]["hover"] if mode == "cut" else NEUTRAL["soft_hover"],
            text_color="white" if mode == "cut" else MODE_THEMES["cut"]["text"],
        )
        self.image_mode_btn.configure(
            fg_color=MODE_THEMES["image"]["primary"] if mode == "image" else NEUTRAL["soft"],
            hover_color=MODE_THEMES["image"]["hover"] if mode == "image" else NEUTRAL["soft_hover"],
            text_color="white" if mode == "image" else MODE_THEMES["image"]["text"],
        )

        self.action_bar.configure(
            fg_color=theme["main_card"],
            border_color=theme["border"],
        )
        self.process_button.configure(fg_color=theme["primary"], hover_color=theme["hover"], text_color="white")
        self.reset_button.configure(fg_color=NEUTRAL["soft"], hover_color=NEUTRAL["soft_hover"], text_color="white")
        self.open_folder_button.configure(fg_color=NEUTRAL["soft"], hover_color=NEUTRAL["soft_hover"], text_color="white")
        self.progress.configure(progress_color=theme["primary"])

        self.cut_panel.configure(
            fg_color=MODE_THEMES["cut"]["main_card"],
            border_color=MODE_THEMES["cut"]["border"],
        )
        self.image_panel.configure(
            fg_color=MODE_THEMES["image"]["main_card"],
            border_color=MODE_THEMES["image"]["border"],
        )

        if mode == "cut":
            self.mode_title_label.configure(text="✂️ Potong PDF", text_color=theme["text"])
            self.mode_desc_label.configure(
                text="Ambil halaman tertentu dari PDF dan simpan sebagai file baru.",
                text_color=theme["muted"],
            )
            self.process_button.configure(text="Potong PDF Sekarang")
            self.cut_panel.grid()
            self.image_panel.grid_remove()

            self.cut_settings_title.configure(text_color=theme["text"])
            self.cut_settings_desc.configure(text_color=theme["muted"])
            self.cut_note.configure(text_color=theme["muted"])
            self.cut_output_mode_label.configure(text_color=theme["muted"])
            self.cut_preview_button.configure(fg_color=theme["main_card_soft"], hover_color=theme["hover"], text_color="white")
            self.compress_pdf_check.configure(fg_color=theme["primary"], hover_color=theme["hover"])

        else:
            self.mode_title_label.configure(text="🖼️ Convert PDF ke Gambar", text_color=theme["text"])
            self.mode_desc_label.configure(
                text="Ubah halaman PDF menjadi gambar JPG, PNG, atau WEBP.",
                text_color=theme["muted"],
            )
            self.process_button.configure(text="Convert Sekarang")
            self.image_panel.grid()
            self.cut_panel.grid_remove()

            self.image_settings_title.configure(text_color=theme["text"])
            self.image_settings_desc.configure(text_color=theme["muted"])
            self.image_note.configure(text_color=theme["muted"])
            self.image_preview_button.configure(fg_color=theme["main_card_soft"], hover_color=theme["hover"], text_color="white")
            self.compress_image_check.configure(fg_color=theme["primary"], hover_color=theme["hover"])
            self.zip_result_check.configure(fg_color=theme["primary"], hover_color=theme["hover"])
            self.image_advanced_button.configure(fg_color=theme["main_card_soft"], hover_color=theme["hover"], text_color="white")
            self.image_format_segment.configure(
                selected_color=theme["primary"],
                selected_hover_color=theme["hover"],
                unselected_color=NEUTRAL["soft"],
                unselected_hover_color=NEUTRAL["soft_hover"],
            )

        self.update_quality_state()

    def update_quality_state(self):
        selected_format = self.image_format.get() if hasattr(self, "image_format") else "JPG"

        quality_slider = getattr(self, "quality_slider", None)
        quality_label = getattr(self, "quality_label", None)

        if quality_slider is None or quality_label is None:
            return

        try:
            if not quality_slider.winfo_exists() or not quality_label.winfo_exists():
                return
        except Exception:
            return

        if selected_format == "PNG":
            quality_slider.configure(state="disabled")
            quality_label.configure(text="PNG")
        else:
            quality_slider.configure(state="normal")
            quality_label.configure(text=str(int(self.image_quality.get())))

    def update_file_card_empty(self):
        self.file_name_label.configure(text="Belum ada PDF dipilih")
        self.file_info_label.configure(text="Pilih PDF untuk mulai memproses file.", text_color=NEUTRAL["muted"])

    def update_file_card_loaded(self, path: str):
        filename = os.path.basename(path)
        self.file_name_label.configure(text=filename)
        self.file_info_label.configure(
            text=f"{self.total_pages} halaman • {format_file_size(self.original_size)}",
            text_color="#4ade80",
        )

    # ---------- Modal preview halaman ----------

    def validate_pdf_selected(self) -> str:
        pdf_path = self.pdf_path.get().strip()

        if not pdf_path:
            raise ValueError("Pilih file PDF terlebih dahulu.")

        if not os.path.exists(pdf_path):
            raise ValueError("File PDF tidak ditemukan.")

        return pdf_path

    def create_preview_modal(
        self,
        title: str,
        page_range_var: ctk.StringVar,
        theme_key: str,
        show_cut_output_mode: bool,
    ):
        try:
            pdf_path = self.validate_pdf_selected()
        except Exception as e:
            messagebox.showerror("Tidak bisa membuka preview", str(e))
            return

        theme = MODE_THEMES[theme_key]

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            messagebox.showerror("Gagal membuka PDF", str(e))
            return

        total_pages = len(doc)

        try:
            current_selected = set(parse_page_ranges(page_range_var.get(), total_pages))
        except Exception:
            current_selected = set()

        modal = ctk.CTkToplevel(self)
        modal.title(title)
        modal.geometry("920x680")
        modal.minsize(760, 560)
        modal.configure(fg_color=NEUTRAL["app_bg"])
        modal.transient(self)
        modal.grab_set()
        modal.grid_columnconfigure(0, weight=1)
        modal.grid_rowconfigure(2, weight=1)

        preview_images = []
        page_vars = []

        ctk.CTkLabel(
            modal,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=theme["text"],
            anchor="w",
        ).grid(row=0, column=0, padx=24, pady=(22, 4), sticky="ew")

        desc_text = "Centang halaman yang ingin diproses. Input halaman akan otomatis diisi berdasarkan pilihan ini."
        ctk.CTkLabel(
            modal,
            text=desc_text,
            text_color=NEUTRAL["muted"],
            anchor="w",
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="ew")

        preview_frame = ctk.CTkScrollableFrame(modal, corner_radius=16, fg_color=NEUTRAL["panel_bg"])
        preview_frame.grid(row=2, column=0, padx=24, pady=(0, 14), sticky="nsew")

        columns = 4
        for column in range(columns):
            preview_frame.grid_columnconfigure(column, weight=1)

        try:
            for page_index in range(total_pages):
                image = render_pdf_thumbnail(doc, page_index)
                ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(image.width, image.height))
                preview_images.append(ctk_image)

                checked = page_index in current_selected
                page_var = ctk.BooleanVar(value=checked)
                page_vars.append(page_var)

                card = ctk.CTkFrame(
                    preview_frame,
                    corner_radius=14,
                    fg_color=NEUTRAL["card_bg"],
                    border_width=1,
                    border_color=theme["border"] if checked else NEUTRAL["line"],
                )
                row = page_index // columns
                column = page_index % columns
                card.grid(row=row, column=column, padx=10, pady=10, sticky="n")

                img_label = ctk.CTkLabel(card, text="", image=ctk_image)
                img_label.grid(row=0, column=0, padx=12, pady=(12, 8))

                checkbox = ctk.CTkCheckBox(
                    card,
                    text=f"Halaman {page_index + 1}",
                    variable=page_var,
                    fg_color=theme["primary"],
                    hover_color=theme["hover"],
                    text_color=NEUTRAL["text"],
                )
                checkbox.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

        finally:
            doc.close()

        # Simpan reference gambar agar tidak hilang dari memory selama modal hidup.
        modal.preview_images = preview_images

        bottom = ctk.CTkFrame(modal, corner_radius=16, fg_color=NEUTRAL["panel_bg"])
        bottom.grid(row=3, column=0, padx=24, pady=(0, 20), sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        if show_cut_output_mode:
            mode_frame = ctk.CTkFrame(bottom, fg_color="transparent")
            mode_frame.grid(row=0, column=0, columnspan=4, padx=16, pady=(14, 4), sticky="ew")
            mode_frame.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                mode_frame,
                text="Mode hasil potong",
                text_color=theme["text"],
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
            ).grid(row=0, column=0, padx=(0, 12), sticky="w")

            ctk.CTkSegmentedButton(
                mode_frame,
                values=list(CUT_OUTPUT_MODE_MAP.keys()),
                variable=self.cut_output_mode,
                selected_color=theme["primary"],
                selected_hover_color=theme["hover"],
                unselected_color=NEUTRAL["soft"],
                unselected_hover_color=NEUTRAL["soft_hover"],
            ).grid(row=0, column=1, sticky="w")

        def select_all():
            for variable in page_vars:
                variable.set(True)

        def clear_all():
            for variable in page_vars:
                variable.set(False)

        def apply_selection():
            selected = [index for index, variable in enumerate(page_vars) if variable.get()]

            if not selected:
                messagebox.showwarning("Belum ada halaman", "Pilih minimal satu halaman.")
                return

            page_range_text = indices_to_page_range_text(selected)
            page_range_var.set(page_range_text)

            if show_cut_output_mode:
                self.cut_output_mode_label.configure(text=f"Mode hasil: {self.cut_output_mode.get()}")
                self.set_status(
                    f"Dipilih: {page_range_text}. Mode hasil: {self.cut_output_mode.get()}.",
                    "success",
                )
            else:
                self.set_status(f"Dipilih untuk convert gambar: {page_range_text}.", "success")

            modal.destroy()

        button_row = ctk.CTkFrame(bottom, fg_color="transparent")
        button_row.grid(row=1, column=0, padx=16, pady=(10, 14), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            button_row,
            text="Pilih Semua",
            width=110,
            fg_color=NEUTRAL["soft"],
            hover_color=NEUTRAL["soft_hover"],
            command=select_all,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            button_row,
            text="Bersihkan",
            width=110,
            fg_color=NEUTRAL["soft"],
            hover_color=NEUTRAL["soft_hover"],
            command=clear_all,
        ).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(
            button_row,
            text="Gunakan Pilihan",
            width=160,
            fg_color=theme["primary"],
            hover_color=theme["hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=apply_selection,
        ).grid(row=0, column=3)

    def open_cut_preview_modal(self):
        self.create_preview_modal(
            title="✂️ Preview & Pilih Halaman PDF",
            page_range_var=self.cut_page_range,
            theme_key="cut",
            show_cut_output_mode=True,
        )

    def open_image_preview_modal(self):
        self.create_preview_modal(
            title="🖼️ Preview & Pilih Halaman Gambar",
            page_range_var=self.convert_page_range,
            theme_key="image",
            show_cut_output_mode=False,
        )

    # ---------- Modal opsi lanjutan ----------

    def open_image_advanced_modal(self):
        theme = MODE_THEMES["image"]

        modal = ctk.CTkToplevel(self)
        modal.title("Opsi Lanjutan Gambar")
        modal.geometry("560x440")
        modal.minsize(520, 400)
        modal.configure(fg_color=NEUTRAL["app_bg"])
        modal.transient(self)
        modal.grab_set()
        modal.grid_columnconfigure(0, weight=1)

        def close_modal():
            self.quality_slider = None
            self.quality_label = None
            self.zoom_label = None
            modal.destroy()

        modal.protocol("WM_DELETE_WINDOW", close_modal)

        ctk.CTkLabel(
            modal,
            text="⚙️ Opsi Lanjutan Gambar",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
            text_color=theme["text"],
        ).grid(row=0, column=0, padx=24, pady=(24, 4), sticky="ew")

        ctk.CTkLabel(
            modal,
            text="Biarkan default jika kamu hanya ingin hasil yang aman dan rapi.",
            text_color=NEUTRAL["muted"],
            anchor="w",
        ).grid(row=1, column=0, padx=24, pady=(0, 20), sticky="ew")

        card = ctk.CTkFrame(
            modal,
            corner_radius=16,
            fg_color=theme["main_card"],
            border_width=1,
            border_color=theme["border"],
        )
        card.grid(row=2, column=0, padx=24, pady=(0, 20), sticky="nsew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text="Ketajaman gambar",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            text_color=theme["text"],
        ).grid(row=0, column=0, padx=18, pady=(20, 8), sticky="w")

        zoom_frame = ctk.CTkFrame(card, fg_color="transparent")
        zoom_frame.grid(row=0, column=1, padx=18, pady=(20, 8), sticky="ew")
        zoom_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkSlider(
            zoom_frame,
            from_=1.0,
            to=4.0,
            number_of_steps=6,
            variable=self.zoom,
            progress_color=theme["primary"],
            button_color=theme["primary"],
            button_hover_color=theme["hover"],
            command=lambda value: self.zoom_label.configure(text=f"{float(value):.1f}x"),
        ).grid(row=0, column=0, sticky="ew")

        self.zoom_label = ctk.CTkLabel(
            zoom_frame,
            text=f"{float(self.zoom.get()):.1f}x",
            width=56,
            text_color=theme["text"],
        )
        self.zoom_label.grid(row=0, column=1, padx=(12, 0))

        ctk.CTkLabel(
            card,
            text="Kualitas JPG/WEBP",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            text_color=theme["text"],
        ).grid(row=1, column=0, padx=18, pady=8, sticky="w")

        quality_frame = ctk.CTkFrame(card, fg_color="transparent")
        quality_frame.grid(row=1, column=1, padx=18, pady=8, sticky="ew")
        quality_frame.grid_columnconfigure(0, weight=1)

        self.quality_slider = ctk.CTkSlider(
            quality_frame,
            from_=10,
            to=100,
            number_of_steps=18,
            variable=self.image_quality,
            progress_color=theme["primary"],
            button_color=theme["primary"],
            button_hover_color=theme["hover"],
            command=lambda value: self.quality_label.configure(text=str(int(value))),
        )
        self.quality_slider.grid(row=0, column=0, sticky="ew")

        self.quality_label = ctk.CTkLabel(
            quality_frame,
            text=str(int(self.image_quality.get())),
            width=56,
            text_color=theme["text"],
        )
        self.quality_label.grid(row=0, column=1, padx=(12, 0))

        ctk.CTkCheckBox(
            card,
            text="Kecilkan dimensi gambar",
            variable=self.resize_image,
            font=ctk.CTkFont(size=14),
            fg_color=theme["primary"],
            hover_color=theme["hover"],
            text_color=theme["text"],
        ).grid(row=2, column=1, padx=18, pady=(14, 8), sticky="w")

        ctk.CTkLabel(
            card,
            text="Maksimal lebar",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            text_color=theme["text"],
        ).grid(row=3, column=0, padx=18, pady=(8, 20), sticky="w")

        ctk.CTkEntry(
            card,
            textvariable=self.max_width,
            height=40,
            placeholder_text="Contoh: 1200",
        ).grid(row=3, column=1, padx=18, pady=(8, 20), sticky="ew")

        button_row = ctk.CTkFrame(modal, fg_color="transparent")
        button_row.grid(row=3, column=0, padx=24, pady=(0, 24), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            button_row,
            text="Simpan Pengaturan",
            height=42,
            width=170,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=theme["primary"],
            hover_color=theme["hover"],
            command=close_modal,
        ).grid(row=0, column=1, sticky="e")

        self.update_quality_state()

    # ---------- Actions ----------

    def select_pdf(self):
        path = filedialog.askopenfilename(
            title="Pilih file PDF",
            filetypes=[("PDF files", "*.pdf")],
        )

        if not path:
            return

        self.pdf_path.set(path)

        try:
            total_pages, original_size = read_pdf_info(path)
            self.total_pages = total_pages
            self.original_size = original_size

            default_range = "1" if total_pages == 1 else f"1-{total_pages}"
            self.cut_page_range.set(default_range)
            self.convert_page_range.set(default_range)

            base_name = safe_filename(Path(path).stem)
            self.cut_output_name.set(f"{base_name}_potong.pdf")

            self.update_file_card_loaded(path)
            self.set_status("PDF siap diproses.", "success")
        except Exception as e:
            self.update_file_card_empty()
            self.set_status(f"Gagal membaca PDF: {e}", "error")
            messagebox.showerror("Gagal membaca PDF", str(e))

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Pilih folder output")

        if folder:
            self.output_folder.set(folder)
            self.folder_label.configure(text=folder)
            self.last_output_folder = folder
            self.set_status("Folder output diperbarui.", "normal")

    def open_output_folder_action(self):
        folder = self.output_folder.get().strip() or self.last_output_folder

        try:
            os.makedirs(folder, exist_ok=True)
            open_folder(folder)
        except Exception as e:
            messagebox.showerror("Gagal membuka folder", str(e))

    def reset_form(self):
        self.pdf_path.set("")
        self.total_pages = 0
        self.original_size = 0
        self.cut_page_range.set("1")
        self.convert_page_range.set("1")
        self.cut_output_name.set("hasil_potong.pdf")
        self.cut_output_mode.set("Gabung jadi 1 PDF")
        self.cut_output_mode_label.configure(text="Mode hasil: Gabung jadi 1 PDF")
        self.compress_pdf.set(True)
        self.compress_image.set(True)
        self.zip_result.set(True)
        self.resize_image.set(False)
        self.image_format.set("JPG")
        self.zoom.set(2.0)
        self.image_quality.set(80)
        self.max_width.set("1200")
        self.update_file_card_empty()
        self.set_mode("cut")
        self.set_status("Form sudah di-reset. Pilih PDF untuk mulai.", "normal")
        self.progress.set(0)

    def validate_common_inputs(self):
        pdf_path = self.pdf_path.get().strip()
        output_folder = self.output_folder.get().strip()

        if not pdf_path:
            raise ValueError("Pilih file PDF terlebih dahulu.")

        if not os.path.exists(pdf_path):
            raise ValueError("File PDF tidak ditemukan.")

        if not output_folder:
            raise ValueError("Pilih folder output terlebih dahulu.")

        os.makedirs(output_folder, exist_ok=True)

        return pdf_path, output_folder

    def start_process(self):
        if self.mode.get() == "cut":
            self.run_in_thread(self.cut_pdf_action)
        else:
            self.run_in_thread(self.convert_images_action)

    def cut_pdf_action(self):
        try:
            self.set_busy("Memotong PDF...")
            pdf_path, output_folder = self.validate_common_inputs()

            output_mode = CUT_OUTPUT_MODE_MAP.get(self.cut_output_mode.get(), "merge")

            original_size, result_size, output_paths = cut_pdf_outputs(
                pdf_path=pdf_path,
                output_folder=output_folder,
                output_name=self.cut_output_name.get().strip(),
                page_range_text=self.cut_page_range.get(),
                compress=self.compress_pdf.get(),
                output_mode=output_mode,
            )

            self.last_output_folder = output_folder
            self.set_done("PDF berhasil dipotong.")

            if len(output_paths) == 1:
                output_info = output_paths[0]
            else:
                output_info = "\n".join(output_paths[:10])
                if len(output_paths) > 10:
                    output_info += f"\n...dan {len(output_paths) - 10} file lainnya"

            message = (
                "PDF berhasil dipotong.\n\n"
                f"Mode hasil: {self.cut_output_mode.get()}\n"
                f"Jumlah output: {len(output_paths)}\n\n"
                f"Lokasi hasil:\n{output_info}\n\n"
                f"Ukuran asli: {format_file_size(original_size)}\n"
                f"Total ukuran hasil: {format_file_size(result_size)}"
            )
            self.show_info("Berhasil", message)

        except Exception as e:
            self.set_error(f"Gagal memotong PDF: {e}")
            self.show_error("Gagal", f"Gagal memotong PDF:\n{e}")

    def convert_images_action(self):
        try:
            self.set_busy("Mengubah PDF ke gambar...")
            pdf_path, output_folder = self.validate_common_inputs()

            max_width = int(self.max_width.get())
            if max_width < 300:
                raise ValueError("Maksimal lebar gambar minimal 300 pixel.")

            result_size, output_paths = convert_pdf_to_images_file(
                pdf_path=pdf_path,
                output_folder=output_folder,
                page_range_text=self.convert_page_range.get(),
                image_format=self.image_format.get(),
                zoom=float(self.zoom.get()),
                compress_image=self.compress_image.get(),
                image_quality=int(self.image_quality.get()),
                resize_image=self.resize_image.get(),
                max_width=max_width,
                zip_result=self.zip_result.get(),
            )

            self.last_output_folder = output_folder
            self.set_done("PDF berhasil di-convert ke gambar.")

            if len(output_paths) == 1:
                output_info = output_paths[0]
            else:
                output_info = "\n".join(output_paths[:10])
                if len(output_paths) > 10:
                    output_info += f"\n...dan {len(output_paths) - 10} file lainnya"

            message = (
                "PDF berhasil di-convert ke gambar.\n\n"
                f"Jumlah output: {len(output_paths)}\n"
                f"Total ukuran hasil: {format_file_size(result_size)}\n\n"
                f"Lokasi hasil:\n{output_info}"
            )
            self.show_info("Berhasil", message)

        except Exception as e:
            self.set_error(f"Gagal convert PDF ke gambar: {e}")
            self.show_error("Gagal", f"Gagal convert PDF ke gambar:\n{e}")

    # ---------- Thread-safe UI helpers ----------

    def run_in_thread(self, target):
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def set_status(self, text: str, status_type: str = "normal"):
        theme = MODE_THEMES[self.mode.get()]
        color_map = {
            "normal": "#d4d4d8",
            "success": theme["status"],
            "error": "#f87171",
            "info": "#60a5fa",
        }
        self.status_label.configure(text=text, text_color=color_map.get(status_type, "#d4d4d8"))

    def set_busy(self, text: str):
        self.after(0, lambda: self.process_button.configure(state="disabled", text="Memproses..."))
        self.after(0, lambda: self.status_label.configure(text=text, text_color="#60a5fa"))
        self.after(0, lambda: self.progress.set(0.55))

    def set_done(self, text: str):
        self.after(0, lambda: self.process_button.configure(state="normal"))
        self.after(0, lambda: self._update_mode_ui())
        self.after(0, lambda: self.set_status(text, "success"))
        self.after(0, lambda: self.progress.set(1))

    def set_error(self, text: str):
        self.after(0, lambda: self.process_button.configure(state="normal"))
        self.after(0, lambda: self._update_mode_ui())
        self.after(0, lambda: self.status_label.configure(text=text, text_color="#f87171"))
        self.after(0, lambda: self.progress.set(0))

    def show_info(self, title: str, message: str):
        self.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title: str, message: str):
        self.after(0, lambda: messagebox.showerror(title, message))


if __name__ == "__main__":
    app = PDFMZApp()
    app.mainloop()
