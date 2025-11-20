import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")

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
# 2. コア機能
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

def save_memo(child_id, memo_text):
    """断片的なメモをシートに保存"""
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    # 保存形式: [日時, 児童ID, メモ内容, "MEMO"]
    values = [[now, child_id, memo_text, "MEMO"]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_todays_memos(child_id):
    """指定した児童の今日のメモを全て取得"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D"
    ).execute()
    rows = sheet.get('values', [])
    
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    
    for row in rows:
        if len(row) >= 4:
            if row[1] == child_id and row[0].startswith(today_str) and row[3] == "MEMO":
                time_part = row[0][11:16]
                memos.append(f"{time_part} {row[2]}")
    
    return "\n".join(memos)

def generate_final_report(child_id, combined_text):
    """集まったメモから最終レポートを生成"""
    # 動作確認済みのモデルID
    MODEL_NAME = "claude-sonnet-4-5-20250929"

    system_prompt = f"""
    あなたは放課後等デイサービスの職員です。
    児童（ID: {child_id}）の観察メモから、保護者用連絡帳と業務記録を作成してください。

    # 条件
    - 断片情報を時系列に沿って統合する。
    - 事実と解釈を区別する。
    - 保護者向け：ネガティブな事実はリフレーミングし、肯定的な姿として伝える。
    - 捏造しない。
    """
    
    try:
        message = anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"以下のメモを統合して連絡帳を作ってください：\n\n{combined_text}"}
            ]
        )
        
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        values = [[now, child_id, combined_text, message.content[0].text]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        
        return message.content[0].text
        
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None

# ---------------------------------------------------------
# 3. UI (Simple & Clean)
# ---------------------------------------------------------
st.title("連絡帳メーカー")

# 児童ID入力（シンプルに）
child_id = st.text_input("児童名 / ID", value="いっくん")

if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""

if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

# タブの絵文字も削除し、機能名のみに
tab1, tab2 = st.tabs(["記録入力", "連絡帳作成"])

with tab1:
    st.write("録音してメモを追加")
    
    # 余計なカラム分割を廃止し、横幅いっぱいに表示させる
    audio_val = st.audio_input("録音開始", key=f"recorder_{st.session_state.audio_key}")
    
    # 録音完了後のフロー
    if audio_val:
        st.write("---") # 区切り線
        st.write("内容確認")
        
        with st.spinner("文字起こし中..."):
            text = transcribe_audio(audio_val)
        
        if text:
            # 認識結果をシンプルに表示
            st.info(text)
            
            # 保存・破棄ボタンを大きく表示
            # use_container_width=True でスマホの横幅いっぱいに広げる
            if st.button("保存する", type="primary", use_container_width=True):
                save_memo(child_id, text)
                st.success("保存しました")
                # リセット
                st.session_state.audio_key += 1
                st.rerun()
            
            if st.button("やり直す", use_container_width=True):
                # 保存せずにリセット
                st.session_state.audio_key += 1
                st.rerun()

    st.write("---")
    st.write("今日の記録")
    
    # プレビュー更新ボタン
    if st.button("記録一覧を更新", use_container_width=True):
        st.session_state.memos_preview = fetch_todays_memos(child_id)
            
    if st.session_state.memos_preview:
        st.text_area("履歴", st.session_state.memos_preview, height=200, disabled=True)

with tab2:
    st.write("連絡帳の生成")
    
    if st.button("生成実行", type="primary", use_container_width=True):
        memos = fetch_todays_memos(child_id)
        
        if not memos:
            st.error("本日の記録がありません。")
        else:
            with st.spinner("執筆中..."):
                report = generate_final_report(child_id, memos)
            
            if report:
                st.markdown("### 作成結果")
                st.markdown(report)
