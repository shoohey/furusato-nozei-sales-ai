"""Claude APIによる穴場商品発掘・スコアリングモジュール"""

import json
import os
import re
import anthropic


CATEGORY_LABELS = {
    "肉類": "肉類（牛肉・豚肉・鶏肉・ジビエなど）",
    "海産物": "海産物（魚介類・海藻・干物など）",
    "野菜・果物": "野菜・果物（生鮮・ドライフルーツなど）",
    "米・穀物": "米・穀物（ブランド米・雑穀など）",
    "酒類": "酒類（日本酒・焼酎・ワイン・ビールなど）",
    "スイーツ・菓子": "スイーツ・菓子（和菓子・洋菓子など）",
    "工芸品": "工芸品（陶器・木工・織物など）",
    "加工品": "加工品（漬物・調味料・缶詰・ハム・ソーセージなど）",
}


def get_api_key(user_key: str = "") -> str:
    """APIキーを取得する（入力値 → Streamlit Secrets → 環境変数の優先順）。"""
    if user_key and user_key.strip():
        return user_key.strip()
    # Streamlit Cloud Secrets対応
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    env_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if env_key:
        return env_key
    raise ValueError("APIキーが設定されていません")


def analyze_products(
    api_key: str,
    prefecture: str,
    municipality: str,
    category: str,
    product_count: int = 10,
) -> list[dict]:
    """
    Claude APIを使って地域の穴場特産品を発掘する。

    Args:
        api_key: Anthropic APIキー
        prefecture: 都道府県名
        municipality: 市区町村名
        category: 商品カテゴリ
        product_count: リストアップする商品数

    Returns:
        list[dict]: 穴場商品リスト
    """
    resolved_key = get_api_key(api_key)
    client = anthropic.Anthropic(api_key=resolved_key)

    category_detail = CATEGORY_LABELS.get(category, category)
    location = f"{prefecture}{municipality}"

    prompt = f"""あなたはふるさと納税の「穴場商品」発掘の専門家です。
大手ふるさと納税サイトで既に大量に出品されている定番商品ではなく、
まだあまり知られていない隠れた逸品・穴場商品を見つけ出すことが使命です。

## 対象地域
{location}

## カテゴリ
{category_detail}

## 重要：穴場商品の条件
以下の条件に合う商品を優先してください：

### 探すべき商品（穴場）
- **小規模な生産者・工房**が作っている高品質な商品
- **地元では有名だが全国的にはほとんど知られていない**特産品
- **新しく立ち上がった**ブランドや商品（ここ数年で始まった事業）
- **伝統製法を守る少量生産品**（大量生産されていない希少性のあるもの）
- **地域の特殊な気候・風土でしか作れない**独自性の高い商品
- **コンテストや品評会で受賞歴があるが知名度が低い**商品
- **異業種参入・新規参入した**ユニークな生産者の商品
- **他のふるさと納税サイトであまり見かけない**商品

### 避けるべき商品（王道すぎる）
- 全国的に有名なブランド牛・ブランド米などの定番品
- 大手企業が大量生産している商品
- 既にふるさと納税サイトで大量に出品されているもの
- どの地域でも似たような商品が出ているもの（例：普通の和牛切り落とし）

## 調査内容
上記の条件を踏まえて、{location}で実際に生産・製造されている{category}の**穴場商品**を**{product_count}個**リストアップしてください。
架空の商品は含めないでください。確信が持てない商品は「confidence: 低」と明記してください。

各商品について以下の情報を調べてください：
1. **name**: 具体的な商品名やブランド名
2. **producer**: 製造元・生産者の名称
3. **producer_url**: 公式Webサイト（不明な場合は "不明"）
4. **appeal** (1-10): ふるさと納税返礼品としての魅力（品質・ストーリー・見栄え）
5. **niche_score** (1-10): 穴場度（高いほどまだ知られていない穴場）
   - 10: ほとんど誰も知らない超穴場
   - 7-9: 地元民は知っているが全国的には無名
   - 4-6: ある程度知られているが競合少ない
   - 1-3: 既にかなり出回っている
6. **description**: 50文字以内の簡潔な説明
7. **differentiation**: この商品ならではの差別化ポイント（他にはない独自の魅力）
8. **target_donor**: この返礼品が刺さりそうなターゲット層
9. **recommendation**: なぜこの穴場商品を営業すべきか
10. **confidence**: 確度（"高" / "中" / "低"）

## 出力形式
必ず以下のJSON形式で出力してください。JSON以外のテキストは含めないでください。

```json
[
  {{
    "name": "商品名",
    "producer": "生産者名",
    "producer_url": "https://example.com",
    "appeal": 8,
    "niche_score": 9,
    "description": "商品の簡潔な説明",
    "differentiation": "他にはない独自の魅力",
    "target_donor": "ターゲット層",
    "recommendation": "営業推薦理由",
    "confidence": "高"
  }}
]
```
"""

    # 商品数に応じてトークン数を調整（1商品あたり約300トークン）
    max_tokens = min(8192, max(4096, product_count * 400))

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    return _parse_response(text)


def _parse_response(text: str) -> list[dict]:
    """Claude APIのレスポンスからJSON商品リストを抽出する。"""
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_match = re.search(r"\[[\s\S]*\]", text)
        if json_match:
            json_str = json_match.group(0)
        else:
            return []

    try:
        products = json.loads(json_str)
        if not isinstance(products, list):
            return []

        normalized = []
        for p in products:
            if not isinstance(p, dict):
                continue
            normalized.append({
                "name": str(p.get("name", "不明")),
                "producer": str(p.get("producer", "不明")),
                "producer_url": str(p.get("producer_url", "不明")),
                "appeal": _clamp(p.get("appeal", 5), 1, 10),
                "niche_score": _clamp(p.get("niche_score", 5), 1, 10),
                "description": str(p.get("description", "")),
                "differentiation": str(p.get("differentiation", "")),
                "target_donor": str(p.get("target_donor", "")),
                "recommendation": str(p.get("recommendation", "")),
                "confidence": str(p.get("confidence", "中")),
            })
        return normalized

    except (json.JSONDecodeError, ValueError):
        return []


def _clamp(value, min_val, max_val):
    """値を範囲内に収める。"""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return min_val
    return max(min_val, min(max_val, v))


def calculate_priority(
    products: list[dict],
    all_site_results: dict[str, dict],
    municipality: str,
) -> list[dict]:
    """
    穴場商品リストにスコアリングして優先度を算出する。

    スコアリング基準:
    - 競合少なさ (30%): 全サイト合計の掲載数が少ないほど高スコア
    - 穴場度 (30%): Claude評価の穴場スコア（高いほど未開拓）
    - 商品魅力度 (25%): 品質・ストーリー・見栄え
    - 参入しやすさ (15%): 生産者のWeb有無・連絡先

    Args:
        products: Claude分析結果の商品リスト
        all_site_results: 商品名 -> {サイト名 -> 検索結果} のネスト辞書
        municipality: 市区町村名

    Returns:
        list[dict]: 優先度付き商品リスト（優先度順にソート済み）
    """
    scored_products = []

    for product in products:
        name = product["name"]
        site_results = all_site_results.get(name, {})

        # 各サイトの件数を集計
        site_counts = {}
        total_count = 0
        has_any = False
        failed_count = 0

        for site_name, result in site_results.items():
            count = result.get("count")
            if count is not None:
                site_counts[site_name] = count
                total_count += count
                has_any = True
            else:
                site_counts[site_name] = None
                if result.get("error"):
                    failed_count += 1

        # 競合スコア計算（掲載数が少ないほど高スコア = 穴場）
        if not has_any:
            # スクレイピング全失敗時は穴場度から推定
            niche = product.get("niche_score", 5)
            competition_score = min(10, niche + 1)
            count_display = "取得不可"
        elif total_count == 0:
            competition_score = 10
            count_display = "0件（超穴場!）"
        elif total_count <= 3:
            competition_score = 9
            count_display = f"{total_count}件（穴場!）"
        elif total_count <= 10:
            competition_score = 8
            count_display = f"{total_count}件"
        elif total_count <= 30:
            competition_score = 6
            count_display = f"{total_count}件"
        elif total_count <= 80:
            competition_score = 4
            count_display = f"{total_count}件"
        elif total_count <= 200:
            competition_score = 2
            count_display = f"{total_count}件（競合多）"
        else:
            competition_score = 1
            count_display = f"{total_count}件（飽和）"

        # 穴場度スコア（Claude評価）
        niche_score = product.get("niche_score", 5)

        # 参入しやすさスコア
        has_url = (
            product.get("producer_url", "不明") != "不明"
            and product.get("producer_url", "") != ""
        )
        accessibility_score = 8 if has_url else 4

        # 魅力度スコア（Claude評価）
        appeal_score = product.get("appeal", 5)

        # 総合スコア（加重平均）- 穴場重視の配分
        total_score = (
            competition_score * 0.30
            + niche_score * 0.30
            + appeal_score * 0.25
            + accessibility_score * 0.15
        )

        # 優先度ランク
        if total_score >= 7.0:
            rank = "A"
        elif total_score >= 5.0:
            rank = "B"
        else:
            rank = "C"

        scored_products.append({
            **product,
            "total_listing_count": count_display,
            "total_listing_raw": total_count if has_any else None,
            "site_counts": site_counts,
            "failed_sites": failed_count,
            "competition_score": competition_score,
            "niche_score_weighted": niche_score,
            "accessibility_score": accessibility_score,
            "total_score": round(total_score, 1),
            "rank": rank,
        })

    scored_products.sort(key=lambda x: x["total_score"], reverse=True)
    return scored_products
