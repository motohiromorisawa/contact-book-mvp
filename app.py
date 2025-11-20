import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz

# ---------------------------------------------------------
# 1. 設定 & デザイン (Industrial Minimal + Usability)
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")

# CSSハック: タブを巨大化し、スマホでの操作性を向上
st.markdown("""
<style>
    /* タブのボタン自体のスタイル変更 */
    button[data-baseweb="tab"] {
        font-size: 20px !important;
        padding: 15px 0px !important;
        font-weight: bold !important;
        flex: 1; /* 等幅で広げる */
    }
    /* 選択されたタブの下線強調 */
    button[data-baseweb="tab"][aria-selected="true"] {
        border-bottom: 4px solid #FF5722 !important;
    }
    
    /* テキストエリアの文字サイズも少し大きく */
    textarea {
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
    """データをシートに保存 (MEMO または REPORT)"""
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    # 保存形式: [日時, ID, テキスト内容, データタイプ]
    values = [[now, child_id, text, data_type]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D",
        valueInputOption="USER_ENTERED", body=body
    ).execute()

def fetch_todays_data(child_id):
    """今日のデータを取得 (メモ一覧と、最新のレポートがあればそれも)"""
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
            # IDと日付の一致確認
            if row[1] == child_id and row[0].startswith(today_str):
                # メモの場合
                if row[3] == "MEMO":
                    time_part = row[0][11:16]
                    memos.append(f"{time_part} {row[2]}")
                # レポートの場合 (後ろにあるものが最新)
                elif row[3] == "REPORT":
                    latest_report = row[2] # レポート本文が入っているカラム
    
    return "\n".join(memos), latest_report

def generate_final_report(child_id, combined_text):
    """Claude 4.5 Sonnetで、親しみやすく楽しい連絡帳を生成"""
    MODEL_NAME = "claude-sonnet-4-5-20250929"

    system_prompt = f"""
    あなたは放課後等デイサービスの、明るく愛情深い職員です。
    児童（ID: {child_id}）の今日の記録から、保護者が読んで「安心する」「クスッと笑える」「育児のヒントになる」連絡帳を作成してください。

    # スタイル指針（重要）
    - **長文禁止**: スマホでパッと読める長さ（300文字程度）にまとめる。
    - **構成**:
        1. **【今日の一コマ📸】**: 最も輝いていた瞬間を、あなたの主観（驚きや感動）を交えてエモーショナルに描く。
        2. **【活動ログ】**: 何をしたかを箇条書きでシンプルに。
        3. **【おうちでのヒント💡】**: もし特筆すべき成長や工夫があれば、家庭で活かせるヒントを短く添える（なければ省略可）。
    - **トーン**: 丁寧すぎない、親しみやすい敬語。
    - **リフレーミング**: 「こだわり」は「探究心」、「多動」は「エネルギー」として肯定的に翻訳する。

    ※職員用記録などの余計な情報は出力せず、保護者宛のメッセージのみを出力すること。
    """
    
    try:
        message = anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=1500,
            temperature=0.5, # 少し創造性を上げて、人間味を出す
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"以下のメモをもとに、素敵な連絡帳を書いてください：\n\n{combined_text}"}
            ]
        )
        
        report_text = message.content[0].text
        # 生成結果を保存 (タイプ=REPORT)
        save_data(child_id, report_text, "REPORT")
        
        return report_text
        
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

tab1, tab2 = st.tabs(["📝 記録入力", "✨ 連絡帳作成"])

# --- TAB 1: 記録入力 ---
with tab1:
    # 録音UI
    audio_val = st.audio_input("録音開始", key=f"recorder_{st.session_state.audio_key}")
    
    if audio_val:
        st.write("---")
        with st.spinner("聞き取っています..."):
            text = transcribe_audio(audio_val)
        
        if text:
            st.info(text)
            col_save, col_cancel = st.columns(2)
            
            with col_save:
                if st.button("保存", type="primary", use_container_width=True):
                    save_data(child_id, text, "MEMO")
                    st.success("保存しました")
                    st.session_state.audio_key += 1
                    st.rerun()
            
            with col_cancel:
                if st.button("破棄", use_container_width=True):
                    st.session_state.audio_key += 1
                    st.rerun()

    # 履歴表示
    st.write("---")
    if st.button("記録一覧を更新", use_container_width=True):
        memos, _ = fetch_todays_data(child_id)
        st.session_state.memos_preview = memos
            
    if st.session_state.memos_preview:
        st.caption("今日の記録済みメモ")
        st.text_area("history", st.session_state.memos_preview, height=150, disabled=True, label_visibility="collapsed")

# --- TAB 2: 連絡帳作成 ---
with tab2:
    # まず既存のデータを取得しにいく
    memos, existing_report = fetch_todays_data(child_id)
    
    # A. すでに作成済みのレポートがある場合
    if existing_report:
        st.success("✅ 本日の連絡帳は作成済みです")
        st.markdown("### 作成された連絡帳")
        st.markdown(existing_report)
        
        st.divider()
        st.caption("内容を修正したい場合や、メモを追加した場合は再生成できます")
        if st.button("🔄 更新して再生成する", type="secondary", use_container_width=True):
            if not memos:
                st.error("メモがありません")
            else:
                with st.spinner("再執筆中..."):
                    report = generate_final_report(child_id, memos)
                if report:
                    st.rerun() # リロードして新しいレポートを表示

    # B. まだレポートがない場合
    else:
        st.info("まだ本日の連絡帳は作成されていません")
        if st.button("✨ 連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません。まずは「記録入力」タブで様子を録音してください。")
            else:
                with st.spinner("Claudeが素敵な文章を考えています..."):
                    report = generate_final_report(child_id, memos)
                
                if report:
                    st.balloons() # 完成のお祝い
                    st.rerun()
