# Pendaftaran member melalui Telegram

Bot [@iixji_bot](https://t.me/iixji_bot) untuk IXP ala Mimbar Jumuah Jawa Timur menggunakan percakapan pribadi dan long polling. Tidak memerlukan webhook atau membuka port publik. Jalankan dashboard dahulu untuk membuat database. Python virtualenv dashboard dan `curl` harus tersedia.

Rahasia token ada di `data/telegram-token` (0600), di luar kode, aset browser, dan version control. URL bertoken diberikan ke curl lewat stdin, bukan argumen proses. Jangan memasukkannya ke log atau unit service.

```bash
cd /opt/arouterserver/dashboard
.venv/bin/python telegram_bot.py --configure --check
.venv/bin/python telegram_bot.py
```

`--configure` memasang daftar perintah dan deskripsi bot. `--check` memverifikasi identitas dan memastikan tidak ada webhook aktif, lalu keluar. Worker menolak berjalan bersamaan dengan worker lokal lain. Webhook yang sudah ada tidak dihapus otomatis.

Untuk berjalan otomatis setelah boot, tersedia unit `services/mimbar-telegram.service`. Sesuaikan path bila aplikasi dipindahkan. Jalankan satu worker saja; hentikan worker terminal sebelum mengaktifkan unit ini.

```bash
sudo install -m 644 services/mimbar-telegram.service /etc/systemd/system/mimbar-telegram.service
sudo systemctl daemon-reload
sudo systemctl enable --now mimbar-telegram.service
```

## Percakapan member

Member membuka tautan bot dan mengetik `/daftar` atau `/start`. Bot meminta, secara berurutan:

1. Lokasi (dibaca dari database; awalnya SUB dan AG).
2. Nama perusahaan/jaringan.
3. ASN publik.
4. Prefix IPv4 dalam CIDR, atau `-`.
5. Prefix IPv6 dalam CIDR, atau `-`; minimal satu keluarga harus terisi.
6. IRR AS-SET, atau `-` untuk pencarian berdasarkan ASN.
7. IP peering LAN IPv4, atau `-` jika belum dialokasikan/tidak digunakan.
8. IP peering LAN IPv6, atau `-`.
9. Nama PIC/tim NOC.
10. Email NOC.

Ringkasan ditampilkan sebelum member mengetik `KIRIM`. `/kembali` mengulang isian sebelumnya dan menghapus isian sesudahnya agar dependensi tetap konsisten. `/lanjut` meneruskan setelah restart. `/batal` menghapus isian belum dikirim; pengajuan yang sudah dikirim tetap tercatat. `/status` hanya menampilkan pengajuan milik identitas Telegram tersebut. Satu pengajuan pending per akun; setelah keputusan, dapat mendaftar lokasi lain. Tidak mengumpulkan password BGP atau kunci SSH.

## Tinjauan admin dan pemetaan ARouteServer

Login dashboard → **Pengajuan member** → **Tinjau**. Verifikasi kewenangan ASN/prefix, objek IRR/ROA, serta alokasi IP LAN. Lengkapi minimal satu IP LAN. Pilih community lokasi jika dibutuhkan. Persetujuan memvalidasi skema ARouteServer dan menambahkan satu entri `clients` per IP, dengan ASN, description, serta opsional `cfg.filtering.irrdb.as_sets`.

Prefix yang dilaporkan tetap menjadi inventaris deklarasi pada pengajuan. Tidak dipetakan otomatis ke `white_list_route`, sebab atribut tersebut mengecualikan rute dari pemeriksaan IRR. Keabsahan sintaks tidak membuktikan kepemilikan ASN/prefix. Kebijakan filter tetap mengikuti konfigurasi lokasi; arsip awal memiliki penegakan IRR/RPKI yang belum aktif dan perlu keputusan operator tersendiri.

Persetujuan hanya mengubah draft lokasi. Build, validasi BIRD 2.19.2, dan deploy tetap dilakukan secara terpisah. Konflik revisi atau IP yang sudah ada di YAML/template menolak perubahan. Keputusan, perubahan draft, audit, dan notifikasi dicatat dalam satu transaksi.

Penolakan wajib menyertakan alasan. Bot mengirim keputusan ke akun pengaju. Pengiriman menggunakan antrean persisten dan retry/backoff, termasuk rate limit Telegram; setelah 10 kegagalan pesan ditandai gagal di dashboard. Bila crash terjadi sesudah Telegram menerima pesan tetapi sebelum pencatatan lokal, pesan dapat terkirim ulang. Offset update dan perubahan percakapan dicatat bersama agar update yang sama tidak membuat pengajuan ganda. Bot mengabaikan pesan grup dan tidak mengirim pesan pembuka tanpa input member.

Halaman pengajuan menampilkan 200 pengajuan terbaru, status worker, serta jumlah pesan gagal. Data disimpan di SQLite `data/mimbar.sqlite3`; backup harus menyertakan database secara konsisten beserta antrean. Token tidak termasuk respons API dashboard.

Referensi: [Telegram Bot API](https://core.telegram.org/bots/api#getupdates) dan [konfigurasi ARouteServer](https://arouteserver.readthedocs.io/en/latest/CONFIG.html).

Transport TLS menggunakan kurva X25519 agar handshake tidak terhenti pada jaringan server ini. Verifikasi sertifikat tetap aktif. Unit systemd dipasang dan diaktifkan pada server saat implementasi.
