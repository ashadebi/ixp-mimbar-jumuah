# IXP ala Mimbar Jumuah Jawa Timur

Dashboard lokal untuk ARouteServer, dengan tema Mimbar Jumuah: hijau tua, kuningan, tipografi serif, dan pesan Jumat berkah. Antarmuka berbahasa Indonesia. Target BIRD adalah **2.19.2**, rilis terbaru seri 2.19 yang diverifikasi pada 11 September 2026.

## Menjalankan aplikasi

Dari `/opt/arouterserver`:

```bash
python3 -m venv dashboard/.venv
dashboard/.venv/bin/pip install -r dashboard/requirements.txt
dashboard/.venv/bin/python dashboard/server.py --host 127.0.0.1 --port 8787 --validator docker
```

Buka http://127.0.0.1:8787 pada server. Untuk browser di komputer lain, gunakan SSH tunnel:

```bash
ssh -L 8787:127.0.0.1:8787 user@server-dashboard
```

Pada kunjungan pertama, buat administrator dengan password minimal 12 karakter. Token penyiapan tersimpan pada `dashboard/data/setup-token` (mode 0600). Akun uji browser memakai database sementara dan tidak membuat akun administrator pada aplikasi utama.

Untuk akses melalui reverse proxy HTTPS, atur `MIMBAR_SECURE_COOKIE=1`. Jangan membuka server pengembangan Python langsung ke Internet. Jalankan sebagai service account tersendiri untuk penggunaan tetap; semua file `data/` dan kunci SSH hanya boleh diakses akun tersebut. Aplikasi memakai pustaka HTTP Python untuk instalasi lokal, bukan platform multi-tenant.

## Fitur yang tersedia

- Login, logout, hash password PBKDF2, sesi cookie HttpOnly/SameSite, token CSRF, dan pembatasan percobaan login.
- Inventaris lokasi SUB/Surabaya dan AG/Tulungagung; lokasi lain dapat ditambah.
- Mesin awal: SUB RS2 (.2), SUB RS3 (.3), dan AG (.14), sesuai referensi dalam arsip. Semua berstatus belum diperiksa saat pertama kali diimpor.
- Tambah/edit mesin: nama, IP SSH, Router ID, username dan port SSH.
- Daftar sesi dengan pencarian ASN/nama/IP, filter IPv4/IPv6, pagination, dan sumber YAML atau template khusus.
- Tambah/hapus sesi YAML; sesi template khusus tampil sebagai informasi dan tetap dipertahankan saat build.
- Formulir kebijakan RPKI, penolakan origin/prefix IRR, path hiding, dan batas prefix; editor YAML untuk opsi lanjutan.
- Draft tersimpan di SQLite, memiliki revisi, dan tidak menimpa arsip.
- Build melalui CLI ARouteServer; pratinjau dan unduh hasil; checksum SHA-256; validasi container dan deployment melalui SSH jika lingkungan sudah disiapkan.
- Riwayat build dan audit aktivitas.
- Tampilan responsif, termasuk navigasi ponsel.

Jumlah awal 242 merupakan definisi sesi pada dua konfigurasi lokasi: SUB 206 (168 YAML + 38 template) dan AG 36. Ini bukan jumlah sesi Established atau total sesi seluruh replika mesin. SUB memiliki 101 ASN unik jika sesi template tambahan ikut dihitung; clients.yml sendiri memiliki 83 ASN.

RS2 diketahui dari gen-config.sh, tetapi general.yml asli khusus RS2 tidak ada dalam arsip. Build RS2 menggunakan draft SUB dan Router ID mesin .2. Tinjau seluruh kebijakan sebelum menerapkan pada RS2.

## Kompatibilitas generator

ARouteServer yang dipasang adalah **1.23.2**. CLI versi ini menyediakan profil seri BIRD 2 sampai **2.16**, belum bernama 2.19.2. Karena itu:

1. Generator menggunakan `bird --cfg ... --target-version 2.16`.
2. Binary validator wajib **BIRD 2.19.2**.
3. Agent tujuan memeriksa bahwa mesin memakai BIRD 2.19.2 dan memvalidasi lagi konfigurasi yang sama.

Profil generator tidak diubah menjadi 2.19.2 secara paksa dan keberhasilan generate bukan bukti kompatibilitas runtime. Parser BIRD saja juga tidak membuktikan kebijakan routing atau perilaku peering sudah sesuai tujuan.

Build menyalin template dan cache dari direktori arsip ke `data/builds/<id>/`, mengubah Router ID pada salinan, dan menjalankan generator di sana. Kebijakan literal dalam 19 template `ji-*` SUB tetap berlaku; formulir global tidak menulis ulang kode template tersebut.

`bgpq4` diperlukan untuk pengambilan data IRR. Pada lingkungan ini tersedia secara lokal di `dashboard/tools/bgpq4/usr/bin/bgpq4`; aplikasi juga bisa memakai `bgpq4`/`bgpq3` pada PATH. PeeringDB dan server IRR memerlukan akses jaringan; kegagalan pengambilan data ditampilkan sebagai build gagal. Aplikasi tidak menonaktifkan filter untuk memaksakan keberhasilan build.

## Container validator BIRD 2.19.2

**Image `mimbar-bird:2.19.2` sudah dibangun dan dijalankan.** Snapshot AG dan SUB lolos parser BIRD 2.19.2 melalui validator dashboard; konfigurasi sengaja salah ditolak. SUB mengeluarkan peringatan inferensi tipe fungsi pada template khusus, tanpa error sintaks. Laporan dan artefak tersedia di `data/probes/`.

Untuk membangun ulang image dan memeriksa contoh dasar:

```bash
docker build -t mimbar-bird:2.19.2 dashboard/container
docker run --rm --network none --read-only --cap-drop ALL mimbar-bird:2.19.2 --version
docker run --rm --network none --read-only --cap-drop ALL -i mimbar-bird:2.19.2 -p -c /dev/stdin < dashboard/container/smoke.conf
```

Dockerfile mengambil source release dari URL resmi CZ.NIC dan membangun BIRD 2.19.2. Pengambilan source dan build image telah berhasil pada lingkungan ini.

Jalankan ulang dashboard dengan:

```bash
MIMBAR_VALIDATOR=docker dashboard/.venv/bin/python dashboard/server.py
```

Validator memakai jaringan `none`, filesystem read-only, pengguna non-root pada image, `cap-drop ALL`, batas CPU/memori/PID, serta input konfigurasi melalui stdin. Image alternatif dapat ditetapkan dengan `MIMBAR_BIRD_IMAGE`, tetapi output versi tetap harus 2.19.2. Hak mengakses daemon Docker sendiri setara hak administrator host; beri hanya ke akun layanan terpercaya.

## Menghubungkan mesin RS

Tidak ada koneksi SSH atau perubahan konfigurasi produksi yang dilakukan saat aplikasi dinyalakan.

1. Atur akun SSH khusus pada RS dan pasang public key milik layanan dashboard.
2. Verifikasi host key melalui saluran yang tepercaya, lalu isi file known_hosts khusus. Aplikasi selalu menggunakan `StrictHostKeyChecking=yes`.
3. Pada RS, pasang agent dari `remote-agent.py` sebagai root-owned `/usr/local/sbin/mimbar-deploy`, mode 0755. Agent memerlukan Python 3, `/usr/sbin/bird`, `/usr/sbin/birdc`, dan file konfigurasi biasa `/etc/bird/bird.conf`.
4. Izinkan akun SSH menjalankan hanya perintah agent berikut melalui sudoers (sesuaikan username):

```sudoers
operator ALL=(root) NOPASSWD: /usr/local/sbin/mimbar-deploy status, /usr/local/sbin/mimbar-deploy apply
```

5. Atur lingkungan layanan dashboard:

```bash
export MIMBAR_SSH_KEY=/path/private-key
export MIMBAR_KNOWN_HOSTS=/path/known_hosts
export MIMBAR_VALIDATOR=docker
export MIMBAR_ALLOW_DEPLOY=1
dashboard/.venv/bin/python dashboard/server.py
```

File `.env.example` hanya contoh dan tidak dimuat otomatis. Gunakan environment service manager atau ekspor variabel secara eksplisit. Jangan menaruh kunci privat di direktori public/dist.

Alur dashboard: pilih mesin → periksa SSH → tinjau kebijakan → buat build → tinjau/unduh konfigurasi → validasi → ketik nama mesin → deploy. Pemeriksaan SSH harus masih berumur maksimal 5 menit; versi mesin, checksum, dan revisi draft/mesin diperiksa kembali oleh server. Perubahan target atau draft mewajibkan build baru.

Agent memeriksa versi dan checksum, menolak include eksternal, menjalankan `bird -p` dan `birdc configure check`, menyimpan backup, lalu reload normal dengan timeout BIRD. Reload normal dipilih agar perubahan filter dievaluasi ulang; sesi yang terdampak dapat restart. Watchdog terpisah mempertahankan lock dan memulihkan file serta konfigurasi lama jika proses berhenti sebelum commit. Transaksi, backup, dan catatan pemulihan tersimpan di `/var/lib/mimbar/`.

**Agent telah diuji dengan daemon BIRD 2.19.2 nyata di container lab tanpa jaringan.** Pengujian mencakup backup, reload, promosi file, penolakan konfigurasi salah, dan pemulihan file serta route aktif setelah kegagalan yang disimulasikan sesudah promosi. Jalur watchdog dengan proses mati dan menunggu timeout penuh belum diuji. Konektivitas SSH serta kebijakan/peering pada RS produksi tetap perlu diverifikasi sebelum digunakan. Jika SSH terputus, status deployment bisa tidak pasti; periksa log transaksi di RS. Pemeriksaan `show status/protocols` bukan jaminan seluruh peering sudah Established.

## Pengujian

```bash
dashboard/.venv/bin/python -m unittest discover -s dashboard/tests -p 'test_*.py'
dashboard/.venv/bin/pip install playwright
dashboard/.venv/bin/python -m playwright install chromium
dashboard/.venv/bin/python dashboard/tests/browser_check.py
```

Tes API memakai database sementara. Tes browser juga memakai database sementara dan memeriksa login/setup, navigasi, pencarian/filter peer, lokasi baru, draft, kebijakan, tambah/hapus peer, pengaturan mesin, tombol deploy yang terkunci, ukuran layar ponsel, dan logout. Screenshot tersedia di `screenshots/` setelah pengujian. Sebanyak 11 tes API dan alur browser berhasil dijalankan. Pemeriksaan schema draft memakai `arouteserver check-config`; pemeriksaan update rilis dinonaktifkan pada operasi ini agar penyimpanan draft tidak menunggu layanan eksternal.

`tests/generator_probe.py` adalah probe terpisah menggunakan salinan cache arsip dengan masa berlaku diperpanjang untuk inspeksi snapshot. Hasilnya tidak dimasukkan ke daftar build aplikasi atau disertifikasi untuk deployment. Build aplikasi normal mempertahankan kebijakan kesegaran cache asal.

WebMCP read-only untuk inspeksi inventaris disediakan secara feature-detect. API WebMCP tidak tersedia pada Chromium uji, sehingga registrasinya belum diuji; dashboard tidak bergantung padanya.

## Batas yang masih perlu diselesaikan di lingkungan RS

- Snapshot SUB/AG sudah lolos parser 2.19.2. Data ini memakai snapshot cache untuk inspeksi; lakukan build dengan data terkini sebelum deployment produksi.
- Kunci SSH, host key terverifikasi, dan agent belum dipasang pada RS produksi.
- Tidak ada telemetry live atau grafik trafik; angka dashboard berasal dari konfigurasi dan catatan operasi aktual.
- Edit template Jinja khusus tetap dilakukan di source oleh administrator, bukan melalui formulir peer biasa.
- Aplikasi lokal ini hanya memiliki satu administrator. Tidak ada SSO/RBAC atau reset password melalui email.

## Rujukan

- [Rilis resmi BIRD](https://bird.nic.cz/get-bird/) — 2.19.2, 30 Juli 2026.
- [Panduan BIRD 2.19.2](https://bird.nic.cz/doc/bird-2.19.2.html) — parser, route-server client, dan configure/check/timeout/confirm.
- [Kebijakan ARouteServer](https://arouteserver.readthedocs.io/en/latest/GENERAL.html).
- [Penggunaan ARouteServer](https://arouteserver.readthedocs.io/en/latest/USAGE.html).

## Mengulang uji lab agent

```bash
docker build -f dashboard/container/Dockerfile.lab -t mimbar-bird-lab:2.19.2 dashboard
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 512m --cpus 1 --tmpfs /run --tmpfs /etc/bird --tmpfs /var/lib/mimbar --tmpfs /tmp mimbar-bird-lab:2.19.2
```

Lab tidak memasang direktori host, tidak memiliki jaringan, dan memakai alamat dokumentasi 192.0.2.0/24, 198.51.100.0/24, serta 203.0.113.0/24. Semua filesystem konfigurasi lab bersifat sementara.

Pendaftaran member melalui Telegram tersedia pada menu **Pengajuan member**. Panduan worker, formulir, tinjauan admin, dan notifikasi: [TELEGRAM.md](TELEGRAM.md).

Dashboard mendukung beberapa akun super-admin dengan password PBKDF2 dan sesi yang terikat ke masing-masing pengguna. Akun awal yang disiapkan: `agoes`, `nurdin`, dan `umam`; ketiganya langsung memiliki hak super-admin saat login. Kredensial awal tersimpan privat di `data/super-admin-credentials.json` (0600), tidak disajikan melalui HTTP. Aktivitas konfigurasi dan tinjauan member mencatat nama pengguna yang melakukan perubahan. Migrasi akun tunggal mempertahankan hash password akun lama dan membatalkan sesi lama yang belum memiliki identitas pemilik.
