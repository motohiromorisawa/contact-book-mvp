import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. デザイン設定 (High Contrast / Simple Theme)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

# カラーパレット定義
# Base: #F8F9FA (Off-White)
# Main: #0F172A (Deep Navy)
# Accent: #334155 (Slate Blue)

st.markdown("""
<style>
    /* 全体の背景とフォント */
    .stApp {
        background-color: #F8F9FA;
        color: #0F172A;
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif;
    }

    /* タイトル周り */
    h1, h2, h3 {
        color: #0F172A !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }
    
    /* 入力フィールドのラベル */
    .stSelectbox label, .stTextInput label, .stTextArea label {
        color: #0F172A !important;
        font-weight: bold !important;
        font-size: 1rem !important;
    }

    /* ボタン（プライマリ） */
    div.stButton > button[type="primary"] {
        background-color: #0F172A !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: bold !important;
        border-radius: 4px !important;
        padding: 0.6rem 1rem !important;
    }
    div.stButton > button[type="primary"]:hover {
        background-color: #334155 !important;
    }

    /* ボタン（セカンダリ） */
    div.stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        color: #0F172A !important;
        border: 2px solid #0F172A !important;
        font-weight: bold !important;
        border-radius: 4px !important;
    }

    /* タブデザイン */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        color: #64748B !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border-bottom: 2px solid transparent !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #0F172A !important;
        border-bottom: 3px solid #0F172A !important;
    }

    /* カスタムボックス定義 (シンプル・高コントラスト) */
    .box-base {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        padding: 20px;
        border-radius: 0px; /* シンプルさを強調するため角丸なし、または小さく */
        margin-bottom: 1.5rem;
        color: #0F172A;
    }
    
    .box-title {
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748B;
        font-weight: bold;
        margin-bottom: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .box-content {
        font-size: 1.1rem;
        line-height: 1.6;
        font-weight: 500;
    }

    /* 役割別のボーダー色 */
    .border-accent { border-left: 5px solid #0F172A; } /* メイン情報 */
    .border-sub { border-left: 5px solid #94A3B8; } /* 補足情報 */

    /* コードブロックの調整 */
    code {
        color: #0F172A !important;
        background-color: #F1F5F9 !important;
        padding: 2px 5px !important;
        border-radius: 4px !important;
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
        st.error(f"データ読込エラー: {e}")
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
                r_staff = row[7]
                r_type = row[3]
                r_text = row[2]
                r_feedback = row[6] if len(row) > 6 else ""
                
                if r_staff == staff_name and r_type == "REPORT":
                    if r_feedback in ["NoEdit", "MinorEdit"]:
                        parts = r_text.split("<<<SEPARATOR>>>")
                        parent_text = parts[0].strip()
                        examples.append(parent_text)
                        
            if len(examples) >= 3:
                break
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
    # シンプル化のためダミーロジック（実際は前回のコード通り）
    return "具体的に褒めることで自己肯定感を高める。"

# ---------------------------------------------------------
# 3. 生成ロジック
# ---------------------------------------------------------
def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"""
        あなたは担当職員「{staff_name}」です。
        以下の「{staff_name}」が過去に書いた文章の文体、語尾、雰囲気を強く模倣して書いてください。
        【{staff_name}の過去の執筆例】
        {examples_text}
        """
    else:
        presets = {
            "親しみ（絵文字あり）": "文体: とても柔らかく。絵文字を適度に使用（✨😊）。",
            "標準（丁寧）": "文体: 丁寧語（です・ます）。客観的な事実と温かい感想。",
            "論理（簡潔）": "文体: 簡潔に。事実を中心に記述。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    - 児童名: {child_name}
    - 担当職員: {staff_name}
    - 本日のヒント: {current_hint}
    
    {style_instruction}

    # 入力された記録
    {combined_text}

    # 検証タスク
    記録内に「本日のヒント」を意識した行動があればYES、なければNO。

    # 出力ルール
    セパレーター: <<<SEPARATOR>>>, <<<NEXT_HINT>>>, <<<HINT_CHECK>>>
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
# 4. UI実装
# ---------------------------------------------------------
st.title("Daily Report Maker")

# 設定エリア（上部）
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"]

col_conf1, col_conf2 = st.columns(2)
with col_conf1:
    staff_name = st.selectbox("担当職員", staff_list)
with col_conf2:
    child_name = st.selectbox("対象児童", child_list)

current_hint = get_todays_hint_from_history(child_name)
past_examples_count = len(get_staff_style_examples(staff_name))

# ヒント表示（シンプル・高コントラスト）
if current_hint:
    st.markdown(f"""
    <div class="box-base border-accent">
        <div class="box-title">TODAY'S FOCUS</div>
        <div class="box-content">{current_hint}</div>
    </div>
    """, unsafe_allow_html=True)

# 文体学習ステータス
if past_examples_count > 0:
    st.markdown(f"""
    <div class="box-base border-sub" style="padding:10px; font-size:0.9rem;">
        <b>LEARNING STATUS:</b> {staff_name}さんの文体を学習済み ({past_examples_count}件)
    </div>
    """, unsafe_allow_html=True)
    style_preset = "自動学習"
else:
    style_preset = st.radio("文体スタイル設定", ["親しみ（絵文字あり）", "標準（丁寧）", "論理（簡潔）"], horizontal=True)

st.write("---")

# タブエリア
tab1, tab2 = st.tabs(["INPUT", "OUTPUT"])

if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

with tab1:
    st.markdown("#### 音声メモ")
    audio_val = st.audio_input("録音", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        with st.spinner("Processing..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.markdown(f"<div class='box-base'>{text}</div>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("保存する", type="primary", use_container_width=True):
                if save_data(child_name, text, "MEMO", "", "", staff_name):
                    st.toast("Saved!")
                    st.session_state.audio_key += 1
                    st.rerun()
            if c2.button("破棄", use_container_width=True):
                st.session_state.audio_key += 1
                st.rerun()
    
    st.markdown("#### 今日の記録一覧")
    if st.button("更新・表示", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
    
    if st.session_state.memos_preview:
        st.text_area("", st.session_state.memos_preview, height=200, disabled=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        parts = existing_report.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else ""

        st.markdown(f"""
        <div class="box-base border-accent" style="background-color:#F1F5F9; text-align:center; font-weight:bold;">
            DONE
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 保護者用")
        st.code(parent_part, language=None)
        
        st.markdown("### 職員共有用")
        st.code(staff_part, language=None)
        
        # フィードバックUI (修正コスト評価 - High Contrast)
        if st.session_state.get("show_feedback", False):
            st.markdown("#### 修正は必要ですか？")
            col1, col2, col3, col4 = st.columns(4)
            if col1.button("そのまま使える", use_container_width=True):
                save_feedback(child_name, "NoEdit")
                st.session_state.show_feedback = False
                st.rerun()
            if col2.button("少し直す", use_container_width=True):
                save_feedback(child_name, "MinorEdit")
                st.session_state.show_feedback = False
                st.rerun()
            if col3.button("結構直す", use_container_width=True):
                save_feedback(child_name, "MajorEdit")
                st.session_state.show_feedback = False
                st.rerun()
            if col4.button("使えない", use_container_width=True):
                save_feedback(child_name, "Useless")
                st.session_state.show_feedback = False
                st.rerun()

        st.divider()
        if st.button("再生成 (Retry)", type="secondary", use_container_width=True):
            with st.spinner("Regenerating..."):
                report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: 
                    st.session_state.show_feedback = True
                    st.rerun()

    else:
        st.info("未作成")
        if st.button("レポートを作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("メモがありません")
            else:
                with st.spinner("Generating..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report:
                    st.session_state.show_feedback = True
                    st.rerun()
