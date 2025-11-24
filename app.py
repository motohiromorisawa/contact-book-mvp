import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. UI設定 & デザイン (CSS Injection)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")

# カラーパレット定義
COLOR_MAIN = "#0F2540"  # ネイビー
COLOR_ACCENT = "#D35400" # オレンジ
COLOR_BG = "#FAFAFA"    # オフホワイト
COLOR_TEXT = "#333333"  # 濃いグレー

st.markdown(f"""
<style>
    /* 全体の背景とフォント設定 */
    .stApp {{
        background-color: {COLOR_BG};
        color: {COLOR_TEXT};
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
    }}
    
    /* ヘッダー周り */
    h1, h2, h3 {{
        color: {COLOR_MAIN} !important;
        font-weight: 700 !important;
    }}
    
    /* 入力エリアの背景を白に */
    .stTextInput > div > div, .stTextArea > div > div {{
        background-color: #FFFFFF !important;
        border-color: #E0E0E0 !important;
        color: {COLOR_MAIN} !important;
    }}

    /* ボタン（標準）：ネイビーの枠線のみ（シンプル） */
    div.stButton > button {{
        background-color: #FFFFFF;
        color: {COLOR_MAIN};
        border: 2px solid {COLOR_MAIN};
        border-radius: 6px;
        font-weight: bold;
        transition: all 0.2s;
    }}
    div.stButton > button:hover {{
        background-color: {COLOR_MAIN};
        color: #FFFFFF;
    }}

    /* タブのデザイン */
    button[data-baseweb="tab"] {{
        background-color: transparent !important;
        color: {COLOR_TEXT} !important;
        font-weight: bold !important;
        border-bottom: 2px solid #E0E0E0 !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {COLOR_ACCENT} !important;
        border-bottom: 3px solid {COLOR_ACCENT} !important;
    }}

    /* カスタムボックス：ヒント表示用（シンプル・高コントラスト） */
    .hint-box {{
        background-color: #FFFFFF;
        border-left: 6px solid {COLOR_MAIN};
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-radius: 0 4px 4px 0;
    }}
    .hint-title {{
        color: {COLOR_MAIN};
        font-weight: bold;
        display: block;
        margin-bottom: 8px;
        font-size: 0.9em;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .hint-content {{
        font-size: 1.1em;
        line-height: 1.6;
        color: {COLOR_TEXT};
    }}

    /* カスタムボックス：学習済みステータス */
    .status-box {{
        padding: 10px;
        font-size: 0.9em;
        color: {COLOR_MAIN};
        border: 1px solid {COLOR_MAIN};
        background-color: #FFFFFF;
        display: inline-block;
        border-radius: 4px;
        margin-bottom: 15px;
    }}

    /* 完了メッセージ */
    .success-text {{
        color: {COLOR_ACCENT};
        font-size: 1.5em;
        font-weight: bold;
        text-align: center;
        margin: 20px 0;
        padding: 20px;
        border: 2px dashed {COLOR_ACCENT};
        background-color: #FFFFFF;
        border-radius: 8px;
    }}
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
# 2. ロジック部 (変更なし)
# ---------------------------------------------------------
def get_lists():
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:B").execute()
        values = sheet.get('values', [])
        children = [row[0] for row in values if len(row) > 0]
        staffs = [row[1] for row in values if len(row) > 1]
        return children, staffs
    except Exception as e:
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
            if len(row) >= 8:
                if row[7] == staff_name and row[3] == "REPORT":
                    feedback = row[6] if len(row) > 6 else ""
                    if feedback in ["NoEdit", "MinorEdit"]:
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
        return "データ取得エラー"

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"あなたは担当職員「{staff_name}」です。以下の過去の執筆例の文体や語尾を強く模倣してください。\n\n【執筆例】\n{examples_text}"
    else:
        presets = {
            "親しみ": "文体: 柔らかく、共感的。絵文字を適度に使用。",
            "標準": "文体: 丁寧語（です・ます）。客観的事実と温かい感想。",
            "論理": "文体: 簡潔に。事実中心。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    
    # 情報
    - 児童: {child_name}
    - 職員: {staff_name}
    - ヒント: {current_hint}

    # 文体指示
    {style_instruction}

    # メモ
    {combined_text}

    # 検証
    ヒントを意識した行動が含まれるかYES/NO判定。

    # 形式
    (マークダウン禁止)
    【今日の様子】...
    【活動内容】...
    【ご連絡】...
    <<<SEPARATOR>>>
    【ヒント振り返り】...
    【特記事項】...
    <<<NEXT_HINT>>>
    (次回ヒント)
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
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None, None

# ---------------------------------------------------------
# 3. UI構築
# ---------------------------------------------------------
st.title("連絡帳メーカー")

child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

# 上部設定エリア：シンプルに
col_conf1, col_conf2 = st.columns(2)
with col_conf1:
    staff_name = st.selectbox("担当職員", staff_list)
with col_conf2:
    child_name = st.selectbox("対象児童", child_list)

# 学習状況表示
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.markdown(f"<div class='status-box'>✔ {staff_name}さんの文体を学習済み ({past_examples_count}件)</div>", unsafe_allow_html=True)
    style_preset = "自動学習"
else:
    style_preset = st.radio("文体スタイル", ["親しみ", "標準", "論理"], horizontal=True)

# ヒント表示
current_hint = get_todays_hint_from_history(child_name)
if current_hint:
    st.markdown(f"""
    <div class="hint-box">
        <span class="hint-title">TODAY'S HINT</span>
        <div class="hint-content">{current_hint}</div>
    </div>
    """, unsafe_allow_html=True)

if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0

# タブエリア
tab1, tab2 = st.tabs(["INPUT (メモ)", "OUTPUT (作成)"])

with tab1:
    audio_val = st.audio_input("音声を記録", key=f"recorder_{st.session_state.audio_key}")
    if audio_val:
        with st.spinner("認識中..."):
            text = transcribe_audio(audio_val)
        if text:
            st.info(f"「{text}」")
            col_act1, col_act2 = st.columns(2)
            if col_act1.button("保存する", use_container_width=True):
                if save_data(child_name, text, "MEMO", "", "", staff_name):
                    st.toast("保存しました")
                    st.session_state.audio_key += 1
                    st.rerun()
            if col_act2.button("破棄", use_container_width=True):
                st.session_state.audio_key += 1
                st.rerun()
    
    st.divider()
    if st.button(f"{child_name}さんの今日の記録を確認", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
    
    if st.session_state.memos_preview:
        st.text_area("記録済みメモ", st.session_state.memos_preview, height=150)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown(f"<div class='success-text'>DONE! 作成完了</div>", unsafe_allow_html=True)
        
        parts = existing_report.split("<<<SEPARATOR>>>")
        
        st.subheader("1. 保護者用")
        st.code(parts[0].strip(), language=None)
        
        st.subheader("2. 職員共有用")
        st.code(parts[1].strip() if len(parts) > 1 else "記録なし", language=None)
        
        st.divider()
        st.markdown("**評価・フィードバック**")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("そのまま使える"): 
            save_feedback(child_name, "NoEdit")
            st.toast("Thank you!")
        if c2.button("少し直す"): 
            save_feedback(child_name, "MinorEdit")
            st.toast("Saved.")
        if c3.button("結構直す"): 
            save_feedback(child_name, "MajorEdit")
            st.toast("Saved.")
        if c4.button("使えない"): 
            save_feedback(child_name, "Useless")
            st.toast("Feedback Saved.")

        st.divider()
        if st.button("再生成する (文体を微調整)", use_container_width=True):
             with st.spinner("AI is thinking..."):
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report: st.rerun()
    else:
        st.info("まだ連絡帳が作成されていません。メモを確認して作成ボタンを押してください。")
        if st.button("連絡帳を生成する", type="primary", use_container_width=True):
            if not memos:
                st.error("メモがありません。まずは記録を入力してください。")
            else:
                with st.spinner("Writing..."):
                    report, next_hint = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: st.rerun()
