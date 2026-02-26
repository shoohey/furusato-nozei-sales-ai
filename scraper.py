"""ふるさと納税 主要サイト スクレイピングモジュール - 競合掲載数チェック（実動作版）"""

import time
import re
import json
import random
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

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
]

# ==============================================================
# サイト定義: 実際の動作確認済みURL・抽出ロジック
# ==============================================================
SITES = {
    "さとふる": {
        "id": "satofull",
        "url_template": "https://www.satofull.jp/products/list.php?q={query}",
        "base_url": "https://www.satofull.jp",
        "timeout": 45,  # ページが大きいため長めに
    },
    "ふるさとチョイス": {
        "id": "furusato_choice",
        "url_template": "https://www.furusato-tax.jp/search?q={query}",
        "base_url": "https://www.furusato-tax.jp",
        "timeout": 20,
    },
    "楽天ふるさと納税": {
        "id": "rakuten",
        # tag=1000811 でふるさと納税カテゴリに絞り込み（f=13は効かない）
        "url_template": "https://search.rakuten.co.jp/search/mall/{query}/?tag=1000811",
        "base_url": "https://www.rakuten.co.jp",
        "timeout": 20,
    },
    "ふるなび": {
        "id": "furunavi",
        # /Product/Search が正しいパス（SPAのためJS描画、件数取得は限定的）
        "url_template": "https://furunavi.jp/Product/Search?keyword={query}",
        "base_url": "https://furunavi.jp",
        "timeout": 20,
        "spa": True,  # SPA: 件数取得が困難なサイト
    },
    "au PAY ふるさと納税": {
        "id": "aupay",
        # search_word パラメータが正しい（q= だと404になる）
        "url_template": "https://furusato.wowma.jp/products/list.php?search_word={query}",
        "base_url": "https://furusato.wowma.jp",
        "timeout": 20,
    },
}

MAX_RETRIES = 2


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def search_all_sites(query: str, delay: float = 2.0) -> dict[str, dict]:
    """全主要サイトで商品を検索し、各サイトの掲載数を返す。"""
    results = {}
    for i, (site_name, site_config) in enumerate(SITES.items()):
        if i > 0:
            time.sleep(delay + random.uniform(0.5, 1.5))
        results[site_name] = _search_site_with_retry(query, site_name, site_config)
    return results


def _search_site_with_retry(query: str, site_name: str, site_config: dict) -> dict:
    """リトライ付きで検索を実行。"""
    last_result = None
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            time.sleep(2 + random.uniform(0.5, 1.5))
        result = _search_site(query, site_name, site_config)
        last_result = result
        if result["error"] is None:
            return result
    return last_result


def _search_site(query: str, site_name: str, site_config: dict) -> dict:
    """個別サイトの検索を実行する。"""
    encoded_query = quote(query, encoding="utf-8")
    url = site_config["url_template"].format(query=encoded_query)
    timeout = site_config.get("timeout", 20)
    site_id = site_config["id"]

    try:
        response = requests.get(url, headers=_get_headers(), timeout=timeout)
        response.raise_for_status()
        response.encoding = "utf-8"

        # 404ページへのリダイレクト検知
        if "404" in response.url and "404" not in url:
            return _result(None, site_name, url, "ページが見つかりません")

        count = _extract_count_for_site(response.text, site_id)

        return _result(count, site_name, url, None)

    except requests.exceptions.Timeout:
        return _result(None, site_name, url, "タイムアウト")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return _result(None, site_name, url, f"HTTPエラー({code})")
    except requests.exceptions.RequestException:
        return _result(None, site_name, url, "接続エラー")
    except Exception:
        return _result(None, site_name, url, "解析エラー")


def _result(count, site_name, url, error):
    return {"count": count, "site_name": site_name, "search_url": url, "error": error}


# ==============================================================
# サイトごとの件数抽出（実際のHTML構造に基づく）
# ==============================================================

def _extract_count_for_site(html: str, site_id: str) -> int | None:
    """サイトIDに応じた専用ロジックで件数を抽出する。"""
    if site_id == "satofull":
        return _extract_satofull(html)
    elif site_id == "furusato_choice":
        return _extract_furusato_choice(html)
    elif site_id == "rakuten":
        return _extract_rakuten(html)
    elif site_id == "furunavi":
        return _extract_furunavi(html)
    elif site_id == "aupay":
        return _extract_aupay(html)
    return None


def _extract_satofull(html: str) -> int | None:
    """さとふる: 複数パターンで件数を抽出。"""
    soup = BeautifulSoup(html, "html.parser")

    # パターン1: aria-label属性から「（1,129）件を表示」
    for elem in soup.find_all(attrs={"aria-label": True}):
        label = elem.get("aria-label", "")
        m = re.search(r"[(（]([\d,]+)[)）]\s*件", label)
        if m:
            count = int(m.group(1).replace(",", ""))
            if count > 0:
                return count

    # パターン2: get_text()で「結果を見る（1,129件）」
    text = soup.get_text()
    m = re.search(r"結果を見る[（(]([\d,]+)件[）)]", text)
    if m:
        return int(m.group(1).replace(",", ""))

    # パターン3: 「X,XXX 件」（60件=1ページ表示数より大きいもの優先）
    for m in re.finditer(r"([\d,]+)\s*件", text):
        count = int(m.group(1).replace(",", ""))
        if count > 60:
            return count

    return None


def _extract_furusato_choice(html: str) -> int | None:
    """ふるさとチョイス: テキスト/JSON内の件数パターンから抽出。"""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    # テキストパターン
    patterns = [
        r"([\d,]+)\s*件\s*(?:の|が|を|見つかり|ヒット)",
        r"検索結果\s*[:：]?\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件\s*中",
        r"全\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            count = int(m.group(1).replace(",", ""))
            if 0 < count <= 100000:
                return count

    # script内JSON
    for pattern in [r'"totalCount"\s*:\s*(\d+)', r'"total"\s*:\s*(\d+)']:
        m = re.search(pattern, html)
        if m:
            count = int(m.group(1))
            if 0 < count <= 100000:
                return count

    return None


def _extract_rakuten(html: str) -> int | None:
    """楽天: HTML内の numFound JSON値から抽出。"""
    # 楽天はSSRでnumFoundをHTMLに埋め込んでいる
    m = re.search(r'"numFound"\s*:\s*(\d+)', html)
    if m:
        count = int(m.group(1))
        if count <= 100000:
            return count

    # フォールバック: テキストから件数
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    m = re.search(r"([\d,]+)\s*件", text)
    if m:
        count = int(m.group(1).replace(",", ""))
        if 0 < count <= 100000:
            return count

    return None


def _extract_furunavi(html: str) -> int | None:
    """ふるなび: SPAのため件数取得が困難。script内JSONから試みる。"""
    # script内のJSON埋め込みを探す
    for pattern in [
        r'"totalCount"\s*:\s*(\d+)',
        r'"total"\s*:\s*(\d+)',
        r'"count"\s*:\s*(\d+)',
        r'"resultCount"\s*:\s*(\d+)',
    ]:
        m = re.search(pattern, html)
        if m:
            count = int(m.group(1))
            if 0 < count <= 100000:
                return count

    # テキストから件数（SPA描画前でも稀にSSR部分に含まれる場合）
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()
    m = re.search(r"([\d,]+)\s*件", text)
    if m:
        count = int(m.group(1).replace(",", ""))
        if 0 < count <= 100000:
            return count

    return None


def _extract_aupay(html: str) -> int | None:
    """au PAY ふるさと納税: テキスト内の「XXX件」パターンから抽出。"""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    patterns = [
        r"([\d,]+)\s*件\s*(?:の|が|を|見つかり|ヒット|表示)",
        r"検索結果\s*[:：]?\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件\s*中",
        r"全\s*([\d,]+)\s*件",
        r"([\d,]+)\s*件",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            count = int(m.group(1).replace(",", ""))
            if 0 < count <= 100000:
                return count

    # script内JSON
    for pattern in [r'"totalCount"\s*:\s*(\d+)', r'"total"\s*:\s*(\d+)']:
        m = re.search(pattern, html)
        if m:
            count = int(m.group(1))
            if 0 < count <= 100000:
                return count

    return None


# ==============================================================
# ユーティリティ
# ==============================================================

def search_product_all_sites(
    municipality: str, product_name: str, delay: float = 2.0
) -> dict[str, dict]:
    """1つの商品について全サイトで検索する。"""
    query = f"{municipality} {product_name}"
    return search_all_sites(query, delay=delay)


def aggregate_counts(site_results: dict[str, dict]) -> dict:
    """全サイトの検索結果を集計する。"""
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
