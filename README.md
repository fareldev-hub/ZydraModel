# Zydra Model (text and image)

<p align="center">
  <a href="https://github.com/fareldev-hub/ZydraModel">
    <img src="https://img.shields.io/badge/Zydra-AI%20Chat-6C5CE7?style=for-the-badge&logo=huggingface&logoColor=white" alt="Zydra AI Chat">
  </a>
  <a href="https://www.docker.com/">
    <img src="https://img.shields.io/badge/Docker-Container-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  </a>
  <a href="https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct">
    <img src="https://img.shields.io/badge/Vision-SmolVLM2%20500M-4285F4?style=for-the-badge" alt="SmolVLM2 500M vision model">
  </a>
</p>

<p align="center">
  <a href="https://img.shields.io/github/commit-activity/t/fareldev-hub/ZydraModel">
    <img src="https://img.shields.io/github/commit-activity/t/fareldev-hub/ZydraModel?label=total%20commits&style=flat-square" alt="Total commits">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
    <img src="https://img.shields.io/github/contributors/fareldev-hub/ZydraModel?style=flat-square" alt="Contributors">
  </a>
  <a href="https://img.shields.io/badge/total%20model%20size-0.51%20GiB-blue?style=flat-square">
    <img src="https://img.shields.io/badge/total%20model%20size-0.51%20GiB-blue?style=flat-square" alt="Ukuran model dan projector vision sekitar 521 MiB">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/code%20license-MIT-green?style=flat-square" alt="Lisensi kode MIT">
  </a>
</p>

## Ukuran total proyek

Per 8 November 2026, file proyek termasuk model vision dan projector berukuran
sekitar **0.51 GiB (546 MB)**. Folder `.git` berukuran sekitar **23 MiB**,
sehingga seluruh folder kerja sekitar **0.54 GiB (570 MB)**. Angka dapat
berubah saat file model atau riwayat Git berubah.

## Statistik dan kontribusi

<p>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
    <img src="https://github-profile-summary-cards.vercel.app/api/cards/profile-details?username=fareldev-hub&theme=github_dark" alt="Grafik kontribusi dan aktivitas commit GitHub Farel Alfareza">
  </a>
</p>

Grafik khusus repository Zydra:

<p>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/commit-activity">
    <img src="https://img.shields.io/badge/Buka-grafik%20commit%20Zydra-24292F?style=for-the-badge&logo=github&logoColor=white" alt="Buka grafik commit Zydra">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
    <img src="https://img.shields.io/badge/Buka-grafik%20kontributor%20Zydra-6C5CE7?style=for-the-badge&logo=github&logoColor=white" alt="Buka grafik kontributor Zydra">
  </a>
</p>

## Persiapan

Pastikan Docker Engine tersedia dan koneksi internet aktif. Docker akan
mengunduh model dari Hugging Face saat container `llama` pertama kali dijalankan.

API menggunakan model layanan `zydra-loRa`, SmolVLM2 500M Q8_0 yang mendukung
gambar dan teks. llama.cpp memerlukan GGUF utama dan `mmproj` untuk encoder
gambar. Cache model disimpan dalam volume Docker `llama-model-cache`, sehingga
unduhan tidak diulang pada restart biasa.

Salin `.env.example` menjadi `.env`, lalu isi `AUTH` dengan password master
yang kuat. Jangan commit file `.env`. Jika `AUTH` dibiarkan kosong, aplikasi
membuat password secara otomatis pada startup pertama dan menyimpannya di
`AUTH_FILE`:

```sh
cp .env.example .env
```

`.env.example` mencantumkan variabel runtime beserta nilai default-nya.

Compose menjalankan API dan server llama.cpp. Server llama.cpp mengunduh model
dari repository `fareld3v-hub/zydra` menggunakan opsi `-hf`.
Repository dapat diganti melalui `HF_MODEL_REPO` di file `.env`.

## Build dan jalankan dengan Docker Compose

Jalankan dari root repository. Pastikan file `.env` sudah tersedia seperti
dijelaskan di bagian persiapan. Compose membangun image jika diperlukan,
menjalankan API dan server llama.cpp di background, dan menyimpan data API pada
volume persisten:

```sh
docker compose up -d --build
```

Container tetap berjalan setelah perintah selesai. Pantau startup dan tunggu
sampai log menampilkan `Model vision zydra-loRa.gguf siap.`:

```sh
docker compose logs -f zydra llama
```

Tekan `Ctrl+C` untuk berhenti mengikuti log; service tetap berjalan. Perintah
berikut menghentikan dan menghapus container, tetapi mempertahankan volume data:

```sh
docker compose down
```

Bobot model tidak disalin ke image API dan di-cache pada volume Docker. Port
host default adalah `8000`; ubah dengan `HOST_PORT` di file `.env` bila port
tersebut sudah digunakan.

Pastikan API dan model siap:

```sh
curl http://localhost:8000/health
```

Lanjutkan setelah respons berisi `"model_ready":true`. API Explorer tersedia di
`http://localhost:8000/` dan menampilkan endpoint GET, termasuk vision. Klik
**Try it out**, isi parameter, lalu **Execute** untuk melihat status dan
response. POST chat OpenAI-compatible dan operasi API key tetap tersedia di
backend, tetapi tidak ditampilkan dalam daftar Explorer. Nama model dikunci ke
`zydra-loRa`.
Saat halaman dibuka, SweetAlert meminta nilai `AUTH` dari file `.env`. Masukkan
nilainya di popup; server memverifikasinya sebelum menampilkan halaman. Setelah
verifikasi berhasil, AUTH disimpan di `localStorage` browser agar halaman tidak
meminta password lagi saat dibuka ulang. API key terakhir yang dibuat atau
berhasil digunakan juga disimpan lokal dan otomatis mengisi field `apikey` pada
endpoint chat. Hapus data situs/browser untuk menghapus credential tersimpan;
jangan aktifkan penyimpanan ini pada perangkat bersama karena script di origin
yang sama dapat mengakses `localStorage`. Request prompt di UI mendukung kolom
`instruction` untuk memberi arahan sistem sebelum prompt dikirim ke model.
Response JSON memakai syntax highlighting; panel **Contoh penggunaan API**
menyediakan JavaScript backend, JavaScript fetch, Python, dan cURL. Halaman
dokumentasi `/docs` dan schema `/openapi.json` tetap dinonaktifkan.

## Uji balasan teks

Selain POST dengan JSON body di bawah, endpoint prompt juga mendukung query:

```sh
curl --get http://localhost:8000/v1/prompt \
  --data-urlencode "apikey=$ZYDRA_API_KEY" \
  --data-urlencode "prompt=Jelaskan fotosintesis secara singkat."
```

Query string dapat tercatat di access log; penggunaan backend sebaiknya
mengirim API key melalui header `X-API-Key`.

Gunakan route `POST /v1/prompt` untuk mengirim satu prompt dan menerima field
`response` langsung:

```sh
set -a
. ./.env
set +a

curl http://localhost:8000/v1/prompt \
  -H "Authorization: Bearer $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Jelaskan fotosintesis secara singkat."}'
```

Route prompt menerima POST dengan API key di header:

```sh
curl http://localhost:8000/v1/prompt \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Jelaskan fotosintesis singkat."}'
```

Endpoint ini mengembalikan JSON berisi `model`, `response`, dan `creator`.
Route chat lama `/api/chat` tidak disediakan. UI tester dilayani melalui GET `/`;
request dari tester memanggil endpoint API di origin yang sama.

API chat kompatibel dengan format OpenAI. Uji dari terminal:

```sh
set -a
. ./.env
set +a
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $AUTH" \
  -H "Content-Type: application/json" \
  -d '{"model":"zydra-loRa","messages":[{"role":"user","content":"Balas singkat: AI siap"}]}'
```

Parameter `tools` dari client OpenAI-compatible diabaikan karena model vision
ini belum mendukung tool calling; chat teks tetap diproses.

Route `GET /v1/chat/vision` menerima URL gambar publik dan caption opsional,
lalu mengembalikan respons dalam format chat completion:

```sh
curl --get http://localhost:8000/v1/chat/vision \
  -H "X-API-Key: $ZYDRA_API_KEY" \
  --data-urlencode "image_link=https://example.com/gambar.jpg" \
  --data-urlencode "apikey=$ZYDRA_API_KEY" \
  --data-urlencode "caption=Jelaskan isi gambar ini."
```

URL harus mengarah langsung ke gambar JPEG, PNG, atau WebP publik berukuran
maksimal 10 MB. Redirect dan alamat lokal/private ditolak. API key dapat dikirim
melalui header `X-API-Key` atau parameter query `apikey`; header tetap
direkomendasikan karena parameter URL dapat tercatat di access log. Nilai URL
dan caption berada di query string.

Jawaban model muncul di `choices[0].message.content`. Endpoint `/health` dan
`/status` tidak memerlukan password. Endpoint API lain memerlukan `AUTH` melalui
header Bearer atau `X-API-Key`.

## Mengelola API keys

Route prompt/chat dan daftar model memerlukan API key. Key dapat dikirim melalui
header `X-API-Key` atau parameter query `apikey`; penggunaan header
direkomendasikan agar key tidak tercatat di URL. Route status `/health`,
`/status`, dan `/ready` tetap bisa diakses tanpa key. Route pengelolaan key
memerlukan AUTH master.

Kelola API key melalui endpoint dengan password master `AUTH`. Buat key:

```sh
curl http://localhost:8000/v1/api-keys \
  -X POST \
  -H "Authorization: ******" \
  -H "Content-Type: application/json" \
  -d '{"name":"aplikasi-saya"}'
```

Key baru berformat `zdy-...`; simpan nilai penuh saat pertama kali diterima.

Key terkelola dapat digunakan untuk endpoint API selain route pengelolaan key.
Route `GET /v1/api-keys`, `POST /v1/api-keys`, dan
`DELETE /v1/api-keys/{key_id}` hanya menerima password master `AUTH`.
Route-route ini mengembalikan JSON dan dapat dipakai untuk melihat metadata
key atau mencabut key kapan saja.

Hash SHA-256 dan metadata key disimpan di `database/api.json`. File lokal ini
diabaikan Git. Di Docker, `API_KEYS_FILE=/data/database/api.json` menempatkannya
di volume `zydra-data` sehingga tetap ada saat container dibuat ulang. Key asli
tidak disimpan dalam file.

## Lisensi

Kode proyek Zydra tersedia di bawah MIT. Model vision SmolVLM2 tersedia di bawah
Apache License 2.0. Identitas Zydra diberikan melalui system prompt API.

Notice model tersedia di `MODEL_LICENSES/NOTICE.md` dan teks lisensi di
`MODEL_LICENSES/SMOLVLM2-APACHE-2.0`.

---

<div align="center">
  <h2>Tentang Pembuat</h2>
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
  <p>Jika project ini bermanfaat, dukung pengembangannya melalui:</p>
  <a href="https://trakteer.id/farel_alfarez">
    <img src="https://img.shields.io/badge/Via-Trakteer-BE1E2D?style=for-the-badge" alt="ThePort (@farel_alfarez) • Trakteer">
  </a>
  &nbsp;
  <a href="https://saweria.co/fareldev">
    <img src="https://img.shields.io/badge/Donasi%20via-Saweria-FFB000?style=for-the-badge" alt="Donasi via Saweria">
  </a>
  <br><br>
  <sub>Terima kasih atas dukungan dan kontribusinya untuk Zydra 💜</sub>
</div>
