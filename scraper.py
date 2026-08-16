import os
import sys
import time
import json
import re
import unicodedata
import urllib.parse
import argparse
import shutil
from datetime import datetime

# Windows環境におけるコンソール文字化け（CP932 / UTF-8）対策
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

import requests
from bs4 import BeautifulSoup

# 漢字数字の変換用
KANJI_NUMS = {'〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9}

def kanji_to_int(kstr):
    """
    漢数字および全角・半角数字を整数に変換
    """
    if not kstr:
        return 0
    kstr = unicodedata.normalize('NFKC', str(kstr)).strip()
    if kstr.isdigit():
        return int(kstr)
    
    # 4桁の漢数字（例: 一九八八 -> 1988, 二〇〇〇 -> 2000）
    if len(kstr) == 4 and all(ch in KANJI_NUMS for ch in kstr):
        val = 0
        for ch in kstr:
            val = val * 10 + KANJI_NUMS[ch]
        return val
        
    if len(kstr) == 1:
        return KANJI_NUMS.get(kstr, 0)
        
    if '十' in kstr:
        parts = kstr.split('十')
        tens = KANJI_NUMS.get(parts[0], 1) if parts[0] else 1
        ones = KANJI_NUMS.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
        
    val = 0
    for ch in kstr:
        val = val * 10 + KANJI_NUMS.get(ch, 0)
    return val

def parse_japanese_birthdate(text):
    """
    議員プロフィール経歴テキスト（和暦・西暦）から生年月（日）または生年を抽出しフォーマット文字列を返す
    例: '1970年5月10日', '1980年3月', '1965年'
    """
    if not text:
        return "不明"
    text = unicodedata.normalize('NFKC', text)
    
    # ページ末尾の「（令和X年X月現在）」などの現在日付を除去して誤検知を防止
    text_clean = re.sub(r'[\(（][^）\)]*?現在[\)）]', '', text)
    
    era_map = {'明治': 1868, '大正': 1912, '昭和': 1926, '平成': 1989, '令和': 2019}
    
    # 1. 生まれ・生・誕生・出身文を優先探索（句読点や改行・丸印で区切られた節内を探索）
    # A. 和暦パターン（例: 昭和四十五年十月十四日生まれ、昭和五十五年大阪生まれ、昭和五十年神奈川県茅ヶ崎市出身）
    m_era = re.search(r'(明治|大正|昭和|平成|令和)(元|[0-9一二三四五六七八九十]+)年(?:\([^\)]*?\))?\s*(?:([0-9一二三四五六七八九十]+)月)?\s*(?:([0-9一二三四五六七八九十]+)日)?[^、,。\n\r○〇\t]{0,30}?(?:生まれ|生れ|誕生|に生まれる|出身)', text_clean)
    if m_era:
        era_name, era_yr_str, mon_str, day_str = m_era.groups()
        era_start = era_map.get(era_name, 1926)
        era_yr = 1 if era_yr_str == '元' else kanji_to_int(era_yr_str)
        year = era_start + era_yr - 1
        month = kanji_to_int(mon_str) if mon_str else None
        day = kanji_to_int(day_str) if day_str else None
        if 1900 <= year <= 2005:
            if month and day:
                return f"{year}年{month}月{day}日"
            elif month:
                return f"{year}年{month}月"
            else:
                return f"{year}年"

    # B. 西暦パターン（例: 一九八八年福岡県北九州市生まれ, 1971年(昭和46年)1月3日生まれ, 1958年4月7日新潟市生まれ）
    m_west = re.search(r'(\d{4}|[一二三四五六七八九〇]{4})年(?:\([^\)]*?\))?\s*(?:(\d{1,2}|[0-9一二三四五六七八九十]+)月)?\s*(?:(\d{1,2}|[0-9一二三四五六七八九十]+)日)?[^、,。\n\r○〇\t]{0,30}?(?:生まれ|生れ|誕生|に生まれる|出身)', text_clean)
    if m_west:
        y = kanji_to_int(m_west.group(1))
        m = kanji_to_int(m_west.group(2)) if m_west.group(2) else None
        d = kanji_to_int(m_west.group(3)) if m_west.group(3) else None
        if 1900 <= y <= 2005:
            if m and d:
                return f"{y}年{m}月{d}日"
            elif m:
                return f"{y}年{m}月"
            else:
                return f"{y}年"

    # C. 年号省略パターン（例: 五十八年生まれ、三十五年東京都生まれ）
    m_no_era = re.search(r'([0-9一二三四五六七八九十]{1,3})年(?:\([^\)]*?\))?\s*(?:([0-9一二三四五六七八九十]+)月)?\s*(?:([0-9一二三四五六七八九十]+)日)?[^、,。\n\r○〇\t]{0,30}?(?:生まれ|生れ|誕生|に生まれる|出身)', text_clean)
    if m_no_era:
        raw_yr = kanji_to_int(m_no_era.group(1))
        # 昭和20〜64年 (1945〜1989年)
        if 20 <= raw_yr <= 64:
            year = 1926 + raw_yr - 1
            month = kanji_to_int(m_no_era.group(2)) if m_no_era.group(2) else None
            day = kanji_to_int(m_no_era.group(3)) if m_no_era.group(3) else None
            if month and day:
                return f"{year}年{month}月{day}日"
            elif month:
                return f"{year}年{month}月"
            else:
                return f"{year}年"

    # 2. 汎用フォールバック（生まれ文が見つからない場合、1900〜2001年の範囲のみ採用）
    for m in re.finditer(r'(明治|大正|昭和|平成)(元|[0-9一二三四五六七八九十]+)年(?:\([^\)]*?\))?\s*([0-9一二三四五六七八九十]+)月\s*(?:([0-9一二三四五六七八九十]+)日)?', text_clean):
        era_name, era_yr_str, mon_str, day_str = m.groups()
        era_start = era_map.get(era_name, 1926)
        era_yr = 1 if era_yr_str == '元' else kanji_to_int(era_yr_str)
        year = era_start + era_yr - 1
        month = kanji_to_int(mon_str)
        day = kanji_to_int(day_str) if day_str else None
        if 1900 <= year <= 2001:
            return f"{year}年{month}月{day}日" if day else f"{year}年{month}月"

    for m in re.finditer(r'(\d{4}|[一二三四五六七八九〇]{4})年(?:\([^\)]*?\))?\s*(\d{1,2}|[0-9一二三四五六七八九十]+)月\s*(?:(\d{1,2}|[0-9一二三四五六七八九十]+)日)?', text_clean):
        y = kanji_to_int(m.group(1))
        mon = kanji_to_int(m.group(2))
        d = kanji_to_int(m.group(3)) if m.group(3) else None
        if 1900 <= y <= 2001:
            return f"{y}年{mon}月{d}日" if d else f"{y}年{mon}月"

    return "不明"

PREFECTURES = [
    '北海道', '青森県', '岩手県', '宮城県', '秋田県', '山形県', '福島県',
    '茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県',
    '新潟県', '富山県', '石川県', '福井県', '山梨県', '長野県', '岐阜県',
    '静岡県', '愛知県', '三重県', '滋賀県', '京都府', '大阪府', '兵庫県',
    '奈良県', '和歌山県', '鳥取県', '島根県', '岡山県', '広島県', '山口県',
    '徳島県', '香川県', '愛媛県', '高知県', '福岡県', '佐賀県', '長崎県',
    '熊本県', '大分県', '宮崎県', '鹿児島県', '沖縄県'
]

FOREIGN_COUNTRIES = [
    'アメリカ', '米国', '台湾', '中国', '韓国', '朝鮮', 'ブラジル', 'カナダ',
    '英国', 'イギリス', 'フランス', 'ドイツ', 'ロシア', 'ハワイ', 'ニューヨーク',
    'ロサンゼルス', '海外', '外国', 'ペルー', 'オーストラリア', '満州', '樺太',
    'アルゼンチン', 'フィリピン', 'シンガポール', 'タイ', 'ベトナム', 'メキシコ'
]

CITY_TO_PREF = {
    '札幌': '北海道', '函館': '北海道', '旭川': '北海道',
    '青森市': '青森県', '盛岡': '岩手県', '仙台': '宮城県', '秋田市': '秋田県', '山形市': '山形県', '福島市': '福島県', '郡山': '福島県', 'いわき': '福島県',
    '水戸': '茨城県', '宇都宮': '栃木県', '前橋': '群馬県', '高崎': '群馬県', '渋川': '群馬県',
    'さいたま': '埼玉県', '浦和': '埼玉県', '大宮': '埼玉県', '川越': '埼玉県',
    '千葉市': '千葉県', '船橋': '千葉県', '柏': '千葉県', '松戸': '千葉県', '千倉': '千葉県', '南房総': '千葉県',
    '東京': '東京都', '墨田区': '東京都', '世田谷': '東京都', '新宿': '東京都', '文京': '東京都', '千代田': '東京都', '港区': '東京都', '杉並': '東京都',
    '横浜': '神奈川県', '川崎': '神奈川県', '相模原': '神奈川県', '鎌倉': '神奈川県', '横須賀': '神奈川県',
    '新潟市': '新潟県', '長岡': '新潟県', '富山市': '富山県', '高岡': '富山県', '金沢': '石川県', '福井市': '福井県', '甲府': '山梨県', '長野市': '長野県', '松本': '長野県',
    '岐阜市': '岐阜県', '大垣': '岐阜県', '静岡市': '静岡県', '浜松': '静岡県', '沼津': '静岡県', '名古屋': '愛知県', '豊橋': '愛知県', '岡崎': '愛知県', '一宮': '愛知県',
    '津市': '三重県', '四日市': '三重県', '伊勢': '三重県', '大津': '滋賀県', '彦根': '滋賀県', '京都': '京都府', '大阪': '大阪府', '堺市': '大阪府', '東大阪': '大阪府',
    '神戸': '兵庫県', '姫路': '兵庫県', '西宮': '兵庫県', '尼崎': '兵庫県', '明石': '兵庫県', '奈良市': '奈良県', '橿原': '奈良県', '和歌山市': '和歌山県',
    '鳥取市': '鳥取県', '米子': '鳥取県', '松江': '島根県', '出雲': '島根県', '岡山市': '岡山県', '倉敷': '岡山県',
    '広島市': '広島県', '福山': '広島県', '呉市': '広島県', '山口市': '山口県', '下関': '山口県', '宇部': '山口県',
    '徳島市': '徳島県', '高松': '香川県', '丸亀': '香川県', '松山市': '愛媛県', '今治': '愛媛県', '高知市': '高知県',
    '福岡市': '福岡県', '北九州': '福岡県', '久留米': '福岡県', '飯塚': '福岡県', '佐賀市': '佐賀県', '鳥栖': '佐賀県', '長崎市': '長崎県', '佐世保': '長崎県',
    '熊本市': '熊本県', '八代': '熊本県', '大分市': '大分県', '別府': '大分県', '中津': '大分県', '宮崎市': '宮崎県', '都城': '宮崎県', '鹿児島市': '鹿児島県', '霧島': '鹿児島県', '那覇': '沖縄県'
}

def kanji_to_int(kstr):
    """
    漢数字および全角・半角数字を整数に変換
    """
    if not kstr:
        return 0
    kstr = unicodedata.normalize('NFKC', str(kstr)).strip()
    if kstr.isdigit():
        return int(kstr)
    
    if len(kstr) == 1:
        return KANJI_NUMS.get(kstr, 0)
        
    if '十' in kstr:
        parts = kstr.split('十')
        tens = KANJI_NUMS.get(parts[0], 1) if parts[0] else 1
        ones = KANJI_NUMS.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
        
    val = 0
    for ch in kstr:
        val = val * 10 + KANJI_NUMS.get(ch, 0)
    return val

def backup_existing_full_data():
    """
    既存のdata.json/data.jsに全件データが含まれている場合、data_full.json / data_full.jsに退避
    """
    if os.path.exists('data.json'):
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                existing = json.load(f)
            members = existing.get('members', [])
            count = len(members)
            # 20名以上（テストデータより明らかに多い全件データなど）の場合に退避
            if count > 20:
                shutil.copyfile('data.json', 'data_full.json')
                if os.path.exists('data.js'):
                    shutil.copyfile('data.js', 'data_full.js')
                print(f"[データ退避] 既存の全件データ（{count}名）を data_full.json および data_full.js に退避しました。")
                return True
        except Exception as e:
            print(f"[警告] バックアップ作成失敗: {e}", file=sys.stderr)
    return False

def restore_full_data():
    """
    退避済みの全件データ（data_full.json/data_full.js）から data.json/data.js を復元
    """
    if os.path.exists('data_full.json') and os.path.exists('data_full.js'):
        shutil.copyfile('data_full.json', 'data.json')
        shutil.copyfile('data_full.js', 'data.js')
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = len(data.get('members', []))
        print(f"[復元完了] data_full.json から全件データ（{count}名）を data.json / data.js に復元しました。")
        return True
    else:
        print("[エラー] 退避ファイル（data_full.json / data_full.js）が見つかりません。", file=sys.stderr)
        return False

def get_shugiin_total_count(headers):
    """
    衆議院の会派別所属議員数一覧表から欠員を除いた現員数を取得
    情報源: https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiha_m.htm
    """
    try:
        url = 'https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/shiryo/kaiha_m.htm'
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = 'cp932'
        soup = BeautifulSoup(r.text, 'html.parser')
        for tr in soup.find_all('tr'):
            tds = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
            if any('計' in td for td in tds):
                for td in tds:
                    m = re.search(r'(\d+)', td)
                    if m and int(m.group(1)) > 100:
                        return int(m.group(1))
    except Exception as e:
        print(f"[警告] 衆議院現員数の取得に失敗しました (デフォルト465を使用): {e}", file=sys.stderr)
    return 465

def get_sangiin_total_count(headers):
    """
    参議院の会派別所属議員数一覧から欠員を除いた現員数を取得
    情報源: https://www.sangiin.go.jp/japanese/joho1/kousei/giin/current/giinsu.htm
    """
    try:
        url = 'https://www.sangiin.go.jp/japanese/joho1/kousei/giin/current/giinsu.htm'
        r = requests.get(url, headers=headers, timeout=10)
        actual_url = r.url
        if 'location.replace' in r.text:
            m = re.search(r'location\.replace\("([^"]+)"\)', r.text)
            if m:
                actual_url = urllib.parse.urljoin(url, m.group(1))
                r = requests.get(actual_url, headers=headers, timeout=10)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        for tr in soup.find_all('tr'):
            tds = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
            if any('合計' in td for td in tds):
                for td in tds:
                    m = re.search(r'(\d+)', td)
                    if m and int(m.group(1)) > 100:
                        return int(m.group(1))
    except Exception as e:
        print(f"[警告] 参議院現員数の取得に失敗しました (デフォルト248を使用): {e}", file=sys.stderr)
    return 248

UNIV_ABBR_MAP = {
    '東大': '東京大学',
    '京大': '京都大学',
    '阪大': '大阪大学',
    '名大': '名古屋大学',
    '東北大': '東北大学',
    '北大': '北海道大学',
    '九大': '九州大学',
    '早大': '早稲田大学',
    '慶大': '慶應義塾大学',
    '慶応大': '慶應義塾大学',
    '慶応': '慶應義塾大学',
    '慶応義塾': '慶應義塾大学',
    '神大': '神戸大学',
    '一橋大': '一橋大学',
    '東工大': '東京工業大学',
    '横国大': '横浜国立大学',
    '都立大': '東京都立大学',
    '同大': '同志社大学',
    '立大': '立命館大学',
    '関大': '関西大学',
    '関学大': '関西学院大学',
    '明大': '明治大学',
    '青学大': '青山学院大学',
    '中大': '中央大学',
    '法大': '法政大学',
    '法政大': '法政大学',
}

def clean_school_name(school):
    if not school:
        return "不明"
    school = unicodedata.normalize('NFKC', school)
    
    # 慶応 -> 慶應
    school = school.replace('慶応', '慶應')
    
    # 私立プレフィックスの除去
    if school.startswith('私立'):
        school = school[2:].strip()
        
    # 現〇〇 の「現」除去
    if school.startswith('現') and len(school) > 1:
        school = school[1:].strip()
        
    # ICUなどの英字プレフィックスの除去 (ICU国際基督教大学 -> 国際基督教大学)
    school = re.sub(r'^[A-Za-z]+(?=[\u3040-\u30ff\u4e00-\u9faf])', '', school).strip()
    
    # 鹿児島ラ・サール -> ラ・サール
    if 'ラ・サール' in school:
        school = school.replace('鹿児島ラ・サール', 'ラ・サール')
        
    # 〇や○や「を経て」「を受け」などの区切り・前置詞の除去
    if '〇' in school or '○' in school:
        parts = re.split(r'[〇○]', school)
        school = parts[-1]
    if 'を経て' in school:
        school = school.split('を経て')[-1]
    if 'を受け' in school:
        school = school.split('を受け')[-1]
    if '・' in school and 'ラ・サール' not in school:
        parts = school.split('・')
        if any(kw in parts[-1] for kw in ['大学', '短大', '高専', '高校', '高等学校', '専門学校', '養護学校', '特別支援学校']):
            school = parts[-1]
        
    # 年月日・プレフィックス・助詞の除去（※「日本大学」の「日」や「同志社大学」の「同」を誤って消さないよう注意）
    school = re.sub(r'^(?:(?:明治|大正|昭和|平成|令和|同)?[0-9一二三四五六七八九十元]+年(?:\([^\)]*?\))?)?\s*(?:[0-9一二三四五六七八九十]+月)?\s*(?:[0-9一二三四五六七八九十]+日)?\s*(?:に|より|から|を経て|を経て、|を受け|を受け、)?', '', school).strip()
    
    # 先頭に残った月・日（「日本」以外）・助詞等のトリム
    while True:
        prev = school
        school = re.sub(r'^(?:同?[0-9一二三四五六七八九十元]+年|年|月|月に|日に|に|より|から|を経て|を経て、|を受け|を受け、)', '', school).strip()
        # 先頭の「日」は「日本」以外の場合のみ除去
        if school.startswith('日') and not school.startswith('日本'):
            school = school[1:].strip()
        if school == prev:
            break

    # 略称マッピング
    for abbr, full in UNIV_ABBR_MAP.items():
        if school == abbr or school == abbr + '学' or school == abbr + '院':
            if '院' in school:
                return full + '大学院' if not full.endswith('大学') else full.replace('大学', '大学院')
            return full
        if school.startswith(abbr) and len(school) <= len(abbr) + 2:
            return full
            
    # "東大学" などの誤変換の修正
    if school == "東大学":
        return "東京大学"
    if school == "京大学":
        return "京都大学"
    if school == "阪大学":
        return "大阪大学"
    if school == "名大学":
        return "名古屋大学"
    if school == "九大学":
        return "九州大学"
        
    return school

PREF_BASE_MAP = {}
for p in PREFECTURES:
    base = p.rstrip('都府県')
    if base != '北海':
        PREF_BASE_MAP[base] = p

def extract_birthplace(text):
    """
    経歴テキストから出身都道府県を抽出（外国出身の場合は '外国'、不明な場合は '不明'）
    """
    if not text:
        return "不明"
    text = unicodedata.normalize('NFKC', text)
    
    # 1. 「出身地・〇〇」「出身地:〇〇」「出身地 〇〇」パターン
    m_direct = re.search(r'出身地[・:\s　]+([^\s,、。○〇\t\n\r]+)', text)
    if m_direct:
        target = m_direct.group(1).strip()
        for pref in PREFECTURES:
            if pref in target:
                return pref
        for city, pref in CITY_TO_PREF.items():
            if city in target:
                return pref
        for kw in FOREIGN_COUNTRIES:
            if kw in target:
                return "外国"
                
    # 2. 節単位の探索
    clauses = re.split(r'[、,。\n\r○〇\t]', text)
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        # 出生・出身関連キーワード（単体の「生」は地方創生・生活等に誤合致するため除外）
        if re.search(r'(?:生まれ|生れ|出生|誕生|に生まれる|出身|育ち|(?:年|月|日)生\b)', clause):
            # 47都道府県
            for pref in PREFECTURES:
                if pref in clause:
                    return pref
            # 市区町村
            for city, pref in CITY_TO_PREF.items():
                if city in clause:
                    return pref
            # 都府県省略（例: 東京に誕生 -> 東京都, 熊本生まれ -> 熊本県）
            for base, pref in PREF_BASE_MAP.items():
                if re.search(base + r'(?:に|で)?(?:生まれ|生れ|誕生|出身|育ち|に生まれる)', clause):
                    return pref
            # 外国
            for kw in FOREIGN_COUNTRIES:
                if re.search(kw + r'[^。\n\r]*?(?:生まれ|生れ|出生|誕生|出身|に生まれる)', clause):
                    return "外国"

    return "不明"

def normalize_party(raw_party, house=None):
    """
    会派略称の表記ゆれ・指定統一ルールの適用
    - 参議院の [みら] -> [みらい]
    - 参議院の [民主] -> [国民]
    - [い党] -> [いのち]
    - [無] -> [無所属]
    """
    if not raw_party:
        return "無所属"
    p = raw_party.strip()
    if p == "無":
        return "無所属"
    if p == "い党":
        return "いのち"
    if p == "みら":
        return "みらい"
    if p == "民主":
        return "国民"
    return p

def is_job_phrase(after_text):
    if not after_text:
        return False
    return bool(re.search(r'^(?:[^\s,、。○〇\(\)（）0-9]{0,10}?(?:研究員|教授|准教授|講師|助教|教員|客員|非常勤|学長|総長|理事|職員|コーチ|監督|教鞭))', after_text))

def extract_school_and_faculty(text):
    """
    経歴テキストから出身校 (school) と 学部名 (faculty) を抽出
    - 大学・大学院名の場合は正式名称（東大 -> 東京大学 等）に補正
    - 出身校が大学・大学院以外（専門学校、高校等）の場合は学部名を 'N/A' とする
    """
    if not text:
        return "不明", "不明"
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('大學院', '大学院').replace('大學', '大学').replace('學部', '学部').replace('研究科', '研究科')
    
    candidates = []
    
    # 0. 〇〇大学(現△△大学□□学部) パターン
    for m in re.finditer(r'(?:(?:明治|大正|昭和|平成|令和|同)?[0-9一二三四五六七八九十元]+年)?([^\s,、。○〇\(\)（）0-9]+?(?:大学院|大学|短期大学|短大|高校|高等学校))\s*[\(（]現[^\)）]*?(?:[^\s,、。○〇\(\)（）0-9]*?(?:学部|研究科))?[\)）]', text):
        raw_school = m.group(1).strip()
        school = clean_school_name(raw_school)
        m_fac = re.search(r'([^\s,、。○〇\(\)（）0-9]*?(?:学部|研究科))[\)）]', m.group(0))
        fac = m_fac.group(1).strip() if m_fac else "不明"
        if '大学' in fac:
            fac = fac.split('大学')[-1]
        candidates.append((m.start(), school, fac if fac else "不明"))

    # 1. 〇〇大学 / 〇〇大学院 / 〇〇短期大学 (+ 学部)
    for m in re.finditer(r'(?:(?:明治|大正|昭和|平成|令和|同)?[0-9一二三四五六七八九十元]+年)?([^\s,、。○〇\(\)（）0-9]+?(?:大学院|大学|短期大学|短大))([^\s,、。○〇\(\)（）0-9]*?(?:学部|研究科))?([^\s,、。○〇\(\)（）0-9]{0,15})?', text):
        after_word = m.group(3) if m.group(3) else ""
        if is_job_phrase(after_word):
            continue
        raw_school = m.group(1).strip()
        school = clean_school_name(raw_school)
        fac = m.group(2).strip() if m.group(2) else "不明"
        if not fac:
            fac = "不明"
        candidates.append((m.start(), school, fac))

    # 2. 〇〇大+学部 または 略称大 (+ 卒 / 卒業 / 修了 / 中退 / 入学)
    # A. 略称大（UNIV_ABBR_MAP に定義されている略称: 東大卒, 法政大卒, 早大院修了 など）
    for abbr in UNIV_ABBR_MAP.keys():
        for m in re.finditer(re.escape(abbr) + r'(?:院)?([^\s,、。○〇\(\)（）0-9]*?(?:学部|研究科))?(?:卒|卒業|修了|中退|在学|入学)?([^\s,、。○〇\(\)（）0-9]{0,15})?', text):
            after_word = m.group(2) if m.group(2) else ""
            if is_job_phrase(after_word):
                continue
            school = clean_school_name(abbr)
            fac = m.group(1).strip() if m.group(1) else "不明"
            candidates.append((m.start(), school, fac))

    # B. 一般の 〇〇大+学部（例: 長崎大医学部）
    for m in re.finditer(r'(?:(?:明治|大正|昭和|平成|令和|同)?[0-9一二三四五六七八九十元]+年)?([^\s,、。○〇\(\)（）0-9]{2,10}?)(?<!学)大([^\s,、。○〇\(\)（）0-9]+?(?:学部|研究科))([^\s,、。○〇\(\)（）0-9]{0,15})?', text):
        after_word = m.group(3) if m.group(3) else ""
        if is_job_phrase(after_word):
            continue
        raw_univ = m.group(1).strip() + '大'
        school = clean_school_name(raw_univ)
        fac = m.group(2).strip() if m.group(2) else "不明"
        if school not in ('拡大', '最大', '不明'):
            candidates.append((m.start(), school, fac))

    # 3. 専門学校・高専・高等学校・養護学校など
    for m in re.finditer(r'(?:(?:明治|大正|昭和|平成|令和|同)?[0-9一二三四五六七八九十元]+年)?([^\s,、。○〇\(\)（）0-9]+?(?:専門学校|高専|高等専門学校|高等学校|高校|中学校|中学|養護学校高等部|特別支援学校高等部|養護学校|特別支援学校|盲学校|聾学校|高等部))', text):
        raw_school = m.group(1).strip()
        school = clean_school_name(raw_school)
        candidates.append((m.start(), school, "N/A"))

    # '不明' や '現...' などを除外
    valid_candidates = [c for c in candidates if c[1] not in ("不明", "拡大", "最大") and not c[1].startswith('現')]

    if not valid_candidates:
        return "不明", "不明"

    # 学部が判明している候補を優先
    valid_fac_candidates = [c for c in valid_candidates if c[2] not in ("不明", "N/A")]
    if valid_fac_candidates:
        valid_fac_candidates.sort(key=lambda x: x[0])
        return valid_fac_candidates[0][1], valid_fac_candidates[0][2]

    # 大学候補を優先
    univ_candidates = [c for c in valid_candidates if "大" in c[1]]
    if univ_candidates:
        univ_candidates.sort(key=lambda x: x[0])
        return univ_candidates[0][1], univ_candidates[0][2]

    valid_candidates.sort(key=lambda x: x[0])
    return valid_candidates[0][1], valid_candidates[0][2]

def extract_elections(text):
    """
    当選回数の抽出
    """
    if not text:
        return 1
    text = unicodedata.normalize('NFKC', str(text))
    m = re.search(r'当選\s*([0-9一二三四五六七八九十]+)\s*回', text)
    if m:
        return kanji_to_int(m.group(1))
    m2 = re.search(r'(\d+)', text)
    if m2:
        return int(m2.group(1))
    return 1

def scrape_shugiin(headers, total_count=465, sleep_sec=1.0, limit=None):
    """
    衆議院公式サイトから議員全一覧およびプロフィールを取得
    情報源: https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/1giin.htm ～ 10giin.htm
    """
    list_urls = [f"https://www.shugiin.go.jp/internet/itdb_annai.nsf/html/statics/syu/{i}giin.htm" for i in range(1, 11)]
    
    members = []
    seen_urls = set()
    target_count = min(limit, total_count) if limit else total_count
    
    for list_url in list_urls:
        try:
            time.sleep(sleep_sec)
            res = requests.get(list_url, headers=headers)
            res.encoding = 'cp932'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            for tr in soup.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 5:
                    continue
                
                name_cell = tds[0]
                a_tag = name_cell.find('a')
                if not a_tag or not a_tag.get('href'):
                    continue
                
                prof_relative = a_tag.get('href')
                prof_url = urllib.parse.urljoin(list_url, prof_relative)
                
                if prof_url in seen_urls:
                    continue
                seen_urls.add(prof_url)
                
                raw_name = name_cell.get_text(strip=True).replace('君', '').replace('\u3000', ' ').strip()
                raw_furigana = tds[1].get_text(separator=' ', strip=True).replace('\u3000', ' ').strip()
                party = normalize_party(tds[2].get_text(strip=True), house="衆議院")
                elections_str = tds[4].get_text(strip=True)
                elections = extract_elections(elections_str)
                
                current_num = len(members) + 1
                print(f"[衆議院 {current_num}/{target_count} 取得中] {raw_name} ({party})")
                
                # 詳細プロフィールページへのアクセス
                time.sleep(sleep_sec)
                p_res = requests.get(prof_url, headers=headers)
                p_res.encoding = 'cp932'
                p_soup = BeautifulSoup(p_res.text, 'html.parser')
                
                contents_div = p_soup.find('div', id='contents')
                bio_text = contents_div.get_text() if contents_div else p_soup.get_text()
                
                birth_str = parse_japanese_birthdate(bio_text)
                birthplace = extract_birthplace(bio_text)
                school, faculty = extract_school_and_faculty(bio_text)
                
                members.append({
                    "name": raw_name,
                    "furigana": raw_furigana,
                    "house": "衆議院",
                    "party": party,
                    "elections": elections,
                    "birthdate": birth_str if birth_str else "不明",
                    "birthplace": birthplace,
                    "school": school,
                    "faculty": faculty,
                    "source_url": prof_url
                })
                
                if limit and len(members) >= limit:
                    return members
                    
        except Exception as e:
            print(f"[衆議院エラー] {list_url}: {e}", file=sys.stderr)
            
    return members

def scrape_sangiin(headers, total_count=248, sleep_sec=1.0, limit=None):
    """
    参議院公式サイトから議員全一覧およびプロフィールを取得
    情報源: https://www.sangiin.go.jp/japanese/joho1/kousei/giin/current/giin.htm
    """
    top_url = "https://www.sangiin.go.jp/japanese/joho1/kousei/giin/current/giin.htm"
    members = []
    seen_urls = set()
    target_count = min(limit, total_count) if limit else total_count
    
    try:
        time.sleep(sleep_sec)
        res = requests.get(top_url, headers=headers)
        actual_url = res.url
        if "location.replace" in res.text:
            m = re.search(r'location\.replace\("([^"]+)"\)', res.text)
            if m:
                actual_url = urllib.parse.urljoin(top_url, m.group(1))
                time.sleep(sleep_sec)
                res = requests.get(actual_url, headers=headers)
                
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for tr in soup.find_all('tr'):
            tds = tr.find_all(['td', 'th'])
            if len(tds) < 4:
                continue
                
            a_tag = None
            name_idx = None
            for i, td in enumerate(tds):
                a = td.find('a')
                if a and a.get('href') and ('profile' in a.get('href') or 'giin' in a.get('href')):
                    a_tag = a
                    name_idx = i
                    break
            
            if not a_tag or name_idx is None:
                continue
                
            prof_relative = a_tag.get('href')
            prof_url = urllib.parse.urljoin(actual_url, prof_relative)
            
            if prof_url in seen_urls:
                continue
            seen_urls.add(prof_url)
            
            # 議員一覧ページから氏名・ふりがな・会派名称を取得
            raw_name = tds[name_idx].get_text(strip=True).replace('\u3000', ' ')
            raw_name = re.sub(r'\[.*?\]', '', raw_name).strip()
            
            raw_furigana = tds[name_idx + 1].get_text(separator=' ', strip=True).replace('\u3000', ' ').strip()
            party = normalize_party(tds[name_idx + 2].get_text(strip=True), house="参議院")
            
            current_num = len(members) + 1
            print(f"[参議院 {current_num}/{target_count} 取得中] {raw_name} ({party})")
            
            # 詳細プロフィールページの取得
            time.sleep(sleep_sec)
            p_res = requests.get(prof_url, headers=headers)
            p_res.encoding = 'utf-8'
            p_soup = BeautifulSoup(p_res.text, 'html.parser')
            
            p_div = p_soup.find('div', id='contents') or p_soup.find('div', id='profile-data')
            page_text = p_div.get_text() if p_div else p_soup.get_text()
            
            elections = extract_elections(page_text)
            birth_str = parse_japanese_birthdate(page_text)
            birthplace = extract_birthplace(page_text)
            school, faculty = extract_school_and_faculty(page_text)
            
            members.append({
                "name": raw_name,
                "furigana": raw_furigana,
                "house": "参議院",
                "party": party,
                "elections": elections,
                "birthdate": birth_str if birth_str else "不明",
                "birthplace": birthplace,
                "school": school,
                "faculty": faculty,
                "source_url": prof_url
            })
            
            if limit and len(members) >= limit:
                return members
                
    except Exception as e:
        print(f"[参議院エラー] {top_url}: {e}", file=sys.stderr)
        
    return members

def update_members_by_id(target_id_str, headers):
    """
    指定されたIDの議員データのみを再取得して更新する。
    target_id_str: '001' や '001,005,010' などのID指定文字列
    """
    start_time = datetime.now()
    print(f"=== 国会議員データ個別ID更新 ===")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    raw_ids = [x.strip() for x in re.split(r'[,、\s]+', target_id_str.strip()) if x.strip()]
    target_ids = [f"{int(x):03d}" if x.isdigit() else x for x in raw_ids if x]
    
    if not target_ids:
        print("[エラー] 更新対象のIDが指定されていません。", file=sys.stderr)
        return
        
    print(f"更新対象ID: {', '.join(target_ids)}")
    
    target_files = []
    if os.path.exists('data.json'):
        target_files.append('data.json')
    if os.path.exists('data_full.json'):
        target_files.append('data_full.json')
        
    if not target_files:
        print("[エラー] data.json または data_full.json が見つかりません。", file=sys.stderr)
        return

    updated_total = 0
    
    for json_file in target_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
        except Exception as e:
            print(f"[エラー] {json_file} の読み込み失敗: {e}", file=sys.stderr)
            continue
            
        members = file_data.get('members', [])
        id_map = {m.get('id'): m for m in members if m.get('id')}
        
        file_updated_count = 0
        for tid in target_ids:
            if tid not in id_map:
                continue
                
            m = id_map[tid]
            url = m.get('profile_url') or m.get('source_url')
            if not url:
                print(f"[{json_file}] ID: {tid} ({m.get('name')}) のプロフィールURLがありません。")
                continue
                
            print(f"\n[{json_file}][ID: {tid}] {m.get('name')} ({m.get('house')}・{m.get('party')}) 更新中...")
            print(f"URL: {url}")
            
            try:
                time.sleep(0.5)
                if m.get('house') == '衆議院':
                    res = requests.get(url, headers=headers, timeout=10)
                    res.encoding = 'cp932'
                    soup = BeautifulSoup(res.text, 'html.parser')
                    div = soup.find('div', id='contents')
                    text = div.get_text() if div else soup.get_text()
                    
                    elec = extract_elections(text)
                    bdate = parse_japanese_birthdate(text)
                    bplace = extract_birthplace(text)
                    sch, fac = extract_school_and_faculty(text)
                    
                    m['elections'] = elec
                    m['birthdate'] = bdate if bdate else m.get('birthdate', '不明')
                    m['birthplace'] = bplace
                    m['school'] = sch
                    m['faculty'] = fac
                    m['party'] = normalize_party(m.get('party', ''), house='衆議院')
                else:
                    res = requests.get(url, headers=headers, timeout=10)
                    res.encoding = 'utf-8'
                    soup = BeautifulSoup(res.text, 'html.parser')
                    div = soup.find('div', id='contents') or soup.find('div', id='profile-data')
                    text = div.get_text() if div else soup.get_text()
                    
                    elec = extract_elections(text)
                    bdate = parse_japanese_birthdate(text)
                    bplace = extract_birthplace(text)
                    sch, fac = extract_school_and_faculty(text)
                    
                    m['elections'] = elec
                    m['birthdate'] = bdate if bdate else m.get('birthdate', '不明')
                    m['birthplace'] = bplace
                    m['school'] = sch
                    m['faculty'] = fac
                    m['party'] = normalize_party(m.get('party', ''), house='参議院')
                    
                print(f"  -> 生年月日: {m['birthdate']}")
                print(f"  -> 出身地:   {m['birthplace']}")
                print(f"  -> 出身校:   {m['school']}")
                print(f"  -> 学部名:   {m['faculty']}")
                file_updated_count += 1
            except Exception as e:
                print(f"[エラー] ID: {tid} ({url}) の更新処理失敗: {e}", file=sys.stderr)
                
        if file_updated_count > 0:
            file_data['last_updated'] = datetime.now().isoformat()
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, ensure_ascii=False, indent=2)
                
            js_file = json_file.replace('.json', '.js')
            with open(js_file, 'w', encoding='utf-8') as f:
                f.write("window.DIET_DATA = " + json.dumps(file_data, ensure_ascii=False, indent=2) + ";\n")
                
            updated_total += file_updated_count
            
    end_time = datetime.now()
    elapsed = end_time - start_time
    total_sec = elapsed.total_seconds()
    minutes, seconds = divmod(int(total_sec), 60)
    if minutes > 0:
        duration_str = f"{minutes}分{seconds}秒 ({total_sec:.2f}秒)"
    else:
        duration_str = f"{total_sec:.2f}秒"
        
    print(f"\n" + "=" * 45)
    print(f"[個別更新完了] 指定IDのデータを更新・保存しました。")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"終了日時: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"処理時間: {duration_str}")
    print("=" * 45)

def main():
    parser = argparse.ArgumentParser(description="国会議員データ収集スクリプト（衆議院・参議院公式ウェブサイト）")
    parser.add_argument("-t", "--test", action="store_true", help="テストモード: 衆議院・参議院それぞれ5名ずつのデータを迅速に取得します")
    parser.add_argument("-l", "--limit", type=int, default=None, help="各議院からの取得上限人数（例: 5）")
    parser.add_argument("-i", "--id", type=str, default=None, help="指定したIDの議員データのみを再取得・更新します（例: --id 001 または -i 001,005）")
    parser.add_argument("-r", "--restore", action="store_true", help="退避済みの全件データ（data_full.json / data_full.js）から復元します")
    args = parser.parse_args()

    if args.restore:
        restore_full_data()
        return

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    if args.id:
        update_members_by_id(args.id, headers)
        return

    limit = 5 if args.test else args.limit

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    start_time = datetime.now()
    
    print(f"=== 国会議員データ収集スクリプト ===")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("情報源: 衆議院公式ウェブサイト (https://www.shugiin.go.jp/) および 参議院公式ウェブサイト (https://www.sangiin.go.jp/)")
    
    # テスト実行時、既存の全件データが存在する場合は退避
    if limit:
        backup_existing_full_data()

    print("\n--- 欠員を除いた所属議員数（現員数）の確認中 ---")
    shugiin_total = get_shugiin_total_count(headers)
    sangiin_total = get_sangiin_total_count(headers)
    print(f"衆議院 現員数: {shugiin_total}名 (欠員を除く)")
    print(f"参議院 現員数: {sangiin_total}名 (欠員を除く)")
    
    if limit:
        print(f"※ 取得制限モード: 衆議院・参議院 各{limit}名を取得します。")
    
    print("\n1. 衆議院公式ウェブサイトからのデータ取得中...")
    shugiin_members = scrape_shugiin(headers, total_count=shugiin_total, sleep_sec=1.0, limit=limit)
    print(f"衆議院: {len(shugiin_members)}名のデータを取得完了")
    
    print("\n2. 参議院公式ウェブサイトからのデータ取得中...")
    sangiin_members = scrape_sangiin(headers, total_count=sangiin_total, sleep_sec=1.0, limit=limit)
    print(f"参議院: {len(sangiin_members)}名のデータを取得完了")
    
    all_raw_members = shugiin_members + sangiin_members
    
    # 衆議院 -> 参議院の順、かつふりがなの昇順でソート
    def member_sort_key(m):
        house_order = 0 if m['house'] == '衆議院' else 1
        furi = unicodedata.normalize('NFKC', m.get('furigana', ''))
        furi = re.sub(r'\s+', ' ', furi).strip()
        return (house_order, furi, m.get('name', ''))
        
    all_raw_members.sort(key=member_sort_key)
    
    processed_members = []
    error_logs = []
    
    for idx, m in enumerate(all_raw_members, start=1):
        member_id = f"{idx:03d}"
        if not m['birthdate'] or m['birthdate'] == "不明":
            error_msg = f"[生年月日未取得] {m['house']} {m['name']} (URL: {m['source_url']})"
            print(error_msg, file=sys.stderr)
            error_logs.append(error_msg)
            
        clean_furi = unicodedata.normalize('NFKC', m['furigana'])
        clean_furi = re.sub(r'\s+', ' ', clean_furi).strip()
            
        # 生年月（日）データを保持し、年齢はデータとしては持たない
        processed_members.append({
            "id": member_id,
            "name": m['name'],
            "furigana": clean_furi,
            "house": m['house'],
            "party": m['party'],
            "elections": m['elections'],
            "birthdate": m['birthdate'],
            "birthplace": m['birthplace'],
            "school": m['school'],
            "faculty": m['faculty'],
            "profile_url": m['source_url']
        })
        
    end_time = datetime.now()
    elapsed = end_time - start_time
    total_sec = elapsed.total_seconds()
    minutes, seconds = divmod(int(total_sec), 60)
    if minutes > 0:
        duration_str = f"{minutes}分{seconds}秒 ({total_sec:.2f}秒)"
    else:
        duration_str = f"{total_sec:.2f}秒"
        
    output_data = {
        "last_updated": end_time.isoformat(),
        "sources": [
            "衆議院公式ウェブサイト (https://www.shugiin.go.jp/)",
            "参議院公式ウェブサイト (https://www.sangiin.go.jp/)"
        ],
        "members": processed_members
    }
    
    # 常に data.json / data.js に保存
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    with open('data.js', 'w', encoding='utf-8') as f:
        f.write("window.DIET_DATA = " + json.dumps(output_data, ensure_ascii=False, indent=2) + ";\n")
        
    # 全件取得時（limitなし）は data_full.json / data_full.js としても保存
    if not limit:
        with open('data_full.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        with open('data_full.js', 'w', encoding='utf-8') as f:
            f.write("window.DIET_DATA = " + json.dumps(output_data, ensure_ascii=False, indent=2) + ";\n")
    else:
        # テスト時は data_test.json / data_test.js にも保存
        with open('data_test.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        with open('data_test.js', 'w', encoding='utf-8') as f:
            f.write("window.DIET_DATA = " + json.dumps(output_data, ensure_ascii=False, indent=2) + ";\n")
        
    if error_logs:
        with open('error_logs.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(error_logs))
            
    print(f"\n" + "=" * 45)
    print(f"[完了] データを data.json および data.js に保存しました。（総計: {len(processed_members)}名）")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"終了日時: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"処理時間: {duration_str}")
    print("=" * 45)

if __name__ == "__main__":
    main()
