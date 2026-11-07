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
  <a href="https://img.shields.io/badge/total%20model%20size-0.96%20GiB-blue?style=flat-square">
    <img src="https://img.shields.io/badge/total%20model%20size-0.96%20GiB-blue?style=flat-square" alt="Total ukuran file model sekitar 0.96 GiB">
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

Pastikan Docker Engine tersedia. Checkpoint dasar Qwen dan adapter Zydra LoRA
harus tersedia di folder berikut:

```text
model/zydra-base/
model/zydra-lora/
```

API menyediakan satu model layanan, `zydra-lora`, menggunakan adapter yang
dilatih dengan `training_data/identity_train.jsonl`. Adapter LoRA tetap
membutuhkan checkpoint dasar Qwen untuk bobot yang tidak diubah saat training;
folder base tidak boleh dihapus selama adapter belum digabungkan. Folder
`model/` diabaikan Git agar bobot model tidak masuk ke repository.

```sh
python3 -m pip install -U huggingface_hub
hf download Qwen/Qwen2.5-0.5B-Instruct --local-dir model/zydra-base
```

Buat atau edit `.env`, gunakan password master yang kuat, dan jangan commit
file tersebut:

```dotenv
AUTH=ganti-dengan-password-kuat
MODEL_PATH=/app/model/zydra-base
MODEL_LORA_PATH=/app/model/zydra-lora
API_KEYS_FILE=/data/database/api.json
```

Runtime menggunakan Transformers dan PEFT untuk menerapkan adapter ke checkpoint
dasar lokal. Container tidak membutuhkan file GGUF atau mengunduh model saat
runtime.

## Identitas dan fine-tuning

API menambahkan aturan agar model tidak menyebut pembuat kecuali ditanya secara
langsung. Pertanyaan identitas diproses oleh model LoRA; API tidak lagi membuat
jawaban identitas langsung dari file terpisah. Dataset training hanya digunakan
saat melatih adapter dan perubahan dataset baru berpengaruh ke bobot setelah
training ulang. Contoh dataset saat ini hanya 35 baris dan cocok untuk menguji
alur, bukan untuk menjamin perilaku produksi.

## Fine-tuning LoRA

Contoh dataset percakapan disimpan di `training_data/identity_train.jsonl`; tambah
contoh beragam dan berkualitas sebelum training. Dataset hanya memakai pesan
user/assistant sehingga identitas dipelajari tanpa system prompt. Skrip melatih
adapter LoRA pada jawaban assistant. Checkpoint dasar Instruct Qwen dapat
diunduh tanpa akses gated:

```sh
python3 -m pip install -r requirements-training.txt
hf download Qwen/Qwen2.5-0.5B-Instruct \
  --local-dir model/zydra-base
python3 scripts/train_identity_lora.py \
  --base-model model/zydra-base \
  --train-file training_data/identity_train.jsonl \
  --epochs 6
```

Training memerlukan RAM/VRAM yang cukup; GPU CUDA disarankan dan training CPU
bisa sangat lambat. Saat runtime, adapter diterapkan ke checkpoint dasar lokal.
Adapter tidak dapat dipakai sebagai file mandiri; menggabungkannya agar hanya
menyimpan bobot Zydra memerlukan proses merge tersendiri dan perubahan runtime.

## Build dan jalankan

Jalankan satu alur berikut dari root repository. Pastikan model dan file `.env`
sudah tersedia seperti dijelaskan di bagian persiapan:

```sh
docker build -t zydra-text .
docker volume create zydra-data
docker rm -f zydra 2>/dev/null || true
docker run -d \
  --name zydra \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/model:/app/model:ro" \
  -v zydra-data:/data \
  zydra-text
docker logs -f zydra
```

Tunggu sampai log menampilkan `Model Zydra LoRA siap.`. Hentikan tampilan log
dengan `Ctrl+C`; container tetap berjalan. Bobot model dipasang dari folder
proyek dan tidak disalin ke image.

Pastikan API dan model siap:

```sh
curl http://localhost:8000/health
```

Lanjutkan setelah respons berisi `"model_ready":true`. API Explorer tersedia di
`http://localhost:8000/`; endpoint GET dan POST dipisahkan dalam tab. Klik
**Try it out**, isi parameter atau body yang tersedia, lalu **Execute** untuk
melihat status dan response. Nama model dikunci ke `zydra-lora`.
Saat halaman dibuka, SweetAlert meminta nilai `AUTH` dari file `.env`. Masukkan
nilainya di popup; server memverifikasinya sebelum menampilkan halaman. AUTH
yang salah menolak akses. Credential hanya diminta sekali saat awal dan hanya
disimpan di memori selama halaman terbuka; tidak ditanamkan ke HTML atau
disimpan di browser. Request prompt di UI mendukung kolom `instruction` untuk
memberi arahan sistem sebelum prompt dikirim ke model.
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
  -d '{"model":"zydra-lora","messages":[{"role":"user","content":"Balas singkat: AI siap"}]}'
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

Base model Qwen2.5-0.5B-Instruct tersedia di bawah Apache License 2.0

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
