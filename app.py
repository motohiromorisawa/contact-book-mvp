import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (Material Design System)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

# マテリアルデザイン・CSS注入
st.markdown("""
<style>
    /* Global Settings */
    .stApp {
        background-color: #F9FAFB; /* Base: Off-white */
        color: #263238; /* Text: High Contrast */
        font-family: "Roboto", "Helvetica", "Hiragino Kaku Gothic ProN", sans-serif;
    }
    
    /* Typography */
    h1, h2, h3 {
        color: #37474F;
        font-weight: 500;
        letter-spacing: 0.02em;
    }
    p, div, label, span {
        line-height: 1.8; /* 余白広め */
        color: #455A64;
    }

    /* Cards (Material Surface) */
    .material-card {
        background-color: #FFFFFF;
        padding: 24px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.06);
        margin-bottom: 24px;
        border: 1px solid #ECEFF1;
    }

    /* Buttons (Material Style) */
    div.stButton > button {
        background-color: #FFFFFF;
        color: #455A64; /* Main: Low Saturation */
        border: 1px solid #CFD8DC;
        border-radius: 4px;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.2s ease-in-out;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    div.stButton > button:hover {
        border-color: #1976D2;
        color: #1976D2;
        background-color: #F5F9FF;
    }
    /* Primary Button */
    div.stButton > button[kind="primary"] {
        background-color: #1976D2; /* Accent: High Saturation */
        color: #FFFFFF;
        border: none;
        box-shadow: 0 2px 4px rgba(25, 118, 210, 0.3);
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1565C0;
        box-shadow: 0 4px 8px rgba(25, 118, 210, 0.4);
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        font-size: 16px !important;
        font-weight: bold !important;
        color: #78909C !important;
        padding-bottom: 12px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #1976D2 !important; /* Accent */
        border-bottom: 2px solid #1976D2 !important;
    }

    /* Custom Classes for Content */
    .hint-box {
        background-color: #E3F2FD; /* Light Blue 50 */
        border-left: 4px solid #1976D2;
        padding: 16px 20px;
        border-radius: 4px;
        margin-bottom: 20px;
        color: #0D47A1;
    }
    .hint-title {
        font-weight: bold;
        font-size: 0.9em;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 8px;
        color: #1976D2;
    }
    .success-box {
        background-color: #E8F5E9; /* Green 50 (Success) */
        color: #2E7D32;
        padding: 16px;
        border-radius: 4px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 24px;
        border: 1px solid #C8E6C9;
    }
    .style-box {
        font-size: 0.85em;
        color: #546E7A;
        background-color: #F5F5F5;
        padding: 8px 12px;
        border-radius: 4px;
        display: inline-block;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# API設定 (変更なし)
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. データ取得・分析ロジック
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
        st.error(f"リスト読込エラー: {e}")
        return [], []

def get_retry_count(child_name):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        count = 0
        for row in rows:
            if len(row) >= 4:
                if row[0].startswith(today_str) and row[1] == child_name and row[3] == "REPORT":
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
                    r_feedback = row[6] if len(row) > 6 else ""
                    if r_feedback in ["NoEdit", "MinorEdit"]:
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
        st.error(f"保存エラー: {e}")
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
    # (既存ロジック)
    return "初回、または過去の記録なし。本人の様子をよく観察し、信頼関係を築く。"

# ---------------------------------------------------------
# 3. 生成ロジック
# ---------------------------------------------------------
def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"【{staff_name}の過去の執筆例】\n{examples_text}\n上記の文体を模倣してください。"
    else:
        presets = {
            "親しみ": "柔らかく共感的。絵文字使用。",
            "標準": "丁寧語。事実と感想のバランス。",
            "論理": "簡潔。事実中心。"
        }
        style_instruction = f"文体: {presets.get(style_preset, '標準')}"

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    児童: {child_name} / 担当: {staff_name}
    ヒント: {current_hint}
    指示: {style_instruction}
    
    フォーマット:
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
            messages=[{"role": "user", "content": f"記録:\n{combined_text}"}]
        )
        full_text = message.content[0].text
        parts = full_text.split("<<<NEXT_HINT>>>")
        report_content = parts[0].strip()
        remaining = parts[1].strip() if len(parts) > 1 else ""
        parts2 = remaining.split("<<<HINT_CHECK>>>")
        next_hint = parts2[0].strip() if parts2 else ""
        hint_used = parts2[1].strip() if len(parts2) > 1 else "UNKNOWN"
        
        save_data(child_name, report_content, "REPORT", next_hint, hint_used, staff_name, retry_count)
        return report_content, next_hint
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

# ヘッダーエリア
st.markdown("<h1 style='margin-bottom: 24px;'>連絡帳メーカー <span style='font-size:0.5em; color:#90A4AE; vertical-align:middle;'>Material Ver.</span></h1>", unsafe_allow_html=True)

# 1. 設定カード
with st.container():
    st.markdown('<div class="material-card">', unsafe_allow_html=True)
    st.markdown("### 📝 設定")
    
    child_list, staff_list = get_lists()
    if not staff_list: staff_list = ["職員A", "職員B"]
    
    col1, col2 = st.columns(2)
    with col1:
        staff_name = st.selectbox("担当職員", staff_list)
    with col2:
        child_name = st.selectbox("対象児童", child_list)

    # 文体学習ステータス
    past_examples_count = len(get_staff_style_examples(staff_name))
    if past_examples_count > 0:
        st.markdown(f"<div class='style-box'>✨ {staff_name}さんの文体を学習済み (精度: 高)</div>", unsafe_allow_html=True)
        style_preset = "自動学習"
    else:
        st.markdown(f"<div class='style-box'>🔰 データ不足のためプリセットを使用</div>", unsafe_allow_html=True)
        style_preset = st.radio("文体プリセット", ["親しみ", "標準", "論理"], horizontal=True, label_visibility="collapsed")
    
    st.markdown('</div>', unsafe_allow_html=True)

# ヒント取得
current_hint = get_todays_hint_from_history(child_name)

# 2. メインエリア
tab1, tab2 = st.tabs(["入力・記録", "出力・検証"])

with tab1:
    st.markdown('<div class="material-card">', unsafe_allow_html=True)
    
    # ヒント表示
    if current_hint:
        st.markdown(f"""
        <div class="hint-box">
            <div class="hint-title">Daily Mission</div>
            {current_hint}
        </div>
        """, unsafe_allow_html=True)

    # 音声入力
    if "audio_key" not in st.session_state: st.session_state.audio_key = 0
    audio_val = st.audio_input("音声を記録する", key=f"recorder_{st.session_state.audio_key}")

    if audio_val:
        st.divider()
        with st.spinner("音声をテキスト化しています..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.info(text)
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("記録を保存", type="primary", use_container_width=True):
                    if save_data(child_name, text, "MEMO", "", "", staff_name):
                        st.toast("保存しました", icon="✅")
                        st.session_state.audio_key += 1
                        st.rerun()
            with col_cancel:
                if st.button("キャンセル", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()
    
    # メモ一覧
    memos, _ = fetch_todays_memos(child_name)
    if memos:
        st.markdown("### 今日のメモ")
        st.text_area("内容", memos, height=150, disabled=True)
    else:
        st.caption("まだ記録がありません")
        
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown('<div class="material-card">', unsafe_allow_html=True)
        st.markdown('<div class="success-box">🎉 作成完了</div>', unsafe_allow_html=True)
        
        parts = existing_report.split("<<<SEPARATOR>>>")
        
        st.subheader("1. 保護者用")
        st.code(parts[0].strip(), language=None)
        
        st.subheader("2. 職員共有用")
        staff_part = parts[1].strip() if len(parts) > 1 else "（なし）"
        st.code(staff_part, language=None)

        # フィードバック (Material Cards for layout)
        if st.session_state.get("show_feedback", True):
            st.divider()
            st.markdown("#### 検証: 修正コストの評価")
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("そのまま使える", use_container_width=True, type="primary"):
                save_feedback(child_name, "NoEdit")
                st.session_state.show_feedback = False
                st.toast("Perfect!", icon="✨")
                st.rerun()
            if c2.button("少し直す", use_container_width=True):
                save_feedback(child_name, "MinorEdit")
                st.session_state.show_feedback = False
                st.toast("Saved.", icon="👍")
                st.rerun()
            if c3.button("結構直す", use_container_width=True):
                save_feedback(child_name, "MajorEdit")
                st.session_state.show_feedback = False
                st.rerun()
            if c4.button("使えない", use_container_width=True):
                save_feedback(child_name, "Useless")
                st.session_state.show_feedback = False
                st.rerun()
        
        st.divider()
        if st.button("再生成する (文体を微調整)", use_container_width=True):
             with st.spinner("チューニング中..."):
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report: st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.markdown('<div class="material-card">', unsafe_allow_html=True)
        st.info("まだ連絡帳が作成されていません。")
        
        if st.button("AI連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("メモがないため作成できません。")
            else:
                with st.spinner("AIが思考中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    if report:
                        st.session_state.show_feedback = True
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
