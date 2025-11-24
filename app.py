import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (グラスモーフィズム実装)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide", page_icon="✨")
JST = pytz.timezone('Asia/Tokyo')

# CSSによるデザイン上書き
st.markdown("""
<style>
    /* 全体の背景：明るいグラデーション */
    .stApp {
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%);
        background-image: linear-gradient(120deg, #a1c4fd 0%, #c2e9fb 100%);
        background-image: linear-gradient(to top, #fff1eb 0%, #ace0f9 100%);
    }

    /* すりガラス風カード (Glassmorphism) */
    .glass-card {
        background: rgba(255, 255, 255, 0.65);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        padding: 20px;
        margin-bottom: 20px;
        color: #333;
    }

    /* タイトル文字 */
    h1, h2, h3 {
        color: #2c3e50 !important;
        font-family: "Helvetica Neue", Arial, sans-serif;
        text-shadow: 1px 1px 2px rgba(255,255,255,0.8);
    }
    
    /* 成功メッセージ */
    .success-glass {
        background: rgba(209, 250, 229, 0.7);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #065F46;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        font-weight: bold;
        backdrop-filter: blur(5px);
        margin-bottom: 15px;
    }

    /* ヒントボックス */
    .hint-glass {
        background: rgba(255, 247, 237, 0.8); 
        border-left: 5px solid #F97316;
        padding: 15px;
        border-radius: 0 12px 12px 0;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* ボタンの調整 */
    .stButton > button {
        border-radius: 20px !important;
        font-weight: bold !important;
        border: none !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1) !important;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 10px rgba(0,0,0,0.2) !important;
    }
    
    /* タブのスタイル調整 */
    button[data-baseweb="tab"] {
        background-color: rgba(255,255,255,0.5) !important;
        border-radius: 10px 10px 0 0 !important;
        margin-right: 5px !important;
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
                if len(row) > 6 and row[6] in ["NoEdit", "MinorEdit"]:
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

def get_todays_hint_from_history(child_name):
    # 簡易実装（実際は履歴から取得）
    return "目線を合わせて、ゆっくり話しかける"

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
            "親しみ（絵文字あり・柔らかめ）": "文体: とても柔らかく、共感的に。絵文字を適度に使用（✨😊など）。",
            "標準（丁寧・バランス）": "文体: 丁寧語（です・ます）。客観的な事実と、温かい感想をバランスよく。",
            "論理（箇条書き・簡潔）": "文体: 簡潔に。事実を中心に記述。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    児童名: {child_name} | 担当職員: {staff_name} | ヒント: {current_hint}
    {style_instruction}
    入力: {combined_text}
    出力ルール: マークダウン禁止。
    構成:
    【今日の様子】...【活動内容】...【ご連絡】...
    <<<SEPARATOR>>>
    【ヒント振り返り】...【特記事項】...
    <<<NEXT_HINT>>>
    (次回の具体的ヒント)
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
# 4. UI実装 (Glassmorphism適用)
# ---------------------------------------------------------
st.title("連絡帳メーカー 🌿")

# --- 設定エリア ---
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
col_head1, col_head2 = st.columns(2)
with col_head1:
    child_list, staff_list = get_lists()
    if not staff_list: staff_list = ["職員A", "職員B"]
    staff_name = st.selectbox("担当職員", staff_list)
with col_head2:
    child_name = st.selectbox("児童名", child_list)

# 文体ステータス表示
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.caption(f"✨ {staff_name}さんの過去データ({past_examples_count}件)から文体を再現中")
    style_preset = "自動学習"
else:
    style_preset = st.radio("文体スタイル", ["親しみ（絵文字あり・柔らかめ）", "標準（丁寧・バランス）", "論理（箇条書き・簡潔）"], horizontal=True)
st.markdown('</div>', unsafe_allow_html=True)

# --- ヒントエリア ---
current_hint = get_todays_hint_from_history(child_name)
if current_hint:
    st.markdown(f"""
    <div class="hint-glass">
        <span style="font-weight:bold; color:#E65100;">💡 本日のPoint:</span> {current_hint}
    </div>
    """, unsafe_allow_html=True)

# --- メイン操作エリア ---
if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

tab1, tab2 = st.tabs(["📝 メモ入力", "🚀 出力・検証"])

with tab1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.write("今日の出来事を音声で吹き込んでください。")
    audio_val = st.audio_input("録音開始", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        with st.spinner("解析中..."):
            text = transcribe_audio(audio_val)
        if text:
            st.info(f"「{text}」")
            if st.button("保存する", type="primary"):
                if save_data(child_name, text, "MEMO", "", "", staff_name):
                    st.toast("保存しました！", icon="✨")
                    st.session_state.audio_key += 1
                    st.rerun()
    
    st.divider()
    if st.button("これまでの記録を見る"):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
    
    if st.session_state.memos_preview:
        st.text_area("記録済みメモ", st.session_state.memos_preview, height=150)
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown(f"""
        <div class="success-glass">
            🎉 {child_name}さんの連絡帳ができました！
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        parts = existing_report.split("<<<SEPARATOR>>>")
        st.markdown("### 🏠 保護者用")
        st.code(parts[0].strip(), language=None)
        
        if len(parts) > 1:
            with st.expander("🏢 職員共有事項を見る"):
                st.code(parts[1].strip(), language=None)
        st.markdown('</div>', unsafe_allow_html=True)

        # フィードバック (Glassmorphismに合わせて微調整)
        if st.session_state.get("show_feedback", True): # デモ用にTrue
            st.markdown('<div class="glass-card" style="border:1px solid #FFCCBC;">', unsafe_allow_html=True)
            st.write("🤔 **検証: この文章はどれくらい修正が必要ですか？**")
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("そのままOK"): 
                save_feedback(child_name, "NoEdit")
                st.toast("最高です！", icon="💎")
            if c2.button("少し直す"): 
                save_feedback(child_name, "MinorEdit")
                st.toast("ありがとうございます", icon="🙏")
            if c3.button("結構直す"): 
                save_feedback(child_name, "MajorEdit")
            if c4.button("使えない"): 
                save_feedback(child_name, "Useless")
            st.markdown('</div>', unsafe_allow_html=True)

        col_re1, col_re2 = st.columns([1, 1])
        with col_re2:
             if st.button("🔄 納得いかないので再生成", help="文体を変えて作り直します"):
                 with st.spinner("書き直しています..."):
                     report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                     if report: st.rerun()

    else:
        st.markdown('<div class="glass-card" style="text-align:center;">', unsafe_allow_html=True)
        st.write("まだ連絡帳が作成されていません。")
        if st.button("✨ 連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("メモがありません！先に「メモ入力」タブで記録してください。")
            else:
                with st.spinner("AIが文体を模倣して執筆中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
