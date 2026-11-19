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

## Clone Repository

Clone repository ini terlebih dahulu, lalu masuk ke direktori hasil clone:

```sh
git clone https://github.com/fareldev-hub/ZydraModel.git
cd ZydraModel
```

## Jalankan Lokal

Dari root repository hasil clone, salin konfigurasi contoh dan ubah `AUTH` pada
`.env` menjadi password yang kuat. Jangan commit file `.env`.

```sh
cp .env.example .env
```

Build dan jalankan:

```sh
docker compose up -d --build
```

Compose menjalankan API dan **dua** `llama-server` dalam satu container `zydra`:

| Model | Port internal | Kegunaan |
| --- | --- | --- |
| `zydra-vision` (SmolVLM2 + mmproj) | `127.0.0.1:8081` | Hanya `/v1/chat/vision` (gambar) |
| `zydra-loRa` | `127.0.0.1:8082` | Hanya `/v1/chat/completions` dan `/v1/prompt` (teks) |

Pemisahan ini mencegah model vision ikut menjawab chat teks (dan sebaliknya),
sehingga jawaban tidak mudah melenceng. `zydra-loRa` sengaja dijalankan dengan
`--no-mmproj`, jadi tidak menerima gambar. Container mengunduh kedua model dari
Hugging Face saat startup pertama. Cache unduhan disimpan pada volume Docker
`llama-model-cache` agar tidak perlu mengunduh ulang saat container dimulai
kembali. Halaman chat otomatis memakai `zydra-vision` saat ada gambar yang
dilampirkan, dan `zydra-loRa` untuk percakapan teks biasa.

Pantau proses startup:

```sh
docker compose logs -f zydra
```

Model siap saat log menampilkan `Model vision zydra-vision dan model chat zydra-loRa siap.`
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

`VISION_MODEL_REPO`/`HF_MODEL_REPO` memakai pasangan SmolVLM2 Q8_0 dengan
projector gambar yang kompatibel. Jika mengganti repository vision, pastikan
GGUF utama dan `mmproj` berasal dari pasangan yang cocok. `CHAT_MODEL_REPO`
memakai `fareld3v-hub/zydra`, dengan file GGUF `zydra-loRa.gguf`.

| Variabel | Fungsi | Default |
| --- | --- | --- |
| `AUTH` | Password admin API dan halaman chat | Contoh di `.env.example` |
| `HOST_PORT` | Port lokal yang dibuka di browser | `8000` |
| `VISION_MODEL_REPO` | Repository model vision (+ mmproj otomatis) | `ggml-org/SmolVLM2-500M-Video-Instruct-GGUF:Q8_0` |
| `VISION_SERVER_URL` | Alamat server llama.cpp vision | `http://127.0.0.1:8081` |
| `VISION_CONTEXT_SIZE` | Ukuran konteks model vision | `2048` |
| `VISION_THREADS` | Jumlah thread CPU model vision | `4` |
| `CHAT_MODEL_REPO` | Repository model chat teks | `fareld3v-hub/zydra` |
| `CHAT_MODEL_FILE` | File GGUF chat | `zydra-loRa.gguf` |
| `CHAT_SERVER_URL` | Alamat server llama.cpp chat | `http://127.0.0.1:8082` |
| `CHAT_CONTEXT_SIZE` | Ukuran konteks model chat | `2048` |
| `CHAT_THREADS` | Jumlah thread CPU model chat | `4` |
| `HF_MODEL_REPO`, `MODEL_CONTEXT_SIZE`, `MODEL_THREADS` | Fallback lama untuk pengaturan vision | lihat `.env.example` |

API tersedia pada port `HOST_PORT`. Kedua `llama-server` hanya mendengarkan pada
`127.0.0.1` di dalam container (port `8081` untuk vision, `8082` untuk chat) dan
tidak diekspos ke host.

`zydra-loRa` menolak `image_data` pada `/v1/chat/completions` dengan HTTP 422,
dan `/v1/chat/vision` menolak model `zydra-loRa` dengan HTTP 400. Gunakan
`zydra-vision` untuk semua request gambar. `GET /health` menampilkan status
masing-masing model melalui `chat_ready`, `vision_ready`, dan `models`.

## Uji Chat API

Setelah `/ready` mengembalikan HTTP 200, uji endpoint chat teks (`zydra-loRa`):

```sh
set -a
. ./.env
set +a

curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"model":"zydra-loRa","messages":[{"role":"user","content":"Balas singkat: server siap"}]}'
```

Uji endpoint vision (`zydra-vision`) dengan URL gambar publik:

```sh
curl "http://localhost:8000/v1/chat/vision?image_link=https%3A%2F%2Fexample.com%2Fgambar.jpg&caption=Apa%20yang%20terlihat%20di%20gambar%20ini%3F" \
  -H "Authorization: Bearer $AUTH"
```

Atau kirim `image_data` (data URL base64) lewat POST `/v1/chat/vision` dengan
`"model": "zydra-vision"`. Jangan mengirim gambar ke `/v1/chat/completions`.

## Deploy ke Railway

1. Buat satu service dari repository ini dan gunakan `Dockerfile`.
2. Tambahkan volume dengan mount path `/data`.
3. Atur `AUTH` dengan password kuat dan pastikan `HF_MODEL_REPO` valid.
4. Buat public domain untuk service API.
5. Buka `/ready` dan tunggu sampai mengembalikan HTTP 200 (artinya kedua model siap).

Entrypoint mengunduh dan menjalankan kedua model serta API dalam satu container.
Jangan buat service `llama` terpisah. Variabel lama `MODEL_SERVER_URL` masih
diterima sebagai alias untuk server vision, tetapi sebaiknya gunakan
`VISION_SERVER_URL` dan `CHAT_SERVER_URL`. Atur resource lewat
`VISION_CONTEXT_SIZE`/`VISION_THREADS` dan `CHAT_CONTEXT_SIZE`/`CHAT_THREADS`.
Pastikan ukuran container cukup untuk memuat dua model sekaligus.

## Troubleshooting

- Jika `/ready` mengembalikan HTTP 503, tunggu unduhan pertama dan periksa
  `docker compose logs -f zydra`. Periksa juga `chat_ready` dan `vision_ready`
  pada `/health` untuk mengetahui model mana yang belum siap.
- Jika log menyebut dimensi `mmproj` tidak cocok, gunakan pasangan GGUF dan
  projector yang kompatibel pada `VISION_MODEL_REPO`.
- Jika chat menolak gambar, itu disengaja: kirim ke `/v1/chat/vision` dengan
  `model: "zydra-vision"`.
- Jika vision menolak `model: "zydra-loRa"`, ganti ke `zydra-vision`.
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