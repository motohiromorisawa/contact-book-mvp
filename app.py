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

st.markdown("""
<style>
    button[data-baseweb="tab"] {
        font-size: 18px !important;
        padding: 12px 0px !important;
        font-weight: bold !important;
        flex: 1;
    }
    code {
        font-family: "Hiragino Kaku Gothic ProN", "Hiragino Sans", Meiryo, sans-serif !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
</style>
""", unsafe_allow_html=True)

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
def get_child_list():
    """スプレッドシートの'member'シートから児童名を取得"""
    try:
        service = get_gsp_service()
        # 【変更点】シート名を 'member' に変更しました（記号なし）
        sheet = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="member!A:A"
        ).execute()
        values = sheet.get('values', [])
        
        child_list = [row[0] for row in values if row]
        
        if not child_list:
            return ["（シート'member'に名前を追加してください）"]
        return child_list
        
    except Exception as e:
        st.error(f"児童リスト読み込みエラー: {e}")
        return ["読込エラー"]

def transcribe_audio(audio_file):
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

def save_data(child_name, text, data_type="MEMO"):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    values = [[now, child_name, text, data_type]]
    body = {'values': values}
    # 記録は 'Sheet1' に保存
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_todays_data(child_name):
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
            if row[1] == child_name and row[0].startswith(today_str):
                if row[3] == "MEMO":
                    time_part = row[0][11:16]
                    memos.append(f"{time_part} {row[2]}")
                elif row[3] == "REPORT":
                    latest_report = row[2]
    
    return "\n".join(memos), latest_report

def generate_final_report(child_name, combined_text):
    MODEL_NAME = "claude-sonnet-4-5-20250929"

    system_prompt = f"""
    あなたは放課後等デイサービスの職員です。
    児童（名前: {child_name}）の記録から、「保護者用連絡帳」と「職員用申し送り」を作成してください。

    # 重要指示
    1. **名前の統一**: 音声入力で「{child_name}」が誤変換されていても、出力では必ず「{child_name}」と正しく表記すること。
    2. **マークダウン禁止**: 太字(**)や見出し記号(##)は使わない。普通のテキスト形式にする。
    3. **自然な文体**: 
       - 過剰な感嘆符や演技がかった表現は避ける。
       - 穏やかで、落ち着いた、普通の日本の保育・療育現場の話し言葉（丁寧語）を使う。
       - 文末は「〜していました。」「〜な様子でした。」など自然に。
    4. **分割出力**: 保護者用と職員用の間に `<<<SEPARATOR>>>` を入れて区切る。

    # 1. 保護者用連絡帳
    構成:
    【今日の様子】
    エピソードを自然な文章でつづる。無理に褒めちぎるのではなく、行動の背景（楽しんでいたこと、頑張っていたこと）を肯定的に描写する。
    
    【活動内容】
    ・箇条書き（記号は・を使用）

    【ご連絡】
    ※家庭へ伝えるべき事項があれば。なければ省略。

    # 2. 職員用申し送り
    構成:
    【特記事項・事実】
    事実ベースの記録
    【申し送り】
    次回への引き継ぎ
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
        save_data(child_name, full_text, "REPORT")
        return full_text
        
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.title("連絡帳メーカー")

# スプレッドシートからリスト取得
child_options = get_child_list()
child_name = st.selectbox("児童名を選択", child_options)

if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

tab1, tab2 = st.tabs(["メモ入力", "出力・コピー"])

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
                    save_data(child_name, text, "MEMO")
                    st.toast(f"{child_name}さんの記録を保存しました", icon="✅")
                    st.session_state.audio_key += 1
                    st.rerun()
            
            with col_cancel:
                if st.button("破棄", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()

    st.write("---")
    if st.button(f"{child_name}さんの記録を表示", use_container_width=True):
        memos, _ = fetch_todays_data(child_name)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.text_area("今日の記録", st.session_state.memos_preview, height=150, disabled=True)

# --- TAB 2: 出力・コピー ---
with tab2:
    memos, existing_report = fetch_todays_data(child_name)
    
    def display_split_report(full_text):
        parts = full_text.split("<<<SEPARATOR>>>")
        parent_part = parts[0].strip()
        staff_part = parts[1].strip() if len(parts) > 1 else "（職員用記録なし）"

        st.markdown("### 1. 保護者用")
        st.code(parent_part, language=None)

        st.divider()

        st.markdown("### 2. 職員共有用")
        st.code(staff_part, language=None)

    if existing_report:
        st.success(f"{child_name}さんの連絡帳：作成済み")
        display_split_report(existing_report)
        
        st.divider()
        if st.button("内容を更新して再生成", type="secondary", use_container_width=True):
            if not memos:
                st.error("メモがありません")
            else:
                with st.spinner("再生成中..."):
                    report = generate_final_report(child_name, memos)
                if report:
                    st.rerun()

    else:
        st.info(f"{child_name}さんの本日の連絡帳は未作成です")
        if st.button("連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません")
            else:
                with st.spinner("自然な文章で作成中..."):
                    report = generate_final_report(child_name, memos)
                
                if report:
                    st.rerun()
