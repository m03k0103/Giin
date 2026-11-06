# parsers.py - 議員属性抽出・正規化パーサーおよび辞書モジュール
import re
import unicodedata
from datetime import datetime

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
