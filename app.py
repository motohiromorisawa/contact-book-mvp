import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (ここを大幅変更)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide", initial_sidebar_state="collapsed")
JST = pytz.timezone('Asia/Tokyo')

# デザインCSS: 明るい・透明感・見やすさ
st.markdown("""
<style>
    /* 全体の背景：淡いグラデーションで明るさを演出 */
    .stApp {
        background: linear-gradient(120deg, #fdfbfb 0%, #ebedee 100%);
        background-attachment: fixed;
    }
    
    /* メインコンテナの調整 */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 5rem;
    }

    /* グラスモーフィズム（すりガラス）カードの共通スタイル */
    .glass-card {
        background: rgba(255, 255, 255, 0.85); /* 白の透過 */
        backdrop-filter: blur(12px);           /* ぼかし効果 */
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.6);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        padding: 24px;
        margin-bottom: 24px;
    }

    /* タイトルのスタイル */
    h1 {
        color: #444 !important;
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-weight: 700 !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    /* テキストの可読性向上 */
    p, li, span {
        color: #333333; /* 真っ黒より読みやすい濃いグレー */
        font-size: 16px !important;
        line-height: 1.7 !important;
    }

    /* ボタンのスタイル：角丸で優しい印象に */
    .stButton > button {
        border-radius: 30px !important;
        font-weight: bold !important;
        border: none !important;
        box-shadow: 0 4px 6px rgba(50, 50, 93, 0.11), 0 1px 3px rgba(0, 0, 0, 0.08) !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 7px 14px rgba(50, 50, 93, 0.1), 0 3px 6px rgba(0, 0, 0, 0.08) !important;
    }

    /* タブのスタイル */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        color: #555 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: rgba(255, 255, 255, 0.8) !important;
        color: #e65100 !important; /* アクセントカラー */
        border-radius: 10px 10px 0 0 !important;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
    }

    /* コードブロック（出力結果）を見やすく白背景に */
    code {
        background-color: #f8f9fa !important;
        color: #2c3e50 !important;
        font-family: "Hiragino Kaku Gothic ProN", Meiryo, sans-serif !important;
        padding: 15px !important;
        border-radius: 10px !important;
        border: 1px solid #eee !important;
        display: block;
    }

    /* カスタムクラス: ヒントボックス */
    .hint-box {
        background: linear-gradient(to right, #fff3e0, #ffe0b2);
        border-left: 6px solid #ff9800;
        padding: 20px;
        border-radius: 12px;
        color: #5d4037;
    }
    .hint-title {
        font-weight: bold;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 1.1em;
        margin-bottom: 8px;
        color: #e65100;
    }

    /* カスタムクラス: 完了メッセージ */
    .success-badge {
        background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
        color: #0d47a1;
        padding: 15px;
        border-radius: 15px;
        text-align: center;
        font-weight: bold;
        font-size: 1.2em;
        margin-bottom: 20px;
        box-shadow: 0 4px 15px rgba(33, 150, 243, 0.2);
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
# 2. ロジック (変更なし)
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
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        for row in reversed(rows):
            if len(row) >= 5 and row[1] == child_name and row[3] == "REPORT":
                row_date = row[0].split(" ")[0]
                if row_date < today_str: return row[4]
        return "初回、または過去の記録なし。本人の様子をよく観察し、信頼関係を築く。"
    except:
        return "ヒント取得エラー"

def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    retry_count = get_retry_count(child_name)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"""
        あなたは担当職員「{staff_name}」です。以下の文体、語尾、雰囲気を強く模倣して書いてください。
        【{staff_name}の過去の執筆例】
        {examples_text}
        """
    else:
        presets = {
            "親しみ": "文体: とても柔らかく、共感的に。絵文字を適度に使用（✨😊など）。",
            "標準": "文体: 丁寧語。客観的な事実と温かい感想をバランスよく。",
            "論理": "文体: 簡潔に。事実を中心に記述。"
        }
        # ラジオボタンのラベルと一致させるための処理（略）
        if "親しみ" in style_preset: style_instruction = presets["親しみ"]
        elif "標準" in style_preset: style_instruction = presets["標準"]
        else: style_instruction = presets["論理"]

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    # 基本情報
    - 児童名: {child_name}
    - 担当職員: {staff_name}
    - 本日のヒント: {current_hint}
    # 文体指示
    {style_instruction}
    # 入力記録
    {combined_text}
    # 検証
    ヒントを意識した行動があればYES、なければNO。
    # 構成
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
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None, None

# ---------------------------------------------------------
# 3. UI実装 (デザイン適用)
# ---------------------------------------------------------
st.markdown("<h1>📛 連絡帳メーカー</h1>", unsafe_allow_html=True)

child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A"] 
if not child_list: child_list = ["児童A"]

# --- 設定エリア（グラスカードに入れる） ---
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
col_conf1, col_conf2 = st.columns(2)
with col_conf1:
    staff_name = st.selectbox("担当職員", staff_list)
with col_conf2:
    child_name = st.selectbox("対象児童", child_list)

# スタイル学習表示
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.markdown(f"🤖 <small>{staff_name}さんの文体を学習済み（{past_examples_count}件）</small>", unsafe_allow_html=True)
    style_preset = "自動学習"
else:
    style_preset = st.radio("文体スタイル", ["親しみ（絵文字・柔らか）", "標準（丁寧・バランス）", "論理（簡潔・事実）"], horizontal=True)
st.markdown('</div>', unsafe_allow_html=True)

current_hint = get_todays_hint_from_history(child_name)

if current_hint:
    st.markdown(f"""
    <div class="hint-box">
        <div class="hint-title">💡 本日の関わりのヒント</div>
        {current_hint}
    </div>
    <br>
    """, unsafe_allow_html=True)

if "memos_preview" not in st.session_state: st.session_state.memos_preview = ""
if "audio_key" not in st.session_state: st.session_state.audio_key = 0
if "show_feedback" not in st.session_state: st.session_state.show_feedback = False

# タブもコンテナで囲むと綺麗だが、Streamlitの制約上そのまま配置
tab1, tab2 = st.tabs(["📝 メモ入力", "📤 出力・検証"])

with tab1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("### 音声で記録する")
    audio_val = st.audio_input("録音ボタンを押して話してください", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        st.write("---")
        with st.spinner("文字起こし中..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.success("認識完了")
            st.write(text)
            col_save, col_cancel = st.columns(2)
            with col_save:
                if st.button("保存する", type="primary", use_container_width=True):
                    if save_data(child_name, text, "MEMO", "", "", staff_name):
                        st.toast("保存しました！", icon="✅")
                        st.session_state.audio_key += 1
                        st.rerun()
            with col_cancel:
                if st.button("やり直す", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 履歴表示エリア
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    if st.button(f"📋 {child_name}さんの今日の記録を見る", use_container_width=True):
        memos, _ = fetch_todays_memos(child_name)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.text_area("今日の記録データ", st.session_state.memos_preview, height=150, disabled=True)
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown(f"""
        <div class="success-badge">
            🎉 作成完了！
        </div>
        """, unsafe_allow_html=True)

        parts = existing_report.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else "（記録なし）"

        col_out1, col_out2 = st.columns(2)
        with col_out1:
            st.markdown("### 🏠 保護者用")
            st.code(parent_part, language=None)
        with col_out2:
            st.markdown("### 🏢 職員共有用")
            st.code(staff_part, language=None)
        
        # フィードバックUI（グラスカード）
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("#### 📊 検証フィードバック")
        st.markdown("この出力は、このあとどれくらい手直しが必要ですか？")
        
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        if f_col1.button("✨ そのままOK"):
            save_feedback(child_name, "NoEdit")
            st.toast("素晴らしい！", icon="✨")
        if f_col2.button("👌 少し直す"):
            save_feedback(child_name, "MinorEdit")
            st.toast("ありがとうございます", icon="🙏")
        if f_col3.button("🔧 結構直す"):
            save_feedback(child_name, "MajorEdit")
            st.toast("改善します", icon="🙇")
        if f_col4.button("❌ 使えない"):
            save_feedback(child_name, "Useless")
            st.toast("申し訳ありません", icon="💦")
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        if st.button("🔄 文体を微調整して再生成", type="secondary"):
            if not memos: st.error("メモがありません")
            else:
                with st.spinner("調整中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                    if report: st.rerun()
    else:
        st.info("まだ連絡帳が作成されていません")
        if st.button("🚀 連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません。まずは「メモ入力」タブで記録してください。")
            else:
                with st.spinner("AIが過去の文体を分析し、執筆中..."):
                    report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: st.rerun()
