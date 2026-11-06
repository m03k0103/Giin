# storage.py - 国会議員データ永続化・アトミック保存・バックアップモジュール
import os
import json
import shutil

DATA_JS_PATH = 'data.js'
DATA_FULL_PATH = 'data_full.js'
DATA_TEST_PATH = 'data_test.js'

def load_diet_data(filepath='data.js'):
    """
    data.js (window.DIET_DATA = ...;) から辞書データをロード
    """
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        prefix = "window.DIET_DATA = "
        if content.startswith(prefix):
            content = content[len(prefix):].strip()
        if content.endswith(';'):
            content = content[:-1].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[警告] {filepath} の読み込みに失敗しました: {e}", file=sys.stderr)
        return None

def atomic_save_diet_data(filepath, data):
    """
    一時ファイル（.tmp）を経由して os.replace() でアトミックに data.js を保存
    """
    tmp_path = filepath + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write("window.DIET_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n")
        os.replace(tmp_path, filepath)
        return True
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise e


def backup_existing_full_data():
    """
    既存の data.js に全件データが含まれている場合、data_full.js に退避
    """
    existing = load_diet_data('data.js')
    if existing:
        members = existing.get('members', [])
        count = len(members)
        # 20名以上（テストデータより明らかに多い全件データなど）の場合に退避
        if count > 20:
            atomic_save_diet_data('data_full.js', existing)
            print(f"[データ退避] 既存の全件データ（{count}名）を data_full.js に退避しました。")
            return True
    return False

def restore_full_data():
    """
    退避済みの全件データ（data_full.js）から data.js を復元
    """
    data = load_diet_data('data_full.js')
    if data:
        count = len(data.get('members', []))
        atomic_save_diet_data('data.js', data)
        print(f"[復元完了] data_full.js から全件データ（{count}名）を data.js に復元しました。")
        return True
    else:
        print("[エラー] 退避ファイル（data_full.js）が見つかりません。", file=sys.stderr)
        return False
