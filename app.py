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
    .saved-badge {
        background-color: #d4edda;
        color: #155724;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
        margin-bottom: 10px;
        text-align: center;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# API設定
if "OPENAI_API_KEY" in st.secrets: openai.api_key = st.secrets["OPENAI_API_KEY"]
if "ANTHROPIC_API_KEY" in st.secrets: anthropic_client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = st.secrets["GCP_SPREADSHEET_ID"]

@st.cache_resource
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
    except Exception as e:
        st.error(f"データ取得エラー: {str(e)}")
        return [], [], ""

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
    except Exception as e:
        st.error(f"プロファイル保存エラー: {str(e)}")
        return False

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
    except Exception as e:
        st.error(f"例文取得エラー: {str(e)}")
        return []

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
    """当日のメモ一覧を取得"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    for row in rows:
        if len(row) >= 5 and row[1] == child_name and row[0].startswith(today_str) and row[3] == "MEMO":
            memos.append(f"・{row[0][11:16]} [{row[4]}] {row[2]}")
    return "\n".join(memos)

def get_todays_report(child_name):
    """
    当日の既に作成済みレポートがあれば取得して返す（永続化対応）
    戻り値: (public_text, internal_text) または (None, None)
    """
    try:
        service = get_gsp_service()
        # 最新のデータから探すため全取得
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:F").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        
        # 後ろから走査して、今日の最新のREPORTを探す
        for row in reversed(rows):
            if len(row) >= 4:
                # 日付一致 AND 名前一致 AND タイプがREPORT
                if row[0].startswith(today_str) and row[1] == child_name and row[3] == "REPORT":
                    final_text = row[2]
                    next_hint = row[5] if len(row) > 5 else ""
                    return final_text, next_hint
        return None, None
    except Exception as e:
        st.error(f"今日のレポート取得エラー: {str(e)}")
        return None, None

def transcribe_audio(audio_file):
    try:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ja")
        return transcript.text
    except Exception as e:
        st.error(f"音声転写エラー: {str(e)}")
        return None

# ---------------------------------------------------------
# 3. 生成ロジック（主観・想い対応版）
# ---------------------------------------------------------
def generate_draft(child_name, memos, staff_name, manual_style):
    
    dynamic_examples = get_high_diff_examples(staff_name, limit=3)
    dynamic_instruction = ""
    if dynamic_examples:
        examples_str = "\n\n".join([f"---修正例{i+1}---\n{ex}" for i, ex in enumerate(dynamic_examples)])
        dynamic_instruction = f"【{staff_name}さんの過去の修正パターン】\n{examples_str}"

    manual_instruction = ""
    if manual_style:
        manual_instruction = f"【{staff_name}さんの文体見本（コピペ）】\n{manual_style}\n※口調だけ真似てください。"

    system_prompt = f"""
    あなたは放課後等デイサービスの熟練スタッフ「{staff_name}」です。
    提供された「活動中の会話ログ」や「メモ」から、保護者への連絡帳を作成します。

    # 名前に関する絶対ルール（最優先）
    1. **正解の名前**: 対象児童の名前は必ず「{child_name}」と表記してください。
    2. **表記ゆれの強制修正**: 
       - 入力ログ内で、読みが同じ別の漢字（例：「太朗」→「太郎」）や、あだ名（例：「たっくん」）が使われていても、出力時はすべてシステム登録名の「{child_name}」に統一してください。
       - 会話ログの漢字変換は間違っている前提で処理してください。

    # 記述の方針
    1. **事実と感想の区別**: 事実（何をしたか）と感想（どう感じたか）を区別する。
    2. **主観（Iメッセージ）**: 「〜という姿に成長を感じました」等のスタッフの主観・想いを一言添える。
    3. **会話からの変換**: 「すごいね！」等の発言は、「〜と声をかけると」のように状況描写に変換する。

    # 文体・スタイル
    {manual_instruction}

    {dynamic_instruction}

    # 入力データ
    {memos}

    # 出力構成
    【今日の{child_name}】
    （一言で）

    【活動内容】
    ・[活動1]
    ・[活動2]

    【印象的だった場面】
    [具体的なエピソード（事実）]
    [★関連するスタッフの感想・主観を一言添える]

    【ご連絡】
    [あれば]

    <<<INTERNAL>>>
    【職員間申し送り】
    [内部共有事項]
    """

    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "下書きを作成してください"}]
        )
        return message.content[0].text
    except Exception as e:
        st.error(f"AI下書き生成エラー: {str(e)}")
        return "エラーが発生しました"

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

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

st.title("連絡帳メーカー")
st.markdown(f'<div class="current-staff">👤 担当者: {selected_staff}</div>', unsafe_allow_html=True)
child_name = st.selectbox("対象児童", child_list)

tab1, tab2 = st.tabs(["1. 録音・記録", "2. 作成・出力"])

# --- Tab 1: 録音・記録 ---
with tab1:
    if "audio_key" not in st.session_state: st.session_state.audio_key = 0
    if "text_key" not in st.session_state: st.session_state.text_key = 0

    st.info("💡 活動中に録音ボタンを押して、会話や様子を記録してください。")

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
        text_val = st.text_area("補足テキスト", key=f"text_{st.session_state.text_key}", height=100)
        if st.button("追加"):
            if text_val and save_memo(child_name, text_val, selected_staff):
                st.toast("メモを追加しました", icon="📝")
                st.session_state.text_key += 1
                st.rerun()

    st.divider()
    st.text_area("本日の記録（AI分析対象）", fetch_todays_memos(child_name), height=200, disabled=True)

# --- Tab 2: 作成・出力 ---
with tab2:
    if "ai_draft" not in st.session_state: st.session_state.ai_draft = ""
    
    # ★重要変更: 児童が選択された時点で、既に保存されたレポートがあるか確認する
    # これにより、別の子の入力後に戻ってきてもデータが消えない
    existing_public, existing_internal = get_todays_report(child_name)

    # A. 既に本日のレポートが存在する場合（コピペ画面を表示）
    if existing_public:
        st.markdown(f"<div class='saved-badge'>✅ {child_name}さんの本日の連絡帳は作成済みです</div>", unsafe_allow_html=True)
        
        st.markdown("##### 1. 保護者用")
        st.code(existing_public, language=None)
        
        if existing_internal:
            st.divider()
            st.markdown("##### 2. 職員用（申し送り）")
            st.code(existing_internal, language=None)
            
        st.divider()
        with st.expander("内容を修正して保存し直す"):
            # 再編集用のエディタ
            re_edit_text = st.text_area("修正用エディタ", value=f"{existing_public}\n<<<INTERNAL>>>\n{existing_internal}", height=300)
            if st.button("修正版を上書き保存", type="primary"):
                 parts = re_edit_text.split("<<<INTERNAL>>>")
                 pub = parts[0].strip()
                 intr = parts[1].strip() if len(parts) > 1 else ""
                 # AIドラフトは不明なので空文字、またはそのままにしておく
                 if save_final_report(child_name, "", pub, intr, selected_staff):
                     st.toast("修正版を保存しました")
                     st.rerun()

    # B. まだ作成されていない場合（ドラフト作成画面）
    else:
        if st.button("AIドラフト作成", type="primary", use_container_width=True):
            memos = fetch_todays_memos(child_name)
            if not memos:
                st.error("記録がありません")
            else:
                with st.spinner("会話ログから執筆中（事実と感想を整理しています...）"):
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
                    st.toast("保存しました！")
                    # ステートをクリアして再読み込み（そうするとAのブロックに入り、コピペ画面になる）
                    st.session_state.ai_draft = ""
                    st.rerun()
