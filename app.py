import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (Clean & Simple)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="centered") # 集中するためcenteredに変更
JST = pytz.timezone('Asia/Tokyo')

# シンプルで高コントラストなCSS
st.markdown("""
<style>
    /* 全体の背景と文字色 */
    .stApp {
        background-color: #F9FAFB;
        color: #1F2937;
    }
    
    /* 入力エリアの背景を白にして浮き立たせる */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        color: #1F2937 !important;
    }

    /* タブのデザイン - シンプルに */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        font-weight: 600 !important;
        color: #6B7280 !important; /* 非アクティブはグレー */
        font-size: 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #2563EB !important; /* アクティブはブルー */
        border-bottom: 2px solid #2563EB !important;
    }

    /* メインボタン (Primary) */
    div.stButton > button[kind="primary"] {
        background-color: #2563EB !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: bold !important;
        padding: 0.5rem 1rem !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1D4ED8 !important;
    }

    /* サブボタン (Secondary) - 枠線のみ */
    div.stButton > button {
        background-color: #FFFFFF !important;
        color: #374151 !important;
        border: 1px solid #D1D5DB !important;
        border-radius: 6px !important;
    }
    div.stButton > button:hover {
        border-color: #2563EB !important;
        color: #2563EB !important;
    }

    /* ヒントボックス (シンプル) */
    .simple-box {
        background-color: #FFFFFF;
        border-left: 4px solid #2563EB;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 0 4px 4px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .box-title {
        font-size: 0.9rem;
        color: #2563EB;
        font-weight: bold;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* 完了メッセージ */
    .success-msg {
        color: #059669; /* 成功時は落ち着いたグリーン(色相例外だが機能色として) */
        font-weight: bold;
        padding: 10px;
        background-color: #ECFDF5;
        border-radius: 6px;
        text-align: center;
        margin-bottom: 20px;
        border: 1px solid #D1FAE5;
    }

    h1, h2, h3 {
        font-family: 'Helvetica Neue', Arial, sans-serif;
        color: #111827 !important;
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
# 2. ロジック (文体学習・計測・生成)
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
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        count = 0
        for row in rows:
            if len(row) >= 4 and row[0].startswith(today_str) and row[1] == child_name and row[3] == "REPORT":
                count += 1
        return count
    except:
        return 0

def get_staff_style_examples(staff_name):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        examples = []
        for row in reversed(rows):
            if len(row) >= 8 and row[7] == staff_name and row[3] == "REPORT":
                feedback = row[6] if len(row) > 6 else ""
                if feedback in ["NoEdit", "MinorEdit"]: # 評価の良いもののみ
                    parts = row[2].split("<<<SEPARATOR>>>")
                    examples.append(parts[0].strip())
            if len(examples) >= 3: break
        return examples
    except:
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
    except Exception as e:
        st.error(f"Save Error: {e}")
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

def get_todays_hint_from_history(child_name):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        for row in reversed(rows):
            if len(row) >= 5 and row[1] == child_name and row[3] == "REPORT":
                if row[0].split(" ")[0] < today_str:
                    return row[4]
        return "初回、または過去の記録なし。本人の様子をよく観察し、信頼関係を築く。"
    except:
        return "ヒント取得エラー"

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"あなたは担当職員「{staff_name}」です。以下の過去の執筆例の文体やトーンを模倣してください。\n【例】\n{examples_text}"
    else:
        presets = {
            "Standard": "丁寧語（です・ます）。客観的な事実と温かい感想をバランスよく。",
            "Friendly": "柔らかく、共感的に。保護者に寄り添うトーン。",
            "Logical": "簡潔に。事実を中心に記述。"
        }
        style_instruction = f"文体: {presets.get(style_preset, 'Standard')}"

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    児童: {child_name}, 職員: {staff_name}
    ヒント: {current_hint}
    {style_instruction}
    
    入力: {combined_text}
    
    出力構成:
    【今日の様子】(肯定的なエピソード)
    【活動内容】(箇条書き)
    【ご連絡】
    <<<SEPARATOR>>>
    【ヒント振り返り】
    【特記事項】
    <<<NEXT_HINT>>>
    (次回の具体的ヒント 1文)
    <<<HINT_CHECK>>>
    YES/NO
    """
    
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "作成してください"}]
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
    except:
        return None, None

# ---------------------------------------------------------
# 3. UI実装
# ---------------------------------------------------------
st.title("Daily Report AI") # タイトルも英語でシンプルに（または「連絡帳作成」）

# データ取得
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]
if not child_list: child_list = ["児童A"]

# 設定エリア (シンプルに横並び)
col1, col2 = st.columns(2)
with col1:
    staff_name = st.selectbox("Staff", staff_list, label_visibility="collapsed", placeholder="担当職員")
with col2:
    child_name = st.selectbox("Child", child_list, label_visibility="collapsed", placeholder="対象児童")

# 文体学習ステータス（控えめに表示）
examples_count = len(get_staff_style_examples(staff_name))
if examples_count > 0:
    st.caption(f"✨ {staff_name}さんの過去スタイル({examples_count}件)を適用中")
    style_preset = "Auto"
else:
    style_preset = st.radio("", ["Standard", "Friendly", "Logical"], horizontal=True, label_visibility="collapsed")
    st.caption("👆 スタイルを選択してください（次回から自動学習します）")

st.markdown("---")

# ヒント表示
current_hint = get_todays_hint_from_history(child_name)
if current_hint:
    st.markdown(f"""
    <div class="simple-box">
        <div class="box-title">TODAY'S FOCUS</div>
        {current_hint}
    </div>
    """, unsafe_allow_html=True)

# メイン処理
tab1, tab2 = st.tabs(["INPUT", "OUTPUT"])

with tab1:
    st.write("###### Voice Memo")
    audio_val = st.audio_input("", key="recorder") # ラベルなしでシンプルに
    
    if audio_val:
        with st.spinner("Processing..."):
            text = transcribe_audio(audio_val)
        if text:
            st.info(text)
            if st.button("Save Memo", type="primary", use_container_width=True):
                if save_data(child_name, text, "MEMO", "", "", staff_name):
                    st.toast("Saved!", icon="✅")
                    st.rerun()
    
    st.write("###### History Today")
    memos, _ = fetch_todays_memos(child_name)
    if memos:
        st.text_area("", memos, height=150, disabled=True)
    else:
        st.caption("No memos yet.")

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown('<div class="success-msg">COMPLETED</div>', unsafe_allow_html=True)
        
        # プレビュー
        st.text_area("", existing_report, height=300)
        
        st.write("###### Quality Check (Required)")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Perfect", use_container_width=True):
            save_feedback(child_name, "NoEdit")
            st.toast("Great!")
            st.rerun()
        if c2.button("Good", use_container_width=True):
            save_feedback(child_name, "MinorEdit")
            st.toast("Thanks")
            st.rerun()
        if c3.button("Bad", use_container_width=True):
            save_feedback(child_name, "MajorEdit")
            st.toast("Recorded")
            st.rerun()
        if c4.button("Retry", type="primary", use_container_width=True):
            with st.spinner("Regenerating..."):
                generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                st.rerun()

    else:
        st.info("Ready to generate report.")
        if st.button("Generate Report", type="primary", use_container_width=True):
            if not memos:
                st.error("Please input memos first.")
            else:
                with st.spinner("Writing..."):
                    generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    st.rerun()
