#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
testing/run_test_suite.py - 国会議員ダッシュボード 統合テストスイート
Design.md（統合デザインハーネス）第3層 Design Quality Gate および各種回帰テストを一括実行する。
"""

import os
import sys
import re
import json
import py_compile
import unittest
import subprocess

# Windows環境コンソール文字化け対策 (GLOBAL_RULES.md §2-2)
if sys.platform == 'win32':
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTING_DIR = os.path.join(ROOT_DIR, 'testing')


def print_gate_header(title):
    print(f"\n{'='*70}\n[Design Quality Gate] {title}\n{'='*70}")


def run_gate1_static_checks():
    """Gate 1: 静的ルール・DOM構造・CSSトークン・セキュリティ検査 (Design.md §3 Gate 1)"""
    print_gate_header("Gate 1: 静的CSS / DOM構造 / セキュリティ検査")
    errors = []

    # 1. index.html 検査
    html_path = os.path.join(ROOT_DIR, 'index.html')
    if not os.path.exists(html_path):
        errors.append("index.html が存在しません")
    else:
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # BAN-09: インライン <style> タグ禁止
        inline_styles = re.findall(r'<style\b[^>]*>([\s\S]*?)</style>', html, re.IGNORECASE)
        if inline_styles:
            errors.append(f"[BAN-09] index.html にインライン <style> が検出されました ({len(inline_styles)} 件)")
        else:
            print("  ✓ [BAN-09] インライン <style> タグ 0件")

        # 必須要素の存在確認
        required_elements = [
            ('theme-toggle', 'テーマ切替ボタン'),
            ('status-bar', '件数ステータスバー (テーブル直上)'),
            ('pagination-info', '件数情報表示スパン'),
            ('members-table', '議員一覧テーブル'),
            ('sort-id', 'IDソートヘッダー')
        ]
        for elem_id, label in required_elements:
            if f'id="{elem_id}"' not in html and f"id='{elem_id}'" not in html:
                errors.append(f"index.html に必須要素 '{elem_id}' ({label}) が見つかりません")
            else:
                print(f"  ✓ 必須UI要素 '{elem_id}' ({label}) 存在確認")

        # 初期ソートインジケーター確認
        if 'id="sort-id">ID ▲</th>' not in html:
            errors.append("index.html の IDソートヘッダー初期マークアップが 'ID ▲' となっていません")
        else:
            print("  ✓ IDソートヘッダー初期表示 'ID ▲' 整合確認")

    # 2. style.css 検査
    css_path = os.path.join(ROOT_DIR, 'style.css')
    if not os.path.exists(css_path):
        errors.append("style.css が存在しません")
    else:
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()

        # 標準 Slate & Blue トークン体系 (Design.md §1.1)
        required_tokens = [
            '--bg-primary', '--bg-secondary', '--bg-card', '--bg-glass',
            '--border-color', '--text-primary', '--text-secondary',
            '--accent-primary', '--color-wiki'
        ]
        for token in required_tokens:
            if token not in css:
                errors.append(f"style.css に標準デザイントークン '{token}' が定義されていません")
            else:
                print(f"  ✓ 標準デザイントークン '{token}' 存在確認")

        # ダークテーマ [data-theme="dark"] 定義確認
        if '[data-theme="dark"]' not in css:
            errors.append("style.css に [data-theme=\"dark\"] セレクタが定義されていません")
        else:
            print("  ✓ [data-theme=\"dark\"] セレクタおよびダークトークン定義確認")

        # Sticky グラスモーフィズムヘッダー (Design.md §1.4-1)
        if 'position: sticky' not in css or 'backdrop-filter' not in css:
            errors.append("style.css に Sticky グラスモーフィズムヘッダー定義が見つかりません")
        else:
            print("  ✓ Sticky グラスモーフィズムヘッダー定義確認")

    # 3. app.js 検査
    app_path = os.path.join(ROOT_DIR, 'app.js')
    if not os.path.exists(app_path):
        errors.append("app.js が存在しません")
    else:
        with open(app_path, 'r', encoding='utf-8') as f:
            js = f.read()

        # BAN-10: escapeHtml 定義および呼び出し確認
        if 'function escapeHtml(' not in js:
            errors.append("[BAN-10] app.js に escapeHtml 関数が定義されていません")
        else:
            escape_calls = len(re.findall(r'escapeHtml\(', js))
            if escape_calls < 5:
                errors.append(f"[BAN-10] escapeHtml の呼び出し箇所が不足しています ({escape_calls} 回)")
            else:
                print(f"  ✓ [BAN-10] escapeHtml 関数定義および呼出網羅確認 ({escape_calls} 箇所)")

        # DocumentFragment 一括描画確認
        if 'createDocumentFragment' not in js:
            errors.append("app.js に DocumentFragment 一括描画処理が見つかりません")
        else:
            print("  ✓ DocumentFragment 一括描画処理確認")

        # テーマ切替ロジック確認
        if 'initTheme' not in js or 'applyTheme' not in js:
            errors.append("app.js にテーマ切替ロジック (initTheme / applyTheme) が見つかりません")
        else:
            print("  ✓ テーマ切替および localStorage 永続化ロジック確認")

    if errors:
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return False
    print(">>> Gate 1 ALL CHECKS PASSED")
    return True


def run_gate2_backend_and_parser_tests():
    """Gate 2: バックエンド構文・パーサー回帰テスト (Design.md §3 Gate 2)"""
    print_gate_header("Gate 2: バックエンド構文コンパイル & パーサー単体回帰テスト")

    # 1. Python 構文コンパイル検査
    python_files = ['parsers.py', 'storage.py', 'scraper.py', 'test_parsers.py']
    for py_file in python_files:
        path = os.path.join(ROOT_DIR, py_file)
        if os.path.exists(path):
            try:
                py_compile.compile(path, doraise=True)
                print(f"  ✓ py_compile: {py_file} 構文正常")
            except py_compile.PyCompileError as e:
                print(f"  ✗ py_compile 構文エラー ({py_file}): {e}", file=sys.stderr)
                return False

    # 2. test_parsers.py 単体回帰テストスイートの実行
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=ROOT_DIR, pattern='test_parsers.py')
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    if not result.wasSuccessful():
        print(f"  ✗ test_parsers.py でエラー/失敗が検出されました (failures={len(result.failures)}, errors={len(result.errors)})", file=sys.stderr)
        return False

    print(f"  ✓ test_parsers.py: {result.testsRun} 件の単体テストすべて合格 (OK)")
    print(">>> Gate 2 ALL CHECKS PASSED")
    return True


def run_gate3_data_integrity():
    """Gate 3: データ整合性検査 (Design.md §3 Gate 2)"""
    print_gate_header("Gate 3: 国会議員データ整合性検査 (data.js)")
    data_path = os.path.join(ROOT_DIR, 'data.js')
    if not os.path.exists(data_path):
        print("  ✗ data.js が存在しません", file=sys.stderr)
        return False

    with open(data_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # window.DIET_DATA = { ... }; から JSON 部分を抽出
    m = re.search(r'window\.DIET_DATA\s*=\s*(\{[\s\S]*\});?\s*$', content)
    if not m:
        print("  ✗ data.js の window.DIET_DATA 宣言をパースできません", file=sys.stderr)
        return False

    try:
        data = json.loads(m.group(1))
    except Exception as e:
        print(f"  ✗ data.js の JSON パースに失敗しました: {e}", file=sys.stderr)
        return False

    members = data.get('members', [])
    member_count = len(members)
    print(f"  ✓ 総議員レコード数: {member_count} 名")

    if member_count < 700:
        print(f"  ✗ 議員レコード数が規定 (700名超) を下回っています ({member_count} 名)", file=sys.stderr)
        return False

    # 必須フィールドの検査
    required_keys = ['id', 'name', 'house', 'party', 'birthdate']
    missing_counts = {k: 0 for k in required_keys}
    for m in members:
        for k in required_keys:
            if not m.get(k):
                missing_counts[k] += 1

    for k, cnt in missing_counts.items():
        if cnt > 0:
            print(f"  ✗ 必須属性 '{k}' の欠損が {cnt} 件検出されました", file=sys.stderr)
            return False
        print(f"  ✓ 必須属性 '{k}' 欠損 0件 (100% 充足)")

    print(">>> Gate 3 ALL CHECKS PASSED")
    return True


def run_gate4_frontend_runtime_tests():
    """Gate 4: フロントエンド描画・計算回帰テスト (Node.js)"""
    print_gate_header("Gate 4: フロントエンド描画・計算回帰テスト (Node.js)")

    test_scripts = [
        os.path.join(TESTING_DIR, 'test_render_runtime.js'),
        os.path.join(TESTING_DIR, 'test_chart.js'),
        os.path.join(TESTING_DIR, 'test_birthplace_chart.js'),
        os.path.join(TESTING_DIR, 'test_today.js'),
        os.path.join(TESTING_DIR, 'test_female_ratio.js')
    ]

    for script in test_scripts:
        if not os.path.exists(script):
            continue
        rel_name = os.path.basename(script)
        cmd = ['node', script]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=ROOT_DIR)
        if res.returncode != 0:
            print(f"  ✗ {rel_name} 実行時エラー:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
            return False
        print(f"  ✓ {rel_name}: 実行時描画・回帰検証 合格")

    print(">>> Gate 4 ALL CHECKS PASSED")
    return True


def main():
    print(f"\n======================================================================")
    print(f"  国会議員ダッシュボード (Giin) Design Quality Gate 統合テストスイート")
    print(f"======================================================================")

    g1 = run_gate1_static_checks()
    g2 = run_gate2_backend_and_parser_tests()
    g3 = run_gate3_data_integrity()
    g4 = run_gate4_frontend_runtime_tests()

    if all([g1, g2, g3, g4]):
        print(f"\n{'#'*70}")
        print(f"  🎉 [PASS] すべての Design Quality Gate (Gate 1〜4) に完全合格しました！")
        print(f"{'#'*70}\n")
        return 0
    else:
        print(f"\n{'!'*70}")
        print(f"  ❌ [FAIL] 一部の Quality Gate でエラーが検出されました。修正してください。")
        print(f"{'!'*70}\n", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
