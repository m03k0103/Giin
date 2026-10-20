# -*- coding: utf-8 -*-
"""
wiki_client.py - Wikipedia / Wikidata 二次データソース連携モジュール
国会議員 属性データ可視化ダッシュボード用

衆議院・参議院公式Webサイトから情報を取得できない場合、または属性に欠損がある場合に、
中立・網羅的な公認二次情報源（Wikipedia 日本語版 / Wikidata）から属性を安全に取得・補完します。
"""

import sys
import re
import json
import urllib.parse
import urllib.request
from datetime import datetime

# Windows環境における文字コード対策
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

# Wikimedia API利用規約に準拠したUser-Agent (連絡先URLを含む)
WIKI_HEADERS = {
    'User-Agent': 'DietMemberDataBot/1.0 (https://github.com/m03k0103/Giin; contact: info@example.com)'
}

def clean_member_name(name):
    """
    議員名から全角・半角スペースを除去し、検索用キーに正規化
    """
    if not name:
        return ""
    return re.sub(r'[\s\u3000]+', '', str(name)).strip()

def strip_wikitext(text):
    """
    Wikitextから内部リンク、テンプレート、参照タグ、HTMLタグを除去して純粋なテキストを抽出
    """
    if not text:
        return ""
    t = str(text)
    # <ref>...</ref> タグの除去
    t = re.sub(r'<ref[^>]*>.*?</ref>', '', t, flags=re.DOTALL)
    t = re.sub(r'<ref[^>]*/>', '', t)
    # <br> などのタグを改行または空白に
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
    t = re.sub(r'<[^>]+>', '', t)
    # [[ファイル:...]] や [[画像:...]] の除去
    t = re.sub(r'\[\[(?:ファイル|画像|File|Image):[^\]]+\]\]', '', t, flags=re.IGNORECASE)
    # [[記事名|表示名]] -> 表示名
    t = re.sub(r'\[\[(?:[^|\]\n]+\|)?([^\]\n]+)\]\]', r'\1', t)
    # 残存する [[ や ]] の除去
    t = t.replace('[[', '').replace(']]', '')
    # {{...}} テンプレート（生年月日以外の装飾、仮リンク等）の除去
    t = re.sub(r'\{\{[^\}]+\}\}', '', t)
    # 前後の空白と連続改行を整理
    lines = [line.strip().lstrip('*#:') for line in t.splitlines() if line.strip()]
    return '\n'.join(lines).strip()

def parse_wiki_birthdate(raw_text):
    """
    WikitextまたはInfobox内のテキストから生年月日を抽出（YYYY年M月D日 または YYYY年M月 または YYYY年）
    """
    if not raw_text:
        return None
        
    # パターン1: {{生年月日と年齢|1963|2|1...}} または {{生年月日|1963|2|1...}}
    m_tpl = re.search(r'\{\{(?:生年月日と年齢|生年月日|Date\s*of\s*birth\s*and\s*age)\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})', raw_text, re.IGNORECASE)
    if m_tpl:
        y, m, d = m_tpl.group(1), int(m_tpl.group(2)), int(m_tpl.group(3))
        return f"{y}年{m}月{d}日"
        
    # パターン2: 1963年2月1日 または [[1963年]][[2月1日]]
    cleaned = strip_wikitext(raw_text)
    m_full = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', cleaned)
    if m_full:
        y, m, d = m_full.group(1), int(m_full.group(2)), int(m_full.group(3))
        return f"{y}年{m}月{d}日"
        
    # パターン3: 1963年2月
    m_ym = re.search(r'(\d{4})年\s*(\d{1,2})月', cleaned)
    if m_ym:
        y, m = m_ym.group(1), int(m_ym.group(2))
        return f"{y}年{m}月"
        
    # パターン4: 1963年
    m_y = re.search(r'(\d{4})年', cleaned)
    if m_y:
        return f"{m_y.group(1)}年"
        
    # パターン5: ISO 形式 (1963-02-01)
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', cleaned)
    if m_iso:
        y, m, d = m_iso.group(1), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{y}年{m}月{d}日"
        
    return None

def fetch_wikipedia_page_content(title):
    """
    Wikipedia API より指定されたタイトルのページ内容（Wikitext）を取得
    """
    params = {
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json',
        'rvslots': 'main',
        'redirects': '1'
    }
    url = 'https://ja.wikipedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            pages = data.get('query', {}).get('pages', {})
            for pid, page in pages.items():
                if pid == '-1':
                    return None, None
                real_title = page.get('title', title)
                content = page.get('revisions', [{}])[0].get('slots', {}).get('main', {}).get('*', '')
                return real_title, content
    except Exception as e:
        print(f"[wiki_client] Wikipedia取得エラー ({title}): {e}", file=sys.stderr)
        return None, None
    return None, None

def search_wikipedia_title(name, house=None):
    """
    直接タイトルでヒットしなかった場合に、Wikipedia検索APIで該当記事タイトルを探索
    """
    query = f"{name} 政治家" if not house else f"{name} {house}"
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': query,
        'format': 'json',
        'srlimit': 3
    }
    url = 'https://ja.wikipedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            search_items = data.get('query', {}).get('search', [])
            if search_items:
                return search_items[0].get('title')
    except Exception as e:
        print(f"[wiki_client] Wikipedia検索エラー ({name}): {e}", file=sys.stderr)
    return None

def fetch_wikidata_entity(name):
    """
    Wikidata SPARQL クエリを用いて生年月日・出生地・出身校の構造化データを取得（短時間タイムアウト付き）
    """
    query = f"""
    SELECT ?item ?itemLabel ?birthDate ?birthPlaceLabel ?schoolLabel WHERE {{
      ?item rdfs:label "{name}"@ja .
      ?item wdt:P31 wd:Q5 .
      OPTIONAL {{ ?item wdt:P569 ?birthDate . }}
      OPTIONAL {{ ?item wdt:P19 ?birthPlace . }}
      OPTIONAL {{ ?item wdt:P69 ?school . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ja". }}
    }} LIMIT 3
    """
    url = 'https://query.wikidata.org/sparql?format=json&query=' + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            bindings = data.get('results', {}).get('bindings', [])
            if not bindings:
                return None
            b = bindings[0]
            bdate_raw = b.get('birthDate', {}).get('value')
            bdate = parse_wiki_birthdate(bdate_raw) if bdate_raw else None
            bplace = b.get('birthPlaceLabel', {}).get('value')
            school = b.get('schoolLabel', {}).get('value')
            return {
                'birthdate': bdate,
                'birthplace_raw': bplace,
                'school_raw': school,
                'source': 'wikidata'
            }
    except Exception:
        # SPARQL は高負荷時にタイムアウトすることがあるため静かにフォールバック
        return None

def extract_infobox_fields(content):
    """
    Infobox（政治家等）の各フィールドを抽出。
    改行＋パイプで区切られたパラメータブロックを確実にキャプチャ。
    """
    fields = {}
    if not content:
        return fields
        
    # 各行の先頭パイプ | key = value をキャプチャ
    matches = re.findall(r'\n\|\s*([a-zA-Z0-9_\u3040-\u30ff\u4e00-\u9faf]+?)\s*=\s*(.*?)(?=\n\s*\||\n\s*\}\})', content, re.DOTALL)
    for k, v in matches:
        fields[k.strip()] = v.strip()
    return fields

def get_secondary_member_data(name, house=None, extract_birthplace_fn=None, extract_school_fn=None):
    """
    指定された議員名から Wikipedia / Wikidata を照会し、属性（生年月日、出身地、出身校、学部）を正規化して返却。
    
    戻り値:
        dict または None
        {
            'name': '...',
            'birthdate': 'YYYY年M月D日',
            'birthplace': '東京都',
            'school': '東京大学',
            'faculty': '法学部',
            'source': 'wikipedia' または 'wikidata',
            'wiki_title': '...',
            'secondary_source': True
        }
    """
    clean_name = clean_member_name(name)
    if not clean_name:
        return None

    res = {
        'name': clean_name,
        'birthdate': None,
        'birthplace': None,
        'school': None,
        'faculty': None,
        'source': None,
        'wiki_title': None,
        'secondary_source': True
    }

    # 1. まず Wikipedia の記事取得を試行（最速・安定）
    wiki_title, content = fetch_wikipedia_page_content(clean_name)
    if not content:
        # 曖昧さ回避や通称名（例: 浮島智子 -> 浮島とも子）の検索
        candidate_title = search_wikipedia_title(clean_name, house)
        if candidate_title and candidate_title != clean_name:
            wiki_title, content = fetch_wikipedia_page_content(candidate_title)

    if content:
        res['wiki_title'] = wiki_title
        res['source'] = 'wikipedia'
        fields = extract_infobox_fields(content)
        
        # 生年月日の抽出
        raw_bdate = fields.get('生年月日')
        if raw_bdate:
            res['birthdate'] = parse_wiki_birthdate(raw_bdate)
            
        # 本文からの生年月日バックアップ抽出（Infoboxにない場合）
        if not res['birthdate']:
            # 導入部から（例: 逢沢 一郎（あいさわ いちろう、1954年6月10日 - ）は...）
            lead_match = re.search(r'（[^）]*?(\d{4}年\d{1,2}月(?:\d{1,2}日)?)[^）]*?）', content[:2000])
            if lead_match:
                res['birthdate'] = parse_wiki_birthdate(lead_match.group(1))

        # 出身地の抽出
        raw_bplace = fields.get('出生地') or fields.get('出身地')
        if raw_bplace:
            clean_bplace = strip_wikitext(raw_bplace)
            if extract_birthplace_fn:
                # 出身地プレフィックスを補ってパーサーに渡す
                pref = extract_birthplace_fn('出身地・' + clean_bplace)
                res['birthplace'] = pref if pref != '不明' else extract_birthplace_fn(clean_bplace)
            else:
                res['birthplace'] = clean_bplace

        # 出身校の抽出
        raw_school = fields.get('学歴') or fields.get('出身校')
        if raw_school:
            clean_school = strip_wikitext(raw_school)
            if extract_school_fn:
                # 複数行ある場合は最初の大学または主要校を優先
                first_line = clean_school.splitlines()[0] if clean_school else ""
                sch, fac = extract_school_fn(first_line)
                if not sch or sch == '不明':
                    sch, fac = extract_school_fn(clean_school)
                res['school'] = sch
                res['faculty'] = fac
            else:
                res['school'] = clean_school

    # 2. Wikipedia で欠損がある項目について、Wikidata SPARQL での補完を試行
    if not (res['birthdate'] and res['birthplace'] and res['school']):
        wd_data = fetch_wikidata_entity(clean_name)
        if wd_data:
            if not res['birthdate'] and wd_data.get('birthdate'):
                res['birthdate'] = wd_data['birthdate']
            if not res['birthplace'] and wd_data.get('birthplace_raw'):
                raw_p = wd_data['birthplace_raw']
                if extract_birthplace_fn:
                    pref = extract_birthplace_fn('出身地・' + raw_p)
                    res['birthplace'] = pref if pref != '不明' else extract_birthplace_fn(raw_p)
                else:
                    res['birthplace'] = raw_p
            if not res['school'] and wd_data.get('school_raw'):
                raw_s = wd_data['school_raw']
                if extract_school_fn:
                    sch, fac = extract_school_fn(raw_s)
                    res['school'] = sch
                    res['faculty'] = fac
                else:
                    res['school'] = raw_s
            if not res['source']:
                res['source'] = 'wikidata'

    # 有効なデータが1つでも取得できたか確認
    if any([res['birthdate'], res['birthplace'], res['school']]):
        return res
    return None
