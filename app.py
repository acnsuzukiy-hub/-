import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from io import StringIO

# --- 設定：管理用パスワード ---
ADMIN_PASSWORD = "admin"  # ← ここを好きなパスワードに変更してください

# --- データベース設定 ---
DB_NAME = 'serial_management.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                serial_number TEXT PRIMARY KEY,
                product_name TEXT,
                current_location TEXT,
                source TEXT,
                destination TEXT,
                status TEXT,
                last_updated TEXT,
                recorded_by TEXT
            )
        ''')
        conn.execute('CREATE TABLE IF NOT EXISTS locations (location_name TEXT PRIMARY KEY)')

def get_all_data():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql('SELECT * FROM inventory', conn)
        df.columns = ['シリアル番号', '商品名', '現在保管場所', '入庫元', '出庫先', 'ステータス', '最終更新日時', '登録・更新者']
        return df

def get_locations():
    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql('SELECT location_name FROM locations ORDER BY location_name', conn)
        return df['location_name'].tolist()

# --- UI設定 ---
st.set_page_config(page_title="シリアル在庫管理システム", layout="wide")
init_db()

st.title("📦 シリアル在庫管理システム")

# サイドバー：認証
st.sidebar.title("🔐 認証")
input_pass = st.sidebar.text_input("管理用パスワードを入力", type="password")
is_admin = (input_pass == ADMIN_PASSWORD)

if is_admin:
    st.sidebar.success("管理者として認証されました")
else:
    if input_pass:
        st.sidebar.error("パスワードが違います")

st.sidebar.divider()

# メインメニュー
# 管理者でない場合は「各種管理」を表示させない
if is_admin:
    menu = ["🏠 在庫一覧・検索", "➕ 1件ずつ登録", "📋 一括登録 (CSV/貼り付け)", "🚚 出庫・移動処理", "⚙️ 各種管理（保管場所・データ削除）"]
else:
    menu = ["🏠 在庫一覧・検索", "➕ 1件ずつ登録", "📋 一括登録 (CSV/貼り付け)", "🚚 出庫・移動処理"]

choice = st.sidebar.selectbox("機能メニュー", menu)

# マスターリストの取得
location_options = get_locations()

# --- 1. 在庫一覧 ---
if choice == "🏠 在庫一覧・検索":
    st.subheader("📊 現在の在庫状況")
    df = get_all_data()
    search_q = st.text_input("🔍 検索", placeholder="シリアルや商品名を入力...")
    if search_q:
        df = df[df.apply(lambda row: row.astype(str).str.contains(search_q).any(), axis=1)]
    
    if not df.empty:
        csv_data = df.to_csv(index=False).encode('utf_8_sig')
        st.download_button(label="📥 在庫リストをCSV保存", data=csv_data, file_name='inventory.csv', mime='text/csv')
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # 個別削除（管理者の場合のみ表示）
        if is_admin:
            with st.expander("🗑️ 特定の在庫データを個別に削除する"):
                del_sn = st.selectbox("削除するシリアルを選択", df['シリアル番号'].tolist())
                if st.button("選択した在庫を削除"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute('DELETE FROM inventory WHERE serial_number = ?', (del_sn,))
                    st.success(f"削除しました: {del_sn}")
                    st.rerun()
    else:
        st.info("データがありません。")

# --- 2. 1件ずつ登録 ---
elif choice == "➕ 1件ずつ登録":
    st.subheader("📝 新規データの個別登録")
    if not location_options:
        st.warning("先に管理メニューで保管場所を登録してください。")
    
    with st.form("single_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            sn = st.text_input("シリアル番号（必須）")
            p_name = st.text_input("商品名")
        with col2:
            loc = st.selectbox("保管場所を選択", location_options) if location_options else st.selectbox("保管場所", ["未登録"])
            src = st.text_input("入庫元")
        
        user_name = st.text_input("👤 登録担当者名")
        submitted = st.form_submit_button("登録する")
        
        if submitted:
            if not sn or not user_name:
                st.error("シリアル番号と担当者名は必須です。")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute('''
                        INSERT INTO inventory (serial_number, product_name, current_location, source, status, last_updated, recorded_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(serial_number) DO UPDATE SET
                            product_name=excluded.product_name, current_location=excluded.current_location,
                            source=excluded.source, last_updated=excluded.last_updated, recorded_by=excluded.recorded_by
                    ''', (sn, p_name, loc, src, "在庫中", datetime.now().strftime("%Y-%m-%d %H:%M"), user_name))
                st.success(f"登録完了: {sn}")

# --- 3. 一括登録 ---
elif choice == "📋 一括登録 (CSV/貼り付け)":
    st.subheader("📋 一括登録")
    template_df = pd.DataFrame(columns=['シリアル番号', '商品名', '入庫元'])
    st.download_button(label="📥 テンプレートCSV保存", data=template_df.to_csv(index=False).encode('utf_8_sig'), file_name='template.csv', mime='text/csv')
    
    user_name = st.text_input("👤 登録担当者名")
    target_loc = st.selectbox("一括登録先の場所を選択", location_options) if location_options else st.selectbox("場所", ["未登録"])
    input_method = st.radio("方法", ["CSVアップロード", "貼り付け"])
    
    df_input = None
    if input_method == "CSVアップロード":
        uploaded_file = st.file_uploader("CSVを選択", type='csv')
        if uploaded_file:
            df_input = pd.read_csv(uploaded_file, encoding='utf_8_sig')
            df_input.columns = ['sn', 'name', 'src']
    else:
        paste_data = st.text_area("貼り付け (シリアル, 商品名, 入庫元)", height=200)
        if paste_data:
            sep = '\t' if '\t' in paste_data else ','
            df_input = pd.read_csv(StringIO(paste_data), sep=sep, header=None, names=['sn', 'name', 'src'])

    if df_input is not None:
        st.dataframe(df_input)
        if st.button("一括登録実行"):
            if user_name and location_options:
                with sqlite3.connect(DB_NAME) as conn:
                    for _, row in df_input.iterrows():
                        conn.execute('''
                            INSERT INTO inventory (serial_number, product_name, current_location, source, status, last_updated, recorded_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(serial_number) DO UPDATE SET
                                product_name=excluded.product_name, current_location=excluded.current_location,
                                source=excluded.source, last_updated=excluded.last_updated, recorded_by=excluded.recorded_by
                        ''', (str(row['sn']), str(row['name']), target_loc, str(row['src']), "在庫中", 
                              datetime.now().strftime("%Y-%m-%d %H:%M"), user_name))
                st.success(f"{len(df_input)} 件登録しました。")

# --- 4. 出庫・移動処理 ---
elif choice == "🚚 出庫・移動処理":
    st.subheader("🚚 出庫・移動の記録")
    with st.form("move_form", clear_on_submit=True):
        target_sn = st.text_input("シリアル番号")
        new_dest = st.text_input("出庫先（送り先）")
        user_name = st.text_input("👤 更新担当者名")
        new_status = st.selectbox("ステータス", ["出荷済", "在庫中", "修理中", "廃棄"])
        
        if st.form_submit_button("移動を確定する"):
            if target_sn and new_dest and user_name:
                with sqlite3.connect(DB_NAME) as conn:
                    cursor = conn.execute('''
                        UPDATE inventory SET destination = ?, current_location = ?, status = ?, last_updated = ?, recorded_by = ?
                        WHERE serial_number = ?
                    ''', (new_dest, new_dest, new_status, datetime.now().strftime("%Y-%m-%d %H:%M"), user_name, target_sn))
                    if cursor.rowcount > 0:
                        st.success("更新完了！")
                    else:
                        st.error("シリアルが見つかりません。")

# --- 5. 各種管理 (認証時のみ表示) ---
elif choice == "⚙️ 各種管理（保管場所・データ削除）":
    st.subheader("⚙️ 管理者専用メニュー")
    
    st.markdown("### 🏘️ 保管場所の管理")
    col1, col2 = st.columns(2)
    with col1:
        new_loc = st.text_input("新しい場所を追加")
        if st.button("場所を登録"):
            if new_loc:
                with sqlite3.connect(DB_NAME) as conn:
                    try:
                        conn.execute('INSERT INTO locations (location_name) VALUES (?)', (new_loc,))
                        st.success(f"追加: {new_loc}")
                        st.rerun()
                    except:
                        st.error("登録済みです。")
    with col2:
        if location_options:
            del_loc = st.selectbox("削除する場所", location_options)
            if st.button("場所を削除"):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute('DELETE FROM locations WHERE location_name = ?', (del_loc,))
                st.warning(f"削除完了: {del_loc}")
                st.rerun()

    st.divider()
    
    st.markdown("### ⚠️ 在庫データの一括リセット")
    confirm = st.checkbox("全データを削除することに同意します")
    if st.button("🚨 全在庫データを削除する"):
        if confirm:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute('DELETE FROM inventory')
            st.success("全データを消去しました。")
            st.rerun()