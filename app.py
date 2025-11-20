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
st.set_page_config(page_title="連絡帳メーカー (蓄積型)", layout="wide")

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

def save_memo(room_id, memo_text):
    """断片的なメモをシートに保存 (Draft列は空にする)"""
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    # 保存形式: [日時, RoomID, メモ内容, "MEMO"(識別用)]
    values = [[now, room_id, memo_text, "MEMO"]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_todays_memos(room_id):
    """今日のメモを全て取得して連結する"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D"
    ).execute()
    rows = sheet.get('values', [])
    
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    
    for row in rows:
        # 行の長さチェック & RoomIDチェック
        if len(row) >= 4 and row[1] == room_id:
            # 日付チェック (タイムスタンプの前半部分で判定)
            if row[0].startswith(today_str):
                # タイプが"MEMO"のものだけ抽出
                if row[3] == "MEMO":
                    memos.append(f"- {row[0][11:16]} : {row[2]}") # 時間: 内容
    
    return "\n".join(memos)

def generate_final_report(room_id, combined_text):
    """集まったメモから最終レポートを生成"""
    MODEL_NAME = "claude-3-5-sonnet-20241022"

    system_prompt = """
    あなたは放課後等デイサービスの熟練職員です。
    提供されたテキストは、一日の中で断続的に記録された**「観察メモの集合（時系列）」**です。
    これらを統合し、一日の活動の流れが見えるような「連絡帳」と「職員用記録」を作成してください。

    # 条件
    - 時系列の断片情報を、自然なストーリーとして繋げること。
    - 「事実」と「解釈」を区別し、保護者には子供の肯定的な姿（リフレーミング）を伝える。
    - メモに記載のない情報は捏造しない。
    - 出力形式はMarkdownで見やすく整形する。
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
        
        # 生成結果をシートに保存（タイプを"REPORT"にする）
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        # 保存形式: [日時, RoomID, 元のメモまとめ, 生成されたレポート]
        values = [[now, room_id, combined_text, message.content[0].text]]
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
# 3. UI
# ---------------------------------------------------------
st.title("📝 連絡帳メーカー (蓄積モード)")
room_id = st.text_input("合言葉 (Room ID)", value="room1")

# 今日のメモを表示するためのコンテナ
if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""

tab1, tab2 = st.tabs(["🎙️ メモを追加 (現場用)", "📑 日報作成 (まとめ用)"])

with tab1:
    st.info("💡 気づいた時に何度でも録音してください。データは蓄積されます。")
    
    audio_input = st.audio_input("マイクボタンでメモを追加")
    audio_upload = st.file_uploader("またはファイルをアップロード", type=["m4a", "mp3", "wav"], key="uploader")
    
    target_audio = audio_input if audio_input else audio_upload
    
    if target_audio:
        if st.button("メモを保存", type="primary"):
            with st.spinner("文字起こし中..."):
                text = transcribe_audio(target_audio)
            
            if text:
                save_memo(room_id, text)
                st.success(f"保存しました！: 「{text}」")
                st.toast("メモを追加しました", icon="✅")

    # 現在の蓄積状況を表示
    st.divider()
    st.caption("📝 今日のメモ一覧")
    if st.button("メモ状況を更新"):
        st.session_state.memos_preview = fetch_todays_memos(room_id)
    
    if st.session_state.memos_preview:
        st.text_area("蓄積されたメモ", st.session_state.memos_preview, height=200, disabled=True)
    else:
        st.write("（まだメモはありません。上のボタンで更新してください）")

with tab2:
    st.write("一日の終わりに、蓄積されたメモから連絡帳を作成します。")
    
    if st.button("🚀 AI連絡帳を作成する"):
        memos = fetch_todays_memos(room_id)
        
        if not memos:
            st.error("今日のメモがまだありません。")
        else:
            st.info(f"以下のメモをもとに作成します...\n{memos}")
            with st.spinner("Claudeが思考中...複数のエピソードを統合しています..."):
                report = generate_final_report(room_id, memos)
            
            if report:
                st.success("作成完了！")
                st.markdown("### 完成した連絡帳")
                st.markdown(report)
                st.caption("※この内容はスプレッドシートにも保存されました")
