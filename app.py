import io
import streamlit as st
from pypdf import PdfReader, PdfWriter


def parse_page_ranges(text: str, total_pages: int) -> list[int]:
    """
    Input contoh:
    - "1-3"     -> halaman 1 sampai 3
    - "1,3,5"   -> halaman 1, 3, dan 5
    - "1-3,7"   -> halaman 1, 2, 3, dan 7

    Output berupa index halaman mulai dari 0.
    """
    pages = []

    for part in text.replace(" ", "").split(","):
        if not part:
            continue

        if "-" in part:
            start, end = part.split("-", 1)
            start = int(start)
            end = int(end)

            if start > end:
                raise ValueError(f"Range tidak valid: {part}")

            pages.extend(range(start, end + 1))
        else:
            pages.append(int(part))

    if not pages:
        raise ValueError("Masukkan minimal satu halaman.")

    for page in pages:
        if page < 1 or page > total_pages:
            raise ValueError(
                f"Halaman {page} di luar batas. PDF ini hanya punya {total_pages} halaman."
            )

    return [page - 1 for page in pages]


def cut_pdf(pdf_bytes: bytes, page_range_text: str) -> bytes:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    total_pages = len(reader.pages)
    selected_pages = parse_page_ranges(page_range_text, total_pages)

    for page_index in selected_pages:
        writer.add_page(reader.pages[page_index])

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)

    return output.read()


st.set_page_config(page_title="Pemotong PDF", page_icon="✂️")

st.title("✂️ Aplikasi Pemotong PDF")
st.write("Upload PDF, pilih halaman yang ingin diambil, lalu download hasilnya.")

uploaded_file = st.file_uploader("Upload file PDF", type=["pdf"])

if uploaded_file:
    pdf_bytes = uploaded_file.read()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)

    st.success(f"PDF berhasil dibaca. Total halaman: {total_pages}")

    page_range = st.text_input(
        "Halaman yang ingin diambil",
        value="1",
        help="Contoh: 1-3, 5, 7-9",
    )

    if st.button("Potong PDF"):
        try:
            result_pdf = cut_pdf(pdf_bytes, page_range)

            st.download_button(
                label="Download PDF hasil",
                data=result_pdf,
                file_name="hasil_potong.pdf",
                mime="application/pdf",
            )

            st.success("PDF berhasil dipotong.")
        except Exception as e:
            st.error(f"Gagal memotong PDF: {e}")