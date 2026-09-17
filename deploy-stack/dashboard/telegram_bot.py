#!/usr/bin/env python3
"""Single-instance Telegram long polling worker. Token never appears in logs."""
import argparse
import fcntl
import json
import os
import time
import subprocess

import onboarding
import server

COMMANDS=[('daftar','Daftar member IXP baru'),('lanjut','Lanjutkan isian'),('kembali','Koreksi isian sebelumnya'),('batal','Hapus isian yang belum dikirim'),('status','Lihat status pengajuan'),('bantuan','Panduan dan penggunaan data')]

class TelegramError(Exception):
    def __init__(self, code=0, retry_after=0):
        self.code,self.retry_after=code,retry_after
        super().__init__('Telegram API gagal (kode '+str(code)+').')

class Telegram:
    def __init__(self, token): self.token=token
    def call(self, method, **data):
        # Pass the URL and payload through stdin, never argv (process listings).
        # X25519 avoids oversized hybrid ClientHello stalls on this network; TLS
        # certificate verification and TLS 1.3 remain enabled.
        config='\n'.join(['url = '+json.dumps('https://api.telegram.org/bot'+self.token+'/'+method), 'request = "POST"', 'header = "Content-Type: application/json"', 'data = '+json.dumps(json.dumps(data)), 'connect-timeout = 10', 'max-time = 40'])
        try:
            response=subprocess.run(['curl','--silent','--curves','X25519','--config','-'],input=config,text=True,capture_output=True,timeout=45)
            if response.returncode:raise TelegramError()
            result=json.loads(response.stdout)
        except (OSError,subprocess.TimeoutExpired,ValueError):raise TelegramError() from None
        if not result.get('ok'):raise TelegramError(result.get('error_code',0),result.get('parameters',{}).get('retry_after',0))
        return result['result']


def flush(api):
    for row in server.query('SELECT * FROM telegram_outbox WHERE sent IS NULL AND attempts<10 AND next_try<=? ORDER BY id LIMIT 30',(time.time(),)):
        # Preserve ordering within each chat, including after throttling.
        if server.query('SELECT id FROM telegram_outbox WHERE chat_id=? AND id<? AND sent IS NULL AND attempts<10',(row['chat_id'],row['id']),True):continue
        try:
            api.call('sendMessage',chat_id=row['chat_id'],text=row['text'])
            server.query('UPDATE telegram_outbox SET sent=?,error=NULL WHERE id=?',(time.time(),row['id']))
        except TelegramError as e:
            attempts=10 if e.code in (400,403) else row['attempts']+1
            server.query('UPDATE telegram_outbox SET attempts=?,next_try=?,error=? WHERE id=?',(attempts,time.time()+max(e.retry_after,min(3600,2**attempts)),str(e),row['id']))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--configure',action='store_true');parser.add_argument('--check',action='store_true');args=parser.parse_args()
    os.umask(0o077)
    token_path=server.DATA/'telegram-token'
    if not token_path.is_file():raise SystemExit('Token belum tersedia di data/telegram-token.')
    if token_path.stat().st_mode & 0o077:raise SystemExit('Token wajib memiliki permission 0600.')
    # Prevent two workers consuming the same offset/outbox on this server.
    lock=(server.DATA/'telegram-worker.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Worker Telegram sudah berjalan.')
    if not server.DB.is_file():raise SystemExit('Jalankan dashboard terlebih dahulu untuk menyiapkan database.')
    onboarding.init_db(server.connect)
    api=Telegram(token_path.read_text().strip())
    try:
        print('Memverifikasi identitas bot…',flush=True)
        me=api.call('getMe')
        print('Memeriksa webhook…',flush=True)
        webhook=api.call('getWebhookInfo')
        if webhook.get('url'):raise SystemExit('Bot mempunyai webhook aktif. Worker polling tidak dijalankan agar integrasi yang ada tetap bekerja.')
        server.query("INSERT OR REPLACE INTO telegram_meta VALUES('username',?)",(me['username'],))
        if args.configure:
            print('Memasang menu perintah…',flush=True)
            api.call('setMyCommands',commands=[{'command':c,'description':d} for c,d in COMMANDS])
            print('Memasang deskripsi bot…',flush=True)
            api.call('setMyDescription',description='Pendaftaran member IXP ala Mimbar Jumuah Jawa Timur. Kirim ASN, prefix, dan kontak NOC melalui formulir percakapan. Admin meninjau sebelum konfigurasi diterapkan.')
            print('Memasang deskripsi singkat…',flush=True)
            api.call('setMyShortDescription',short_description='Pendaftaran member IXP Jawa Timur • SUB Surabaya & AG Tulungagung • /daftar')
        print('Bot terverifikasi: @'+me['username']+'; webhook tidak aktif.',flush=True)
        if args.check:return
    except TelegramError as e:raise SystemExit(str(e)) from None
    conversation=onboarding.Conversation(server.connect)
    while True:
        try:
            flush(api)
            offset=server.query("SELECT value FROM telegram_meta WHERE key='offset'",one=True)
            updates=api.call('getUpdates',offset=int(offset['value']) if offset else 0,timeout=20,limit=50,allowed_updates=['message'])
            server.query("INSERT OR REPLACE INTO telegram_meta VALUES('heartbeat',?)",(str(time.time()),))
            for update in updates:conversation.handle(update)
            flush(api)
            server.query("INSERT OR REPLACE INTO telegram_meta VALUES('last_error','')")
        except TelegramError as e:
            server.query("INSERT OR REPLACE INTO telegram_meta VALUES('last_error',?)",(str(e),))
            print(str(e),flush=True);time.sleep(max(5,min(60,e.retry_after)))
        except Exception as e:
            # Never print a raw transport exception (it may embed the token URL).
            print('Worker gagal: '+type(e).__name__+'; mencoba ulang.',flush=True)
            server.query("INSERT OR REPLACE INTO telegram_meta VALUES('last_error','Worker gagal memproses update; periksa log.')")
            time.sleep(5)

if __name__=='__main__':main()
