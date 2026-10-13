# ZydraModel

Zydra menyediakan API chat yang kompatibel dengan format OpenAI, playground web,
dan API untuk mengubah system instructions. API dan Ollama berjalan bersama-sama
dalam satu container/service Railway.

## Deploy ke Railway

1. Buat service Railway dari repository ini. Railway akan menggunakan `Dockerfile`
   dan konfigurasi di `railway.toml`.
2. Tambahkan **Volume** dan mount pada `/data`. Volume menyimpan model Ollama,
   system instructions, dan password otomatis agar tetap ada setelah restart/deploy.
3. Variable non-rahasia seperti `OLLAMA_URL`, `INSTRUCTIONS_FILE`, dan
   `MODEL_STATUS_FILE` sudah memiliki default di image. Pastikan `OLLAMA_URL`
   tidak dioverride ke service lain.
4. `AUTH` dibuat secara acak saat boot pertama jika variable `AUTH` tidak disetel.
   Password ditampilkan **satu kali** di log deploy saat dibuat. Simpan password
   itu untuk UI dan API; proses berikutnya membaca password dari volume `/data`.
   Semua endpoint `/v1/*` memerlukan password tersebut melalui header
   `Authorization` (Bearer) atau `X-API-Key`. Anda juga bisa menetapkan `AUTH`
   sendiri melalui Railway Variables untuk menimpa password otomatis.
5. Deploy. Saat pertama kali berjalan, container mengunduh `qwen3-vl:2b` dan
   membuat model `zydra`; simpan model pada Railway Volume `/data`. Saat setup
   masih berlangsung, chat menjawab dengan status model sedang disiapkan (503),
   beserta tahap setup saat ini. Cek `/status` atau `/health` dan coba lagi setelah
   `"model_ready": true`.
6. Buka URL service Railway untuk mencoba playground.

Railway menyediakan `PORT` secara otomatis. API bind ke port tersebut dan
meneruskan permintaan ke Ollama lokal. Ollama menyimpan model di `/data/ollama`;
volume yang dipasang pada `/data` mempertahankan model saat container di-deploy
ulang. Tanpa volume, model akan diunduh kembali saat container dibuat ulang.
Railway tidak menambahkan variable service dari `railway.toml` secara otomatis;
default konfigurasi di atas disediakan oleh image aplikasi, sedangkan `AUTH`
dibuat dan disimpan oleh aplikasi pada boot pertama jika tidak ditetapkan manual.
`/status` dan `/health` melaporkan tahap setup (`waiting_for_ollama`,
`downloading_base_model`, `creating_zydra_model`, `ready`, atau `failed`) dan
apakah model `zydra` siap. Jika status `failed`, buka log deploy Railway untuk
melihat error dari perintah pull atau create.

Jika chat gagal, API mengembalikan detail error dari Ollama. Periksa log deploy
Railway untuk memastikan model `zydra` selesai dibuat dan service memiliki resource
yang cukup untuk menjalankan inferensi.

## Menjalankan dengan Docker

```sh
docker build -t zydra .
docker run --rm -p 8000:8000 -v zydra-data:/data zydra
```

Buka `http://localhost:8000`, ambil password otomatis dari log pertama, lalu
masukkan ke playground. Atau set `AUTH` sendiri saat menjalankan Docker.
Playground mengingat password hanya selama sesi tab browser; tutup tab untuk menghapusnya.

## API untuk developer

Semua contoh memakai password `AUTH` melalui bearer authentication:

```sh
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ganti-dengan-password-kuat" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"zydra\",\"messages\":[{\"role\":\"user\",\"content\":\"Jelaskan fotosintesis secara singkat.\"}]}"
```

Endpoint utama:

| Method | Path | Fungsi |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | Text generation dan vision; format request/response mengikuti OpenAI Chat Completions. Mendukung `stream: true` (SSE), `tools`, `temperature`, `top_p`, `max_tokens`, dan pesan vision `image_url` berupa data URL base64 atau URL gambar HTTP(S). |
| `GET` | `/v1/models` | Daftar model yang tersedia melalui API. |
| `GET` | `/v1/instructions` | Membaca system instructions aktif. |
| `PUT` | `/v1/instructions` | Mengganti system instructions; JSON body: `{"instructions":"..."}`. Maksimum 20.000 karakter. |
| `GET` | `/health` | Status container/API dan nilai `model_ready`. Tidak memerlukan API key. |
| `GET` | `/status` | Tahap setup model dan pesan status terbaru; tidak memerlukan API key. |
| `GET` | `/ready` | HTTP 200 hanya setelah model `zydra` siap; selain itu HTTP 503. |

Instruksi tersimpan pada `/data/instructions.txt` secara default. Gunakan volume
Railway di `/data` agar model Ollama dan perubahan instruksi bertahan. Path
instruksi bisa diubah melalui variable `INSTRUCTIONS_FILE`.

Contoh vision dengan URL gambar:

```sh
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ganti-dengan-password-kuat" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"zydra\",\"messages\":[{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"Apa yang terlihat pada gambar ini?\"},{\"type\":\"image_url\",\"image_url\":{\"url\":\"https://example.com/gambar.jpg\"}}]}]}"
```

Atau kirim gambar sebagai `data:image/png;base64,...`. Gambar dibatasi maksimal
10 MB per gambar. Spesifikasi endpoint juga tersedia pada `/docs`.
