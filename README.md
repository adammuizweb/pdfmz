# PDFMZ - Aplikasi Pemotong PDF

PDFMZ adalah aplikasi sederhana untuk memotong file PDF dan convert ke gambar.

Ada dua versi:

| Versi | Platform | Cara Pakai |
|---|---|---|
| **Web** 🌐 | Browser (client-side) | Buka [`web/index.html`](web/index.html) atau langsung coba di [home.adammuiz.com/pdf/](https://home.adammuiz.com/pdf/) |
| **Desktop** 💻 | Windows / Linux / macOS | `streamlit run app.py` (Python) atau download [compiled binary](https://github.com/adammuizweb/pdfmz/releases) |

## Fitur (Web)

- Potong PDF — pilih halaman via range (`1-3,5,7`), preview thumbnail
- Convert PDF ke gambar — JPG / PNG / WEBP, slider kualitas & zoom
- Semua proses di **browser** — file tidak dikirim ke server
- Dukungan mobile & tablet

## Fitur (Desktop)

- Upload file PDF
- Pilih halaman yang ingin diambil
- Convert PDF ke gambar dengan kontrol kualitas
- Mendukung format halaman:
  - `1`
  - `1-3`
  - `1,3,5`
  - `1-3,7,10`
- Download hasil PDF yang sudah dipotong

## Cara Menjalankan Aplikasi

### 1. Clone repository

```bash
git clone https://github.com/adammuizweb/pdfmz.git
cd pdfmz
```

### 2. Buat virtual environment

```bash
python -m venv .venv
```

### 3. Aktifkan virtual environment

Untuk Windows PowerShell:

```bash
.venv\Scripts\activate
```

Untuk Mac/Linux:

```bash
source .venv/bin/activate
```

### 4. Install library

```bash
pip install -r requirements.txt
```

### 5. Jalankan aplikasi

```bash
streamlit run app.py
```

Setelah itu buka browser ke alamat:

```text
http://localhost:8501
```

## Struktur Project

```text
PDFMZ/
├── web/
│   └── index.html        # Versi web (client-side JS)
├── app.py                # Versi desktop (Python + Streamlit)
├── requirements.txt
├── README.md
└── .gitignore
```

## Catatan

File PDF yang di-upload dan hasil PDF yang di-download tidak otomatis masuk ke folder project.

Hasil PDF akan diunduh melalui browser.
