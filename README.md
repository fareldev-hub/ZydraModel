# ZydraModel

Zydra menyediakan API chat yang kompatibel dengan format OpenAI, playground web,
dan API untuk mengubah system instructions. Container menjalankan API dan Ollama
lokal bersama-sama. Service Ollama terpisah `https://ollama-run.up.railway.app`
tetap dapat dipilih dengan mengatur `OLLAMA_URL`.

## Deploy ke Railway

1. Buat service Railway dari repository ini. Railway akan menggunakan `Dockerfile`
   dan konfigurasi di `railway.toml`.
2. Tambahkan **Volume** dan mount pada `/data`. Volume menyimpan model Ollama dan
   system instructions agar tetap ada setelah restart/deploy.
3. Tambahkan variable `AUTH` dengan password yang kuat. Password yang sama digunakan
   untuk membuka playground dan autentikasi API. Semua endpoint `/v1/*`
   memerlukan password tersebut melalui header `Authorization` (Bearer) atau `X-API-Key`.
4. Hapus `OLLAMA_URL` dari Variables jika sebelumnya disetel ke
   `https://ollama-run.up.railway.app`; default API adalah `http://localhost:11434`
   dan container akan menjalankan Ollama sendiri. Jika ingin menggunakan service
   Ollama terpisah, set `OLLAMA_URL` ke URL service tersebut dan pastikan model
   `zydra` tersedia di sana.
5. Deploy. Saat pertama kali berjalan, container mengunduh `qwen3-vl:2b` dan
   membuat model `zydra`; simpan model pada Railway Volume `/data`.
6. Buka URL service Railway untuk mencoba playground.

Railway menyediakan `PORT` secara otomatis. API bind ke port tersebut dan
meneruskan permintaan ke Ollama lokal. `/health` melaporkan apakah Ollama dapat
dijangkau dan model `zydra` siap.

Jika chat gagal, API mengembalikan detail error dari Ollama. Periksa log deploy
Railway dan pastikan URL upstream dapat diakses serta model bernama `zydra` tersedia.

## Menjalankan dengan Docker

```sh
docker build -t zydra .
docker run --rm -p 8000:8000 -e AUTH="ganti-dengan-password-kuat" -v zydra-data:/data zydra
```

Buka `http://localhost:8000` lalu masukkan password `AUTH`. Playground mengingat
password hanya selama sesi tab browser; tutup tab untuk menghapusnya.

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
