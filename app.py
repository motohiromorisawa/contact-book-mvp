import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー Pro", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

st.markdown("""
<style>
    .stTextArea textarea {
        font-size: 16px !important;
        line-height: 1.6 !important;
        font-family: "Hiragino Kaku Gothic ProN", sans-serif !important;
    }
    .status-box {
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# API設定
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. データ操作
# ---------------------------------------------------------
def get_lists():
    """児童リストと職員リストを取得"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:B").execute()
        values = sheet.get('values', [])
        children = [row[0] for row in values if len(row) > 0]
        staffs = [row[1] for row in values if len(row) > 1]
        return children, staffs
    except:
        return [], []

def save_memo(child_name, text, staff_name):
    """メモ（素材）の保存"""
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        # [日時, 名前, 本文, タイプ, Staff]
        values = [[now, child_name, text, "MEMO", staff_name]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def save_final_report(child_name, ai_draft, final_text, next_hint, staff_name):
    """
    レポート保存（AI生成版と、人間修正版の両方を保存）
    Sheet1の列構成: A:日時, B:名前, C:FinalText, D:Type, E:Staff, F:NextHint, G:AI_Draft
    """
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        
        # G列にAIの初稿(ai_draft)を保存することで、C列(final_text)との差分分析が可能になる
        values = [[now, child_name, final_text, "REPORT", staff_name, next_hint, ai_draft]]
        
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def fetch_todays_memos(child_name):
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    
    memos = []
    for row in rows:
        # 日付一致 AND 名前一致 AND タイプがMEMO
        if len(row) >= 4 and row[1] == child_name and row[0].startswith(today_str) and row[3] == "MEMO":
            time_part = row[0][11:16]
            memos.append(f"・{time_part} {row[2]}")
            
    return "\n".join(memos)

def transcribe_audio(audio_file):
    try:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ja")
        return transcript.text
    except:
        return None

# ---------------------------------------------------------
# 3. 生成ロジック
# ---------------------------------------------------------
def generate_draft(child_name, memos, staff_name, style_example):
    
    # 職員独自のスタイル指定
    style_prompt = ""
    if style_example:
        style_prompt = f"""
        【重要：文体・トーンの指定】
        以下の「{staff_name}」の過去の執筆例の文体（語尾、長さ、漢字の開き方など）を忠実に再現してください。
        
        --- 執筆例開始 ---
        {style_example}
        --- 執筆例終了 ---
        """
    else:
        style_prompt = "文体：です・ます調。保護者に安心感を与える、簡潔で丁寧なプロフェッショナルな文章。"

    system_prompt = f"""
    あなたは放課後等デイサービスの職員です。
    提供されたメモから、保護者への「連絡帳」の下書きを作成してください。

    # 前提
    - 児童名: {child_name}
    - 担当職員: {staff_name}

    {style_prompt}

    # 構成
    1. 今日の様子（ポジティブなエピソードを中心に）
    2. 活動内容（事実ベース）
    3. ご連絡（あれば）
    4. 次回への申し送り（職員間用）

    # ルール
    - 絵文字は使用禁止。
    - マークダウンは使用禁止（プレーンテキスト）。
    - 挨拶から始めてください。
    - 職員間の申し送りは、最後に `<<<INTERNAL>>>` という区切り線を入れて記述してください。
    """

    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            temperature=0.3,
            system=system_prompt,
            messages=[{"role": "user", "content": f"以下のメモから作成してください：\n\n{memos}"}]
        )
        return message.content[0].text
    except Exception as e:
        return f"エラー: {e}"

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

# --- サイドバー（設定・チューニング） ---
with st.sidebar:
    st.header("設定")
    
    # リスト取得
    child_list, staff_list = get_lists()
    if not staff_list: staff_list = ["職員A", "職員B"]
    
    staff_name = st.selectbox("担当職員", staff_list, key="staff_select")
    
    st.divider()
    st.subheader("文体チューニング")
    st.caption("あなたの「いつもの書き方」をここに貼り付けると、AIがそれを真似します。")
    style_example = st.text_area(
        "過去の連絡帳例", 
        height=200, 
        placeholder="例：\n本日は公園へ出かけました。〇〇くんは、滑り台が気に入ったようで、繰り返し楽しんでいました。\nおやつの時間は..."
    )

# --- メインエリア ---
st.title("連絡帳作成")

# 児童選択
child_name = st.selectbox("対象児童", child_list)

# タブ構成
tab1, tab2 = st.tabs(["1. 素材入力 (メモ)", "2. 編集・出力"])

# --- タブ1：メモ入力 ---
with tab1:
    st.info("日中の様子を箇条書きや音声で入力してください。")
    
    col_input1, col_input2 = st.columns(2)
    
    with col_input1:
        # 音声入力
        audio_val = st.audio_input("音声でメモ", key="audio_memo")
        if audio_val:
            with st.spinner("文字起こし中..."):
                transcribed = transcribe_audio(audio_val)
            if transcribed:
                if save_memo(child_name, transcribed, staff_name):
                    st.success("保存しました")
                    st.rerun()

    with col_input2:
        # テキスト入力
        text_val = st.text_input("テキストでメモ", key="text_memo")
        if st.button("メモ追加"):
            if text_val:
                if save_memo(child_name, text_val, staff_name):
                    st.success("保存しました")
                    st.rerun()
    
    st.divider()
    st.subheader("本日の記録済みメモ")
    current_memos = fetch_todays_memos(child_name)
    if current_memos:
        st.text_area("", current_memos, height=150, disabled=True)
    else:
        st.caption("まだ記録がありません")

# --- タブ2：生成と編集 ---
with tab2:
    # State初期化
    if "ai_draft" not in st.session_state: st.session_state.ai_draft = ""
    if "editing_text" not in st.session_state: st.session_state.editing_text = ""

    # 生成ボタン
    if st.button("AIドラフトを作成する", type="primary", use_container_width=True):
        memos = fetch_todays_memos(child_name)
        if not memos:
            st.error("メモがないため作成できません。")
        else:
            with st.spinner("AIが執筆中..."):
                draft = generate_draft(child_name, memos, staff_name, style_example)
                st.session_state.ai_draft = draft
                st.session_state.editing_text = draft # 初期値としてセット
    
    # 編集エリア（生成されている場合のみ表示）
    if st.session_state.ai_draft:
        st.divider()
        st.markdown("#### 編集エリア")
        st.caption("AIが作成した下書きです。必要な部分を修正してください。")
        
        # ユーザーが編集するテキストエリア
        final_text = st.text_area(
            "内容を確認・修正",
            value=st.session_state.editing_text,
            height=400
        )
        
        col_submit, col_copy = st.columns([1, 1])
        
        with col_submit:
            if st.button("この内容で確定・保存", type="primary", use_container_width=True):
                # 内部用メモの分離（保存用）
                parts = final_text.split("<<<INTERNAL>>>")
                public_text = parts[0].strip()
                next_hint = parts[1].strip() if len(parts) > 1 else ""
                
                # 保存実行（AI生データ と 修正後データ の両方を送る）
                if save_final_report(child_name, st.session_state.ai_draft, public_text, next_hint, staff_name):
                    st.toast("保存しました！お疲れ様でした。")
                    # ステートクリア
                    st.session_state.ai_draft = ""
                    st.session_state.editing_text = ""
                    st.rerun()
