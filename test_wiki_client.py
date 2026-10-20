# -*- coding: utf-8 -*-
"""
test_wiki_client.py - Wikipedia / Wikidata 二次データソース連携テスト
"""

import sys
import unittest
import wiki_client
import scraper

class TestWikiClient(unittest.TestCase):

    def test_clean_member_name(self):
        self.assertEqual(wiki_client.clean_member_name("逢沢  一郎"), "逢沢一郎")
        self.assertEqual(wiki_client.clean_member_name("青木 ひとみ"), "青木ひとみ")
        self.assertEqual(wiki_client.clean_member_name("　石破　茂　"), "石破茂")

    def test_parse_wiki_birthdate(self):
        # テンプレート形式
        self.assertEqual(wiki_client.parse_wiki_birthdate("{{生年月日と年齢|1954|6|10}}"), "1954年6月10日")
        self.assertEqual(wiki_client.parse_wiki_birthdate("{{生年月日|1963|2|1}}"), "1963年2月1日")
        # 和文形式
        self.assertEqual(wiki_client.parse_wiki_birthdate("[[1978年]][[5月2日]]"), "1978年5月2日")
        self.assertEqual(wiki_client.parse_wiki_birthdate("1981年4月14日"), "1981年4月14日")
        self.assertEqual(wiki_client.parse_wiki_birthdate("1974年12月"), "1974年12月")
        self.assertEqual(wiki_client.parse_wiki_birthdate("1965年"), "1965年")

    def test_strip_wikitext(self):
        raw = "{{JPN}} [[岡山県]][[御津郡]]<ref>注釈</ref>"
        cleaned = wiki_client.strip_wikitext(raw)
        self.assertIn("岡山県", cleaned)
        self.assertNotIn("<ref>", cleaned)
        self.assertNotIn("[[", cleaned)

    def test_get_secondary_member_data(self):
        test_cases = [
            ("逢沢一郎", "衆議院", "1954年6月10日", "岡山県", ["慶應義塾大学"]),
            ("石破茂", "衆議院", "1957年2月4日", "東京都", ["慶應義塾大学"]),
            ("浮島とも子", "衆議院", "1963年2月1日", "東京都", ["東京立正高等学校"]),
            ("小泉進次郎", "衆議院", "1981年4月14日", "神奈川県", ["コロンビア大学", "関東学院大学"])
        ]
        
        for name, house, expected_bdate, expected_pref, expected_schools in test_cases:
            with self.subTest(name=name):
                data = wiki_client.get_secondary_member_data(
                    name=name,
                    house=house,
                    extract_birthplace_fn=scraper.extract_birthplace,
                    extract_school_fn=scraper.extract_school_and_faculty
                )
                self.assertIsNotNone(data, f"Data for {name} should not be None")
                print(f"[TEST] {name} -> bdate: {data.get('birthdate')}, place: {data.get('birthplace')}, school: {data.get('school')}, faculty: {data.get('faculty')}")
                if expected_bdate:
                    self.assertEqual(data.get('birthdate'), expected_bdate)
                if expected_pref:
                    self.assertEqual(data.get('birthplace'), expected_pref)
                if expected_schools:
                    self.assertIn(data.get('school'), expected_schools)

if __name__ == '__main__':
    unittest.main()
