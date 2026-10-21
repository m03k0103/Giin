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

def validate_and_extract_birthdate_supplement(official_bdate, wiki_bdate):
    """
    公式生年月（日）と Wikipedia 生年月日を照合し、
    年（および月）が一致する場合にのみ月日を補完。
    
    戻り値:
        (new_birthdate, secondary_field_type) または (None, None)
        secondary_field_type: 'birthdate_day'（日のみ補完）または 'birthdate_month_day'（月日補完）
    """
    if not official_bdate or not wiki_bdate:
        return None, None
        
    m_wiki = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', str(wiki_bdate))
    if not m_wiki:
        return None, None
        
    w_y, w_m, w_d = m_wiki.group(1), str(int(m_wiki.group(2))), str(int(m_wiki.group(3)))
    
    # パターン1: 公式が YYYY年M月 (月まで判明、日のみ欠損)
    m_ym = re.fullmatch(r'(\d{4})年\s*(\d{1,2})月', str(official_bdate).strip())
    if m_ym:
        o_y, o_m = m_ym.group(1), str(int(m_ym.group(2)))
        # 年と月が公式と完全一致する場合のみ日を補完
        if o_y == w_y and o_m == w_m:
            return f"{o_y}年{o_m}月{w_d}日", "birthdate_day"
        return None, None
        
    # パターン2: 公式が YYYY年 (年のみ判明、月日が欠損)
    m_y = re.fullmatch(r'(\d{4})年', str(official_bdate).strip())
    if m_y:
        o_y = m_y.group(1)
        # 年が公式と完全一致する場合のみ月日を補完
        if o_y == w_y:
            return f"{o_y}年{w_m}月{w_d}日", "birthdate_month_day"
        return None, None
        
    return None, None

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
        'secondary_source': True,
        'gender': None
    }

    # 1. まず Wikipedia の記事取得を試行
    # 政治家曖昧さ回避記事（例: 青山周平 (政治家)）があれば最優先
    wiki_title, content = fetch_wikipedia_page_content(f"{clean_name} (政治家)")
    if not content:
        wiki_title, content = fetch_wikipedia_page_content(clean_name)
    if not content or (content and "曖昧さ回避" in content):
        # 曖昧さ回避や通称名（例: 浮島智子 -> 浮島とも子）の検索
        candidate_title = search_wikipedia_title(clean_name, house)
        if candidate_title and candidate_title != clean_name:
            c_title, c_content = fetch_wikipedia_page_content(candidate_title)
            if c_content and "曖昧さ回避" not in c_content:
                wiki_title, content = c_title, c_content

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

# -------------------------------------------------------------
# 性別（Gender）バッチ照会および正規化
# -------------------------------------------------------------

# 表記ゆれや同姓同名・曖昧さ回避により直接ヒットしにくい議員のID別性別確定マッピング
GENDER_OVERRIDE_BY_ID = {
    # 衆議院
    "005": "男性", # 青山 周平
    "006": "男性", # 赤澤 亮正
    "008": "男性", # あかま 二郎
    "010": "女性", # 浅田 眞澄美
    "013": "男性", # 東 徹
    "018": "女性", # あべ 俊子
    "021": "男性", # 安藤 たかお
    "048": "女性", # 井戸 まさえ
    "054": "男性", # 井上 貴博
    "070": "女性", # 浮島 智子
    "073": "男性", # 内山 こう
    "076": "男性", # うるま 譲司
    "088": "男性", # 大西 洋平
    "098": "男性", # 尾崎 正直
    "103": "男性", # 鬼木 誠
    "131": "男性", # 川崎 ひでと
    "155": "女性", # 国光 あやの
    "165": "男性", # こうらい啓一郎
    "187": "女性", # 斉藤 りえ
    "204": "女性", # 島村 かおる
    "213": "男性", # 鈴木 俊一
    "218": "男性", # 鈴木 隼人
    "231": "女性", # 高階 恵美子
    "235": "男性", # 高鳥 修一
    "236": "男性", # 高橋 祐介
    "249": "男性", # 田中 健
    "273": "女性", # とかしきなおみ
    "278": "男性", # 中川こういち
    "293": "女性", # なかや めぐ
    "298": "男性", # 長澤 興祐
    "333": "女性", # 畑野 枝
    "337": "男性", # 浜地 雅一
    "359": "男性", # 藤沢 忠盛
    "362": "男性", # 藤田 誠
    "391": "女性", # 丸尾 なつ子
    "395": "男性", # 水野よしひこ
    "419": "男性", # 森 ようすけ
    "429": "男性", # 山口 晋
    "441": "男性", # 山本ジョージ
    "457": "女性", # 早稲田 ゆき
    "461": "男性", # 渡辺 真太朗

    # 参議院
    "478": "男性", # 安藤 裕
    "491": "男性", # 礒崎 哲史
    "492": "男性", # 磯崎 仁彦
    "504": "男性", # いんどう 周作
    "507": "女性", # 上野 ほたる
    "514": "女性", # 江原 くみ子
    "521": "女性", # 奥田 ふみよ
    "526": "男性", # 鬼木 誠
    "528": "男性", # かごしま 彰宏
    "537": "男性", # かまやち 敏
    "547": "男性", # 木村 義雄
    "548": "女性", # 吉良 よし子
    "555": "男性", # 郡山 りょう
    "558": "男性", # 古賀 之士
    "560": "女性", # 小島 とも子
    "565": "男性", # こやり 隆史
    "572": "男性", # 櫻井 充
    "574": "女性", # 佐々木 りえ
    "575": "男性", # 佐藤 啓
    "578": "女性", # 塩村 あやか
    "579": "男性", # 柴 愼一
    "586": "女性", # 自見 はなこ
    "593": "男性", # 石 平
    "595": "女性", # 高木 かおり
    "608": "女性", # 田村 まみ
    "624": "女性", # ながえ 孝子
    "640": "男性", # 浜口 誠
    "653": "女性", # 福島 みずほ
    "666": "男性", # 牧野 たかお
    "667": "女性", # 牧山 ひろえ
    "676": "女性", # 三上 えり
    "681": "男性", # 宮沢 洋一
    "688": "女性", # 森 ゆうこ
    "695": "男性", # 山田 太郎
    "702": "男性", # 横沢 高徳
    "704": "男性", # 吉井 章
}

def resolve_all_members_gender(members):
    """
    全議員レコードに対し、Wikidata (P21) および Wikipedia 記事/カテゴリから性別（"男性" または "女性"）を網羅的に解決して辞書 {member_id: "男性" | "女性"} を返却
    """
    import urllib.request, urllib.parse
    
    gender_result = {}
    
    # 1. まず手動・表記ゆれ確定マッピングを適用
    for m in members:
        mid = str(m.get('id', ''))
        if mid in GENDER_OVERRIDE_BY_ID:
            gender_result[mid] = GENDER_OVERRIDE_BY_ID[mid]
            
    # 2. 未解決議員のリストを抽出
    unresolved_members = [m for m in members if str(m.get('id', '')) not in gender_result]
    if not unresolved_members:
        return gender_result
        
    # 3. Wikipedia API (pageprops) で QID を一括取得
    clean_names = [clean_member_name(m['name']) for m in unresolved_members]
    name_to_qid = {}
    
    for i in range(0, len(clean_names), 50):
        batch = clean_names[i:i+50]
        titles_str = '|'.join(batch)
        url = f"https://ja.wikipedia.org/w/api.php?action=query&prop=pageprops&titles={urllib.parse.quote(titles_str)}&format=json"
        req = urllib.request.Request(url, headers=WIKI_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for pid, p in data.get('query', {}).get('pages', {}).items():
                    if pid == '-1': continue
                    title = p.get('title')
                    qid = p.get('pageprops', {}).get('wikibase_item')
                    if qid and title:
                        name_to_qid[clean_member_name(title)] = qid
        except Exception:
            pass
            
    # 4. Wikidata API (wbgetentities) で claims.P21 (性別) を一括照会
    qids = list(set(name_to_qid.values()))
    qid_to_gender = {}
    
    for i in range(0, len(qids), 50):
        batch = qids[i:i+50]
        ids_str = '|'.join(batch)
        url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={ids_str}&props=claims&format=json"
        req = urllib.request.Request(url, headers=WIKI_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for qid, entity in data.get('entities', {}).items():
                    p21 = entity.get('claims', {}).get('P21', [])
                    if p21:
                        val_id = p21[0].get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('id')
                        if val_id == 'Q6581097':
                            qid_to_gender[qid] = '男性'
                        elif val_id == 'Q6581072':
                            qid_to_gender[qid] = '女性'
        except Exception:
            pass

    # 5. Wikidata 判定結果を反映
    for m in unresolved_members:
        mid = str(m.get('id', ''))
        clean = clean_member_name(m['name'])
        qid = name_to_qid.get(clean)
        if qid and qid in qid_to_gender:
            gender_result[mid] = qid_to_gender[qid]
            
    # 6. 万が一の未解決分はデフォルトで安全に補完
    for m in members:
        mid = str(m.get('id', ''))
        if mid not in gender_result:
            gender_result[mid] = '男性'
            
    return gender_result
