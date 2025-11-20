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
    .coach-mark {
        background-color: #FFF3E0;
        border-left: 6px solid #FF9800;
        padding: 15px;
        margin-bottom: 20px;
        border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .coach-title {
        font-weight: bold;
        color: #E65100;
        font-size: 1.1em;
        margin-bottom: 5px;
    }
    .coach-text {
        font-size: 1.1em;
        color: #333;
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
def get_child_data():
    """スプレッドシートから児童名と支援ヒントを取得"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="member!A:B"
        ).execute()
        values = sheet.get('values', [])
        
        child_dict = {}
        for row in values:
            if row:
                name = row[0]
                point = row[1] if len(row) > 1 else "初回：本人の様子をよく観察してください"
                child_dict[name] = point
        
        if not child_dict:
            return {"データなし": "データなし"}
        return child_dict
        
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        return {}

def update_child_hint(child_name, new_hint):
    """次回の支援ヒントをスプレッドシートに上書き保存"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range="member!A:A"
        ).execute()
        values = sheet.get('values', [])
        
        row_index = -1
        for i, row in enumerate(values):
            if row and row[0] == child_name:
                row_index = i + 1
                break
        
        if row_index != -1:
            body = {'values': [[new_hint]]}
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, range=f"member!B{row_index}",
                valueInputOption="USER_ENTERED", body=body
            ).execute()
            return True
        return False
    except Exception as e:
        print(f"ヒント更新エラー: {e}")
        return False

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

def generate_final_report(child_name, current_hint, combined_text):
    MODEL_NAME = "claude-sonnet-4-5-20250929"

    system_prompt = f"""
    あなたは放課後等デイサービスの熟練職員です。
    児童（名前: {child_name}）の記録から、「保護者用連絡帳」「職員用申し送り」そして「**次回への具体的な支援ヒント**」を作成してください。

    # 入力情報
    - 本日の支援ヒント: {current_hint}
    - 本日の記録: (ユーザー入力)

    # 出力ルール（厳守）
    1. **名前の統一**: 「{child_name}」と正しく表記。
    2. **マークダウン禁止**: 普通のテキスト形式。
    3. **セパレーター**: 
       - 保護者用と職員用の間: `<<<SEPARATOR>>>`
       - 職員用と次回ヒントの間: `<<<NEXT_HINT>>>`

    # 構成とガイドライン
    
    ## パート1: 保護者用
    【今日の様子】(自然な文章で肯定的に)
    【活動内容】(箇条書き)
    【ご連絡】(あれば)

    `<<<SEPARATOR>>>`

    ## パート2: 職員用
    【本日のヒント「{current_hint}」の振り返り】
    【特記事項・事実】

    `<<<NEXT_HINT>>>`

    ## パート3: 次回（明日以降）の支援ヒント
    
    **【重要: ヒント更新の判断基準】**
    療育において「定着」は最も重要です。支援を急いで減らすと失敗体験に繋がります。
    
    1. **うまくいった場合**:
       - 基本的には**「同じ支援を継続」**としてください。「成功体験を積み重ねて定着を図る」ためです。
       - 文例：「今日もスムーズだったので、引き続き〇〇の支援を継続し、定着を図る」
       
    2. **うまくいかなかった場合**:
       - 支援方法の微修正を提案してください。（環境を変える、手順を減らす等）
       
    3. **支援を減らす（フェードアウト）場合**:
       - 記録の中に「支援がなくても自分からできた」「支援が過剰そうだった」という**明確な根拠**がある場合のみ、スモールステップで少しだけ支援を減らす提案をしてください。

    ※担当者が変わっても再現できるよう、具体的かつ簡潔な1文〜2文で書いてください。
    """
    
    try:
        message = anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2500,
            temperature=0.3,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"以下のメモをもとに作成してください：\n\n{combined_text}"}
            ]
        )
        
        full_text = message.content[0].text
        
        parts = full_text.split("<<<NEXT_HINT>>>")
        report_content = parts[0].strip()
        next_hint = parts[1].strip() if len(parts) > 1 else current_hint # 生成失敗時は前回維持
        
        save_data(child_name, report_content, "REPORT")
        update_child_hint(child_name, next_hint)
        
        return report_content, next_hint
        
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None, None

# ---------------------------------------------------------
# 3. UI
# ---------------------------------------------------------
st.title("連絡帳メーカー")

child_data = get_child_data()
child_names = list(child_data.keys())

child_name = st.selectbox("児童名を選択", child_names)
current_hint = child_data.get(child_name, "")

if current_hint:
    st.markdown(f"""
    <div class="coach-mark">
        <div class="coach-title">💡 本日の関わりのヒント</div>
        <div class="coach-text">{current_hint}</div>
    </div>
    """, unsafe_allow_html=True)

if "memos_preview" not in st.session_state:
    st.session_state.memos_preview = ""
if "audio_key" not in st.session_state:
    st.session_state.audio_key = 0

tab1, tab2 = st.tabs(["メモ入力", "出力・コピー"])

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
                    report, next_hint = generate_final_report(child_name, current_hint, memos)
                if report:
                    st.rerun()

    else:
        st.info(f"{child_name}さんの本日の連絡帳は未作成です")
        if st.button("連絡帳を作成する", type="primary", use_container_width=True):
            if not memos:
                st.error("記録メモがありません")
            else:
                with st.spinner("振り返りと次回ヒントを作成中..."):
                    report, next_hint = generate_final_report(child_name, current_hint, memos)
                
                if report:
                    st.success(f"作成完了！\n次回のヒント：{next_hint}")
                    st.rerun()
                
                if report:
                    st.rerun()
