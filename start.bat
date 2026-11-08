@echo off & (where python >nul 2>&1 && python -x "%~f0" %* || (where py >nul 2>&1 && py -x "%~f0" %* || (echo [ERROR] Python is not installed. & pause))) & exit /b
# -*- coding: utf-8 -*-
r"""
Giin (国会議員 属性データ可視化ダッシュボード) ローカルサーバー起動スクリプト
- デフォルトポート: 8007
- フォールバックポート: 8057 (8058..8099)
- 多重起動防止: すでに 8007 (または記録ポート) で稼働中ならブラウザを開くのみ
- 未稼働時: 空きポートを探索してバックグラウンド起動し、.server_port / .server_pid を保存
"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
PRIMARY_PORT = 8007
FALLBACK_PORT = 8057
HEALTH_PATH = "/index.html"
PORT_FILE = ROOT_DIR / ".server_port"
PID_FILE = ROOT_DIR / ".server_pid"


def is_http_alive(port: int, health_path: str = HEALTH_PATH, timeout: float = 1.0) -> bool:
    """指定ポートのサーバーが HTTP リクエストに応答可能かを判定"""
    url = f"http://localhost:{port}{health_path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except urllib.error.HTTPError as e:
        return 200 <= e.code < 500
    except Exception:
        return False


def is_port_in_use(port: int) -> bool:
    """Windows 特有の多重バインド防止 (SO_EXCLUSIVEADDRUSE) を含めてポート空き状況を判定"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return True

    for bind_host in ("0.0.0.0", "127.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE") and sys.platform == "win32":
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                except OSError:
                    pass
            try:
                s.bind((bind_host, port))
            except OSError:
                return True
    return False


def find_available_port() -> int:
    """8007 -> 8057 -> 8058..8099 の順で空きポートを探索"""
    if not is_port_in_use(PRIMARY_PORT):
        return PRIMARY_PORT
    if not is_port_in_use(FALLBACK_PORT):
        return FALLBACK_PORT
    for p in range(8058, 8100):
        if not is_port_in_use(p):
            return p
    raise RuntimeError("ポート 8007, 8057 および代替ポートがすべて使用中です。")


def read_int_file(file_path: Path) -> int | None:
    if file_path.exists():
        try:
            txt = file_path.read_text(encoding="utf-8").strip()
            return int(txt) if txt.isdigit() else None
        except Exception:
            pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Giin Dashboard Local Server Starter")
    parser.add_argument("-n", "--no-browser", action="store_true", help="起動後にブラウザを自動で開かない")
    parser.add_argument("-p", "--port", type=int, default=None, help="明示的に使用するポート番号")
    args = parser.parse_args()

    print("=" * 64)
    print("  国会議員 属性データ可視化ダッシュボード (Giin)")
    print("  Local Server Starter")
    print("=" * 64)

    # 1. すでに稼働中かチェック (8007 または .server_port の保存ポート)
    active_port = None
    if is_http_alive(PRIMARY_PORT):
        active_port = PRIMARY_PORT
    else:
        saved_port = read_int_file(PORT_FILE)
        if saved_port and is_http_alive(saved_port):
            active_port = saved_port

    if active_port is not None:
        url = f"http://localhost:{active_port}/index.html"
        print(f"[*] サーバーは既にポート {active_port} で稼働中です。")
        if not args.no_browser:
            print(f"[*] ブラウザを開きます: {url}")
            webbrowser.open(url)
        else:
            print(f"[*] URL: {url}")
        print("=" * 64)
        return

    # 2. 未稼働の場合、空きポートを探索
    target_port = args.port
    if target_port is None:
        try:
            target_port = find_available_port()
        except RuntimeError as e:
            print(f"[エラー] {e}", file=sys.stderr)
            input("Enterキーを押して終了してください...")
            sys.exit(1)

    if target_port != PRIMARY_PORT:
        print(f"[!] デフォルトポート {PRIMARY_PORT} は他プロセスで使用中のため、フォールバックポート {target_port} を使用します。")

    print(f"[*] ポート {target_port} でローカルサーバーを起動しています...")

    # 3. バックグラウンドで python -m http.server を起動
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    server_cmd = [sys.executable, "-m", "http.server", str(target_port), "--directory", str(ROOT_DIR)]
    try:
        proc = subprocess.Popen(
            server_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
        )
    except Exception as e:
        print(f"[エラー] サーバーの起動に失敗しました: {e}", file=sys.stderr)
        input("Enterキーを押して終了してください...")
        sys.exit(1)

    # 4. .server_port と .server_pid に保存
    try:
        PORT_FILE.write_text(str(target_port), encoding="utf-8")
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    except Exception as e:
        print(f"[警告] .server_port / .server_pid の記録に失敗しました: {e}", file=sys.stderr)

    # 5. サーバー応答待機 (ヘルスチェック)
    print(f"[*] サーバーの応答を確認中 (ポート: {target_port})...")
    t0 = time.time()
    ready = False
    while time.time() - t0 < 5.0:
        if is_http_alive(target_port):
            ready = True
            break
        time.sleep(0.2)

    url = f"http://localhost:{target_port}/index.html"
    if ready:
        print(f"[*] サーバーが正常に起動しました (PID: {proc.pid}, Port: {target_port})")
    else:
        print("[!] 応答待機がタイムアウトしましたが、プロセスは実行中です。")

    if not args.no_browser:
        print(f"[*] ブラウザを開きます: {url}")
        webbrowser.open(url)
    else:
        print(f"[*] URL: {url}")
    print("=" * 64)


if __name__ == "__main__":
    main()
