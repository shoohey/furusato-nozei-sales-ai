"""ふるさと納税営業AI - 穴場商品発掘プラットフォーム"""

import json
import os
import streamlit as st
from scraper import search_all_sites, aggregate_counts, get_site_names
from analyzer import analyze_products, calculate_priority, get_api_key
import time

# ページ設定
st.set_page_config(
    page_title="ふるさと納税 営業AI",
    page_icon="🏛️",
    layout="wide",
)

# テーマ: 白背景 + フレンドリーカラー
st.markdown("""
<style>
    /* 白背景ベース */
    .stApp {
        background-color: #ffffff;
        color: #333333;
    }
    .stApp > header {
        background-color: #ffffff;
    }
    [data-testid="stSidebar"] {
        background-color: #f0f7f0;
    }
    [data-testid="stSidebar"] .stMarkdown {
        color: #2d5a2d;
    }

    /* タイトル */
    .stApp h1 {
        color: #2e7d32;
    }
    .stApp h2, .stApp h3 {
        color: #37474f;
    }

    /* メトリクスカード */
    [data-testid="stMetric"] {
        background-color: #f8faf8;
        border: 1px solid #c8e6c9;
        border-radius: 12px;
        padding: 12px 16px;
    }
    [data-testid="stMetricValue"] {
        color: #2e7d32;
    }

    /* エキスパンダー */
    div[data-testid="stExpander"] {
        background-color: #fafffe;
        border: 1px solid #c8e6c9;
        border-radius: 12px;
        margin-bottom: 10px;
    }
    div[data-testid="stExpander"] summary {
        color: #333333;
    }

    /* ボタン */
    .stButton > button[kind="primary"] {
        background-color: #43a047;
        border-color: #43a047;
        color: white;
        border-radius: 8px;
        font-weight: bold;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2e7d32;
        border-color: #2e7d32;
    }

    /* プログレスバー */
    .stProgress > div > div {
        background-color: #66bb6a;
    }

    /* インフォボックス */
    [data-testid="stAlert"] {
        border-radius: 10px;
    }

    /* セレクトボックス */
    .stSelectbox label, .stTextInput label {
        color: #2d5a2d;
        font-weight: 600;
    }

    /* divider */
    hr {
        border-color: #e0e0e0;
    }

    /* サイト別バッジ */
    .site-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.85em;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 4px;
    }
    .site-badge-satofull { background-color: #fff3e0; color: #e65100; }
    .site-badge-choice { background-color: #e3f2fd; color: #1565c0; }
    .site-badge-rakuten { background-color: #fce4ec; color: #c62828; }
    .site-badge-furunavi { background-color: #e8f5e9; color: #2e7d32; }
    .site-badge-aupay { background-color: #f3e5f5; color: #6a1b9a; }
</style>
""", unsafe_allow_html=True)

SITE_BADGE_CLASS = {
    "さとふる": "site-badge-satofull",
    "ふるさとチョイス": "site-badge-choice",
    "楽天ふるさと納税": "site-badge-rakuten",
    "ふるなび": "site-badge-furunavi",
    "au PAY ふるさと納税": "site-badge-aupay",
}


@st.cache_data
def load_prefectures():
    """都道府県・市区町村データを読み込む。"""
    data_path = os.path.join(os.path.dirname(__file__), "data", "prefectures.json")
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    st.title("🏛️ ふるさと納税 営業AI")
    st.caption("まだ知られていない穴場商品を発掘し、主要5サイトでの競合状況を一括分析します")

    prefectures_data = load_prefectures()

    # 環境変数のAPIキーを取得
    env_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    # --- サイドバー ---
    with st.sidebar:
        st.header("🔍 調査条件")

        prefecture = st.selectbox(
            "都道府県",
            options=list(prefectures_data.keys()),
            index=0,
        )

        municipalities = prefectures_data.get(prefecture, [])
        municipality = st.selectbox(
            "市区町村",
            options=municipalities,
            index=0,
        )

        categories = [
            "肉類",
            "海産物",
            "野菜・果物",
            "米・穀物",
            "酒類",
            "スイーツ・菓子",
            "工芸品",
            "加工品",
        ]
        category = st.selectbox(
            "商品カテゴリ",
            options=categories,
            index=0,
        )

        st.divider()

        # APIキー入力（環境変数があれば省略可）
        if env_api_key:
            st.success("APIキー: 環境変数から取得済み")
            api_key = env_api_key
            api_key_input = ""
        else:
            api_key_input = st.text_input(
                "Anthropic API Key",
                type="password",
                placeholder="sk-ant-...",
                help="Claude APIの利用に必要です",
            )
            api_key = api_key_input

        st.divider()

        # 調査対象サイト表示
        st.markdown("**調査対象サイト:**")
        for name in get_site_names():
            badge_cls = SITE_BADGE_CLASS.get(name, "")
            st.markdown(
                f'<span class="site-badge {badge_cls}">{name}</span>',
                unsafe_allow_html=True,
            )

        st.divider()

        start_button = st.button(
            "🚀 調査開始",
            use_container_width=True,
            type="primary",
            disabled=not api_key,
        )

        if not api_key:
            st.warning("APIキーを入力してください")

        st.divider()
        st.caption("© 2024 株式会社北国からの贈り物")

    # --- メインエリア ---
    if start_button and api_key:
        run_analysis(api_key, prefecture, municipality, category)
    elif "results" in st.session_state:
        display_results(st.session_state["results"], st.session_state["params"])
    else:
        show_welcome()


def show_welcome():
    """初期表示の案内を表示する。"""
    st.info(
        "👈 サイドバーで調査条件を選択し、「調査開始」ボタンを押してください。\n\n"
        "**使い方:**\n"
        "1. 都道府県・市区町村を選択\n"
        "2. 商品カテゴリを選択\n"
        "3. Anthropic APIキーを入力（環境変数設定済みなら不要）\n"
        "4. 「調査開始」をクリック"
    )

    with st.expander("このツールについて"):
        st.markdown("""
        **ふるさと納税 営業AI** は、まだ知られていない穴場商品を効率的に発掘するためのツールです。

        **主な機能:**
        - 🔍 **穴場商品AI発掘**: 小規模生産者・地元の隠れた逸品をClaude AIが探索
        - 📊 **5サイト一括競合調査**: さとふる・ふるさとチョイス・楽天・ふるなび・au PAYの掲載数をチェック
        - 💎 **穴場スコアリング**: 競合少なさ × 穴場度 × 商品魅力度で優先度を判定
        - 🏢 **生産者情報**: 生産者名やWebサイトURLを提示
        - 🎯 **ターゲット分析**: どんな寄附者に刺さるかを提示

        **スコアリング基準:**
        - **競合少なさ** (30%): 全サイト合計の掲載数が少ないほど高スコア
        - **穴場度** (30%): まだ知られていない度合い（AIが評価）
        - **商品魅力度** (25%): 品質・ストーリー・ギフト適性
        - **参入しやすさ** (15%): 生産者のWeb有無・連絡の取りやすさ
        """)


def run_analysis(api_key: str, prefecture: str, municipality: str, category: str):
    """分析を実行する。"""
    st.subheader(f"📍 {prefecture} {municipality} - {category}")

    progress = st.progress(0)
    status = st.empty()

    # Step 1: Claude APIで穴場特産品を発掘
    status.info("🔍 AIが地域の穴場商品を発掘中...")
    progress.progress(10)

    try:
        products = analyze_products(api_key, prefecture, municipality, category)
    except Exception as e:
        st.error(f"AI分析でエラーが発生しました: {str(e)}")
        return

    if not products:
        st.warning("該当する特産品が見つかりませんでした。条件を変えてお試しください。")
        return

    status.info(f"💎 {len(products)}件の穴場候補を発見！ 5サイト一括競合調査を開始します...")
    progress.progress(20)

    # Step 2: 各商品について全サイトで掲載数を検索
    site_names = get_site_names()
    total_searches = len(products) * len(site_names)
    all_site_results = {}  # 商品名 -> {サイト名 -> 結果}

    search_count = 0
    for i, product in enumerate(products):
        query = f"{municipality} {product['name']}"
        status.info(
            f"🔍 競合調査中... ({i+1}/{len(products)}) "
            f"「{product['name']}」を5サイトで検索"
        )

        site_results = search_all_sites(query, delay=2.0)
        all_site_results[product["name"]] = site_results

        search_count += len(site_names)
        progress.progress(20 + int(65 * search_count / total_searches))

    # Step 3: スコアリング・優先度付け
    status.info("📊 スコアリング・優先度を計算中...")
    progress.progress(90)

    scored_products = calculate_priority(products, all_site_results, municipality)

    progress.progress(100)
    status.success(
        f"✅ 分析完了！ {len(scored_products)}件の商品 × "
        f"{len(site_names)}サイトを調査しました"
    )

    # 結果をセッションに保存
    st.session_state["results"] = scored_products
    st.session_state["params"] = {
        "prefecture": prefecture,
        "municipality": municipality,
        "category": category,
    }

    display_results(scored_products, st.session_state["params"])


def display_results(products: list[dict], params: dict):
    """分析結果を表示する。"""
    st.subheader(
        f"📊 分析結果 - {params['prefecture']} {params['municipality']} "
        f"({params['category']})"
    )

    # サマリー
    rank_counts = {"A": 0, "B": 0, "C": 0}
    for p in products:
        rank_counts[p["rank"]] = rank_counts.get(p["rank"], 0) + 1

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("調査商品数", f"{len(products)}件")
    with col2:
        st.metric("🔴 Aランク", f"{rank_counts.get('A', 0)}件")
    with col3:
        st.metric("🟡 Bランク", f"{rank_counts.get('B', 0)}件")
    with col4:
        st.metric("⚪ Cランク", f"{rank_counts.get('C', 0)}件")

    st.divider()

    # 結果テーブル
    for product in products:
        rank = product["rank"]
        rank_emoji = {"A": "🔴", "B": "🟡", "C": "⚪"}.get(rank, "⚪")
        rank_label = {"A": "高", "B": "中", "C": "低"}.get(rank, "低")

        with st.expander(
            f"{rank_emoji} **{rank}ランク** | {product['name']} "
            f"(スコア: {product['total_score']}) "
            f"| 合計掲載: {product['total_listing_count']}",
            expanded=(rank == "A"),
        ):
            col_left, col_right = st.columns([2, 1])

            with col_left:
                st.markdown(f"**商品名:** {product['name']}")
                st.markdown(f"**生産者:** {product['producer']}")

                url = product.get("producer_url", "不明")
                if url and url != "不明":
                    st.markdown(f"**HP:** [{url}]({url})")
                else:
                    st.markdown("**HP:** 不明")

                st.markdown(f"**説明:** {product.get('description', '')}")

                differentiation = product.get("differentiation", "")
                if differentiation:
                    st.markdown(f"**差別化ポイント:** {differentiation}")

                target = product.get("target_donor", "")
                if target:
                    st.markdown(f"**ターゲット層:** {target}")

            with col_right:
                st.markdown(f"**優先度:** {rank_emoji} {rank}ランク（{rank_label}優先度）")
                st.markdown(f"**総合スコア:** {product['total_score']}/10")
                st.markdown(f"**合計掲載数:** {product['total_listing_count']}")
                niche = product.get('niche_score', product.get('niche_score_weighted', '-'))
                st.markdown(f"**穴場度:** {niche}/10")
                st.markdown(f"**魅力度:** {product.get('appeal', '-')}/10")
                st.markdown(f"**確度:** {product.get('confidence', '-')}")

            # サイト別掲載数
            st.markdown("---")
            st.markdown("**📊 サイト別掲載数:**")
            site_counts = product.get("site_counts", {})
            site_cols = st.columns(len(site_counts) if site_counts else 1)

            for idx, (site_name, count) in enumerate(site_counts.items()):
                badge_cls = SITE_BADGE_CLASS.get(site_name, "")
                with site_cols[idx]:
                    count_str = f"{count}件" if count is not None else "取得不可"
                    st.markdown(
                        f'<span class="site-badge {badge_cls}">{site_name}</span>'
                        f"<br><strong>{count_str}</strong>",
                        unsafe_allow_html=True,
                    )

            st.info(f"💡 **営業推薦理由:** {product.get('recommendation', 'なし')}")


if __name__ == "__main__":
    main()
