import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz
import difflib  # 差分計算用

# ---------------------------------------------------------
# 1. 設定 & デザイン
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳Co-Pilot", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

st.markdown("""
<style>
    .main-header { font-size: 24px; font-weight: bold; color: #1E88E5; margin-bottom: 20px; }
    .status-badge { background-color: #E8F5E9; color: #2E7D32; padding: 5px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    /* テキストエリアを使いやすく */
    textarea { font-size: 16px !important; line-height: 1.5 !important; font-family: "Hiragino Kaku Gothic ProN", sans-serif !important; }
</style>
""", unsafe_allow_html=True)

# API設定 (secretsから取得)
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

# ---------------------------------------------------------
# 2. ロジック類
# ---------------------------------------------------------
def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def calculate_similarity(text1, text2):
    """2つのテキストの類似度を0.0〜1.0で算出（1.0が完全一致）"""
    return difflib.SequenceMatcher(None, text1, text2).ratio()

def save_final_record(child_name, final_text, original_ai_text, staff_name):
    """
    最終結果を保存し、AI原案との「乖離度」を品質指標として記録する
    """
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        
        # 類似度計算 (これがUX満足度の客観指標になる)
        similarity_score = calculate_similarity(original_ai_text, final_text)
        
        # [日時, 名前, 最終本文, タイプ, AI原案(分析用), 類似度スコア, 担当者]
        values = [[now, child_name, final_text, "REPORT_FINAL", original_ai_text, similarity_score, staff_name]]
        
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# (メモ取得や音声認識の関数は既存のものを流用・簡略化して記載)
def fetch_todays_memos(child_name):
    # ダミーロジック: 実際はスプレッドシートから取得
    return "10:00 朝の会で元気よく挨拶\n12:00 給食を完食。野菜も食べた。\n15:00 友達とおもちゃの貸し借りでトラブルがあったが、自分で「ごめんね」と言えた。"

def generate_draft(child_name, memos, staff_name):
    # ダミー生成ロジック: 実際はClaude APIを呼ぶ
    # 高速化のため、ストリーミングっぽく見せたり、非同期が望ましいが、一旦同期処理
    try:
        system_prompt = f"担当者{staff_name}として、{child_name}の連絡帳原案を作成。"
        # ここでAPIコール...
        # message = anthropic_client...
        
        # デモ用返却値
        return f"""【今日の様子】
本日は朝の会でとても元気よく挨拶をしてくれました。給食の時間には野菜も含めて完食され、素晴らしい食欲でした。

【活動内容】
・朝の会
・給食
・自由遊び

【特記事項】
午後、お友達とおもちゃの貸し借りで少しトラブルになりましたが、保育士が仲介する前に自分から「ごめんね」と伝えることができ、成長を感じました。"""
    except:
        return ""

# ---------------------------------------------------------
# 3. UI構築
# ---------------------------------------------------------
# セッション状態の初期化
if "draft_text" not in st.session_state: st.session_state.draft_text = ""
if "ai_original_text" not in st.session_state: st.session_state.ai_original_text = ""
if "step" not in st.session_state: st.session_state.step = 1  # 1:メモ入力, 2:編集

st.markdown("<div class='main-header'>連絡帳Co-Pilot 🤝</div>", unsafe_allow_html=True)

# サイドバー設定
with st.sidebar:
    st.header("設定")
    staff_name = st.text_input("担当者名", "鈴木")
    child_name = st.selectbox("児童名", ["田中 太郎", "佐藤 花子"])
    
    # 完了後のリセットボタン
    if st.button("次の児童へ（リセット）"):
        st.session_state.draft_text = ""
        st.session_state.ai_original_text = ""
        st.session_state.step = 1
        st.rerun()

# --- STEP 1: 素材集め ---
if st.session_state.step == 1:
    st.subheader("1. 今日の記録を確認")
    
    col_memo, col_action = st.columns([2, 1])
    
    with col_memo:
        # メモは編集可能にする（誤字脱字直しのため）
        current_memos = fetch_todays_memos(child_name)
        memos_edited = st.text_area("本日のメモ（編集可）", current_memos, height=200)
    
    with col_action:
        st.info("💡 ヒント: メモが具体的だと、より良い原案ができます。")
        st.write("音声入力ボタン（省略）")
        
        st.markdown("###")
        if st.button("この内容で下書きを作成 🚀", type="primary", use_container_width=True):
            with st.spinner("AIが執筆中..."):
                draft = generate_draft(child_name, memos_edited, staff_name)
                st.session_state.ai_original_text = draft
                st.session_state.draft_text = draft
                st.session_state.step = 2
                st.rerun()

# --- STEP 2: 編集と仕上げ (The Live Editor) ---
elif st.session_state.step == 2:
    st.subheader("2. 仕上げ（編集・確認）")
    
    col_left, col_right = st.columns([1, 1])
    
    # 左側：参照用メモ（見ながら書くため）
    with col_left:
        st.caption("参照：本日のメモ")
        st.info(fetch_todays_memos(child_name))
        
        st.divider()
        st.caption("AIへの調整指示（リテイク）")
        c1, c2, c3 = st.columns(3)
        if c1.button("もっと短く"):
            st.toast("短く書き直します（未実装デモ）")
        if c2.button("もっと丁寧に"):
            st.toast("丁寧に書き直します（未実装デモ）")
        if c3.button("絵文字あり"):
            st.toast("絵文字を追加します（未実装デモ）")

    # 右側：メインエディタ
    with col_right:
        st.markdown("##### 📝 連絡帳ドラフト")
        # ここが核心：AIの出力をそのまま編集させる
        final_text = st.text_area(
            "ここを直接書き換えてください",
            value=st.session_state.draft_text,
            height=400,
            key="editor"
        )
        
        st.write("---")
        
        # アクションエリア
        col_copy, col_done = st.columns([1, 1])
        
        with col_copy:
            # コピー機能はStreamlitの仕様上難しいが、codeブロックで代用可
            st.caption("コピー用")
            st.code(final_text, language=None)
            
        with col_done:
            # 完了ボタンを押した瞬間が「計測」の瞬間
            if st.button("これで完了（保存） ✅", type="primary", use_container_width=True):
                if save_final_record(child_name, final_text, st.session_state.ai_original_text, staff_name):
                    st.balloons()
                    st.success("保存しました！お疲れ様でした。")
                    
                    # 類似度を表示（開発時は表示し、本番では隠しても良い）
                    sim = calculate_similarity(st.session_state.ai_original_text, final_text)
                    st.caption(f"🔧 AI活用率（修正の少なさ）: {sim*100:.1f}%")
                    
                    # 少し待ってからリセットなどの処理
