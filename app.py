import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & Material Design CSS
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="centered") # 集中させるためcenteredに変更

# マテリアルデザイン適用CSS
st.markdown("""
<style>
    /* ========== 全体設定 ========== */
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Roboto', 'Noto Sans JP', sans-serif;
        color: #263238; /* Blue Grey 900 */
        background-color: #F7F9FA; /* Base Color */
    }
    
    /* Streamlitのデフォルト背景を上書き */
    .stApp {
        background-color: #F7F9FA;
    }

    /* ========== コンポーネント: カード (Surface) ========== */
    div[data-testid="stVerticalBlock"] > div {
        /* コンテナごとの余白調整はPython側で行うが、全体的なリズムを整える */
    }
    
    .material-card {
        background-color: #FFFFFF;
        padding: 32px;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24); /* Elevation 1 */
        margin-bottom: 24px;
        border: 1px solid #ECEFF1;
    }

    /* ========== タイポグラフィ ========== */
    h1 {
        font-weight: 700 !important;
        color: #1A237E !important; /* Deep Indigo */
        font-size: 1.75rem !important;
        letter-spacing: -0.02em !important;
        margin-bottom: 0.5rem !important;
    }
    h2, h3 {
        font-weight: 500 !important;
        color: #37474F !important;
        letter-spacing: 0.02em !important;
    }
    p, li, label {
        color: #455A64 !important; /* Blue Grey 700 */
        line-height: 1.7 !important;
    }

    /* ========== 入力フォーム (Inputs) ========== */
    .stSelectbox > div > div, .stTextInput > div > div {
        background-color: #FFFFFF !important;
        border: 1px solid #B0BEC5 !important; /* Blue Grey 200 */
        border-radius: 4px !important;
        color: #263238 !important;
        box-shadow: none !important;
    }
    /* フォーカス時 */
    .stSelectbox > div > div:focus-within {
        border-color: #3949AB !important; /* Accent Color */
        border-width: 2px !important;
    }

    /* ========== ボタン (Buttons) ========== */
    /* Primary Action */
    div.stButton > button {
        background-color: #3949AB !important; /* Indigo 600 */
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 4px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.16) !important; /* Elevation 2 */
        font-weight: 500 !important;
        letter-spacing: 0.05em !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.2s ease !important;
        text-transform: uppercase !important; /* Material Standard */
        width: 100%;
    }
    div.stButton > button:hover {
        background-color: #303F9F !important; /* Indigo 700 */
        box-shadow: 0 4px 8px rgba(0,0,0,0.2) !important; /* Elevation 4 */
    }
    div.stButton > button:active {
        box-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    }

    /* Secondary / Ghost Buttons (透明背景にしたい場合) */
    button[kind="secondary"] {
        background-color: transparent !important;
        border: 1px solid #3949AB !important;
        color: #3949AB !important;
        box-shadow: none !important;
    }

    /* ========== タブ (Tabs) ========== */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        color: #546E7A !important;
        font-weight: 500 !important;
        border-bottom: 2px solid transparent !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #3949AB !important;
        border-bottom: 2px solid #3949AB !important;
    }

    /* ========== その他UIパーツ ========== */
    /* 音声入力等のウィジェット背景 */
    .stAudioInput {
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 10px;
        border: 1px solid #B0BEC5;
    }
    
    /* コーチマーク・ヒントボックス */
    .hint-box {
        background-color: #E8EAF6; /* Indigo 50 */
        border-left: 4px solid #3949AB;
        padding: 16px;
        margin-bottom: 24px;
        border-radius: 0 4px 4px 0;
        color: #283593;
    }
    .hint-label {
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        color: #3949AB;
        margin-bottom: 4px;
    }
    
    /* ステータス表示 */
    .status-text {
        font-size: 0.85rem;
        color: #78909C;
        text-align: right;
        margin-top: -10px;
        margin-bottom: 20px;
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
# 2. ロジック (絵文字排除)
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
    # (省略: 以前と同じロジック)
    return 0

def get_staff_style_examples(staff_name):
    # (省略: 以前と同じロジック)
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

def get_hint(child_name):
    # デモ用
    return "本人の興味のある話題から会話を広げ、肯定的な反応を引き出す。"

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"担当職員「{staff_name}」の過去の文体（語尾、リズム）を模倣してください。\n{examples_text}"
    else:
        # プリセット名から絵文字を除去し、トーンを定義
        presets = {
            "親しみ（柔らかめ）": "文体: 非常に柔らかい口語調。共感的。",
            "標準（丁寧）": "文体: 標準的な丁寧語（です・ます）。",
            "論理（簡潔）": "文体: 簡潔、事実中心。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービス 連絡帳作成タスク。
    
    児童名: {child_name}
    担当職員: {staff_name}
    支援ヒント: {current_hint}
    
    指示:
    1. 以下の文体指示に従うこと: {style_instruction}
    2. マークダウンは使用しない。
    3. 絵文字は一切使用しない。
    
    入力:
    {combined_text}

    出力形式:
    保護者様へ
    ...
    <<<SEPARATOR>>>
    職員間共有
    ...
    <<<NEXT_HINT>>>
    (次回ヒント)
    <<<HINT_CHECK>>>
    YES/NO
    """
    
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "作成開始"}]
        )
        full_text = message.content[0].text
        parts = full_text.split("<<<NEXT_HINT>>>")
        report_content = parts[0].strip()
        remaining = parts[1].strip() if len(parts) > 1 else ""
        parts2 = remaining.split("<<<HINT_CHECK>>>")
        next_hint = parts2[0].strip() if parts2 else ""
        hint_used = parts2[1].strip() if len(parts2) > 1 else "UNKNOWN"
        
        if save_data(child_name, report_content, "REPORT", next_hint, hint_used, staff_name, retry_count):
            return report_content, next_hint
        return None, None
    except Exception as e:
        return None, None

# ---------------------------------------------------------
# 3. UI 構築 (Material Layout)
# ---------------------------------------------------------

# ヘッダーエリア
st.markdown("<h1>連絡帳作成システム</h1>", unsafe_allow_html=True)
st.markdown("<p class='status-text'>System Ready</p>", unsafe_allow_html=True)

# データ取得
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

# === 設定カード ===
st.markdown('<div class="material-card">', unsafe_allow_html=True)
st.markdown("<h3>設定</h3>", unsafe_allow_html=True)
col1, col2 = st.columns(2)
with col1:
    staff_name = st.selectbox("担当職員", staff_list)
with col2:
    child_name = st.selectbox("対象児童", child_list)

# 文体学習ステータス（シンプルに）
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.caption(f"✓ {staff_name} の文体を学習済み")
    style_preset = "自動学習"
else:
    style_preset = st.radio("文体プリセット", ["親しみ（柔らかめ）", "標準（丁寧）", "論理（簡潔）"], horizontal=True)

current_hint = get_hint(child_name)
if current_hint:
    st.markdown(f"""
    <div class="hint-box">
        <div class="hint-label">Today's Focus</div>
        {current_hint}
    </div>
    """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True) # End Card

# === メインタブエリア ===
tab1, tab2 = st.tabs(["記録入力", "出力・検証"])

with tab1:
    st.markdown('<div class="material-card">', unsafe_allow_html=True)
    st.markdown("<h3>音声メモ</h3>", unsafe_allow_html=True)
    
    if "audio_key" not in st.session_state: st.session_state.audio_key = 0
    
    audio_val = st.audio_input("録音", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        with st.spinner("処理中..."):
            text = transcribe_audio(audio_val)
        if text:
            st.text_area("認識結果", text, height=100)
            col_save, col_discard = st.columns(2)
            with col_save:
                if st.button("保存する"):
                    save_data(child_name, text, "MEMO", "", "", staff_name)
                    st.success("保存完了")
                    st.session_state.audio_key += 1
                    st.rerun()
            with col_discard:
                if st.button("破棄", type="secondary"): # typeは効かないがCSSクラスがないため無視される。Secondary的な見た目はCSSでやる必要があるが、ここでは標準ボタンで統一
                    st.session_state.audio_key += 1
                    st.rerun()
    
    st.markdown("---")
    memos, _ = fetch_todays_memos(child_name)
    if memos:
        st.markdown("#### 今日の記録一覧")
        st.code(memos, language=None)
    else:
        st.caption("本日の記録はまだありません")
        
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="material-card">', unsafe_allow_html=True)
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown("<h3>作成結果</h3>", unsafe_allow_html=True)
        
        parts = existing_report.split("<<<SEPARATOR>>>")
        st.subheader("1. 保護者様へ")
        st.text_area("保護者用", parts[0].strip(), height=300)
        
        if len(parts) > 1:
            st.subheader("2. 職員共有")
            st.text_area("職員用", parts[1].strip(), height=150)
        
        st.markdown("---")
        st.markdown("#### 品質検証フィードバック")
        st.caption("この出力の修正コストを選択してください")
        
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("修正なし"):
            save_feedback(child_name, "NoEdit")
            st.toast("記録しました")
        if c2.button("微修正"):
            save_feedback(child_name, "MinorEdit")
            st.toast("記録しました")
        if c3.button("要修正"):
            save_feedback(child_name, "MajorEdit")
            st.toast("記録しました")
        if c4.button("利用不可"):
            save_feedback(child_name, "Useless")
            st.toast("記録しました")
            
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("再生成する"):
            with st.spinner("再構成中..."):
                report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: st.rerun()
                
    else:
        st.info("記録をもとに連絡帳を作成します")
        if st.button("連絡帳を作成"):
            if not memos:
                st.error("メモデータがありません")
            else:
                with st.spinner("作成中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    if report: st.rerun()
                    
    st.markdown('</div>', unsafe_allow_html=True)
