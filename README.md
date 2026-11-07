# Zydra Model (text-based)

<p align="center">
  <a href="https://github.com/fareldev-hub/ZydraModel">
    <img src="https://img.shields.io/badge/Zydra-AI%20Chat-6C5CE7?style=for-the-badge&logo=huggingface&logoColor=white" alt="Zydra AI Chat">
  </a>
  <a href="https://www.docker.com/">
    <img src="https://img.shields.io/badge/Docker-Container-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  </a>
  <a href="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct">
    <img src="https://img.shields.io/badge/Base-Qwen2.5%200.5B%20Instruct-4285F4?style=for-the-badge" alt="Qwen2.5 0.5B Instruct">
  </a>
</p>

<p align="center">
  <a href="https://img.shields.io/github/commit-activity/t/fareldev-hub/ZydraModel">
    <img src="https://img.shields.io/github/commit-activity/t/fareldev-hub/ZydraModel?label=total%20commits&style=flat-square" alt="Total commits">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/graphs/contributors">
    <img src="https://img.shields.io/github/contributors/fareldev-hub/ZydraModel?style=flat-square" alt="Contributors">
  </a>
  <a href="https://img.shields.io/badge/total%20model%20size-1.43%20GiB-blue?style=flat-square">
    <img src="https://img.shields.io/badge/total%20model%20size-1.43%20GiB-blue?style=flat-square" alt="Total ukuran file model sekitar 1.43 GiB">
  </a>
  <a href="https://github.com/fareldev-hub/ZydraModel/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/code%20license-MIT-green?style=flat-square" alt="Lisensi kode MIT">
  </a>
</p>

## Ukuran total proyek

Per 7 November 2026, seluruh file proyek termasuk checkpoint dan bobot model
lokal berukuran sekitar **1.43 GiB (1.53 GB)**. Folder `.git` menyimpan
riwayat dan objek Git sekitar **5.82 GiB (6.25 GB)**, sehingga seluruh folder
proyek termasuk riwayat Git berukuran sekitar **7.25 GiB (7.79 GB)**. Angka
ini dapat berubah saat model, file proyek, atau riwayat Git berubah.

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

Pastikan Docker Engine tersedia dan letakkan model Qwen2.5-0.5B-Instruct GGUF di:

```text
model/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

Folder `model/` diabaikan Git agar bobot model yang besar tidak ikut masuk ke
repository. Qwen2.5-0.5B-Instruct adalah model instruction-tuned, mendukung
template chat, dan checkpoint Hugging Face-nya dapat di-fine-tune dengan LoRA.
Bobot GGUF Q4_K_M resminya berukuran 491,400,032 byte (sekitar 469 MiB).
Model dan GGUF resminya tersedia di bawah Apache 2.0. Unduh model:

```sh
python3 -m pip install -U huggingface_hub
hf download Qwen/Qwen2.5-0.5B-Instruct-GGUF \
  qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --local-dir model
```

File quantized ini sekitar 469 MiB. Buat atau edit `.env`, gunakan password
master yang kuat, dan jangan commit file tersebut:

```dotenv
AUTH=ganti-dengan-password-kuat
MODEL_PATH=/app/model/qwen2.5-0.5b-instruct-q4_k_m.gguf
API_KEYS_FILE=/data/database/api.json
```

Model ini dijalankan dari GGUF menggunakan `llama.cpp` dan template chat model
otomatis dari metadata GGUF; Ollama tidak diperlukan saat build maupun runtime.
Ukuran file bobot bukan kebutuhan RAM total: runtime juga memakai memori untuk
context/KV cache dan proses, sementara kualitas/kemampuan model 0.5B lebih
terbatas daripada model 1.5B.

## Identitas dan fine-tuning

API tidak lagi menyisipkan identitas sebagai pesan system pada request model.
Dataset LoRA hanya berisi pesan user/assistant, sehingga identitas Zydra
dipelajari dalam bobot dan model dapat mempertahankannya saat dijalankan di luar
API. `training/data.txt` menjadi metadata untuk jawaban identitas deterministik
di API, bukan prompt model. Tanpa adapter hasil fine-tuning, model Instruct
dasar tetap dapat memberi jawaban generik atau keliru; fine-tuning tidak
menjamin semua keluaran selalu benar. Contoh dataset saat ini hanya 35 baris
dan cocok untuk menguji alur, bukan untuk menjamin perilaku produksi.

Metadata identitas dibaca dari `training/data.txt` oleh handler identitas API.
Setelah mengubah kode API, rebuild image dan buat ulang container:

```sh
docker build -t zydra-text .
docker rm -f zydra
docker run -d \
  --name zydra \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/model:/app/model:ro" \
  -v "$(pwd)/training/data.txt:/app/training/data.txt:ro" \
  -v zydra-data:/data \
  zydra-text
```

## Fine-tuning LoRA

Contoh dataset percakapan disimpan di `training_data/identity_train.jsonl`; tambah
contoh beragam dan berkualitas sebelum training. Dataset hanya memakai pesan
user/assistant sehingga identitas dipelajari tanpa system prompt. Skrip melatih
adapter LoRA pada jawaban assistant. Checkpoint dasar Instruct Qwen dapat
diunduh tanpa akses gated:

```sh
python3 -m pip install -r requirements-training.txt
hf download Qwen/Qwen2.5-0.5B-Instruct \
  --local-dir model/qwen2.5-0.5b-instruct
python3 scripts/train_identity_lora.py \
  --base-model model/qwen2.5-0.5b-instruct \
  --train-file training_data/identity_train.jsonl \
  --epochs 6
```

Training memerlukan RAM/VRAM yang cukup; GPU CUDA disarankan dan training CPU
bisa sangat lambat. Adapter LoRA dapat dijalankan bersama GGUF dasar tanpa
menulis salinan model gabungan berukuran besar. Konversikan adapter dengan
`llama.cpp`:

```sh
git clone --depth 1 https://github.com/ggml-org/llama.cpp
python3 llama.cpp/convert_lora_to_gguf.py \
  model/qwen2.5-0.5b-zydra-lora \
  --base model/qwen2.5-0.5b-instruct \
  --outfile model/qwen2.5-0.5b-zydra-lora.gguf \
  --outtype f16
```

Atur `MODEL_PATH` ke GGUF dasar dan `MODEL_LORA_PATH` ke adapter GGUF pada
`.env`, lalu recreate container. Bobot dasar Q4_K_M (~469 MiB) dan adapter
LoRA tetap terpisah; adapter diterapkan saat runtime dan bukan system prompt.
Skrip `merge_identity_lora.py` tetap tersedia bila diperlukan ekspor model
gabungan mandiri, tetapi proses merge dan konversi memerlukan ruang disk lebih
banyak.

## Build dan jalankan

Build image aplikasi:

```sh
docker build -t zydra-text .
```

Buat volume permanen untuk model dan konfigurasi, lalu jalankan container:

```sh
docker volume create zydra-data
# Jika container versi lama masih berjalan, hapus container-nya terlebih dahulu.
docker rm -f zydra
docker run -d \
  --name zydra \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/model:/app/model:ro" \
  -v "$(pwd)/training/data.txt:/app/training/data.txt:ro" \
  -v zydra-data:/data \
  zydra-text
```

Model harus sudah ada di folder `model/` sebelum container dijalankan. Pantau
proses pemuatan:

```sh
docker logs -f zydra
```

Pemuatan selesai saat log menampilkan `Model Zydra lokal siap.`. File bobot
model sekitar 469 MiB; bobot tetap berada di folder proyek dan tidak disalin ke
image. Hentikan tampilan log dengan `Ctrl+C`; container tetap berjalan.

Pastikan API dan model siap:

```sh
curl http://localhost:8000/health
```

Lanjutkan setelah respons berisi `"model_ready":true`. API Explorer tersedia di `http://localhost:8000/`. Setiap route ditampilkan
sebagai item tersendiri. Klik **Try it out**, isi parameter atau body yang
tersedia, lalu **Execute** untuk melihat status dan response route tersebut.
Saat halaman dibuka, SweetAlert meminta nilai `AUTH` dari file `.env`. Masukkan
nilainya di popup; server memverifikasinya sebelum menampilkan halaman. AUTH
yang salah menolak akses. Credential hanya diminta sekali saat awal dan hanya
disimpan di memori selama halaman terbuka; tidak ditanamkan ke HTML atau
disimpan di browser. Tombol **Buat API key** meminta nama saja, kemudian server
membuat key acak dan UI menampilkan nilai lengkapnya sekali dengan opsi salin.
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
  -d '{"model":"zydra","messages":[{"role":"user","content":"Balas singkat: AI siap"}]}'
```

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

Base model Qwen2.5-0.5B-Instruct dan varian GGUF resminya tersedia di bawah
Apache License 2.0. Salinan lengkap lisensi ada di
[`MODEL_LICENSES/QWEN-APACHE-2.0.txt`](MODEL_LICENSES/QWEN-APACHE-2.0.txt);
notice dan atribusi model juga ada di `MODEL_LICENSES/NOTICE.md`. Keduanya
disertakan dalam Docker image di `/app/MODEL_LICENSES`. Lisensi model berlaku
terpisah dari lisensi MIT kode proyek. Lihat pula
[lisensi resmi Qwen](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/LICENSE).

## Perintah Docker

```sh
docker logs -f zydra
docker stop zydra
docker start zydra
docker rm -f zydra
```

Model berada di folder proyek `model/`, terpisah dari volume `zydra-data`.
Menghapus volume `zydra-data` hanya menghapus konfigurasi dan API key; untuk
menghapus bobot model, hapus file lokal
`model/qwen2.5-0.5b-instruct-q4_k_m.gguf`.

API tester dilayani di route root (`/`) dan menampilkan response endpoint yang
dipilih. Endpoint dokumentasi `/docs` dan `/openapi.json` tetap dinonaktifkan.

Notice base model tersedia di `MODEL_LICENSES/`.

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
