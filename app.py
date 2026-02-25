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

def get_staff_custom_prompt(staff_name):
    """スタッフのカスタムプロンプトを取得"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:D").execute()
        values = sheet.get('values', [])
        for row in values:
            if len(row) > 1 and row[1] == staff_name:
                if len(row) > 3:
                    return row[3]  # D列のカスタムプロンプト
                break
        return ""
    except Exception as e:
        st.error(f"カスタムプロンプト取得エラー: {str(e)}")
        return ""

def save_staff_custom_prompt(staff_name, custom_prompt):
    """スタッフのカスタムプロンプト（保護者用）を保存"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:D").execute()
        values = sheet.get('values', [])
        update_index = -1
        for i, row in enumerate(values):
            if len(row) > 1 and row[1] == staff_name:
                update_index = i; break
        if update_index != -1:
            body = {'values': [[custom_prompt]]}
            service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range=f"member!D{update_index + 1}", valueInputOption="USER_ENTERED", body=body).execute()
            return True
        return False
    except Exception as e:
        st.error(f"カスタムプロンプト保存エラー: {str(e)}")
        return False

def get_staff_custom_prompt_internal(staff_name):
    """スタッフの内部用カスタムプロンプト（職員用）を取得"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:E").execute()
        values = sheet.get('values', [])
        for row in values:
            if len(row) > 1 and row[1] == staff_name:
                if len(row) > 4:
                    return row[4]  # E列の内部用カスタムプロンプト
                break
        return ""
    except Exception as e:
        st.error(f"内部用カスタムプロンプト取得エラー: {str(e)}")
        return ""

def save_staff_custom_prompt_internal(staff_name, custom_prompt_internal):
    """スタッフの内部用カスタムプロンプト（職員用）を保存"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:E").execute()
        values = sheet.get('values', [])
        update_index = -1
        for i, row in enumerate(values):
            if len(row) > 1 and row[1] == staff_name:
                update_index = i; break
        if update_index != -1:
            body = {'values': [[custom_prompt_internal]]}
            service.spreadsheets().values().update(spreadsheetId=SPREADSHEET_ID, range=f"member!E{update_index + 1}", valueInputOption="USER_ENTERED", body=body).execute()
            return True
        return False
    except Exception as e:
        st.error(f"内部用カスタムプロンプト保存エラー: {str(e)}")
        return False

def get_high_diff_examples(staff_name, limit=3):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
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

def save_memo(child_name, text, staff_name, is_highlight=False):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    tag = "HIGHLIGHT" if is_highlight else ""
    body = {'values': [[now, child_name, text, "MEMO", staff_name, "", "", tag]]}
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H", valueInputOption="USER_ENTERED", body=body).execute()
    return True

def save_final_report(child_name, ai_draft, final_text, next_hint, staff_name):
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    body = {'values': [[now, child_name, final_text, "REPORT", staff_name, next_hint, ai_draft, ""]]}
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H", valueInputOption="USER_ENTERED", body=body).execute()
    return True

def save_ai_draft_temp(child_name, ai_draft, staff_name):
    """AIドラフトを一時保存（未確定状態）"""
    service = get_gsp_service()
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    # 本文を空にして、AIドラフトのみ保存（未確定状態を表す）
    body = {'values': [[now, child_name, "", "REPORT", staff_name, "", ai_draft, ""]]}
    service.spreadsheets().values().append(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H", valueInputOption="USER_ENTERED", body=body).execute()
    return True

def fetch_todays_memos(child_name):
    """当日のメモ一覧を取得"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    for row in rows:
        if len(row) >= 5 and row[1] == child_name and row[0].startswith(today_str) and row[3] == "MEMO":
            highlight_tag = "⭐" if len(row) > 7 and row[7] == "HIGHLIGHT" else ""
            memos.append(f"・{row[0][11:16]} [{row[4]}] {highlight_tag}{row[2]}")
    return "\n".join(memos)

def get_todays_report(child_name):
    """
    当日の既に作成済みレポートがあれば取得して返す（永続化対応）
    戻り値: (public_text, internal_text) または (None, None)
    """
    try:
        service = get_gsp_service()
        # 最新のデータから探すため全取得
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
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

def get_todays_ai_draft(child_name):
    """
    当日の未確定AIドラフトがあれば取得して返す（ページ再読み込み対応）
    戻り値: ai_draft文字列 または None
    """
    try:
        service = get_gsp_service()
        # H列（タグ）も含めて全取得
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        
        # 後ろから走査して、今日の最新のAIドラフト（未確定）を探す
        for row in reversed(rows):
            if len(row) >= 7:
                # 日付一致 AND 名前一致 AND タイプがREPORT AND AIドラフトが存在
                if (row[0].startswith(today_str) and 
                    row[1] == child_name and 
                    row[3] == "REPORT" and 
                    row[6]):  # G列（AIドラフト）に内容がある
                    # 本文（C列）が空または極短い場合は未確定と判断
                    if not row[2] or len(row[2].strip()) < 10:
                        return row[6]  # AIドラフトを返す
        return None
    except Exception as e:
        st.error(f"今日のAIドラフト取得エラー: {str(e)}")
        return None

def get_past_reports(child_name, limit=3):
    """
    その児童の過去の連絡帳を新しい順に最大limit件取得（当日分は除外）
    戻り値: 過去の連絡帳テキストのリスト
    """
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        
        # 該当児童のREPORTレコードを抽出（当日以外かつ本文が存在するもの）
        past_reports = []
        for row in rows:
            if (len(row) >= 4 and 
                row[1] == child_name and 
                row[3] == "REPORT" and 
                not row[0].startswith(today_str) and  # 当日分は除外
                len(row) >= 3 and row[2] and len(row[2].strip()) > 10):  # 本文が存在
                past_reports.append({
                    'timestamp': row[0],
                    'text': row[2]
                })
        
        # タイムスタンプでソート（新しい順）
        past_reports.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # 最大limit件まで取得してテキストのみ返す
        return [report['text'] for report in past_reports[:limit]]
    except Exception as e:
        st.error(f"過去の連絡帳取得エラー: {str(e)}")
        return []

def transcribe_audio(audio_file, child_names: list = None):
    try:
        # prompt生成: 児童名リストと放課後等デイサービスでよく使われる語彙
        prompt_parts = []
        
        # 児童名リストを追加
        if child_names:
            child_names_str = "、".join(child_names)
            prompt_parts.append(f"児童名: {child_names_str}")
        
        # 放課後等デイサービスでよく使われる語彙
        common_vocab = [
            "活動", "製作", "おやつ", "公園", "制作", "工作", "ブロック",
            "パズル", "粘土", "プリント", "着替え", "トイレ", "手洗い"
        ]
        vocab_str = "、".join(common_vocab)
        prompt_parts.append(f"よく使われる語彙: {vocab_str}")
        
        # promptを結合
        prompt = "。".join(prompt_parts) + "。"
        
        # Whisper API呼び出しにpromptパラメータを追加
        transcript = openai.audio.transcriptions.create(
            model="whisper-1", 
            file=audio_file, 
            language="ja",
            prompt=prompt
        )
        return transcript.text
    except Exception as e:
        st.error(f"音声転写エラー: {str(e)}")
        return None

# ---------------------------------------------------------
# 3. 生成ロジック（主観・想い対応版）
# ---------------------------------------------------------

def get_default_guardian_prompt(child_name, staff_name, manual_instruction, dynamic_instruction, memos):
    """デフォルトの保護者用プロンプトを返す"""
    return f"""
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

    # 入力データについての注意
    以下のメモには、騒音環境での録音による音声認識の誤認識が混入している
    可能性があります。文脈として明らかに不自然・意味不明な部分は無視し、
    意味が取れる部分のみを使って連絡帳を作成してください。
    断片的な情報であっても、複数のメモを組み合わせて文脈を補完してください。

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
    """

def get_default_internal_prompt(child_name, staff_name, manual_instruction, dynamic_instruction, memos):
    """デフォルトの職員用（申し送り）プロンプトを返す"""
    return f"""
    【職員間申し送り】
    以下の内容を含めて職員間の申し送り事項を作成してください：

    # 申し送り内容
    1. **支援のポイント**: 今日の支援で特に注意したこと
    2. **行動の特徴**: 普段と違った行動や気になる点
    3. **配慮事項**: 明日以降の支援で気をつけるべきこと
    4. **保護者への報告事項**: 伝える必要がある事項があれば

    # 入力データについての注意
    以下のメモには、騒音環境での録音による音声認識の誤認識が混入している
    可能性があります。文脈として明らかに不自然・意味不明な部分は無視し、
    意味が取れる部分のみを使って連絡帳を作成してください。
    断片的な情報であっても、複数のメモを組み合わせて文脈を補完してください。

    # 入力データ
    {memos}

    # 文体・スタイル
    {manual_instruction}

    {dynamic_instruction}
    """

def fetch_todays_memos_with_tags(child_name):
    """当日のメモをタグ付き情報込みで取得"""
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    
    highlighted_memos = []
    normal_memos = []
    
    for row in rows:
        if len(row) >= 5 and row[1] == child_name and row[0].startswith(today_str) and row[3] == "MEMO":
            memo_text = f"・{row[0][11:16]} [{row[4]}] {row[2]}"
            if len(row) > 7 and row[7] == "HIGHLIGHT":
                highlighted_memos.append(memo_text)
            else:
                normal_memos.append(memo_text)
    
    # HIGHLIGHTタグ付きのメモを優先して結合
    all_memos = highlighted_memos + normal_memos
    return "\n".join(all_memos), highlighted_memos

def generate_draft(child_name, memos, staff_name, manual_style, custom_prompt=None, custom_prompt_internal=None, past_reports=None):
    
    dynamic_examples = get_high_diff_examples(staff_name, limit=3)
    dynamic_instruction = ""
    if dynamic_examples:
        examples_str = "\n\n".join([f"---修正例{i+1}---\n{ex}" for i, ex in enumerate(dynamic_examples)])
        dynamic_instruction = f"【{staff_name}さんの過去の修正パターン】\n{examples_str}"

    manual_instruction = ""
    if manual_style:
        manual_instruction = f"【{staff_name}さんの文体見本（コピペ）】\n{manual_style}\n※口調だけ真似てください。"

    # タグ付きメモ情報を取得
    structured_memos, highlighted_memos = fetch_todays_memos_with_tags(child_name)
    
    # HIGHLIGHTタグ付きメモがある場合の追加指示
    highlight_instruction = ""
    if highlighted_memos:
        highlight_instruction = f"\n\n【重要】以下のメモは「印象的な場面」としてタグ付けされています。【印象的だった場面】セクションで優先的に使用してください：\n" + "\n".join(highlighted_memos)

    # 過去の連絡帳を文脈として追加
    past_reports_instruction = ""
    if past_reports:
        past_reports_str = "\n\n".join([f"---過去の連絡帳{i+1}---\n{report}" for i, report in enumerate(past_reports)])
        past_reports_instruction = f"\n\n【過去の連絡帳（文脈参考用）】\n{past_reports_str}\n\n※過去との比較表現（「先週より」「以前と比べて」など）は使わない。ただし過去の記録から読み取れるその子の特徴・傾向・言葉遣いの癖を踏まえて、今日のエピソードをより具体的・自然に書くこと。"

    # 保護者用プロンプト作成
    if custom_prompt and custom_prompt.strip():
        guardian_prompt = custom_prompt.format(
            staff_name=staff_name,
            child_name=child_name,
            manual_instruction=manual_instruction,
            dynamic_instruction=dynamic_instruction,
            memos=structured_memos + highlight_instruction + past_reports_instruction
        )
    else:
        guardian_prompt = get_default_guardian_prompt(child_name, staff_name, manual_instruction, dynamic_instruction, structured_memos + highlight_instruction + past_reports_instruction)

    # 職員用プロンプト作成
    if custom_prompt_internal and custom_prompt_internal.strip():
        internal_prompt = custom_prompt_internal.format(
            staff_name=staff_name,
            child_name=child_name,
            manual_instruction=manual_instruction,
            dynamic_instruction=dynamic_instruction,
            memos=structured_memos + past_reports_instruction
        )
    else:
        internal_prompt = get_default_internal_prompt(child_name, staff_name, manual_instruction, dynamic_instruction, structured_memos + past_reports_instruction)

    # 両方のプロンプトを組み合わせてClaudeに送信
    combined_prompt = f"{guardian_prompt}\n\n<<<INTERNAL>>>\n{internal_prompt}"

    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000, temperature=0.3, system=combined_prompt,
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
    
    st.divider()
    with st.expander("**🎯 保護者用プロンプト編集**"):
        st.markdown("保護者向け連絡帳のシステムプロンプトをカスタマイズできます")
        
        # 現在保存されているカスタムプロンプトを取得
        saved_custom_prompt = get_staff_custom_prompt(selected_staff)
        
        # デフォルト保護者用プロンプトの生成
        default_guardian_prompt_template = """
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
    """
        
        # デフォルト値の設定
        prompt_value = saved_custom_prompt if saved_custom_prompt else default_guardian_prompt_template.strip()
        
        custom_prompt_input = st.text_area(
            "保護者用カスタムプロンプト",
            value=prompt_value,
            height=300,
            help="空にするとデフォルト保護者用プロンプトが使用されます。{staff_name}, {child_name}, {manual_instruction}, {dynamic_instruction}, {memos}の変数が利用可能です。"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("保護者用プロンプトを保存", type="primary"):
                if save_staff_custom_prompt(selected_staff, custom_prompt_input):
                    st.toast("保護者用プロンプトを保存しました")
                    
        with col2:
            if st.button("保護者用をデフォルトに戻す"):
                if save_staff_custom_prompt(selected_staff, ""):
                    st.toast("保護者用をデフォルトプロンプトに戻しました")
                    st.rerun()

    with st.expander("**👥 職員用プロンプト編集（申し送り）**"):
        st.markdown("職員間申し送りのシステムプロンプトをカスタマイズできます")
        
        # 現在保存されている内部用カスタムプロンプトを取得
        saved_custom_prompt_internal = get_staff_custom_prompt_internal(selected_staff)
        
        # デフォルト職員用プロンプトの生成
        default_internal_prompt_template = """
    【職員間申し送り】
    以下の内容を含めて職員間の申し送り事項を作成してください：

    # 申し送り内容
    1. **支援のポイント**: 今日の支援で特に注意したこと
    2. **行動の特徴**: 普段と違った行動や気になる点
    3. **配慮事項**: 明日以降の支援で気をつけるべきこと
    4. **保護者への報告事項**: 伝える必要がある事項があれば

    # 入力データ
    {memos}

    # 文体・スタイル
    {manual_instruction}

    {dynamic_instruction}
    """
        
        # デフォルト値の設定
        prompt_internal_value = saved_custom_prompt_internal if saved_custom_prompt_internal else default_internal_prompt_template.strip()
        
        custom_prompt_internal_input = st.text_area(
            "職員用カスタムプロンプト",
            value=prompt_internal_value,
            height=300,
            help="空にするとデフォルト職員用プロンプトが使用されます。{staff_name}, {child_name}, {manual_instruction}, {dynamic_instruction}, {memos}の変数が利用可能です。"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("職員用プロンプトを保存", type="primary"):
                if save_staff_custom_prompt_internal(selected_staff, custom_prompt_internal_input):
                    st.toast("職員用プロンプトを保存しました")
                    
        with col2:
            if st.button("職員用をデフォルトに戻す"):
                if save_staff_custom_prompt_internal(selected_staff, ""):
                    st.toast("職員用をデフォルトプロンプトに戻しました")
                    st.rerun()

st.title("連絡帳メーカー")
st.markdown(f'<div class="current-staff">👤 担当者: {selected_staff}</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["1. 録音・記録", "2. 作成・出力"])

# --- Tab 1: 録音・記録 ---
with tab1:
    if "audio_key" not in st.session_state: st.session_state.audio_key = 0
    if "text_key" not in st.session_state: st.session_state.text_key = 0

    # 録音エリア（中央配置）
    st.markdown("**タップして録音開始 → もう一度タップで停止（最大60秒）**", 
               help="録音ボタンを押すと録音が開始され、もう一度押すと停止します")
    audio = st.audio_input("🎙️ 会話・様子を録音", key=f"audio_{st.session_state.audio_key}", 
                          help="録音ボタンを押して開始、もう一度押して停止")
    
    # 児童選択（録音エリアの下に配置）
    child_name = st.selectbox("対象児童", child_list, 
                             help="録音後に対象の児童を選択してください")

    col1, col2 = st.columns(2)
    with col1:
        # 録音処理
        if audio:
            with st.spinner("会話を分析中..."):
                # get_lists_and_profileから児童名リストを取得
                child_names, _, _ = get_lists_and_profile()
                text = transcribe_audio(audio, child_names)
            if text:
                # 文字起こし結果を確認・編集用のセッション状態に保存
                st.session_state[f"transcribed_text_{st.session_state.audio_key}"] = text
                st.session_state.audio_key += 1
                st.rerun()
        
        # 文字起こし結果の確認・編集エリア
        current_transcription_key = f"transcribed_text_{st.session_state.audio_key - 1}"
        if current_transcription_key in st.session_state:
            transcribed_text = st.text_area(
                "文字起こし結果（編集可能）",
                value=st.session_state[current_transcription_key],
                height=150,
                key=f"edit_transcription_{st.session_state.audio_key - 1}"
            )
            
            # 印象的な場面タグ付けチェックボックス
            is_highlight = st.checkbox(
                "⭐ 印象的な場面としてタグ付け", 
                key=f"highlight_audio_{st.session_state.audio_key - 1}"
            )
            
            col_save, col_cancel = st.columns(2)
            with col_save:
                # 保存ボタンは児童が選択されている場合のみ活性化
                save_disabled = not child_name
                if st.button("保存する", type="primary", key=f"save_{st.session_state.audio_key - 1}", 
                           disabled=save_disabled, 
                           help="児童を選択してから保存してください" if save_disabled else None):
                    if transcribed_text and save_memo(child_name, transcribed_text, selected_staff, is_highlight):
                        st.toast("録音を保存しました", icon="🎙️")
                        del st.session_state[current_transcription_key]
                        st.rerun()
                        
            with col_cancel:
                if st.button("キャンセル", key=f"cancel_{st.session_state.audio_key - 1}"):
                    del st.session_state[current_transcription_key]
                    st.rerun()

    with col2:
        text_val = st.text_area("補足テキスト", key=f"text_{st.session_state.text_key}", height=100)
        # 印象的な場面タグ付けチェックボックス
        is_highlight_text = st.checkbox(
            "⭐ 印象的な場面としてタグ付け", 
            key=f"highlight_text_{st.session_state.text_key}"
        )
        # テキストメモの保存ボタンも児童が選択されている場合のみ活性化
        memo_disabled = not child_name
        if st.button("追加", disabled=memo_disabled, 
                    help="児童を選択してからメモを追加してください" if memo_disabled else None):
            if text_val and save_memo(child_name, text_val, selected_staff, is_highlight_text):
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
    
    # ★新機能: セッション状態が空の場合、Google Sheetsから未確定AIドラフトを復元
    if not st.session_state.ai_draft and not existing_public:
        restored_draft = get_todays_ai_draft(child_name)
        if restored_draft:
            st.session_state.ai_draft = restored_draft
            st.info("📄 以前作成したAIドラフトを復元しました")

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
                    # 過去の連絡帳を取得（最新3件）
                    past_reports = get_past_reports(child_name, limit=3)
                    # カスタムプロンプトを取得（保護者用・職員用両方）
                    custom_prompt = get_staff_custom_prompt(selected_staff)
                    custom_prompt_internal = get_staff_custom_prompt_internal(selected_staff)
                    draft = generate_draft(child_name, memos, selected_staff, style_input, custom_prompt, custom_prompt_internal, past_reports)
                    st.session_state.ai_draft = draft
                    # ★新機能: AIドラフトを一時保存（ページ再読み込み対応）
                    try:
                        save_ai_draft_temp(child_name, draft, selected_staff)
                    except Exception as e:
                        st.error(f"ドラフト一時保存エラー: {str(e)}")

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
