import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

# ---------------------------------------------------------
# 1. 設定
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳ドラフト生成", layout="wide")

# APIキー設定 (Streamlit Secretsより)
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
    """
    Whisper API (v1) を使用。
    ※Streamlit CloudのCPU負荷を避けるため、whisper.cppではなくAPIを利用
    """
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

def generate_draft(input_text):
    """
    Claude 4.5 Sonnet を使用してドラフト生成
    """
    MODEL_NAME = "claude-sonnet-4-5-20250929" 

    system_prompt = """
    あなたは放課後等デイサービスの熟練職員です。
    入力された音声テキスト（散文・箇条書き）から、保護者に渡す「連絡帳のドラフト」と「職員用記録」を作成してください。
    
    # 条件
    - 「事実」と「解釈」を高度に区別しつつ、保護者には情緒的なつながりを伝える。
    - ネガティブな事実はリフレーミングし、発達的視点からの肯定的な解釈を加える。
    - 常同行動（回転など）は「没頭」「探究」といった強みとして表現する。
    - 入力にない情報は絶対に捏造しない。文脈補完が必要な場合は[ ]で確認を促すこと。
    """
    
    try:
        message = anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000, # 4.5の表現力を活かすため少し増枠
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"以下の音声メモから連絡帳を作ってください：\n\n{input_text}"}
            ]
        )
        return message.content[0].text
    except Exception as e:
        st.error(f"生成エラー (Model: {MODEL_NAME}): {e}")
        return None

def save_to_sheet(room_id, original_text, draft_text):
    service = get_gsp_service()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = [[now, room_id, original_text, draft_text]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_latest_draft(room_id):
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D"
    ).execute()
    rows = sheet.get('values', [])
    for row in reversed(rows):
        if len(row) >= 4 and row[1] == room_id:
            return row[2], row[3]
    return None, None

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.title("📝 親の実践サポート：連絡帳メーカー")

room_id = st.text_input("合言葉 (Room ID)", value="room1")

tab1, tab2 = st.tabs(["📱 スマホ入力", "💻 PC確認・編集"])

with tab1:
    st.info("💡 下のマイクボタンを押して話しかけるか、録音ファイルをアップロードしてください。")
    
    # 音声入力手段を2つ用意（マイク入力 OR ファイルアップロード）
    audio_input = st.audio_input("マイクボタンを押して録音開始")
    audio_upload = st.file_uploader("または録音ファイルをアップロード", type=["m4a", "mp3", "wav"])
    
    # どちらかの入力があれば処理対象とする
    audio_file = audio_input if audio_input else audio_upload
    
    if audio_file is not None:
        # ボタンを押さなくても、録音完了したら即座に処理開始するフローに変更も可能ですが、
        # 誤動作防止のためボタン制を維持します。
        if st.button("魔法をかける (AI処理開始)"):
            with st.spinner("音声を文字に変換中..."):
                text = transcribe_audio(audio_file)
            
            if text:
                st.success("聞き取り完了")
                with st.expander("認識されたテキスト"):
                    st.write(text)
                
                with st.spinner("Claude 4.5 Sonnet が執筆中..."):
                    draft = generate_draft(text)
                
                if draft:
                    st.success("作成完了！PCタブで確認してください。")
                    save_to_sheet(room_id, text, draft)

with tab2:
    if st.button("最新のドラフトを取得"):
        original, draft = fetch_latest_draft(room_id)
        if draft:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.caption("元の音声テキスト")
                st.info(original)
            with col2:
                st.caption("生成された連絡帳")
                st.text_area("エディタ", draft, height=500)
        else:
            st.warning("データが見つかりません。")
