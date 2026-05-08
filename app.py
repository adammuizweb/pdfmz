import io
import zipfile

import fitz  # PyMuPDF
import streamlit as st
from PIL import Image
from pypdf import PdfReader, PdfWriter


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

    # Hilangkan halaman duplikat tetapi tetap pertahankan urutan input
    unique_pages = []
    for page in pages:
        if page not in unique_pages:
            unique_pages.append(page)

    return [page - 1 for page in unique_pages]


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


# =========================
# Fitur potong PDF
# =========================

def cut_pdf(pdf_bytes: bytes, page_range_text: str, compress: bool = True) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    total_pages = len(reader.pages)
    selected_pages = parse_page_ranges(page_range_text, total_pages)

    for page_index in selected_pages:
        writer.add_page(reader.pages[page_index])

    # Penting:
    # compress_content_streams() dipanggil setelah halaman masuk ke PdfWriter.
    # Kalau dipanggil sebelum writer.add_page(), bisa muncul error:
    # "Page must be part of a PdfWriter"
    if compress:
        for page in writer.pages:
            try:
                page.compress_content_streams()
            except Exception:
                # Tidak semua halaman PDF bisa dikompres dengan cara ini.
                # Kalau gagal di halaman tertentu, proses tetap lanjut.
                pass

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    return output.read()


# =========================
# Fitur convert PDF ke gambar
# =========================

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


def convert_pdf_to_images(
    pdf_bytes: bytes,
    page_range_text: str,
    image_format: str,
    zoom: float,
    compress_image: bool,
    image_quality: int,
    resize_image: bool,
    max_width: int,
) -> list[tuple[str, bytes, str]]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    selected_pages = parse_page_ranges(page_range_text, total_pages)

    image_format = image_format.upper()

    extension_map = {
        "JPG": "jpg",
        "PNG": "png",
        "WEBP": "webp",
    }

    mime_map = {
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }

    extension = extension_map[image_format]
    mime_type = mime_map[image_format]

    images = []

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

        filename = f"halaman_{page_index + 1}.{extension}"
        images.append((filename, image_bytes, mime_type))

    doc.close()
    return images


def create_zip_from_images(images: list[tuple[str, bytes, str]]) -> bytes:
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, image_bytes, _ in images:
            zip_file.writestr(filename, image_bytes)

    output.seek(0)
    return output.read()


# =========================
# Tampilan aplikasi
# =========================

st.set_page_config(page_title="PDFMZ", page_icon="✂️")

st.title("✂️ PDFMZ - Aplikasi Pemotong PDF")
st.write("Upload PDF, pilih halaman, lalu potong PDF atau convert PDF ke gambar.")

uploaded_file = st.file_uploader("Upload file PDF", type=["pdf"])

if uploaded_file:
    pdf_bytes = uploaded_file.read()
    original_size = len(pdf_bytes)

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))

        if reader.is_encrypted:
            st.error("PDF ini terenkripsi/password protected, jadi belum bisa diproses.")
        else:
            total_pages = len(reader.pages)

            st.success(f"PDF berhasil dibaca. Total halaman: {total_pages}")
            st.info(f"Ukuran file asli: {format_file_size(original_size)}")

            default_page_range = "1" if total_pages == 1 else f"1-{total_pages}"

            tab_cut, tab_convert = st.tabs(["Potong PDF", "Convert ke Gambar"])

            # =========================
            # Tab Potong PDF
            # =========================
            with tab_cut:
                st.subheader("Potong PDF")

                page_range_cut = st.text_input(
                    "Halaman yang ingin diambil",
                    value=default_page_range,
                    help="Contoh: 1-3, 5, 7-9",
                    key="page_range_cut",
                )

                compress_pdf = st.checkbox(
                    "Compress PDF hasil",
                    value=True,
                    help="Compress ringan menggunakan pypdf. Untuk PDF scan/gambar, hasilnya mungkin tidak terlalu kecil.",
                    key="compress_pdf",
                )

                if st.button("Potong PDF", key="button_cut_pdf"):
                    try:
                        result_pdf = cut_pdf(
                            pdf_bytes=pdf_bytes,
                            page_range_text=page_range_cut,
                            compress=compress_pdf,
                        )

                        result_size = len(result_pdf)

                        st.success("PDF berhasil dipotong.")
                        st.info(f"Ukuran file hasil: {format_file_size(result_size)}")

                        if result_size < original_size:
                            saved_size = original_size - result_size
                            st.success(
                                f"Ukuran berkurang sekitar {format_file_size(saved_size)}."
                            )
                        elif compress_pdf:
                            st.warning(
                                "File hasil tidak lebih kecil. Ini normal untuk beberapa PDF, terutama PDF hasil scan/gambar."
                            )

                        st.download_button(
                            label="Download PDF hasil",
                            data=result_pdf,
                            file_name="hasil_potong.pdf",
                            mime="application/pdf",
                            key="download_cut_pdf",
                        )

                    except Exception as e:
                        st.error(f"Gagal memotong PDF: {e}")

            # =========================
            # Tab Convert ke Gambar
            # =========================
            with tab_convert:
                st.subheader("Convert PDF ke Gambar")

                page_range_image = st.text_input(
                    "Halaman yang ingin di-convert",
                    value=default_page_range,
                    help="Contoh: 1-3, 5, 7-9",
                    key="page_range_image",
                )

                image_format = st.selectbox(
                    "Format gambar",
                    options=["JPG", "PNG", "WEBP"],
                    index=0,
                    key="image_format",
                )

                zoom = st.slider(
                    "Kualitas render gambar",
                    min_value=1.0,
                    max_value=4.0,
                    value=2.0,
                    step=0.5,
                    help="Semakin besar nilainya, gambar semakin tajam tetapi ukuran file semakin besar.",
                    key="zoom",
                )

                compress_image = st.checkbox(
                    "Compress gambar hasil convert",
                    value=True,
                    key="compress_image",
                )

                image_quality = 80
                if image_format in ["JPG", "WEBP"]:
                    image_quality = st.slider(
                        "Kualitas gambar",
                        min_value=10,
                        max_value=100,
                        value=80,
                        step=5,
                        help="Semakin kecil nilainya, ukuran file semakin kecil tetapi kualitas gambar menurun.",
                        key="image_quality",
                    )
                else:
                    st.caption(
                        "Untuk PNG, compress dilakukan dengan optimize dan compress_level. Ukuran bisa tetap besar jika gambarnya kompleks."
                    )

                resize_image = st.checkbox(
                    "Kecilkan dimensi gambar",
                    value=False,
                    help="Aktifkan jika ingin gambar lebih kecil ukurannya.",
                    key="resize_image",
                )

                max_width = 1200
                if resize_image:
                    max_width = st.number_input(
                        "Maksimal lebar gambar dalam pixel",
                        min_value=300,
                        max_value=5000,
                        value=1200,
                        step=100,
                        key="max_width",
                    )

                if st.button("Convert ke Gambar", key="button_convert_image"):
                    try:
                        images = convert_pdf_to_images(
                            pdf_bytes=pdf_bytes,
                            page_range_text=page_range_image,
                            image_format=image_format,
                            zoom=zoom,
                            compress_image=compress_image,
                            image_quality=image_quality,
                            resize_image=resize_image,
                            max_width=int(max_width),
                        )

                        if not images:
                            st.error("Tidak ada gambar yang berhasil dibuat.")
                        elif len(images) == 1:
                            filename, image_bytes, mime_type = images[0]

                            st.success("PDF berhasil di-convert menjadi gambar.")
                            st.info(f"Ukuran gambar: {format_file_size(len(image_bytes))}")

                            st.download_button(
                                label=f"Download {filename}",
                                data=image_bytes,
                                file_name=filename,
                                mime=mime_type,
                                key="download_single_image",
                            )
                        else:
                            zip_bytes = create_zip_from_images(images)

                            st.success(
                                f"PDF berhasil di-convert menjadi {len(images)} gambar."
                            )
                            st.info(f"Ukuran ZIP: {format_file_size(len(zip_bytes))}")

                            st.download_button(
                                label="Download semua gambar dalam ZIP",
                                data=zip_bytes,
                                file_name="hasil_convert_gambar.zip",
                                mime="application/zip",
                                key="download_zip_images",
                            )

                    except Exception as e:
                        st.error(f"Gagal convert PDF ke gambar: {e}")

    except Exception as e:
        st.error(f"Gagal membaca PDF: {e}")
