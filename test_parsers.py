# test_parsers.py - パーサー・正規化モジュールの単体回帰テストスイート
import unittest
from parsers import (
    kanji_to_int,
    parse_japanese_birthdate,
    extract_birthplace,
    normalize_party,
    clean_school_name,
    extract_school_and_faculty,
    extract_elections,
    is_job_phrase
)

class TestKanjiToInt(unittest.TestCase):
    def test_four_digit_kanji(self):
        self.assertEqual(kanji_to_int('一九八八'), 1988)
        self.assertEqual(kanji_to_int('二〇〇〇'), 2000)
        self.assertEqual(kanji_to_int('一九六〇'), 1960)
        self.assertEqual(kanji_to_int('一九四五'), 1945)

    def test_decimal_kanji(self):
        self.assertEqual(kanji_to_int('十'), 10)
        self.assertEqual(kanji_to_int('十二'), 12)
        self.assertEqual(kanji_to_int('二十'), 20)
        self.assertEqual(kanji_to_int('二十三'), 23)
        self.assertEqual(kanji_to_int('三十'), 30)
        self.assertEqual(kanji_to_int('四十五'), 45)

    def test_single_and_zenkaku(self):
        self.assertEqual(kanji_to_int('〇'), 0)
        self.assertEqual(kanji_to_int('七'), 7)
        self.assertEqual(kanji_to_int('５'), 5)
        self.assertEqual(kanji_to_int('１２'), 12)
        self.assertEqual(kanji_to_int('42'), 42)

    def test_empty_and_none(self):
        self.assertEqual(kanji_to_int(''), 0)
        self.assertEqual(kanji_to_int(None), 0)


class TestParseJapaneseBirthdate(unittest.TestCase):
    def test_wareki_full(self):
        self.assertEqual(parse_japanese_birthdate('昭和45年5月10日生まれ'), '1970年5月10日')
        self.assertEqual(parse_japanese_birthdate('平成2年1月1日生まれ'), '1990年1月1日')
        self.assertEqual(parse_japanese_birthdate('平成12年3月15日生'), '2000年3月15日')

    def test_wareki_month_or_year_only(self):
        self.assertEqual(parse_japanese_birthdate('昭和55年3月生'), '1980年3月')
        self.assertEqual(parse_japanese_birthdate('昭和40年生まれ'), '1965年')

    def test_seireki(self):
        self.assertEqual(parse_japanese_birthdate('1970年5月10日生'), '1970年5月10日')
        self.assertEqual(parse_japanese_birthdate('1985年12月生'), '1985年12月')
        self.assertEqual(parse_japanese_birthdate('1960年生まれ'), '1960年')

    def test_kanji_numerals(self):
        self.assertEqual(parse_japanese_birthdate('昭和四十五年五月十日生'), '1970年5月10日')
        self.assertEqual(parse_japanese_birthdate('一九八八年三月五日生'), '1988年3月5日')

    def test_unknown(self):
        self.assertEqual(parse_japanese_birthdate(''), '不明')
        self.assertEqual(parse_japanese_birthdate(None), '不明')
        self.assertEqual(parse_japanese_birthdate('生年月日なし'), '不明')


class TestExtractBirthplace(unittest.TestCase):
    def test_direct_prefix(self):
        self.assertEqual(extract_birthplace('出身地: 東京都千代田区'), '東京都')
        self.assertEqual(extract_birthplace('出身地: 大阪府大阪市'), '大阪府')
        self.assertEqual(extract_birthplace('出生地: 北海道札幌市'), '北海道')

    def test_city_to_pref(self):
        self.assertEqual(extract_birthplace('神奈川県横浜で生まれ、育つ'), '神奈川県')
        self.assertEqual(extract_birthplace('札幌で生まれ育つ'), '北海道')
        self.assertEqual(extract_birthplace('福岡県久留米市出身'), '福岡県')

    def test_pref_base_omission(self):
        self.assertEqual(extract_birthplace('東京に生まれ、幼少期を過ごす'), '東京都')
        self.assertEqual(extract_birthplace('熊本誕生。'), '熊本県')
        self.assertEqual(extract_birthplace('大阪出身、大学進学に伴い上京'), '大阪府')

    def test_foreign(self):
        self.assertEqual(extract_birthplace('台湾台北市生まれ'), '外国')
        self.assertEqual(extract_birthplace('ブラジル・サンパウロ出身'), '外国')

    def test_unknown(self):
        self.assertEqual(extract_birthplace(''), '不明')
        self.assertEqual(extract_birthplace('詳細な生い立ちは非公表'), '不明')


class TestNormalizeParty(unittest.TestCase):
    def test_party_mapping(self):
        self.assertEqual(normalize_party('みら'), 'みらい')
        self.assertEqual(normalize_party('民主'), '国民')
        self.assertEqual(normalize_party('い党'), 'いのち')
        self.assertEqual(normalize_party('無'), '無所属')
        self.assertEqual(normalize_party('自民'), '自民')
        self.assertEqual(normalize_party('公明'), '公明')


class TestSchoolAndFaculty(unittest.TestCase):
    def test_clean_school_name(self):
        self.assertEqual(clean_school_name('東大'), '東京大学')
        self.assertEqual(clean_school_name('慶大'), '慶應義塾大学')
        self.assertEqual(clean_school_name('私立早稲田大学'), '早稲田大学')

    def test_extract_old_school_names(self):
        school, faculty = extract_school_and_faculty('城西歯科大学(現明海大学)卒業')
        self.assertEqual(school, '城西歯科大学')

        school2, faculty2 = extract_school_and_faculty('大阪外国語大学(現大阪大学外国語学部)卒業')
        self.assertEqual(school2, '大阪外国語大学')
        self.assertEqual(faculty2, '外国語学部')

    def test_high_school_faculty_na(self):
        school, faculty = extract_school_and_faculty('都立日比谷高校卒業')
        self.assertEqual(school, '都立日比谷高校')
        self.assertEqual(faculty, 'N/A')

    def test_university_and_faculty(self):
        school, faculty = extract_school_and_faculty('東京大学法学部卒業')
        self.assertEqual(school, '東京大学')
        self.assertEqual(faculty, '法学部')

    def test_job_phrase_exclusion(self):
        self.assertTrue(is_job_phrase('名誉教授'))
        self.assertTrue(is_job_phrase('特命教授'))
        self.assertTrue(is_job_phrase('客員教授'))
        self.assertTrue(is_job_phrase('教鞭'))
        
        # 職歴記述（客員教授）のみのテキストの場合、学歴として拾われないこと
        school, faculty = extract_school_and_faculty('早稲田大学大学院客員教授を務める')
        self.assertEqual(school, '不明')


class TestExtractElections(unittest.TestCase):
    def test_elections_count(self):
        self.assertEqual(extract_elections('当選5回'), 5)
        self.assertEqual(extract_elections('衆院当選3回、参院1回'), 3)
        self.assertEqual(extract_elections('新人議員（1回）'), 1)
        self.assertEqual(extract_elections('回数未記載'), 1)

if __name__ == '__main__':
    unittest.main()
