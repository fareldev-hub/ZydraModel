# Menjalankan Zydra

## Prasyarat

- Docker Engine dan Docker Compose
- Koneksi internet untuk unduhan model pertama
- Direktori `MODEL_LICENSES/` tersedia saat build image

## Jalankan Lokal

Dari root repository, salin konfigurasi contoh dan ubah `AUTH` pada `.env`
menjadi password yang kuat. Jangan commit file `.env`.

```sh
cp .env.example .env
```

Build dan jalankan:

```sh
docker compose up -d --build
```

Compose menjalankan API dan `llama-server` dalam satu container `zydra`.
Container mengunduh model dan projector gambar dari Hugging Face saat startup
pertama. Cache unduhan disimpan pada volume Docker `llama-model-cache` agar
tidak perlu mengunduh ulang saat container dimulai kembali.

Pantau proses startup:

```sh
docker compose logs -f zydra
```

Model siap saat log menampilkan `Server llama.cpp dan model Hugging Face siap.`
Periksa status dengan:

```sh
curl -i http://localhost:8000/ready
```

HTTP 200 berarti model siap. Buka `http://localhost:8000/` dan masukkan nilai
`AUTH` saat diminta.

Hentikan container tanpa menghapus volume data dan cache:

```sh
docker compose down
```

Jalankan kembali:

```sh
docker compose up -d
```

## Konfigurasi

Default `HF_MODEL_REPO` memakai pasangan SmolVLM2 Q8_0 dengan projector gambar
yang kompatibel. Jika mengganti repository, pastikan GGUF utama dan `mmproj`
berasal dari pasangan yang cocok.

| Variabel | Fungsi | Default |
| --- | --- | --- |
| `AUTH` | Password admin API dan halaman chat | Contoh di `.env.example` |
| `HOST_PORT` | Port lokal yang dibuka di browser | `8000` |
| `HF_MODEL_REPO` | Repository dan quantization model | `ggml-org/SmolVLM2-500M-Video-Instruct-GGUF:Q8_0` |
| `MODEL_CONTEXT_SIZE` | Ukuran konteks model | `2048` |
| `MODEL_THREADS` | Jumlah thread CPU | `4` |

API tersedia pada port `HOST_PORT`. `llama-server` hanya mendengarkan pada
`127.0.0.1:8081` di dalam container.

## Uji Chat API

Setelah `/ready` mengembalikan HTTP 200, uji endpoint chat:

```sh
set -a
. ./.env
set +a

curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"model":"zydra-loRa","messages":[{"role":"user","content":"Balas singkat: server siap"}]}'
```

## Deploy ke Railway

1. Buat satu service dari repository ini dan gunakan `Dockerfile`.
2. Tambahkan volume dengan mount path `/data`.
3. Atur `AUTH` dengan password kuat dan pastikan `HF_MODEL_REPO` valid.
4. Buat public domain untuk service API.
5. Buka `/ready` dan tunggu sampai mengembalikan HTTP 200.

Entrypoint mengunduh dan menjalankan model serta API dalam satu container.
Jangan buat service `llama` terpisah. Hapus variabel lama `MODEL_SERVER_URL` jika
masih ada. Gunakan `MODEL_CONTEXT_SIZE` dan `MODEL_THREADS` untuk mengatur
resource model.

## Troubleshooting

- Jika `/ready` mengembalikan HTTP 503, tunggu unduhan pertama dan periksa
  `docker compose logs -f zydra`.
- Jika log menyebut dimensi `mmproj` tidak cocok, gunakan pasangan GGUF dan
  projector yang kompatibel.
- Jika port `8000` sudah digunakan, ubah `HOST_PORT` di `.env`.
- Jika build gagal karena `MODEL_LICENSES/` tidak ditemukan, pulihkan direktori
  tersebut sebelum menjalankan `docker compose up -d --build`.