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
st.set_page_config(page_title="連絡帳メーカー (現場用)", layout="wide")

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
        # 行の長さチェック
        if len(row) >= 4:
            # IDチェック (完全一致) AND 日付チェック (前方一致) AND タイプチェック
            if row[1] == child_id and row[0].startswith(today_str) and row[3] == "MEMO":
                # 時間(HH:MM)だけ切り出して表示
                time_part = row[0][11:16]
                memos.append(f"- {time_part} : {row[2]}")
    
    return "\n".join(memos)

def generate_final_report(child_id, combined_text):
    """集まったメモから最終レポートを生成"""
    # 動作確認済みのモデルID
    MODEL_NAME = "claude-4-5-sonnet-20250929"

    system_prompt = f"""
    あなたは放課後等デイサービスの熟練職員です。
    児童（ID: {child_id}）に関する断続的な観察メモ（時系列）から、
    保護者へ渡す「連絡帳」と、内部用の「業務記録」を作成してください。

    # 条件
    - 断片的な情報を、一日の自然なストーリーとして統合する。
    - 「事実」と「解釈」を区別する。
    - 保護者向けには、ネガティブな事実もリフレーミングし、子供の成長や肯定的な姿として伝える。
    - メモにない情報は捏造しない。
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
        
        # 生成結果を保存
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
# 3. UI
# ---------------------------------------------------------
st.title("📝 連絡帳メーカー (現場用)")

# 複数人対応のため、ラベルを明確化
child_id = st.text_input("児童の名前またはID (例: いっくん)", value="いっくん")

# セッション状態の初期化
if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""

tab1, tab2 = st.tabs(["🎙️ メモ入力", "📑 連絡帳作成"])

with tab1:
    st.info(f"💡 「{child_id}」さんの記録を追加します。マイクボタンを押して話してください。")
    
    # ファイルアップロードを削除し、マイク入力のみに
    audio_input = st.audio_input("録音ボタン")
    
    if audio_input:
        if st.button("このメモを保存", type="primary"):
            with st.spinner("文字に変換中..."):
                text = transcribe_audio(audio_input)
            
            if text:
                save_memo(child_id, text)
                st.success(f"保存しました: {text}")
                st.toast("メモを追加しました", icon="✅")

    st.divider()
    
    # 今日のメモ確認エリア
    col1, col2 = st.columns([2, 1])
    with col1:
        st.caption(f"📝 {child_id}さんの今日のメモ")
    with col2:
        if st.button("🔄 更新"):
            st.session_state.memos_preview = fetch_todays_memos(child_id)
            
    if st.session_state.memos_preview:
        st.text_area("記録済み", st.session_state.memos_preview, height=200, disabled=True)
    else:
        st.write("（まだ記録はありません）")

with tab2:
    st.write(f"蓄積されたメモから、{child_id}さんの連絡帳を作成します。")
    
    if st.button("🚀 連絡帳を作成する"):
        memos = fetch_todays_memos(child_id)
        
        if not memos:
            st.error(f"本日の{child_id}さんのメモが見つかりません。")
        else:
            st.info(f"以下のメモを使用します:\n{memos}")
            with st.spinner("Claudeが執筆中..."):
                report = generate_final_report(child_id, memos)
            
            if report:
                st.success("作成完了！")
                st.markdown(report)
                st.caption("※データは自動保存されました")
