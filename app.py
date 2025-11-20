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

# CSSでマイクボタンを巨大化させるハック
st.markdown("""
<style>
    /* 音声入力ウィジェットのボタンを巨大化 */
    [data-testid="stAudioInput"] button {
        width: 100% !important;
        height: 100px !important;
        font-size: 2rem !important;
        background-color: #FFEBEE !important; /* 薄い赤色で目立たせる */
        border-radius: 20px !important;
    }
    /* 録音完了後の波形表示エリアも見やすく */
    [data-testid="stAudioInput"] {
        margin-bottom: 20px !important;
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
                memos.append(f"- {time_part} : {row[2]}")
    
    return "\n".join(memos)

def generate_final_report(child_id, combined_text):
    """集まったメモから最終レポートを生成"""
    # 指定されたモデルID
    MODEL_NAME = "claude-sonnet-4-5-20250929"

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
        st.error(f"生成エラー (Model: {MODEL_NAME}): {e}")
        return None

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.title("📝 連絡帳メーカー (現場用)")

child_id = st.text_input("児童の名前またはID", value="いっくん")

if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""

# マイクウィジェットを強制リセットするためのカウンター
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

tab1, tab2 = st.tabs(["🎙️ メモ入力", "📑 連絡帳作成"])

with tab1:
    st.info(f"💡 「{child_id}」さんの記録を追加します。下の大きなボタンを押して録音してください。")
    
    # keyに数値を渡すことで、数値を変更した時にウィジェットを強制リセットできる
    audio_val = st.audio_input("録音", key=f"recorder_{st.session_state.audio_key}")
    
    # 録音が完了し、データが存在する時だけ保存ボタンを表示する
    if audio_val:
        st.success("録音完了！保存ボタンを押してください。")
        if st.button("このメモを保存する (Save)", type="primary", use_container_width=True):
            with st.spinner("文字に変換中..."):
                text = transcribe_audio(audio_val)
            
            if text:
                save_memo(child_id, text)
                st.toast(f"保存しました: {text}", icon="✅")
                
                # 保存成功後、キーを更新してマイク入力をリセット（空にする）
                st.session_state.audio_key += 1
                st.rerun()

    st.divider()
    
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
    
    if st.button("🚀 連絡帳を作成する", type="primary"):
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
