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
JST = pytz.timezone('Asia/Tokyo')

# デザインCSS
st.markdown("""
<style>
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold !important; }
    .success-box { background-color: #E3F2FD; color: #1565C0; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; margin-bottom: 15px; }
    .style-box { background-color: #F3E5F5; border-left: 5px solid #9C27B0; padding: 10px; font-size: 0.9em; color: #4A148C; margin-bottom: 10px;}
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
# 2. データ取得・分析ロジック
# ---------------------------------------------------------
def get_lists():
    """児童リストと職員リストを取得"""
    try:
        service = get_gsp_service()
        # memberシートのA列(児童)とB列(職員)を取得
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="member!A:B").execute()
        values = sheet.get('values', [])
        children = [row[0] for row in values if len(row) > 0]
        staffs = [row[1] for row in values if len(row) > 1]
        return children, staffs
    except Exception as e:
        st.error(f"リスト読込エラー: {e}")
        return [], []

def get_retry_count(child_name):
    """本日のこの児童に対する生成回数をカウント（再生成の指標）"""
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
        
        count = 0
        for row in rows:
            if len(row) >= 4:
                # 日付一致 AND 名前一致 AND タイプがREPORT
                if row[0].startswith(today_str) and row[1] == child_name and row[3] == "REPORT":
                    count += 1
        return count
    except:
        return 0

def get_staff_style_examples(staff_name):
    """
    その職員の過去のレポートから、評価が高かった（修正なしor微修正）ものを最大3件取得
    """
    try:
        service = get_gsp_service()
        # 全データを取得 (A:G列) ※G列はFeedback
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:H").execute()
        rows = sheet.get('values', [])
        
        examples = []
        # 新しいものから走査
        for row in reversed(rows):
            if len(row) >= 8: # H列まであるか
                r_staff = row[7] # H列: StaffName
                r_type = row[3]
                r_text = row[2]
                r_feedback = row[6] if len(row) > 6 else ""
                
                if r_staff == staff_name and r_type == "REPORT":
                    # 良い評価のものだけを学習データにする（変な癖を学ばないため）
                    if r_feedback in ["NoEdit", "MinorEdit"]:
                        # 保護者パートのみを抽出（区切り文字で分割）
                        parts = r_text.split("<<<SEPARATOR>>>")
                        parent_text = parts[0].strip()
                        examples.append(parent_text)
                        
            if len(examples) >= 3:
                break
        
        return examples
    except Exception as e:
        return []

def transcribe_audio(audio_file):
    try:
        transcript = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, language="ja")
        return transcript.text
    except:
        return None

def save_data(child_name, text, data_type, next_hint="", hint_used="", staff_name="", retry_count=0):
    try:
        service = get_gsp_service()
        now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
        # [日時, 名前, 本文, タイプ, 次回ヒント, ヒント活用, 評価(空), 職員名, 再生成数]
        values = [[now, child_name, text, data_type, next_hint, hint_used, "", staff_name, retry_count]]
        body = {'values': values}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:I", valueInputOption="USER_ENTERED", body=body
        ).execute()
        return True
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def save_feedback(child_name, feedback_score):
    try:
        service = get_gsp_service()
        sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:G").execute()
        rows = sheet.get('values', [])
        for i in range(len(rows) - 1, -1, -1):
            if len(rows[i]) >= 4 and rows[i][1] == child_name and rows[i][3] == "REPORT":
                body = {'values': [[feedback_score]]}
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID, range=f"Sheet1!G{i+1}", valueInputOption="USER_ENTERED", body=body
                ).execute()
                return True
        return False
    except:
        return False

def fetch_todays_memos(child_name):
    service = get_gsp_service()
    sheet = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="Sheet1!A:D").execute()
    rows = sheet.get('values', [])
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    memos = []
    latest_report = None
    for row in rows:
        if len(row) >= 4 and row[1] == child_name and row[0].startswith(today_str):
            if row[3] == "MEMO":
                memos.append(f"{row[0][11:16]} {row[2]}")
            elif row[3] == "REPORT":
                latest_report = row[2]
    return "\n".join(memos), latest_report

def get_hint(child_name):
    # (省略: 前回のコードと同様のロジック)
    return "よく観察し、肯定的なフィードバックを行う。"

# ---------------------------------------------------------
# 3. 生成ロジック (スタイル適応)
# ---------------------------------------------------------
def generate_final_report(child_name, current_hint, combined_text, staff_name, style_preset):
    
    # 1. 再生成カウント取得
    retry_count = get_retry_count(child_name)
    
    # 2. 文体データの取得 (Few-Shot)
    past_examples = get_staff_style_examples(staff_name)
    
    style_instruction = ""
    if past_examples:
        # 過去データがある場合: Few-Shot Prompting
        examples_text = "\n---\n".join(past_examples)
        style_instruction = f"""
        あなたは担当職員「{staff_name}」です。
        以下の「{staff_name}」が過去に書いた文章の文体、語尾、雰囲気を強く模倣して書いてください。
        
        【{staff_name}の過去の執筆例】
        {examples_text}
        """
    else:
        # データがない場合: プリセット適用
        presets = {
            "親しみ（絵文字あり・柔らかめ）": "文体: とても柔らかく、共感的に。絵文字を適度に使用（✨😊など）。保護者に寄り添うトーン。",
            "標準（丁寧・バランス）": "文体: 丁寧語（です・ます）。客観的な事実と、温かい感想をバランスよく。",
            "論理（箇条書き・簡潔）": "文体: 簡潔に。事実を中心に記述。情緒的な表現よりも、何ができたかを明確に。"
        }
        style_instruction = presets.get(style_preset, "文体: 丁寧語")

    system_prompt = f"""
    放課後等デイサービスの連絡帳作成。
    
    # 基本情報
    - 児童名: {child_name}
    - 担当職員: {staff_name}
    - 本日のヒント: {current_hint}

    # 文体・スタイルの指示 (最重要)
    {style_instruction}

    # 入力された記録
    {combined_text}

    # 検証タスク
    記録内に「本日のヒント」を意識した行動があればYES、なければNO。

    # 出力フォーマット
    (マークダウン禁止)
    
    【今日の様子】
    ...
    【活動内容】
    ...
    【ご連絡】
    ...
    <<<SEPARATOR>>>
    【ヒント振り返り】
    ...
    【特記事項】
    ...
    <<<NEXT_HINT>>>
    (次回の具体的ヒント 1文)
    <<<HINT_CHECK>>>
    YES/NO
    """
    
    try:
        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500, temperature=0.3, system=system_prompt,
            messages=[{"role": "user", "content": "作成してください"}]
        )
        full_text = message.content[0].text
        
        # パース処理
        parts = full_text.split("<<<NEXT_HINT>>>")
        report_content = parts[0].strip()
        remaining = parts[1].strip() if len(parts) > 1 else ""
        parts2 = remaining.split("<<<HINT_CHECK>>>")
        next_hint = parts2[0].strip() if parts2 else ""
        hint_used = parts2[1].strip() if len(parts2) > 1 else "UNKNOWN"
        
        # 保存 (StaffNameとRetryCountも含める)
        if save_data(child_name, report_content, "REPORT", next_hint, hint_used, staff_name, retry_count):
            return report_content, next_hint
        return None, None
    except Exception as e:
        st.error(f"生成エラー: {e}")
        return None, None

# ---------------------------------------------------------
# 4. UI実装
# ---------------------------------------------------------
st.title("連絡帳メーカー 🤖")

# 1. 担当者と児童の選択
child_list, staff_list = get_lists()
if not staff_list: staff_list = ["職員A", "職員B"] # デフォルト

col_conf1, col_conf2 = st.columns(2)
with col_conf1:
    staff_name = st.selectbox("担当職員（あなたの名前）", staff_list)
with col_conf2:
    child_name = st.selectbox("対象児童", child_list)

# 文体学習状況の表示
past_examples_count = len(get_staff_style_examples(staff_name))
if past_examples_count > 0:
    st.markdown(f"<div class='style-box'>🤖 {staff_name}さんの過去データ({past_examples_count}件)から文体を学習済みです</div>", unsafe_allow_html=True)
    style_preset = "自動学習"
else:
    st.info(f"🔰 {staff_name}さんのデータがまだありません。スタイルを選択してください。")
    style_preset = st.radio("文体スタイル", ["親しみ（絵文字あり・柔らかめ）", "標準（丁寧・バランス）", "論理（箇条書き・簡潔）"], horizontal=True)

# (以下、メモ入力部分は省略なしで実装可能だが、長くなるためタブ構成のみ記載)
current_hint = "（デモ用ヒント）"
tab1, tab2 = st.tabs(["メモ入力", "作成・検証"])

with tab1:
    # 音声入力・保存処理 (前述と同じロジック)
    # save_data 呼び出し時に staff_name を渡すのを忘れずに
    # save_data(child_name, text, "MEMO", "", "", staff_name)
    st.write("（音声入力・メモ保存UI）") 
    # ※実際のコードではここに前回の tab1 の内容が入ります

with tab2:
    memos, existing_report = fetch_todays_memos(child_name)
    
    if existing_report:
        st.markdown("<div class='success-box'>🎉 作成完了</div>", unsafe_allow_html=True)
        # レポート表示...
        st.code(existing_report) # 簡略表示
        
        # フィードバックUI (修正コスト評価)
        if st.button("評価を記録して終了"):
             st.toast("記録しました")

        st.divider()
        if st.button("🔄 気に入らないので再生成する (文体を微調整)"):
             with st.spinner("文体を変えて再生成中..."):
                 # ここで再度 generate_final_report を呼ぶと、内部で retry_count が +1 された状態で記録される
                 report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                 if report: st.rerun()

    else:
        if st.button("連絡帳を作成する", type="primary"):
            with st.spinner("過去の文体を分析中..."):
                report, _ = generate_final_report(child_name, current_hint, memos, staff_name, style_preset)
                if report: st.rerun()
