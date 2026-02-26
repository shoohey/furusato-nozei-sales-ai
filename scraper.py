"""ふるさと納税 主要サイト スクレイピングモジュール - 競合掲載数チェック（改良版）"""

import time
import re
import json
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# User-Agent ローテーション（ボット検知回避）
USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
        "Gecko/20100101 Firefox/124.0"
    ),
]

# 主要ふるさと納税サイト定義
SITES = {
    "さとふる": {
        "id": "satofull",
        "url_template": "https://www.satofull.jp/products/list.php?q={query}&cnt=60",
        "base_url": "https://www.satofull.jp",
    },
    "ふるさとチョイス": {
        "id": "furusato_choice",
        "url_template": "https://www.furusato-tax.jp/search?q={query}",
        "base_url": "https://www.furusato-tax.jp",
    },
    "楽天ふるさと納税": {
        "id": "rakuten",
        "url_template": "https://search.rakuten.co.jp/search/mall/{query}/?f=13",
        "base_url": "https://www.rakuten.co.jp",
    },
    "ふるなび": {
        "id": "furunavi",
        "url_template": "https://furunavi.jp/search?keyword={query}",
        "base_url": "https://furunavi.jp",
    },
    "au PAY ふるさと納税": {
        "id": "aupay",
        "url_template": "https://furusato.wowma.jp/search/?q={query}",
        "base_url": "https://furusato.wowma.jp",
    },
}

MAX_RETRIES = 3


def _get_headers(referer: str | None = None) -> dict[str, str]:
    """ブラウザに近いリクエストヘッダーを生成する。"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if referer else "none",
        "Sec-Fetch-User": "?1",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _create_session(base_url: str) -> requests.Session:
    """セッションを作成し、ベースURLに事前アクセスしてクッキーを取得する。"""
    session = requests.Session()
    session.headers.update(_get_headers())
    try:
        session.get(base_url, timeout=10)
    except requests.exceptions.RequestException:
        pass  # クッキー取得失敗は無視して続行
    return session


def search_all_sites(query: str, delay: float = 2.0) -> dict[str, dict]:
    """
    全主要サイトで商品を検索し、各サイトの掲載数を返す。

    Args:
        query: 検索クエリ（例: "帯広市 牛肉"）
        delay: リクエスト間隔（秒）

    Returns:
        dict: サイト名 -> 検索結果
    """
    results = {}
    for i, (site_name, site_config) in enumerate(SITES.items()):
        if i > 0:
            # ランダムなジッターを追加してパターン検知を回避
            jitter = random.uniform(0.5, 1.5)
            time.sleep(delay + jitter)
        results[site_name] = _search_site_with_retry(query, site_name, site_config)
    return results


def _search_site_with_retry(
    query: str, site_name: str, site_config: dict
) -> dict:
    """リトライ付きで個別サイトの検索を実行する。"""
    last_result = None
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            wait = (2 ** attempt) + random.uniform(0.5, 1.5)
            time.sleep(wait)

        result = _search_site(query, site_name, site_config)
        last_result = result

        # 成功した場合はそのまま返す
        if result["error"] is None:
            return result

    return last_result


def _search_site(query: str, site_name: str, site_config: dict) -> dict:
    """個別サイトの検索を実行する。"""
    encoded_query = quote(query, encoding="utf-8")
    url = site_config["url_template"].format(query=encoded_query)
    base_url = site_config["base_url"]

    session = _create_session(base_url)
    # 検索ページ用のヘッダーを更新（RefererをベースURLに設定）
    session.headers.update(_get_headers(referer=base_url))

    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        response.encoding = "utf-8"

        soup = BeautifulSoup(response.text, "html.parser")
        count = _extract_count(soup, response.text, site_config["id"])

        return {
            "count": count,
            "site_name": site_name,
            "search_url": url,
            "error": None,
        }

    except requests.exceptions.Timeout:
        return {
            "count": None,
            "site_name": site_name,
            "search_url": url,
            "error": "タイムアウト",
        }
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "不明"
        return {
            "count": None,
            "site_name": site_name,
            "search_url": url,
            "error": f"HTTPエラー({status})",
        }
    except requests.exceptions.RequestException:
        return {
            "count": None,
            "site_name": site_name,
            "search_url": url,
            "error": "接続エラー",
        }
    except Exception:
        return {
            "count": None,
            "site_name": site_name,
            "search_url": url,
            "error": "解析エラー",
        }
    finally:
        session.close()


def _extract_count(soup: BeautifulSoup, raw_html: str, site_id: str) -> int | None:
    """サイトごとの件数抽出ロジック（多段フォールバック）。"""

    # ===== Phase 1: scriptタグ内の埋め込みJSON から抽出 =====
    count = _extract_count_from_embedded_json(soup)
    if count is not None:
        return count

    # ===== Phase 2: サイト固有のCSSセレクタ =====
    count = _extract_count_from_selectors(soup, site_id)
    if count is not None:
        return count

    # ===== Phase 3: ページ全体のテキストから汎用パターンで抽出 =====
    count = _extract_count_from_text(soup)
    if count is not None:
        return count

    # ===== Phase 4: HTML属性からの抽出 =====
    count = _extract_count_from_attributes(soup)
    if count is not None:
        return count

    return None


def _extract_count_from_embedded_json(soup: BeautifulSoup) -> int | None:
    """scriptタグ内に埋め込まれたJSONデータからカウントを抽出する。"""
    for script in soup.find_all("script"):
        text = script.string or ""
        if not text.strip():
            continue

        # Next.js の __NEXT_DATA__
        if script.get("id") == "__NEXT_DATA__":
            try:
                data = json.loads(text)
                count = _find_count_in_dict(data)
                if count is not None:
                    return count
            except (json.JSONDecodeError, ValueError):
                pass

        # JSON埋め込みパターン（各種フレームワーク）
        json_count_patterns = [
            r'"totalCount"\s*:\s*(\d+)',
            r'"total_count"\s*:\s*(\d+)',
            r'"totalHits"\s*:\s*(\d+)',
            r'"total_hits"\s*:\s*(\d+)',
            r'"hitCount"\s*:\s*(\d+)',
            r'"hit_count"\s*:\s*(\d+)',
            r'"numFound"\s*:\s*(\d+)',
            r'"resultCount"\s*:\s*(\d+)',
            r'"result_count"\s*:\s*(\d+)',
            r'"searchCount"\s*:\s*(\d+)',
            r'"itemCount"\s*:\s*(\d+)',
            r'"item_count"\s*:\s*(\d+)',
            r'"nbHits"\s*:\s*(\d+)',
            r'"total"\s*:\s*(\d+)',
        ]
        for pattern in json_count_patterns:
            m = re.search(pattern, text)
            if m:
                count = int(m.group(1))
                if 0 < count <= 100000:
                    return count

    return None


def _find_count_in_dict(data: dict | list, depth: int = 0) -> int | None:
    """ネストされた辞書/リストからカウント系のキーを探す（深さ制限付き）。"""
    if depth > 5:
        return None

    count_keys = {
        "totalCount", "total_count", "totalHits", "total_hits",
        "hitCount", "hit_count", "numFound", "resultCount",
        "result_count", "searchCount", "itemCount", "item_count",
        "nbHits",
    }

    if isinstance(data, dict):
        for key, value in data.items():
            if key in count_keys and isinstance(value, (int, float)):
                v = int(value)
                if 0 < v <= 100000:
                    return v
            if isinstance(value, (dict, list)):
                result = _find_count_in_dict(value, depth + 1)
                if result is not None:
                    return result
    elif isinstance(data, list):
        for item in data[:10]:  # リストは先頭10件まで
            if isinstance(item, (dict, list)):
                result = _find_count_in_dict(item, depth + 1)
                if result is not None:
                    return result

    return None


def _extract_count_from_selectors(soup: BeautifulSoup, site_id: str) -> int | None:
    """サイト固有のCSSセレクタでカウントを抽出する。"""
    selector_map = {
        "satofull": [
            ".num", ".result-count", ".search-result-count",
            ".product-count", ".item-count", ".total-num",
            "[data-count]", ".list-count",
            "#search-result-count", ".search-result-num",
        ],
        "furusato_choice": [
            ".resultCount", ".search-result-num", ".total",
            ".result-count", ".search-count", ".hit-count",
            "[data-total]", ".search-result-count",
            ".p-search-result__count", ".c-count",
        ],
        "rakuten": [
            ".search-count", ".result-count-num", "span.total",
            ".item-count", "._1Gstb", ".searchCount",
            "[data-ratid='srp_count']",
            ".dui-container .count",
            "#s_result_header_footer .number",
        ],
        "furunavi": [
            ".search-result-count", ".total-count", ".result-num",
            ".search-count", ".item-count", ".product-count",
            "[data-search-count]", ".search-hit-count",
            ".p-search__count", ".result-count",
        ],
        "aupay": [
            ".result-count", ".search-num", ".total",
            ".search-result-count", ".item-count",
            "[data-count]", ".search-count",
            ".c-search-result__count",
        ],
    }

    selectors = selector_map.get(site_id, [])
    for selector in selectors:
        try:
            elem = soup.select_one(selector)
            if elem:
                # data属性にカウントがある場合
                for attr in ["data-count", "data-total", "data-search-count"]:
                    val = elem.get(attr)
                    if val:
                        try:
                            return int(val.replace(",", ""))
                        except ValueError:
                            pass
                # テキストから数値を抽出
                match = re.search(r"([\d,]+)", elem.get_text())
                if match:
                    count = int(match.group(1).replace(",", ""))
                    if 0 < count <= 100000:
                        return count
        except Exception:
            continue

    return None


def _extract_count_from_text(soup: BeautifulSoup) -> int | None:
    """ページ全体のテキストから汎用パターンで件数を抽出する。"""
    text = soup.get_text()

    patterns = [
        r"([\d,]+)\s*件\s*(?:の|が|を|見つかり|ヒット|表示)",
        r"検索結果\s*[:：]?\s*([\d,]+)\s*件",
        r"全\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件\s*中",
        r"該当\s*([\d,]+)\s*件",
        r"([\d,]+)\s*品",
        r"([\d,]+)\s*件\s*の\s*(?:返礼品|お礼の品|商品|寄附)",
        r"(?:返礼品|お礼の品|商品)\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            count = int(match.group(1).replace(",", ""))
            if 0 < count <= 100000:
                return count

    return None


def _extract_count_from_attributes(soup: BeautifulSoup) -> int | None:
    """HTML要素のdata属性やmetaタグからカウントを抽出する。"""
    # data属性からの抽出
    count_attrs = [
        "data-total-count", "data-count", "data-total",
        "data-search-count", "data-hit-count", "data-result-count",
    ]
    for attr in count_attrs:
        elem = soup.find(attrs={attr: True})
        if elem:
            try:
                count = int(elem[attr].replace(",", ""))
                if 0 < count <= 100000:
                    return count
            except (ValueError, KeyError):
                pass

    # metaタグからの抽出
    for meta in soup.find_all("meta"):
        name = meta.get("name", "") or meta.get("property", "")
        content = meta.get("content", "")
        if any(k in name.lower() for k in ["totalresults", "total-results", "count"]):
            try:
                return int(content.replace(",", ""))
            except ValueError:
                pass

    return None


def search_product_all_sites(
    municipality: str,
    product_name: str,
    delay: float = 2.0,
) -> dict[str, dict]:
    """
    1つの商品について全サイトで検索する。

    Args:
        municipality: 市区町村名
        product_name: 商品名
        delay: リクエスト間隔（秒）

    Returns:
        dict: サイト名 -> 検索結果
    """
    query = f"{municipality} {product_name}"
    return search_all_sites(query, delay=delay)


def aggregate_counts(site_results: dict[str, dict]) -> dict:
    """
    全サイトの検索結果を集計する。

    Returns:
        dict: {
            "total_count": int or None,  # 全サイト合計
            "site_counts": dict,  # サイトごとの件数
            "searched_sites": int,  # 検索成功サイト数
            "failed_sites": int,  # 検索失敗サイト数
            "details": dict,  # 各サイトの詳細
        }
    """
    total = 0
    site_counts = {}
    searched = 0
    failed = 0
    has_any_count = False

    for site_name, result in site_results.items():
        count = result.get("count")
        if count is not None:
            total += count
            site_counts[site_name] = count
            searched += 1
            has_any_count = True
        else:
            site_counts[site_name] = None
            if result.get("error"):
                failed += 1

    return {
        "total_count": total if has_any_count else None,
        "site_counts": site_counts,
        "searched_sites": searched,
        "failed_sites": failed,
        "details": site_results,
    }


def get_site_names() -> list[str]:
    """対応サイト名のリストを返す。"""
    return list(SITES.keys())
