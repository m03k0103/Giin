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
import wiki_client

# GLOBAL_RULES.md §4 に準拠した標準ブラウザヘッダー (Chrome 128相当)
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
    'Sec-Ch-Ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Upgrade-Insecure-Requests': '1'
}


from parsers import (
    KANJI_NUMS, kanji_to_int, parse_japanese_birthdate,
    PREFECTURES, FOREIGN_COUNTRIES, CITY_TO_PREF, PREF_BASE_MAP,
    UNIV_ABBR_MAP, clean_school_name, extract_birthplace,
    normalize_party, is_job_phrase, extract_school_and_faculty, extract_elections
)
from storage import (
    DATA_JS_PATH, DATA_FULL_PATH, DATA_TEST_PATH,
    load_diet_data, atomic_save_diet_data,
    backup_existing_full_data, restore_full_data
)

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

def update_members_by_id(target_id_str, headers=None):
    """
    指定されたIDの議員データのみを再取得して更新する。
    target_id_str: '001' や '001,005,010' などのID指定文字列
    """
    if headers is None:
        headers = DEFAULT_HEADERS
        
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
    if os.path.exists('data.js'):
        target_files.append('data.js')
    if os.path.exists('data_full.js'):
        target_files.append('data_full.js')
        
    if not target_files:
        print("[エラー] data.js または data_full.js が見つかりません。", file=sys.stderr)
        return

    updated_total = 0
    
    for js_file in target_files:
        file_data = load_diet_data(js_file)
        if not file_data:
            print(f"[エラー] {js_file} の読み込み失敗", file=sys.stderr)
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
                print(f"[{js_file}] ID: {tid} ({m.get('name')}) のプロフィールURLがありません。")
                continue
                
            lock_label = ""
            print(f"\n[{js_file}][ID: {tid}] {m.get('name')} ({m.get('house')}・{m.get('party')}){lock_label} 更新中...")
            print(f"URL: {url}")
            
            try:
                time.sleep(1.0)
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
                # 二次データソース（Wikipedia / Wikidata）フォールバック
                if not bdate or bplace == '不明' or sch == '不明':
                    try:
                        wdata = wiki_client.get_secondary_member_data(
                            m.get('name'),
                            house=m.get('house'),
                            extract_birthplace_fn=extract_birthplace,
                            extract_school_fn=extract_school_and_faculty
                        )
                        if wdata:
                            if not bdate and wdata.get('birthdate'):
                                m['birthdate'] = wdata['birthdate']
                                print(f"  -> [Wikipedia補完] 生年月日: {m['birthdate']}")
                            if bplace == '不明' and wdata.get('birthplace') and wdata['birthplace'] != '不明':
                                m['birthplace'] = wdata['birthplace']
                                print(f"  -> [Wikipedia補完] 出身地:   {m['birthplace']}")
                            if sch == '不明' and wdata.get('school') and wdata['school'] != '不明':
                                m['school'] = wdata['school']
                                m['faculty'] = wdata.get('faculty', 'N/A')
                                print(f"  -> [Wikipedia補完] 出身校:   {m['school']} ({m['faculty']})")
                            m['secondary_source'] = wdata.get('source', 'wikipedia')
                    except Exception as we:
                        pass
                file_updated_count += 1

            except Exception as e:
                print(f"[エラー] ID: {tid} ({url}) の更新処理失敗: {e}", file=sys.stderr)
                
        if file_updated_count > 0:
            file_data['last_updated'] = datetime.now().isoformat()
            atomic_save_diet_data(js_file, file_data)
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


def enrich_members_with_wiki(target_ids=None):
    """
    data.js 内の「不明」属性を持つ議員に対し、Wikipedia / Wikidata から安全に補完
    """
    filepath = 'data.js'
    file_data = load_diet_data(filepath)
    if not file_data:
        print("[エラー] data.js が読み込めません。", file=sys.stderr)
        return
        
    members = file_data.get('members', [])
    updated_count = 0
    start_time = datetime.now()
    
    print("=== Wikipedia / Wikidata による欠損属性の補完（--wiki-enrich） ===")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    target_set = set(target_ids) if target_ids else None
    
    for m in members:
        mid = m.get('id')
        if target_set and mid not in target_set:
            continue
            
            
        need_bdate = not m.get('birthdate') or m.get('birthdate') == '不明'
        need_bdate_sub = bool(m.get('birthdate') and not re.search(r'\d+年\d+月\d+日', m.get('birthdate')))
        need_bplace = not m.get('birthplace') or m.get('birthplace') == '不明'
        need_school = not m.get('school') or m.get('school') == '不明'
        
        if not (need_bdate or need_bdate_sub or need_bplace or need_school):
            continue
            
        name = m.get('name')
        house = m.get('house')
        print(f"[ID: {mid}] {name} ({house}) の補完データを Wikipedia から照会中...")
        time.sleep(0.5)
        
        try:
            wdata = wiki_client.get_secondary_member_data(
                name=name,
                house=house,
                extract_birthplace_fn=extract_birthplace,
                extract_school_fn=extract_school_and_faculty
            )
            if not wdata:
                print(f"  -> Wikipedia/Wikidata に該当情報なし")
                continue
                
            field_updated = False
            updated_fields = list(m.get('secondary_fields', []))
            if need_bdate and wdata.get('birthdate'):
                m['birthdate'] = wdata['birthdate']
                print(f"  -> [生年月日補完] {m['birthdate']}")
                field_updated = True
                if 'birthdate' not in updated_fields:
                    updated_fields.append('birthdate')
            elif need_bdate_sub and wdata.get('birthdate'):
                new_bdate, sec_type = wiki_client.validate_and_extract_birthdate_supplement(m.get('birthdate'), wdata.get('birthdate'))
                if new_bdate:
                    m['birthdate'] = new_bdate
                    print(f"  -> [生年月日の月日補完] {m['birthdate']} ({sec_type})")
                    field_updated = True
                    if sec_type not in updated_fields:
                        updated_fields.append(sec_type)
                
            if need_bplace and wdata.get('birthplace') and wdata['birthplace'] != '不明':
                m['birthplace'] = wdata['birthplace']
                print(f"  -> [出身地補完]   {m['birthplace']}")
                field_updated = True
                if 'birthplace' not in updated_fields:
                    updated_fields.append('birthplace')
                
            if need_school and wdata.get('school') and wdata['school'] != '不明':
                m['school'] = wdata['school']
                m['faculty'] = wdata.get('faculty', 'N/A')
                print(f"  -> [出身校補完]   {m['school']} ({m['faculty']})")
                field_updated = True
                if 'school' not in updated_fields:
                    updated_fields.append('school')
                
            if field_updated:
                m['secondary_source'] = wdata.get('source', 'wikipedia')
                m['secondary_fields'] = updated_fields
                updated_count += 1
        except Exception as e:
            print(f"  -> 照会エラー: {e}", file=sys.stderr)
            
    if updated_count > 0:
        file_data['last_updated'] = datetime.now().isoformat()
        sources = file_data.get('sources', [])
        wiki_source = "Wikipedia / Wikidata (https://ja.wikipedia.org/, https://www.wikidata.org/)"
        if wiki_source not in sources:
            sources.append(wiki_source)
        file_data['sources'] = sources
        
        atomic_save_diet_data('data.js', file_data)
        if os.path.exists('data_full.js'):
            atomic_save_diet_data('data_full.js', file_data)
            
    end_time = datetime.now()
    duration = end_time - start_time
    print(f"\n[補完完了] {updated_count}名の属性を Wikipedia / Wikidata から補完しました。（処理時間: {duration.total_seconds():.2f}秒）")




def enrich_members_gender(filepath='data.js'):
    """
    data.js 内の全議員に対し、Wikidata / Wikipedia から性別（男性 / 女性）を取得して付与・保存
    """
    file_data = load_diet_data(filepath)
    if not file_data or 'members' not in file_data:
        print(f"エラー: {filepath} が見つからないか、有効な議員データが含まれていません。", file=sys.stderr)
        return

    members = file_data['members']
    start_time = datetime.now()
    print(f"=== Wikipedia / Wikidata による性別情報の補完（--enrich-gender） ===")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"対象議員数: {len(members)}名")

    gender_map = wiki_client.resolve_all_members_gender(members)
    
    male_count = 0
    female_count = 0
    updated_count = 0

    for m in members:
        mid = str(m.get('id', ''))
        gender = gender_map.get(mid, '男性')
        m['gender'] = gender
        if gender == '男性':
            male_count += 1
        elif gender == '女性':
            female_count += 1
            
        sec = list(m.get('secondary_fields', []))
        if 'gender' not in sec:
            sec.append('gender')
        m['secondary_fields'] = sec
        updated_count += 1

    file_data['last_updated'] = datetime.now().isoformat()
    sources = file_data.get('sources', [])
    wiki_source = "Wikipedia / Wikidata (https://ja.wikipedia.org/, https://www.wikidata.org/)"
    if wiki_source not in sources:
        sources.append(wiki_source)
    file_data['sources'] = sources

    atomic_save_diet_data(filepath, file_data)
    if os.path.exists('data_full.js'):
        atomic_save_diet_data('data_full.js', file_data)

    end_time = datetime.now()
    duration = end_time - start_time
    print(f"\n[性別補完完了] 全{updated_count}名の性別を付与しました。（男性: {male_count}名, 女性: {female_count}名 / 処理時間: {duration.total_seconds():.2f}秒）")

def main():
    parser = argparse.ArgumentParser(description="国会議員データ収集スクリプト（衆議院・参議院公式ウェブサイト）")
    parser.add_argument("-t", "--test", action="store_true", help="テストモード: 衆議院・参議院それぞれ5名ずつのデータを迅速に取得します")
    parser.add_argument("-l", "--limit", type=int, default=None, help="各議院からの取得上限人数（例: 5）")
    parser.add_argument("-i", "--id", type=str, default=None, help="指定したIDの議員データのみを再取得・更新します（例: --id 001 または -i 001,005）")
    parser.add_argument("-r", "--restore", action="store_true", help="退避済みの全件データ（data_full.js）から復元します")
    parser.add_argument("--wiki-enrich", action="store_true", help="既存の data.js 内で出身地や出身校が「不明」の議員に対し、Wikipedia/Wikidata から補完・更新を実行します")
    parser.add_argument("--enrich-gender", action="store_true", help="全議員に対し、Wikidata/Wikipedia から性別（男性/女性）を取得・補完します")
    parser.add_argument("--use-wiki", action="store_true", help="個別更新(-i)や欠損時に Wikipedia/Wikidata を優先・併用して補完します")
    args = parser.parse_args()

    if args.restore:
        restore_full_data()
        return

    if args.enrich_gender:
        enrich_members_gender()
        return

    if args.wiki_enrich:
        target_ids = None
        if args.id:
            raw_ids = [x.strip() for x in re.split(r'[,、\s]+', args.id.strip()) if x.strip()]
            target_ids = [f"{int(x):03d}" if x.isdigit() else x for x in raw_ids if x]
        enrich_members_with_wiki(target_ids=target_ids)
        return

    headers = DEFAULT_HEADERS

    if args.id:
        update_members_by_id(args.id, headers)
        return

    limit = 5 if args.test else args.limit
    
    start_time = datetime.now()
    
    print(f"=== 国会議員データ収集スクリプト ===")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("情報源: 衆議院公式ウェブサイト (https://www.shugiin.go.jp/) および 参議院公式ウェブサイト (https://www.sangiin.go.jp/)")
    
    # 既存データのロード（二次ソース補完属性のインテリジェントマージ用）
    existing_data = load_diet_data('data.js') or {}
    existing_map = {}
    for em in existing_data.get('members', []):
        if em.get('id'):
            existing_map[em.get('id')] = em
        if em.get('house') and em.get('name'):
            existing_map[(em.get('house'), em.get('name'))] = em

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
            
        # 既存データとのインテリジェントマージ（二次ソース補完属性の安全継承）
        key = (m['house'], m['name'])
        prev_m = existing_map.get(member_id) or existing_map.get(key)
        
        final_elections = m['elections']
        final_birthdate = m['birthdate']
        final_birthplace = m['birthplace']
        final_school = m['school']
        final_faculty = m['faculty']
        final_gender = '男性'
        secondary_fields = []
        secondary_source = None
        
        if prev_m:
            prev_sec = prev_m.get('secondary_fields', [])
            
            # 1. 生年月日の月日補完（Wikipedia由来）の継承
            if any(k in prev_sec for k in ['birthdate_day', 'birthdate_month_day', 'birthdate']):
                prev_b = prev_m.get('birthdate')
                if prev_b and final_birthdate and prev_b.startswith(final_birthdate):
                    final_birthdate = prev_b
                    for s_tag in ['birthdate_day', 'birthdate_month_day', 'birthdate']:
                        if s_tag in prev_sec and s_tag not in secondary_fields:
                            secondary_fields.append(s_tag)
                            
            # 2. 出身地補完（Wikipedia由来）の継承
            if 'birthplace' in prev_sec and final_birthplace == '不明' and prev_m.get('birthplace') != '不明':
                final_birthplace = prev_m.get('birthplace')
                if 'birthplace' not in secondary_fields:
                    secondary_fields.append('birthplace')
                    
            # 3. 出身校・学部名補完（Wikipedia由来）の継承
            if 'school' in prev_sec and final_school == '不明' and prev_m.get('school') != '不明':
                final_school = prev_m.get('school')
                final_faculty = prev_m.get('faculty', '-')
                if 'school' not in secondary_fields:
                    secondary_fields.append('school')
                    
            # 4. 性別属性（Wikipedia/Wikidata由来）の継承
            if prev_m.get('gender'):
                final_gender = prev_m.get('gender')
            if 'gender' in prev_sec or final_gender:
                if 'gender' not in secondary_fields:
                    secondary_fields.append('gender')
                    
            if prev_m.get('secondary_source'):
                secondary_source = prev_m.get('secondary_source')
        else:
            # 新規議員の場合も性別タグを設定
            secondary_fields.append('gender')
            secondary_source = 'wikipedia'
            
        record = {
            "id": member_id,
            "name": m['name'],
            "furigana": clean_furi,
            "house": m['house'],
            "party": m['party'],
            "gender": final_gender,
            "elections": final_elections,
            "birthdate": final_birthdate,
            "birthplace": final_birthplace,
            "school": final_school,
            "faculty": final_faculty,
            "profile_url": m['source_url']
        }
        if secondary_fields:
            record["secondary_source"] = secondary_source or "wikipedia"
            record["secondary_fields"] = secondary_fields
            
        processed_members.append(record)
        
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
    
    # data.js にアトミック保存
    atomic_save_diet_data('data.js', output_data)
        
    # 全件取得時（limitなし）は data_full.js としても保存
    if not limit:
        atomic_save_diet_data('data_full.js', output_data)
    else:
        # テスト時は data_test.js に保存
        atomic_save_diet_data('data_test.js', output_data)
        
    if error_logs:
        with open('error_logs.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(error_logs))
            
    print(f"\n" + "=" * 45)
    print(f"[完了] データを data.js にアトミック保存しました。（総計: {len(processed_members)}名 / インテリジェントマージ適用）")
    print(f"開始日時: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"終了日時: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"処理時間: {duration_str}")
    print("=" * 45)

if __name__ == "__main__":
    main()
