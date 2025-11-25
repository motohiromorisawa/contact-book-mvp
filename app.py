import streamlit as st
import openai
import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import pytz
import difflib

# ---------------------------------------------------------
# 1. 設定 & デザイン
# ---------------------------------------------------------
st.set_page_config(page_title="連絡帳メーカー", layout="wide")
JST = pytz.timezone('Asia/Tokyo')

st.markdown("""
<style>
    .stTextArea textarea {
        font-size: 16px !important;
        line-height: 1.6 !important;
        font-family: "Hiragino Kaku Gothic ProN", sans-serif !important;
    }
    .current-staff {
        background-color: #E8F5E9;
        color: #2E7D32;
        padding: 8px 15px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9em;
        display: inline-block;
        margin-bottom: 10px;
    }
    .copy-box {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #d6d6d6;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# API設定
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

def get_gsp_service():
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# ---------------------------------------------------------
# 2. データ操作
# ---------------------------------------------------------

def get_lists_and_profile(target_staff_name=None):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:C").execute()
        values = sheet.get('values', [])
        children = [row[0] for row in values if len(row) > 0 and row[0]]
        staffs = []
        for row in values:
            if len(row) > 1 and row[1] and row[1] not in staffs:
                staffs.append(row[1])
        current_profile = ""
        if target_staff_name:
            for row in values:
                if len(row) > 1 and row[1] == target_staff_name:
                    if len(row) > 2: current_profile = row[2]
                    break
        return children, staffs, current_profile
    except: return [], [], ""

def save_staff_profile(staff_name, profile_text):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:C").execute()
        values = sheet.get('values', [])
        update_index = -1
        for i, row in enumerate(values):
            if len(row) > 1 and row[1] == staff_name:
                update_index = i; break
        if update_index != -1:
            body = {'values': [[profile_text]]}
            service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range=f"member!C{update_index + 1}", valueInputOption="USER_ENTERED", body=body).execute()
            return True
        return False
    except: return False

def get_high_diff_examples(staff_name, limit=3):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G").execute()
        rows = sheet.get('values', [])
        candidates = []
        for row in rows:
            if len(row) >= 7 and row[4] == staff_name and row[3] == "REPORT":
                similarity = difflib.SequenceMatcher(None, row[6], row[2]).ratio()
                if (1.0 - similarity) > 0.05:
                    candidates.append({"text": row[2], "diff": 1.0 - similarity})
        candidates.sort(key=lambda x: x["diff"], reverse=True)
        return [item["text"] for item in candidates[:limit]]
    except: return []

def save_memo(child_name, text, staff_name):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    body = {'values': [[now, child_name, text, "MEMO", staff_name]]}
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E", valueInputOption="USER_ENTERED", body=body).execute()
    return True

def save_final_report(child_name, ai_draft, final_text, next_hint, staff_name):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    body = {'values': [[now, child_name, final_text, "REPORT", staff_name, next_hint, ai_draft]]}
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G", valueInputOption="USER_ENTERED", body=body).execute()
    return True

def fetch_todays_memos(child_name):
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    for row in rows:
        if len(row) >= 5 and row[1] == child_name and row[0].startswith(today_str) and row[3] == "MEMO":
            memos.append(f"・{row[0][11:16]} [{row[4]}] {row[2]}")
    return "\n".join(memos)

def transcribe_audio(audio_file):
    try:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ja")
        return transcript.text
    except: return None

# ---------------------------------------------------------
# 3. 生成ロジック（会話ログ対応版）
# ---------------------------------------------------------
def generate_draft(child_name, memos, staff_name, manual_style):
    
    # 過去データの取得
    dynamic_examples = get_high_diff_examples(staff_name, limit=3)
    dynamic_instruction = ""
    if dynamic_examples:
        examples_str = "\n\n".join([f"---修正例{i+1}---\n{ex}" for i, ex in enumerate(dynamic_examples)])
        dynamic_instruction = f"【{staff_name}さんの過去の修正パターン（重要）】\n{examples_str}"

    manual_instruction = ""
    if manual_style:
        manual_instruction = f"【{staff_name}さんの文体見本（コピペ）】\n{manual_style}\n※内容は無視し、口調だけ真似てください。"

    system_prompt = f"""
    あなたは放課後等デイサービスの熟練スタッフ「{staff_name}」です。
    提供された「活動中の会話ログ」や「メモ」から、保護者への連絡帳を作成します。

    # 入力情報の性質（最重要）
    今回の入力データは、**「子どもとの活動中に録音された会話そのもの」**が含まれています。
    
    ## 処理のルール
    1. **会話のフィルタリング**:
       - 「すごいね！」「貸してごらん」「順番だよ」といったスタッフの発言は、**事実（「順番を守るよう促しました」「褒めると嬉しそうでした」）に変換**してください。
       - そのまま「スタッフが『すごいね』と言いました」と書かないでください。
    
    2. **事実の抽出**:
       - 会話の中から「何をして遊んでいるか」「誰と関わっているか」「どんな反応か」を抜き出してください。

    3. **子どもの発言**:
       - 子どもの言葉（「やりたい！」「やだ」など）は、臨場感を伝えるためにカギカッコ『』で引用してください。

    # 文体・スタイル
    {manual_instruction}

    {dynamic_instruction}

    # 入力データ
    {memos}

    # 出力構成
    【今日の{child_name}さん】
    （一言で）

    【活動内容】
    ・[活動1]
    ・[活動2]

    【印象的だった場面】
    [具体的なエピソード]

    【ご連絡】
    [あれば]

    <<<INTERNAL>>>
    【職員間申し送り】
    [保護者に見せない内部共有事項]
    """

    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "下書きを作成してください"}]
        )
        return message.content[0].text
    except: return "エラーが発生しました"

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

# サイドバー
with st.sidebar:
    st.title("設定")
    child_list, staff_list, _ = get_lists_and_profile(None)
    if not staff_list: staff_list = ["職員A"]
    selected_staff = st.selectbox("担当職員", staff_list, key="staff_selector")
    
    _, _, saved_profile = get_lists_and_profile(selected_staff)
    st.divider()
    st.markdown(f"**✏️ {selected_staff}さんの文体マスター**")
    style_input = st.text_area("過去の連絡帳（コピペ用）", value=saved_profile, height=200)
    if st.button("設定を保存"):
        if save_staff_profile(selected_staff, style_input): st.toast("保存しました")

# メイン
st.title("連絡帳メーカー")
st.markdown(f'<div class="current-staff">👤 担当者: {selected_staff}</div>', unsafe_allow_html=True)
child_name = st.selectbox("対象児童", child_list)

tab1, tab2 = st.tabs(["1. 録音・記録", "2. 作成・出力"])

# Tab 1: 録音・記録
with tab1:
    if "audio_key" not in st.session_state: st.session_state.audio_key = 0
    if "text_key" not in st.session_state: st.session_state.text_key = 0

    st.info("💡 活動中に録音ボタンを押して、そのままポケットに入れてください。会話からAIが活動内容を拾います。")

    col1, col2 = st.columns(2)
    with col1:
        audio = st.audio_input("会話・様子を録音", key=f"audio_{st.session_state.audio_key}")
        if audio:
            with st.spinner("会話を分析中..."):
                text = transcribe_audio(audio)
            if text and save_memo(child_name, text, selected_staff):
                st.toast("録音を保存しました", icon="🎙️")
                st.session_state.audio_key += 1
                st.rerun()

    with col2:
        text_val = st.text_input("補足テキスト", key=f"text_{st.session_state.text_key}")
        if st.button("追加"):
            if text_val and save_memo(child_name, text_val, selected_staff):
                st.toast("メモを追加しました", icon="📝")
                st.session_state.text_key += 1
                st.rerun()

    st.divider()
    st.text_area("本日の記録（AI分析対象）", fetch_todays_memos(child_name), height=200, disabled=True)

# Tab 2: 作成・出力
with tab2:
    # ステート管理
    if "ai_draft" not in st.session_state: st.session_state.ai_draft = ""
    if "save_success" not in st.session_state: st.session_state.save_success = False
    if "final_public" not in st.session_state: st.session_state.final_public = ""
    if "final_internal" not in st.session_state: st.session_state.final_internal = ""

    # --- A. 保存完了後の表示 (コピペ用画面) ---
    if st.session_state.save_success:
        st.success("🎉 保存しました！各ツールに貼り付けてください。")
        
        st.markdown("##### 1. 保護者用（連絡帳アプリ・メールへ）")
        st.code(st.session_state.final_public, language=None)
        
        if st.session_state.final_internal:
            st.divider()
            st.markdown("##### 2. 職員用（日報・申し送りへ）")
            st.code(st.session_state.final_internal, language=None)
            
        st.divider()
        if st.button("次の児童へ（リセット）", type="primary", use_container_width=True):
            # ステートを全クリア
            st.session_state.ai_draft = ""
            st.session_state.save_success = False
            st.session_state.final_public = ""
            st.session_state.final_internal = ""
            st.rerun()

    # --- B. 作成・編集画面 ---
    else:
        if st.button("AIドラフト作成", type="primary", use_container_width=True):
            memos = fetch_todays_memos(child_name)
            if not memos:
                st.error("記録がありません")
            else:
                with st.spinner("会話ログから事実を抽出して執筆中..."):
                    draft = generate_draft(child_name, memos, selected_staff, style_input)
                    st.session_state.ai_draft = draft

        if st.session_state.ai_draft:
            st.divider()
            final_text = st.text_area("内容の確認・修正", value=st.session_state.ai_draft, height=400)
            
            if st.button("この内容で確定・保存", type="primary", use_container_width=True):
                parts = final_text.split("<<<INTERNAL>>>")
                public = parts[0].strip()
                internal = parts[1].strip() if len(parts) > 1 else ""
                
                if save_final_report(child_name, st.session_state.ai_draft, public, internal, selected_staff):
                    # 保存成功フラグを立てて、結果を表示するための変数に格納
                    st.session_state.save_success = True
                    st.session_state.final_public = public
                    st.session_state.final_internal = internal
                    st.rerun()
