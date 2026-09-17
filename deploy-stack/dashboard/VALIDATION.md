# Hasil pemeriksaan — 11 September 2026

| Pemeriksaan | Hasil |
|---|---|
| Sintaks JavaScript dan Python | Lulus |
| API: autentikasi, CSRF, revisi draft, validasi input, penguncian deploy | 11 tes lulus |
| Browser: setup/login, navigasi, lokasi, pencarian/filter peer, draft, kebijakan, tambah/hapus peer, edit mesin, logout | Lulus |
| Layar ponsel 390 × 844 | Tidak ada overflow horizontal; navigasi dapat digunakan |
| Generator ARouteServer 1.23.2, profil 2.16, snapshot AG | Berhasil, 302.276 byte |
| Generator ARouteServer 1.23.2, profil 2.16, snapshot SUB | Berhasil, 1.419.975 byte |
| Image mimbar-bird:2.19.2 | Berhasil dibangun dari source resmi; binary melaporkan 2.19.2 |
| Parser BIRD: contoh dasar dan snapshot AG | Lulus |
| Parser BIRD: snapshot SUB | Lulus, dengan peringatan inferensi return type template khusus |
| Parser BIRD: konfigurasi sengaja salah | Ditolak, status validation_failed |
| Agent dengan daemon BIRD nyata dalam lab | Backup, reload normal, confirm, dan promosi file berhasil |
| Agent: input konfigurasi salah | Ditolak; file aktif tidak berubah |
| Agent: kegagalan setelah promosi | File dan route aktif kembali ke konfigurasi sebelumnya |

Laporan parser rinci ada di `data/probes/validator-report.json`; artefak snapshot berada pada direktori yang sama. Snapshot memakai cache arsip dengan umur berlaku diperpanjang khusus untuk inspeksi; artefak tidak dimasukkan sebagai build produksi dashboard.

Tidak ada perubahan pada mesin RS produksi. Pemeriksaan SSH produksi, peering end-to-end, serta rollback setelah crash yang menunggu timeout penuh belum dilakukan. Keberhasilan parser tidak menilai ketepatan kebijakan jaringan.

## Onboarding Telegram

- 17 tes backend/API lulus, termasuk 6 tes onboarding: validasi input, resume/deduplikasi, persetujuan atomik, pemetaan AS-SET tanpa whitelist, penolakan, isolasi akun, konflik IP, dan retry antrean.
- Browser nyata lulus alur kirim pengajuan simulasi → tinjau → isi IP LAN → persetujuan ke draft. Database uji terisolasi; tidak mengirim chat uji ke member. Screenshot: `screenshots/members.png`.
- API Telegram live: identitas @iixji_bot terverifikasi, webhook kosong, menu perintah dan deskripsi berhasil dipasang.
- Prefix deklarasi belum diverifikasi kepemilikannya secara otomatis; keputusan admin diperlukan. Tidak ada deployment ke mesin RS dari pengajuan.

## Multi-user super-admin

19 tes backend/API lulus: mencakup migrasi akun tunggal yang mempertahankan hash, sesi independen tiga pengguna, login salah lintas akun ditolak, dan audit atas nama pengguna aktif. Footer daftar lokasi di halaman login dihapus sesuai permintaan.
