import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (UI刷新)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

# デザインCSS (オフホワイト・シンプル・高コントラスト)
st.markdown("""
<style>
    /* 全体のフォントと背景 */
    .stApp {
        background-color: #F8F9FA;
        color: #1E293B;
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
    }

    /* タイトルまわり */
    h1 {
        color: #1E293B !important;
        font-weight: 700 !important;
        border-bottom: 2px solid #E2E8F0;
        padding-bottom: 10px;
    }
    
    /* タブのデザイン */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        border: none !important;
        color: #64748B !important; /* Main color (Low Saturation) */
        font-weight: bold !important;
        font-size: 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #2563EB !important; /* Accent color */
        border-bottom: 3px solid #2563EB !important;
    }

    /* ボタン (Primary - Accent Color) */
    div.stButton > button[kind="primary"] {
        background-color: #2563EB !important;
        color: white !important;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: bold;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        transition: all 0.2s;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #1D4ED8 !important;
    }

    /* ボタン (Secondary - Main Color) */
    div.stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        color: #475569 !important;
        border-radius: 6px;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: #94A3B8 !important;
        color: #1E293B !important;
    }

    /* コーチマーク (ヒント表示) */
    .coach-mark {
        background-color: #EFF6FF; /* Very Light Accent */
        border-left: 4px solid #2563EB;
        padding: 16px;
        margin-bottom: 20px;
        border-radius: 0 6px 6px 0;
        color: #1E3A8A;
    }
    .coach-title {
        font-weight: bold;
        color: #2563EB;
        font-size: 1.0em;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* 成功メッセージエリア */
    .success-box {
        background-color: #F0FDF4; /* 薄い緑（成功色）だが彩度低め */
        border: 1px solid #BBF7D0;
        color: #15803D;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 20px;
    }

    /* 学習済み表示 */
    .style-box {
        background-color: #F1F5F9; /* Off-white Gray */
        border: 1px solid #E2E8F0;
        padding: 10px 15px;
        border-radius: 6px;
        font-size: 0.9em;
        color: #475569;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* コードブロックの背景を白に */
    .stCode {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0;
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
# 2. データ取得・分析ロジック (変更なし)
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
    except Exception as e:
        st.error(f"リスト読込エラー: {e}")
        return [], []

def get_todays_hint_from_history(child_name):
    """過去のレポートから今日のヒントを取得"""
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

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"担当職員「{staff_name}」の過去の文体（語尾・雰囲気）を模倣してください。\n【過去の例】\n{examples_text}"
    else:
        presets = {
            "親しみ（絵文字あり）": "文体: 柔らかく、共感的に。絵文字を適度に使用（✨😊）。",
            "標準（丁寧）": "文体: 丁寧語（です・ます）。客観的事実と感想をバランスよく。",
            "論理（簡潔）": "文体: 簡潔に。事実を中心に記述。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービス連絡帳作成。
    児童: {child_name}, 職員: {staff_name}
    本日のヒント: {current_hint}
    
    {style_instruction}
    
    入力記録:
    {combined_text}
    
    出力構成:
    1. 保護者用 (今日の様子, 活動内容, ご連絡)
    <<<SEPARATOR>>>
    2. 職員用 (ヒント振り返り, 特記事項)
    <<<NEXT_HINT>>>
    (次回ヒント1文)
    <<<HINT_CHECK>>>
    YES/NO (ヒント活用有無)
    """
    
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "作成実行"}]
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
# 3. UI実装
# ---------------------------------------------------------
st.title("連絡帳メーカー")

# Session State初期化
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

# 1. 担当者と児童の選択
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

col1, col2 = st.columns(2)
with col1:
    staff_name = st.selectbox("担当職員", staff_list)
with col2:
    child_name = st.selectbox("対象児童", child_list)

current_hint = get_todays_hint_from_history(child_name)

# ヒント表示 (Accent Colorを利用)
with st.expander("💡 本日の関わりのヒント", expanded=True):
    st.markdown(f"""
    <div class="coach-mark">
        <div class="coach-title">
            <span>KEY POINT</span>
        </div>
        {current_hint}
    </div>
    """, unsafe_allow_html=True)

# 学習状況表示 (Main Color - Low Saturation)
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.markdown(f"""
    <div class='style-box'>
        <span>🤖</span>
        <span><b>{staff_name}</b> さんの文体を学習済みです（過去の良質な記録 {past_examples_count}件に基づく）</span>
    </div>
    """, unsafe_allow_html=True)
    style_preset = "自動学習"
else:
    st.caption("スタイルを選択してください（データが蓄積されると自動学習に切り替わります）")
    style_preset = st.radio("", ["親しみ（絵文字あり）", "標準（丁寧）", "論理（簡潔）"], horizontal=True)

# メインエリア
st.markdown("---")
tab1, tab2 = st.tabs(["📝 メモ入力", "📤 出力・検証"])

with tab1:
    st.caption("音声またはテキストで記録を入力してください")
    audio_val = st.audio_input("録音", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        with st.spinner("文字起こし中..."):
            text = transcribe_audio(audio_val)
        if text:
            st.info(f"認識結果: {text}")
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("保存する", type="primary", use_container_width=True):
                    if save_data(child_name, text, "MEMO", "", "", staff_name):
                        st.toast("保存しました", icon="✅")
                        st.session_state.audio_key += 1
                        st.rerun()
            with c2:
                if st.button("破棄", type="secondary", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()

    if st.button(f"現在の記録を確認", type="secondary", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.text_area("今日の記録", st.session_state.memos_preview, height=150, disabled=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown("<div class='success-box'>🎉 連絡帳の作成が完了しました</div>", unsafe_allow_html=True)
        
        parts = existing_report.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else ""

        st.subheader("1. 保護者用")
        st.code(parent_part, language=None)
        
        st.subheader("2. 職員共有用")
        st.code(staff_part, language=None)
        
        # フィードバックUI
        if st.session_state.get("show_feedback", False):
            st.markdown("---")
            st.markdown("**【検証】この文章の修正コストを教えてください**")
            
            # Simple 4 buttons layout
            fb1, fb2, fb3, fb4 = st.columns(4)
            if fb1.button("そのままOK", use_container_width=True, type="primary"):
                save_feedback(child_name, "NoEdit")
                st.session_state.show_feedback = False
                st.toast("最高評価を記録しました", icon="✨")
                st.rerun()
            if fb2.button("少し直す", use_container_width=True):
                save_feedback(child_name, "MinorEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました", icon="👍")
                st.rerun()
            if fb3.button("結構直す", use_container_width=True):
                save_feedback(child_name, "MajorEdit")
                st.session_state.show_feedback = False
                st.toast("改善します", icon="🙇")
                st.rerun()
            if fb4.button("使えない", use_container_width=True):
                save_feedback(child_name, "Useless")
                st.session_state.show_feedback = False
                st.toast("申し訳ありません", icon="💦")
                st.rerun()

        st.markdown("---")
        if st.button("🔄 内容を更新して再生成", type="secondary", use_container_width=True):
             with st.spinner("文体を調整して再生成中..."):
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report:
                     st.session_state.show_feedback = True
                     st.rerun()

    else:
        st.info("まだ連絡帳が作成されていません。")
        if st.button("連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません")
            else:
                with st.spinner("AIが執筆中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    if report:
                        st.session_state.show_feedback = True
                        st.rerun()
