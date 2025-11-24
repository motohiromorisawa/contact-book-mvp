import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz
import difflib # 差分計算用

# ---------------------------------------------------------
# 1. 設定 & デザイン
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー Pro", layout="wide")

st.markdown("""
<style>
    /* テキストエリアを見やすく */
    .stTextArea textarea {
        font-size: 16px !important;
        line-height: 1.6 !important;
        font-family: "Hiragino Kaku Gothic ProN", sans-serif !important;
    }
    /* サイドバーの強調 */
    [data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
</style>
""", unsafe_allow_html=True)

JST = pytz.timezone('Asia/Tokyo')

# API設定
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. データ操作 (設定・ログ)
# ---------------------------------------------------------

def get_staff_list():
    """memberシートから職員名を取得"""
    try:
        service = get_gsp_service()
        # A列:児童, B列:職員, C列:文体サンプル
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!B:C").execute()
        values = sheet.get('values', [])
        # 重複排除してリスト化
        staff_dict = {} # {name: style_text}
        for row in values:
            if row:
                name = row[0]
                style = row[1] if len(row) > 1 else ""
                staff_dict[name] = style
        return staff_dict
    except:
        return {"職員A": ""}

def save_staff_style(name, style_text):
    """職員の文体サンプルを保存 (簡易的にmemberシートのC列を更新するロジック)"""
    # 注: 実運用では行を検索してUpdateする必要がありますが、ここでは簡易実装とします
    # 実際には「設定保存」ボタンでDBや別シートに保存する形が望ましい
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!B:B").execute()
        rows = sheet.get('values', [])
        
        target_row = -1
        for i, row in enumerate(rows):
            if row and row[0] == name:
                target_row = i + 1
                break
        
        if target_row != -1:
            body = {'values': [[style_text]]}
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range=f"member!C{target_row}",
                valueInputOption="USER_ENTERED", body=body
            ).execute()
            return True
        else:
            # 新規追加等の処理が必要だが今回は割愛
            return False
    except:
        return False

def calculate_similarity_score(original, final):
    """
    AI生成文(original)と人間修正文(final)の類似度を0.0~1.0で計算
    1.0 = 修正なし (AI完璧)
    0.0 = 全書き換え (AI役に立たず)
    """
    return difflib.SequenceMatcher(None, original, final).ratio()

def save_report_log(child_name, final_text, staff_name, similarity_score, hint_used):
    """
    修正後の確定データを保存
    similarity_score (修正率) がKPIになる
    """
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        # [日時, 児童名, 確定本文, TYPE, 次回ヒント(空), ヒント活用, 類似度スコア, 職員名]
        values = [[now, child_name, final_text, "REPORT_FINAL", "", hint_used, similarity_score, staff_name]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

# (メモ取得・音声認識などの既存関数はそのまま利用)
def fetch_todays_memos(child_name):
    # ... (前回のコードと同じ) ...
    return "10:00 朝の会に参加。\n14:00 工作でハサミを使った。", None 

# ---------------------------------------------------------
# 3. AI生成 (ユーザー定義スタイル反映)
# ---------------------------------------------------------
def generate_draft(child_name, memos, staff_name, staff_style_example):
    
    system_prompt = f"""
    あなたは放課後等デイサービスの職員「{staff_name}」です。
    以下の「あなたの過去の文章例」を参考に、**文体や口調を真似て**連絡帳の下書きを作成してください。

    【{staff_name}の文章スタイル例】
    {staff_style_example}

    【ルール】
    - 出力は保護者宛の本文のみ。
    - 時候の挨拶などは例に従う。
    - マークダウンは使わない。
    
    【本日のメモ】
    {memos}
    """
    
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "連絡帳の下書きをお願いします。"}]
        )
        return message.content[0].text
    except Exception as e:
        return f"生成エラー: {e}"

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

# --- サイドバー（設定エリア） ---
with st.sidebar:
    st.header("⚙️ 職員設定")
    staff_data = get_staff_list()
    current_staff = st.selectbox("担当者名", list(staff_data.keys()))
    
    current_style = staff_data.get(current_staff, "")
    
    st.subheader("あなたの文章スタイル")
    st.caption("AIに真似させたい、過去の自分の良い文章を貼り付けてください（箇条書きでも、実際のメールでも可）。")
    new_style = st.text_area("文章例（チューニング用）", value=current_style, height=300)
    
    if st.button("設定を保存"):
        if save_staff_style(current_staff, new_style):
            st.success("スタイルを学習しました")
        else:
            st.error("保存失敗（スプレッドシートmemberを確認してください）")

# --- メインエリア ---
st.title("連絡帳メーカー Pro")
st.caption(f"担当: {current_staff} さん")

# 児童選択など（省略）
child_name = "山田 太郎" # デモ用

# セッション状態管理
if "draft_text" not in st.session_state:
    st.session_state.draft_text = ""

# タブ構成はやめて、自然なフロー（上から下へ）にする
# STEP 1: 情報収集
st.subheader("1. 今日の記録")
col_input, col_view = st.columns([1, 1])
with col_input:
    # 音声入力など
    st.info("（ここに音声入力UI）")
with col_view:
    memos, _ = fetch_todays_memos(child_name)
    st.text_area("収集されたメモ", memos, disabled=True, height=100)

st.divider()

# STEP 2: ドラフト生成
col_gen_btn, _ = st.columns([1, 2])
with col_gen_btn:
    if st.button("✨ AIドラフトを作成", type="primary"):
        with st.spinner(f"{current_staff}さんの文体を再現中..."):
            draft = generate_draft(child_name, memos, current_staff, new_style)
            st.session_state.draft_text = draft

# STEP 3: 編集と確定（ここがUXの肝）
if st.session_state.draft_text:
    st.subheader("2. 編集・確認")
    st.caption("AIの提案を修正してください。あなたの修正がAIを賢くします。")
    
    # 編集エリア（AIの出力をデフォルト値として入れる）
    final_text = st.text_area("連絡帳エディタ", value=st.session_state.draft_text, height=300)
    
    col_copy, col_finish = st.columns([1, 1])
    
    with col_finish:
        # 完了ボタン
        if st.button("決定して記録する（完了）", type="primary", use_container_width=True):
            # 裏側でスコア計算
            score = calculate_similarity_score(st.session_state.draft_text, final_text)
            
            # 保存処理
            save_report_log(child_name, final_text, current_staff, score, "Unchecked")
            
            st.success("保存しました！お疲れ様でした。")
            
            # スコアによるフィードバック（ユーザーには褒めるだけ、開発者には数値が見える）
            if score > 0.9:
                st.toast("素晴らしい！ほぼAIのまま使えましたね。", icon="🤖")
            elif score > 0.6:
                st.toast("記録完了。あなたの修正を学習しました。", icon="✨")
            else:
                st.toast("記録完了。大幅な修正お疲れ様です。", icon="💪")
            
            # クリップボード用表示（Streamlitの制限上、ユーザーにコピーさせる）
            st.code(final_text, language=None)
            st.caption("↑ 右上のボタンでコピーして連絡帳アプリに貼り付けてください")
