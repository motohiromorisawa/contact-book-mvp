import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")

# CSS: タブを大きく、見やすく
st.markdown("""
<style>
    button[data-baseweb="tab"] {
        font-size: 20px !important;
        padding: 15px 0px !important;
        font-weight: bold !important;
        flex: 1;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        border-bottom: 4px solid #2196F3 !important;
    }
    /* コピー用テキストエリア（st.code）のフォント調整 */
    code {
        font-family: "Helvetica Neue", Arial, "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif !important;
        font-size: 16px !important;
    }
</style>
""", unsafe_allow_html=True)

# JSTタイムゾーン設定
JST = pytz.timezone('Asia/Tokyo')

# APIキー設定
if "OPENAI_API_KEY" in st.secrets:
    openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets:
    anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# Google Sheets 設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. データ操作機能
# ---------------------------------------------------------
def transcribe_audio(audio_file):
    """Whisper APIで音声認識"""
    try:
        transcript = openai.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file,
            language="ja"
        )
        return transcript.text
    except Exception as e:
        st.error(f"音声認識エラー: {e}")
        return None

def save_data(child_id, text, data_type="MEMO"):
    """データをシートに保存"""
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    values = [[now, child_id, text, data_type]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_todays_data(child_id):
    """今日のデータを取得"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D"
    ).execute()
    rows = sheet.get('values', [])
    
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    latest_report = None
    
    for row in rows:
        if len(row) >= 4:
            if row[1] == child_id and row[0].startswith(today_str):
                if row[3] == "MEMO":
                    time_part = row[0][11:16]
                    memos.append(f"{time_part} {row[2]}")
                elif row[3] == "REPORT":
                    latest_report = row[2]
    
    return "\n".join(memos), latest_report

def generate_final_report(child_id, combined_text):
    """連絡帳と業務記録を生成"""
    MODEL_NAME = "claude-3-5-sonnet-20241022" # 安定版を使用

    system_prompt = f"""
    あなたは放課後等デイサービスの職員です。
    児童（ID: {child_id}）の記録から、「保護者用連絡帳」と「職員用申し送り」を作成してください。

    # 出力ルール（厳守）
    1. **絵文字禁止**: 文字化けを防ぐため、絵文字は一切使用しないこと。記号（■や・など）は使用可。
    2. **分割出力**: 保護者用と職員用の間に `<<<SEPARATOR>>>` という文字列を入れて区切ること。

    # 1. 保護者用連絡帳
    - 構成:
        【今日の一コマ】（情緒的・肯定的なエピソード）
        【活動内容】（箇条書き）
        【家庭への連絡】（必要な場合のみ）
    - 文体: 丁寧語。ネガティブな事実はリフレーミングし、肯定的に伝える。

    # 2. 職員用申し送り
    - 構成:
        【特記事項】（トラブル、体調変化、排泄など事実ベース）
        【ISP関連】（支援計画に基づく行動評価）
        【申し送り】（明日以降のスタッフへの共有事項）
    - 文体: 簡潔な常体（だ・である）。事実を正確に。
    """
    
    try:
        message = anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"以下のメモをもとに作成してください：\n\n{combined_text}"}
            ]
        )
        
        full_text = message.content[0].text
        save_data(child_id, full_text, "REPORT")
        return full_text
        
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.title("連絡帳メーカー")

child_id = st.text_input("児童名 / ID", value="いっくん")

if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

tab1, tab2 = st.tabs(["📝 記録入力", "📋 出力・コピー"])

# --- TAB 1: 記録入力 ---
with tab1:
    audio_val = st.audio_input("録音開始", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        st.write("---")
        with st.spinner("文字起こし中..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.info(text)
            col_save, col_cancel = st.columns(2)
            
            with col_save:
                if st.button("保存", type="primary", use_container_width=True):
                    save_data(child_id, text, "MEMO")
                    st.toast("保存しました", icon="✅")
                    st.session_state.audio_key += 1
                    st.rerun()
            
            with col_cancel:
                if st.button("破棄", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()

    st.write("---")
    if st.button("記録一覧を更新", use_container_width=True):
        memos, _ = fetch_todays_data(child_id)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.caption("今日の記録済みメモ")
        st.text_area("history", st.session_state.memos_preview, height=150, disabled=True, label_visibility="collapsed")

# --- TAB 2: 出力・コピー ---
with tab2:
    memos, existing_report = fetch_todays_data(child_id)
    
    # レポート表示用関数
    def display_split_report(full_text):
        # セパレーターで分割
        parts = full_text.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else "（職員用記録なし）"

        st.markdown("### 1. 保護者用 (コピペ用)")
        st.caption("右上のコピーボタンでコピーできます")
        # st.codeを使うと、右上にコピーボタンが自動でつきます
        st.code(parent_part, language=None)

        st.divider()

        st.markdown("### 2. 職員共有用 (コピペ用)")
        st.caption("右上のコピーボタンでコピーできます")
        st.code(staff_part, language=None)

    # A. 既にレポートがある場合
    if existing_report:
        st.success("✅ 作成済み")
        display_split_report(existing_report)
        
        st.divider()
        if st.button("🔄 内容を更新して再生成", type="secondary", use_container_width=True):
            if not memos:
                st.error("メモがありません")
            else:
                with st.spinner("再生成中..."):
                    report = generate_final_report(child_id, memos)
                if report:
                    st.rerun()

    # B. まだない場合
    else:
        st.info("本日の連絡帳は未作成です")
        if st.button("✨ 連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません")
            else:
                with st.spinner("保護者用と職員用を書き分けています..."):
                    report = generate_final_report(child_id, memos)
                
                if report:
                    st.balloons()
                    st.rerun()
