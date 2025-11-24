import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (UI刷新版)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide", initial_sidebar_state="collapsed")
JST = pytz.timezone('Asia/Tokyo')

# CSSによるオフホワイト基調・高可視性デザイン
st.markdown("""
<style>
    /* 全体の背景色をオフホワイトに */
    .stApp {
        background-color: #F8F9FA;
        color: #333333;
    }
    
    /* コンテナ（カード）のデザイン */
    .css-1y4p8pa, .stMarkdown, .stButton {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
    }

    /* コーチマーク（ヒント表示） - 視認性重視 */
    .coach-mark {
        background-color: #FFFFFF;
        border-left: 6px solid #FF9800;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        padding: 15px 20px;
        margin-bottom: 20px;
        border-radius: 8px;
    }
    .coach-title {
        font-weight: bold;
        color: #E65100;
        font-size: 1.1em;
        margin-bottom: 5px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    /* 完了メッセージボックス - 安心感のある青 */
    .success-box {
        background-color: #FFFFFF;
        border: 2px solid #E3F2FD;
        color: #0D47A1;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 1.2em;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(227, 242, 253, 0.5);
    }
    
    /* スタイル学習済みバッジ */
    .style-box {
        background-color: #FFFFFF;
        border: 1px solid #E1BEE7;
        border-left: 5px solid #9C27B0;
        padding: 12px;
        border-radius: 6px;
        font-size: 0.95em;
        color: #4A148C;
        margin-bottom: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    /* タブのデザイン調整 */
    button[data-baseweb="tab"] {
        background-color: white;
        border-radius: 4px 4px 0 0;
        margin-right: 2px;
        border: 1px solid #E0E0E0;
        border-bottom: none;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #FFFFFF !important;
        border-top: 3px solid #0288D1 !important;
        font-weight: bold !important;
        color: #0288D1 !important;
    }
    
    /* 入力エリアの強調 */
    .stTextArea textarea {
        border: 1px solid #CFD8DC;
        border-radius: 6px;
    }
    
    /* ボタンの視認性向上 */
    .stButton button {
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
# 2. データ取得・分析ロジック
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

def get_todays_hint_from_history(child_name):
    """前回のレポートから次回のヒントを取得"""
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
        style_instruction = f"あなたは担当職員「{staff_name}」です。以下の過去の執筆例の文体や雰囲気を強く模倣してください。\n【執筆例】\n{examples_text}"
    else:
        presets = {
            "親しみ（絵文字あり・柔らかめ）": "文体: とても柔らかく、共感的に。絵文字を適度に使用（✨😊など）。",
            "標準（丁寧・バランス）": "文体: 丁寧語（です・ます）。客観的な事実と温かい感想をバランスよく。",
            "論理（箇条書き・簡潔）": "文体: 簡潔に。事実を中心に記述。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    児童名: {child_name} | 担当職員: {staff_name} | 本日のヒント: {current_hint}
    
    {style_instruction}
    
    # 入力された記録
    {combined_text}

    # 検証: 記録内に「ヒント」を意識した行動があればYES、なければNO。
    
    # 出力ルール: マークダウン禁止。以下のセパレーターを使用。
    <<<SEPARATOR>>> (保護者用と職員用の間)
    <<<NEXT_HINT>>> (職員用と次回ヒントの間)
    <<<HINT_CHECK>>> (次回ヒントと判定の間)
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
# 3. UI実装
# ---------------------------------------------------------
st.title("連絡帳メーカー 📝")

child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

# 1. 設定エリア（白背景のカード風に）
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        staff_name = st.selectbox("担当職員", staff_list)
    with col2:
        child_name = st.selectbox("対象児童", child_list)

# 2. 学習状況とヒント表示
current_hint = get_todays_hint_from_history(child_name)
past_examples_count = len(get_staff_style_examples(staff_name))

col_hint, col_style = st.columns([2, 1])

with col_hint:
    if current_hint:
        st.markdown(f"""
        <div class="coach-mark">
            <div class="coach-title">💡 今日の関わりのヒント</div>
            {current_hint}
        </div>
        """, unsafe_allow_html=True)

with col_style:
    if past_examples_count > 0:
        st.markdown(f"<div class='style-box'>🤖 文体学習中<br>データ数: {past_examples_count}件</div>", unsafe_allow_html=True)
        style_preset = "自動学習"
    else:
        style_preset = st.radio("文体スタイル", ["親しみ", "標準", "論理"], horizontal=True, label_visibility="collapsed")
        st.caption("👆 文体を選択（データが溜まると自動化されます）")

if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

# タブ切り替え
tab1, tab2 = st.tabs(["メモ入力", "作成・検証"])

with tab1:
    st.write("##### 🎙️ 音声で記録")
    audio_val = st.audio_input("録音開始", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        with st.spinner("文字起こし中..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.success(f"認識完了: {text}")
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("この内容で保存", type="primary", use_container_width=True):
                    if save_data(child_name, text, "MEMO", "", "", staff_name):
                        st.toast("保存しました", icon="✅")
                        st.session_state.audio_key += 1
                        st.rerun()
            with col_cancel:
                if st.button("破棄してやり直す", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()

    st.write("---")
    if st.button(f"{child_name}さんの今日の記録を確認", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.text_area("保存済みメモ", st.session_state.memos_preview, height=150, disabled=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    def display_report_card(title, content):
        st.markdown(f"### {title}")
        st.code(content, language=None)

    if existing_report:
        st.markdown("<div class='success-box'>🎉 連絡帳の下書きができました</div>", unsafe_allow_html=True)
        
        parts = existing_report.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else "（職員用記録なし）"

        display_report_card("1. 保護者連絡用", parent_part)
        st.divider()
        display_report_card("2. 職員共有用", staff_part)
        
        # フィードバックUI（修正コスト評価）
        if st.session_state.get("show_feedback", False):
            st.info("【検証】この下書きの修正コストを教えてください")
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("そのまま使える", use_container_width=True):
                save_feedback(child_name, "NoEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました！", icon="✨")
                st.rerun()
            if c2.button("少し直す", use_container_width=True):
                save_feedback(child_name, "MinorEdit")
                st.session_state.show_feedback = False
                st.toast("記録しました", icon="👍")
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
        if st.button("🔄 内容を更新して再生成する"):
             with st.spinner("文体や構成を再調整中..."):
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report:
                     st.session_state.show_feedback = True
                     st.rerun()

    else:
        st.info("まだ連絡帳が作成されていません。メモが十分にあれば作成できます。")
        if st.button("連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません。まずはタブ1でメモを入力してください。")
            else:
                with st.spinner("AIが過去の文体に合わせて執筆中..."):
                    report, next_hint = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report:
                    st.session_state.show_feedback = True
                    st.rerun()
