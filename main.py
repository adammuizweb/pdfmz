import io
import os
import threading
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter


# =========================
# Konfigurasi tampilan
# =========================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


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


def cut_pdf_file(
    pdf_path: str,
    output_path: str,
    page_range_text: str,
    compress: bool = True,
) -> tuple[int, int]:
    with open(pdf_path, "rb") as file:
        pdf_bytes = file.read()

    reader = PdfReader(io.BytesIO(pdf_bytes))

    if reader.is_encrypted:
        raise ValueError("PDF terenkripsi/password protected belum didukung.")

    writer = PdfWriter()
    selected_pages = parse_page_ranges(page_range_text, len(reader.pages))

    for page_index in selected_pages:
        writer.add_page(reader.pages[page_index])

    if compress:
        for page in writer.pages:
            try:
                page.compress_content_streams()
            except Exception:
                pass

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    return len(pdf_bytes), os.path.getsize(output_path)


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

        self.title("PDFMZ - Aplikasi Pemotong PDF")
        self.geometry("920x720")
        self.minsize(860, 680)

        self.pdf_path = ctk.StringVar(value="")
        self.output_folder = ctk.StringVar(value=str(Path.home() / "Downloads"))
        self.total_pages = 0
        self.original_size = 0

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="✂️ PDFMZ",
            font=ctk.CTkFont(size=34, weight="bold"),
        )
        title.grid(row=0, column=0, padx=24, pady=(22, 4), sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Potong PDF, compress ringan, dan convert PDF ke gambar tanpa browser.",
            font=ctk.CTkFont(size=15),
            text_color="gray70",
        )
        subtitle.grid(row=1, column=0, padx=24, pady=(0, 18), sticky="w")

        file_frame = ctk.CTkFrame(self)
        file_frame.grid(row=1, column=0, padx=24, pady=18, sticky="ew")
        file_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            file_frame,
            text="Pilih PDF",
            command=self.select_pdf,
            width=130,
        ).grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        ctk.CTkEntry(
            file_frame,
            textvariable=self.pdf_path,
            placeholder_text="Belum ada file PDF dipilih",
        ).grid(row=0, column=1, padx=(0, 16), pady=(16, 8), sticky="ew")

        ctk.CTkButton(
            file_frame,
            text="Folder Output",
            command=self.select_output_folder,
            width=130,
        ).grid(row=1, column=0, padx=16, pady=(8, 16), sticky="w")

        ctk.CTkEntry(
            file_frame,
            textvariable=self.output_folder,
            placeholder_text="Folder hasil output",
        ).grid(row=1, column=1, padx=(0, 16), pady=(8, 16), sticky="ew")

        self.info_label = ctk.CTkLabel(
            file_frame,
            text="Pilih file PDF terlebih dahulu.",
            text_color="gray70",
            anchor="w",
        )
        self.info_label.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="ew")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=2, column=0, padx=24, pady=(0, 18), sticky="nsew")

        self.tab_cut = self.tabs.add("Potong PDF")
        self.tab_convert = self.tabs.add("Convert ke Gambar")

        self._build_cut_tab()
        self._build_convert_tab()

        footer = ctk.CTkFrame(self, corner_radius=0)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            footer,
            text="Siap.",
            anchor="w",
            text_color="gray70",
        )
        self.status_label.grid(row=0, column=0, padx=24, pady=(10, 4), sticky="ew")

        self.progress = ctk.CTkProgressBar(footer)
        self.progress.grid(row=1, column=0, padx=24, pady=(0, 14), sticky="ew")
        self.progress.set(0)

    def _build_cut_tab(self):
        self.tab_cut.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkFrame(self.tab_cut)
        frame.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Halaman yang ingin diambil").grid(
            row=0, column=0, padx=16, pady=(18, 8), sticky="w"
        )

        self.cut_page_range = ctk.StringVar(value="1")
        ctk.CTkEntry(
            frame,
            textvariable=self.cut_page_range,
            placeholder_text="Contoh: 1-3, 5, 7-9",
        ).grid(row=0, column=1, padx=16, pady=(18, 8), sticky="ew")

        self.compress_pdf = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            frame,
            text="Compress PDF hasil",
            variable=self.compress_pdf,
        ).grid(row=1, column=1, padx=16, pady=8, sticky="w")

        self.cut_output_name = ctk.StringVar(value="hasil_potong.pdf")
        ctk.CTkLabel(frame, text="Nama file hasil").grid(
            row=2, column=0, padx=16, pady=8, sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=self.cut_output_name).grid(
            row=2, column=1, padx=16, pady=8, sticky="ew"
        )

        ctk.CTkButton(
            frame,
            text="Potong PDF",
            command=self.start_cut_pdf,
            height=42,
        ).grid(row=3, column=1, padx=16, pady=(18, 18), sticky="e")

        note = ctk.CTkLabel(
            frame,
            text="Catatan: compress PDF menggunakan metode ringan. Untuk PDF scan/gambar, ukuran mungkin tidak banyak berkurang.",
            text_color="gray70",
            wraplength=650,
            justify="left",
        )
        note.grid(row=4, column=0, columnspan=2, padx=16, pady=(0, 18), sticky="w")

    def _build_convert_tab(self):
        self.tab_convert.grid_columnconfigure(0, weight=1)
        self.tab_convert.grid_rowconfigure(0, weight=1)

        # Pakai scrollable frame supaya tombol tetap bisa dijangkau
        # walaupun layar laptop kecil atau window aplikasi tidak tinggi.
        frame = ctk.CTkScrollableFrame(self.tab_convert)
        frame.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        frame.grid_columnconfigure(1, weight=1)

        self.convert_page_range = ctk.StringVar(value="1")
        ctk.CTkLabel(frame, text="Halaman yang ingin di-convert").grid(
            row=0, column=0, padx=16, pady=(18, 8), sticky="w"
        )
        ctk.CTkEntry(
            frame,
            textvariable=self.convert_page_range,
            placeholder_text="Contoh: 1-3, 5, 7-9",
        ).grid(row=0, column=1, padx=16, pady=(18, 8), sticky="ew")

        self.image_format = ctk.StringVar(value="JPG")
        ctk.CTkLabel(frame, text="Format gambar").grid(
            row=1, column=0, padx=16, pady=8, sticky="w"
        )
        ctk.CTkOptionMenu(
            frame,
            values=["JPG", "PNG", "WEBP"],
            variable=self.image_format,
            command=lambda _: self.update_quality_state(),
        ).grid(row=1, column=1, padx=16, pady=8, sticky="w")

        self.zoom = ctk.DoubleVar(value=2.0)
        ctk.CTkLabel(frame, text="Kualitas render").grid(
            row=2, column=0, padx=16, pady=8, sticky="w"
        )
        zoom_frame = ctk.CTkFrame(frame, fg_color="transparent")
        zoom_frame.grid(row=2, column=1, padx=16, pady=8, sticky="ew")
        zoom_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(
            zoom_frame,
            from_=1.0,
            to=4.0,
            number_of_steps=6,
            variable=self.zoom,
            command=lambda value: self.zoom_label.configure(text=f"{float(value):.1f}x"),
        ).grid(row=0, column=0, sticky="ew")
        self.zoom_label = ctk.CTkLabel(zoom_frame, text="2.0x", width=50)
        self.zoom_label.grid(row=0, column=1, padx=(10, 0))

        self.compress_image = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            frame,
            text="Compress gambar hasil convert",
            variable=self.compress_image,
        ).grid(row=3, column=1, padx=16, pady=8, sticky="w")

        self.image_quality = ctk.IntVar(value=80)
        ctk.CTkLabel(frame, text="Kualitas JPG/WEBP").grid(
            row=4, column=0, padx=16, pady=8, sticky="w"
        )
        quality_frame = ctk.CTkFrame(frame, fg_color="transparent")
        quality_frame.grid(row=4, column=1, padx=16, pady=8, sticky="ew")
        quality_frame.grid_columnconfigure(0, weight=1)
        self.quality_slider = ctk.CTkSlider(
            quality_frame,
            from_=10,
            to=100,
            number_of_steps=18,
            variable=self.image_quality,
            command=lambda value: self.quality_label.configure(text=str(int(value))),
        )
        self.quality_slider.grid(row=0, column=0, sticky="ew")
        self.quality_label = ctk.CTkLabel(quality_frame, text="80", width=50)
        self.quality_label.grid(row=0, column=1, padx=(10, 0))

        self.resize_image = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            frame,
            text="Kecilkan dimensi gambar",
            variable=self.resize_image,
        ).grid(row=5, column=1, padx=16, pady=8, sticky="w")

        self.max_width = ctk.StringVar(value="1200")
        ctk.CTkLabel(frame, text="Maksimal lebar gambar").grid(
            row=6, column=0, padx=16, pady=8, sticky="w"
        )
        ctk.CTkEntry(frame, textvariable=self.max_width).grid(
            row=6, column=1, padx=16, pady=8, sticky="ew")

        self.zip_result = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            frame,
            text="Simpan hasil banyak gambar ke ZIP",
            variable=self.zip_result,
        ).grid(row=7, column=1, padx=16, pady=8, sticky="w")

        ctk.CTkButton(
            frame,
            text="Convert ke Gambar",
            command=self.start_convert_images,
            height=44,
        ).grid(row=8, column=1, padx=16, pady=(18, 28), sticky="e")

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

            self.info_label.configure(
                text=(
                    f"PDF berhasil dibaca. Total halaman: {total_pages}. "
                    f"Ukuran: {format_file_size(original_size)}"
                ),
                text_color="#4ade80",
            )
            self.set_status("PDF siap diproses.")
        except Exception as e:
            self.info_label.configure(text=f"Gagal membaca PDF: {e}", text_color="#f87171")
            self.set_status("Gagal membaca PDF.")

    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Pilih folder output")

        if folder:
            self.output_folder.set(folder)

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

    def start_cut_pdf(self):
        self.run_in_thread(self.cut_pdf_action)

    def cut_pdf_action(self):
        try:
            self.set_busy("Memotong PDF...")
            pdf_path, output_folder = self.validate_common_inputs()

            output_name = self.cut_output_name.get().strip()
            if not output_name.lower().endswith(".pdf"):
                output_name += ".pdf"

            output_name = safe_filename(output_name)
            output_path = os.path.join(output_folder, output_name)

            original_size, result_size = cut_pdf_file(
                pdf_path=pdf_path,
                output_path=output_path,
                page_range_text=self.cut_page_range.get(),
                compress=self.compress_pdf.get(),
            )

            message = (
                "PDF berhasil dipotong.\n\n"
                f"File hasil:\n{output_path}\n\n"
                f"Ukuran asli: {format_file_size(original_size)}\n"
                f"Ukuran hasil: {format_file_size(result_size)}"
            )

            self.set_done("PDF berhasil dipotong.")
            self.show_info("Berhasil", message)

        except Exception as e:
            self.set_error(f"Gagal memotong PDF: {e}")
            self.show_error("Gagal", f"Gagal memotong PDF:\n{e}")

    def start_convert_images(self):
        self.run_in_thread(self.convert_images_action)

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

            self.set_done("PDF berhasil di-convert ke gambar.")
            self.show_info("Berhasil", message)

        except Exception as e:
            self.set_error(f"Gagal convert PDF ke gambar: {e}")
            self.show_error("Gagal", f"Gagal convert PDF ke gambar:\n{e}")

    def update_quality_state(self):
        selected_format = self.image_format.get()

        if selected_format == "PNG":
            self.quality_slider.configure(state="disabled")
            self.quality_label.configure(text="PNG")
        else:
            self.quality_slider.configure(state="normal")
            self.quality_label.configure(text=str(int(self.image_quality.get())))

    def run_in_thread(self, target):
        thread = threading.Thread(target=target, daemon=True)
        thread.start()

    def set_status(self, text: str):
        self.status_label.configure(text=text, text_color="gray70")
        self.progress.set(0)

    def set_busy(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text, text_color="#60a5fa"))
        self.after(0, lambda: self.progress.set(0.45))

    def set_done(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text, text_color="#4ade80"))
        self.after(0, lambda: self.progress.set(1))

    def set_error(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text, text_color="#f87171"))
        self.after(0, lambda: self.progress.set(0))

    def show_info(self, title: str, message: str):
        self.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title: str, message: str):
        self.after(0, lambda: messagebox.showerror(title, message))


if __name__ == "__main__":
    app = PDFMZApp()
    app.mainloop()
