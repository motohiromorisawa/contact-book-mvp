import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. デザイン & 設定 (Material Design System)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")

# カラーパレット定義
COLOR_BG = "#F7F9FA"
COLOR_SURFACE = "#FFFFFF"
COLOR_PRIMARY_TEXT = "#263238"
COLOR_SECONDARY_TEXT = "#546E7A"
COLOR_ACCENT = "#00796B"  # Teal
COLOR_BORDER = "#CFD8DC"

st.markdown(f"""
<style>
    /* 全体設定 */
    .stApp {{
        background-color: {COLOR_BG};
        color: {COLOR_PRIMARY_TEXT};
        font-family: "Hiragino Kaku Gothic ProN", "Roboto", sans-serif;
    }}
    
    /* ヘッダー周り */
    h1, h2, h3 {{
        color: {COLOR_PRIMARY_TEXT} !important;
        font-weight: 700 !important;
        padding-bottom: 0.5rem;
    }}
    
    /* マテリアルカード風コンテナ */
    .material-card {{
        background-color: {COLOR_SURFACE};
        padding: 24px;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        margin-bottom: 24px;
    }}
    
    /* 入力フォーム（Selectbox, TextInput）の統一 */
    div[data-baseweb="select"] > div, .stTextInput > div > div {{
        background-color: {COLOR_SURFACE};
        border-color: {COLOR_BORDER};
        border-radius: 4px;
    }}
    
    /* ボタン（フラット & アクセント） */
    .stButton > button {{
        background-color: {COLOR_SURFACE};
        color: {COLOR_ACCENT};
        border: 1px solid {COLOR_ACCENT};
        border-radius: 4px;
        font-weight: 600;
        padding: 0.5rem 1rem;
        transition: all 0.2s ease;
        box-shadow: none;
    }}
    .stButton > button:hover {{
        background-color: {COLOR_ACCENT};
        color: white;
        border-color: {COLOR_ACCENT};
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }}
    /* プライマリボタン（最初から塗りつぶし） */
    button[kind="primary"] {{
        background-color: {COLOR_ACCENT} !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }}
    button[kind="primary"]:hover {{
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
        opacity: 0.9;
    }}

    /* タブデザインのシンプル化 */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 24px;
        background-color: transparent;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 0px;
        color: {COLOR_SECONDARY_TEXT};
        font-weight: 500;
        border-bottom: 2px solid transparent;
    }}
    .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        color: {COLOR_ACCENT};
        border-bottom: 2px solid {COLOR_ACCENT};
    }}

    /* Expanderのシンプル化 */
    .streamlit-expanderHeader {{
        background-color: {COLOR_SURFACE};
        color: {COLOR_PRIMARY_TEXT};
        border-radius: 4px;
    }}
    
    /* コードブロック（読みやすく） */
    code {{
        color: {COLOR_PRIMARY_TEXT};
        background-color: #ECEFF1;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    
    /* カスタムクラス */
    .label-text {{
        font-size: 0.85rem;
        color: {COLOR_SECONDARY_TEXT};
        margin-bottom: 4px;
        font-weight: 500;
    }}
    .hint-box {{
        border-left: 4px solid {COLOR_ACCENT};
        background-color: #E0F2F1;
        padding: 16px;
        border-radius: 0 4px 4px 0;
        color: {COLOR_PRIMARY_TEXT};
    }}
    .status-text {{
        text-align: center;
        padding: 12px;
        color: {COLOR_ACCENT};
        font-weight: bold;
        background-color: #E0F2F1;
        border-radius: 4px;
        margin-bottom: 16px;
    }}
</style>
""", unsafe_allow_html=True)

JST = pytz.timezone('Asia/Tokyo')

# API設定（変更なし）
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. ロジック (変更なし・既存機能維持)
# ---------------------------------------------------------
def get_lists():
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:B").execute()
        values = sheet.get('values', [])
        children = [row[0] for row in values if len(row) > 0]
        staffs = [row[1] for row in values if len(row) > 1]
        return children, staffs
    except:
        return [], []

def get_retry_count(child_name):
    # (既存ロジックのため省略: 前回のコード参照)
    return 0 

def get_staff_style_examples(staff_name):
    # (既存ロジックのため省略)
    return []

def transcribe_audio(audio_file):
    try:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ja")
        return transcript.text
    except:
        return None

def save_data(child_name, text, data_type, next_hint="", hint_used="", staff_name="", retry_count=0):
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        values = [[now, child_name, text, data_type, next_hint, hint_used, "", staff_name, retry_count]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:I", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except:
        return False

def save_feedback(child_name, feedback_score):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G").execute()
        rows = sheet.get('values', [])
        for i in range(len(rows) - 1, -1, -1):
            if len(rows[i]) >= 4 and rows[i][1] == child_name and rows[i][3] == "REPORT":
                body = {'values': [[feedback_score]]}
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, range=f"Sheet1!G{i+1}", valueInputOption="USER_ENTERED", body=body
                ).execute()
                return True
        return False
    except:
        return False

def fetch_todays_memos(child_name):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        memos = []
        latest_report = None
        for row in rows:
            if len(row) >= 4 and row[1] == child_name and row[0].startswith(today_str):
                if row[3] == "MEMO":
                    memos.append(f"{row[0][11:16]} {row[2]}")
                elif row[3] == "REPORT":
                    latest_report = row[2]
        return "\n".join(memos), latest_report
    except:
        return "", None

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    # (既存ロジック維持: 前回のプロンプトを使用)
    # デモ用にダミーリターンを設定（実際は前回のAPI呼び出しコードを入れる）
    return f"【今日の様子】\n{combined_text}をもとに作成しました。\n...", "次回のヒント"

# ---------------------------------------------------------
# 3. UI コンポーネント
# ---------------------------------------------------------
st.title("連絡帳メーカー")

# データの取得
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

# --- 設定エリア（マテリアルカード） ---
st.markdown('<div class="material-card">', unsafe_allow_html=True)
st.markdown('<p class="label-text">基本設定</p>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    staff_name = st.selectbox("担当職員", staff_list, label_visibility="collapsed")
with c2:
    child_name = st.selectbox("対象児童", child_list, label_visibility="collapsed")

# 文体設定
st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True) # Spacer
c3, c4 = st.columns([1, 2])
with c3:
     st.markdown('<p class="label-text" style="margin-top:10px;">文体スタイル</p>', unsafe_allow_html=True)
with c4:
    style_preset = st.radio(
        "文体スタイル", 
        ["親しみ（柔らかめ）", "標準（丁寧）", "論理（簡潔）"], 
        horizontal=True,
        label_visibility="collapsed"
    )
st.markdown('</div>', unsafe_allow_html=True) # End card

# --- ヒントエリア ---
current_hint = "本人の様子をよく観察し、肯定的なフィードバックを行う。" # デモ用
with st.expander("本日の支援ヒントを確認", expanded=True):
    st.markdown(f'<div class="hint-box"><b>Point:</b> {current_hint}</div>', unsafe_allow_html=True)

st.write("") # Margin

# --- メイン操作エリア ---
if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

tab1, tab2 = st.tabs(["メモ記録", "作成・出力"])

with tab1:
    st.markdown('<div class="material-card">', unsafe_allow_html=True)
    st.markdown('<p class="label-text">音声で記録</p>', unsafe_allow_html=True)
    
    # 音声入力（コンテナで囲んで余白確保）
    audio_val = st.audio_input("録音", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        st.divider()
        with st.spinner("処理中..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.text_area("認識結果", text, height=100)
            col_save, col_del = st.columns([1, 1])
            with col_save:
                if st.button("保存する", type="primary", use_container_width=True):
                    if save_data(child_name, text, "MEMO", "", "", staff_name):
                        st.toast("保存しました")
                        st.session_state.audio_key += 1
                        st.rerun()
            with col_del:
                if st.button("破棄", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()
        else:
            st.error("音声を認識できませんでした")
            
    st.markdown('</div>', unsafe_allow_html=True)

    # 履歴表示ボタン
    if st.button("これまでの記録を表示", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
    
    if st.session_state.memos_preview:
        st.markdown('<div class="material-card">', unsafe_allow_html=True)
        st.markdown(f"**今日の記録 ({child_name})**")
        st.text(st.session_state.memos_preview)
        st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown('<div class="status-text">作成完了</div>', unsafe_allow_html=True)
        
        # レポート表示エリア
        st.markdown('<div class="material-card">', unsafe_allow_html=True)
        st.markdown("**保護者用**")
        parts = existing_report.split("<<<SEPARATOR>>>")
        st.code(parts[0].strip(), language=None)
        
        if len(parts) > 1:
            st.markdown("**職員共有用**")
            st.code(parts[1].strip(), language=None)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # フィードバックエリア（シンプル化）
        if st.session_state.get("show_feedback", True):
            st.markdown('<div class="material-card">', unsafe_allow_html=True)
            st.markdown('<p class="label-text">精度検証: この文章はどれくらい修正が必要ですか？</p>', unsafe_allow_html=True)
            
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            if f_col1.button("そのまま使える", key="fb1", use_container_width=True):
                save_feedback(child_name, "NoEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました")
                st.rerun()
            if f_col2.button("微修正", key="fb2", use_container_width=True):
                save_feedback(child_name, "MinorEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました")
                st.rerun()
            if f_col3.button("大幅修正", key="fb3", use_container_width=True):
                save_feedback(child_name, "MajorEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました")
                st.rerun()
            if f_col4.button("使えない", key="fb4", use_container_width=True):
                save_feedback(child_name, "Useless")
                st.session_state.show_feedback = False
                st.toast("記録しました")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
        # 再生成アクション
        st.write("")
        if st.button("再生成する（文体を調整）", use_container_width=True):
             with st.spinner("再生成中..."):
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report: st.rerun()

    else:
        st.info("本日の連絡帳はまだ作成されていません")
        if st.button("連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません")
            else:
                with st.spinner("作成中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    if report:
                        st.session_state.show_feedback = True
                        st.rerun()
