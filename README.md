# PDFMZ - Aplikasi Pemotong PDF

PDFMZ adalah aplikasi sederhana untuk memotong file PDF berdasarkan halaman yang dipilih.  
Aplikasi ini dibuat menggunakan Python, Streamlit, dan pypdf.

## Fitur

- Upload file PDF
- Pilih halaman yang ingin diambil
- Mendukung format halaman seperti:
  - `1`
  - `1-3`
  - `1,3,5`
  - `1-3,7,10`
- Download hasil PDF yang sudah dipotong

## Cara Menjalankan Aplikasi

1. Clone repository
git clone URL_REPOSITORY_KAMU
cd PDFMZ

2. Buat virtual environment
python -m venv .venv

3. Aktifkan virtual environment
- Untuk Windows PowerShell:
.venv\Scripts\activate
- Untuk Mac/Linux:
source .venv/bin/activate

4. Install library
pip install -r requirements.txt

5. Jalankan aplikasi
streamlit run app.py

Setelah itu buka browser ke alamat:
http://localhost:8501

# Struktur Project
PDFMZ/
├── app.py
├── requirements.txt
├── README.md
└── .gitignore

# Catatan
File PDF yang di-upload dan hasil PDF yang di-download tidak otomatis masuk ke folder project.
Hasil PDF akan diunduh melalui browser.