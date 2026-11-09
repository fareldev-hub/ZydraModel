# Menjalankan Zydra

<p>
  <a href="https://huggingface.co/fareld3v-hub/zydra">
    <img src="https://img.shields.io/badge/Model-zydra--loRa-355e3b?style=flat-square" alt="Model Zydra zydra-loRa">
  </a>
  <a href="https://huggingface.co/fareld3v-hub/zydra/tree/main">
    <img src="https://img.shields.io/badge/Files-GGUF%20%2B%20mmproj-6c8b62?style=flat-square" alt="File model GGUF dan mmproj">
  </a>
  <a href="https://huggingface.co/fareld3v-hub/zydra/tree/main">
    <img src="https://img.shields.io/badge/Download-size%20~572%20MiB-8ca579?style=flat-square" alt="Ukuran download Zydra dan mmproj sekitar 572 MiB">
  </a>
</p>

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

## Statistik

<p>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/commit-activity">
    <img src="https://img.shields.io/github/commit-activity/t/fareldev-hub/ZydraModel?label=total%20commits&style=flat-square" alt="Aktivitas commit Zydra">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
    <img src="https://img.shields.io/github/contributors/fareldev-hub/ZydraModel?style=flat-square" alt="Kontributor Zydra">
  </a>
</p>

<a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
  <img src="https://github-profile-summary-cards.vercel.app/api/cards/profile-details?username=fareldev-hub&theme=github_dark" alt="Ringkasan kontribusi GitHub Farel Alfareza">
</a>

## Developer

<div align="center">
  <a href="https://github.com/fareldev-hub">
    <img style="border-radius:10px;" src="https://github.com/fareldev-hub.png?size=160" width="112" alt="Avatar Farel Alfareza">
  </a>
  <h3>Farel Alfareza</h3>
  <p>Pembuat dan pemelihara <strong>Zydra</strong>.</p>
  <a href="https://github.com/fareldev-hub">
    <img src="https://img.shields.io/badge/GitHub-fareldev--hub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub @fareldev-hub">
  </a>
  &nbsp;
  <a href="https://tiktok.com/@logic__vibes">
    <img src="https://img.shields.io/badge/TikTok-%40logic__vibes-000000?style=for-the-badge&logo=tiktok&logoColor=white" alt="TikTok @logic__vibes">
  </a>
  <p>Dukung pengembangan melalui:</p>
  <a href="https://trakteer.id/farel_alfarez">
    <img src="https://img.shields.io/badge/Via-Trakteer-BE1E2D?style=for-the-badge" alt="ThePort (@farel_alfarez) via Trakteer">
  </a>
  &nbsp;
  <a href="https://saweria.co/fareldev">
    <img src="https://img.shields.io/badge/Donasi%20via-Saweria-FFB000?style=for-the-badge" alt="Donasi via Saweria">
  </a>
  <br><br>
  <sub>Terima kasih atas dukungan dan kontribusinya untuk Zydra.</sub>
</div>