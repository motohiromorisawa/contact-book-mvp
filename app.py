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
# 2. データ操作（読み書き）
# ---------------------------------------------------------

def get_lists_and_profile(target_staff_name=None):
    """
    児童リスト、職員リスト、および選択された職員の保存済みスタイルを取得
    memberシート: A列=児童, B列=職員, C列=職員ごとのスタイル設定(文体マスター)
    """
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
                    if len(row) > 2:
                        current_profile = row[2]
                    break
                    
        return children, staffs, current_profile
    except Exception as e:
        st.error(f"リスト取得エラー: {e}")
        return [], [], ""

def save_staff_profile(staff_name, profile_text):
    """職員のスタイル設定をmemberシートのC列に保存"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:C").execute()
        values = sheet.get('values', [])
        
        update_index = -1
        for i, row in enumerate(values):
            if len(row) > 1 and row[1] == staff_name:
                update_index = i
                break
        
        if update_index != -1:
            body = {'values': [[profile_text]]}
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID, 
                range=f"member!C{update_index + 1}", 
                valueInputOption="USER_ENTERED", 
                body=body
            ).execute()
            return True
        else:
            return False
    except Exception as e:
        st.error(f"プロフィール保存エラー: {e}")
        return False

def get_high_diff_examples(staff_name, limit=3):
    """
    その職員の過去データから、AI案(G列)と完成版(C列)の差分が大きい
    上位レポートを抽出し、Few-Shotの例として返す。
    """
    try:
        service = get_gsp_service()
        # A:Time, B:Child, C:FinalText, D:Type, E:Staff, F:NextHint, G:AI_Draft
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G").execute()
        rows = sheet.get('values', [])
        
        candidates = []
        for row in rows:
            if len(row) >= 7 and row[4] == staff_name and row[3] == "REPORT":
                final_text = row[2]
                ai_draft = row[6]
                
                similarity = difflib.SequenceMatcher(None, ai_draft, final_text).ratio()
                diff_score = 1.0 - similarity
                
                if diff_score > 0.05:
                    candidates.append({
                        "text": final_text,
                        "diff": diff_score
                    })
        
        candidates.sort(key=lambda x: x["diff"], reverse=True)
        return [item["text"] for item in candidates[:limit]]
    except:
        return []

def save_memo(child_name, text, staff_name):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    values = [[now, child_name, text, "MEMO", staff_name]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:E", valueInputOption="USER_ENTERED", body=body
    ).execute()
    return True

def save_final_report(child_name, ai_draft, final_text, next_hint, staff_name):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    values = [[now, child_name, final_text, "REPORT", staff_name, next_hint, ai_draft]]
    body = {'values': values}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G", valueInputOption="USER_ENTERED", body=body
    ).execute()
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
    except:
        return None

# ---------------------------------------------------------
# 3. 生成ロジック（修正済）
# ---------------------------------------------------------
def generate_draft(child_name, memos, staff_name, manual_style):
    
    # 1. 自動学習データ（過去の高修正ログ）
    dynamic_examples = get_high_diff_examples(staff_name, limit=3)
    dynamic_instruction = ""
    if dynamic_examples:
        examples_str = "\n\n".join([f"---学習済み修正例{i+1}---\n{ex}" for i, ex in enumerate(dynamic_examples)])
        dynamic_instruction = f"""
        【AIが学習した{staff_name}さんの修正パターン】
        以下は、過去にAIが出力したものを{staff_name}さんが「自ら修正した」信頼できる正解データです。
        ここに表れている文体の特徴（語尾、漢字の比率、文章の長さ）を最優先で再現してください。
        {examples_str}
        """

    # 2. 手動スタイル（ここを修正：例文貼り付けに対応）
    manual_instruction = ""
    if manual_style:
        manual_instruction = f"""
        【{staff_name}さんの文体マスター（重要）】
        以下のテキストは、この職員が「普段書いている連絡帳のサンプル（コピペ）」または「文体への指示」です。
        
        !!! 注意 !!!
        ここに具体的なエピソード（「公園に行った」等）が書かれていても、それは**文体のサンプルとしてのみ**扱ってください。
        今回の連絡帳の内容には**絶対に含めないでください**。
        「書き方」「トーン」「リズム」だけを抽出して真似てください。

        --- 文体マスター ---
        {manual_style}
        ------------------
        """

    # システムプロンプト構成
    system_prompt = f"""
    あなたは放課後等デイサービスの熟練スタッフ「{staff_name}」です。
    提供されたメモから、保護者への連絡帳（日報）を作成します。

    # 入力情報の解釈ルール
    1. **発話の主体**: 入力テキストはすべて「スタッフがスマホに向かって喋った報告」です。「すごいねー」「できた！」などの言葉は、文脈上明らかでない限り「スタッフの感想」として処理し、**子どもの発言として記述しないでください。**
    2. **子どもの発言**: 明示的に引用されている場合のみ、子どもの発言として記述してください。

    # 文章作成の原則
    1. **具体的に記述**: 「頑張りました」等の評価ではなく、「30分集中して取り組んでいました」のように事実を記述。
    2. **専門用語の排除**: 保護者に伝わる日常語で記述。
    3. **ポジティブな視点**: 「できませんでした」ではなく「挑戦していました」と記述。

    # スタイル定義
    {manual_instruction}

    {dynamic_instruction}

    # 今回の入力メモ
    {memos}

    # 出力構成
    【今日の{child_name}さん】
    （一言でその日の様子）

    【活動内容】
    ・[活動1]
    ・[活動2]

    【印象的だった場面】
    [具体的な行動・表情。子どもの言葉は引用で]

    【ご連絡】
    [事務連絡があれば]

    <<<INTERNAL>>>
    【職員間申し送り】
    [保護者に見せない引継ぎ事項]
    """

    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "下書きを作成してください"}]
        )
        return message.content[0].text
    except Exception as e:
        return f"エラー: {e}"

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------

# --- サイドバー ---
with st.sidebar:
    st.title("設定")
    
    # リスト取得
    child_list, staff_list, _ = get_lists_and_profile(None)
    if not staff_list: staff_list = ["職員A", "職員B"]
    
    selected_staff = st.selectbox("担当職員", staff_list, key="staff_selector")
    
    # 選択された職員の保存済みスタイルをロード
    _, _, saved_profile = get_lists_and_profile(selected_staff)
    
    st.divider()
    st.markdown(f"**✏️ {selected_staff}さんの文体マスター**")
    st.caption("あなたが過去に書いた「良い連絡帳」をそのままコピペしてください。AIがその書き方を真似します。")
    
    style_input = st.text_area(
        "過去の連絡帳（コピペ用）",
        value=saved_profile,
        height=250,
        placeholder="例：\n本日は〇〇公園へ出かけました。〜\n\n（ここに普段の文章をそのまま貼り付けると、AIが口調を学習します）"
    )
    
    if st.button("この文体を保存"):
        if save_staff_profile(selected_staff, style_input):
            st.toast(f"{selected_staff}さんの文体を保存しました", icon="💾")
        else:
            st.error("保存失敗")

# --- メイン画面 ---
st.title("連絡帳メーカー")
st.markdown(f'<div class="current-staff">👤 担当者: {selected_staff}</div>', unsafe_allow_html=True)

child_name = st.selectbox("対象児童", child_list)

tab1, tab2 = st.tabs(["1. メモ入力", "2. 編集・保存"])

# --- Tab 1 ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        audio = st.audio_input("音声メモ")
        if audio:
            with st.spinner("文字起こし中..."):
                text = transcribe_audio(audio)
            if text and save_memo(child_name, text, selected_staff):
                st.toast("保存しました")
                st.rerun()
    with col2:
        text = st.text_input("テキストメモ")
        if st.button("追加"):
            if text and save_memo(child_name, text, selected_staff):
                st.toast("保存しました")
                st.rerun()

    st.divider()
    st.text_area("本日の記録", fetch_todays_memos(child_name), height=200, disabled=True)

# --- Tab 2 ---
with tab2:
    if "ai_draft" not in st.session_state: st.session_state.ai_draft = ""
    
    if st.button("AIドラフト作成", type="primary", use_container_width=True):
        memos = fetch_todays_memos(child_name)
        if not memos:
            st.error("メモがありません")
        else:
            with st.spinner(f"{selected_staff}さんの文体を再現中..."):
                draft = generate_draft(child_name, memos, selected_staff, style_input)
                st.session_state.ai_draft = draft

    if st.session_state.ai_draft:
        st.divider()
        final_text = st.text_area("AI作成案（修正してください）", value=st.session_state.ai_draft, height=400)
        
        if st.button("この内容で確定・保存", type="primary", use_container_width=True):
            parts = final_text.split("<<<INTERNAL>>>")
            public = parts[0].strip()
            internal = parts[1].strip() if len(parts) > 1 else ""
            
            if save_final_report(child_name, st.session_state.ai_draft, public, internal, selected_staff):
                st.success("保存しました")
                st.session_state.ai_draft = ""
                st.rerun()
