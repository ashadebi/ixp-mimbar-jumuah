"""Scheduled retention maintenance; does not import/start collector server."""
import argparse
import os
import signal
import threading
import time
from pathlib import Path
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    interval = float(os.environ.get('PRUNE_INTERVAL', '300'))
    retention = int(os.environ.get('RETENTION_SECONDS', '129600'))
    if interval <= 0 or retention <= 0:
        raise SystemExit('PRUNE_INTERVAL and RETENTION_SECONDS must be positive')
    data = Path(os.environ.get('DATA_DIR', '/data'))
    store = Store(str(data / 'syslog.sqlite3'), retention=retention)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        store.prune()
        (data / 'pruner-heartbeat').touch()
        print('retention prune complete', flush=True)
        if args.once or stop.wait(interval):
            break


if __name__ == '__main__':
    main()
