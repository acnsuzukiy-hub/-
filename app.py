import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
from io import StringIO

# --- 設定：管理用パスワード ---
ADMIN_PASSWORD = "admin"  # ← ここを好きなパスワードに変更してください

# --- UI設定 ---
st.set_page_config(page_title="シリアル在庫管理システム", layout="wide")

# --- Googleスプレッドシート接続 ---
# Streamlit公式のGSheetsConnectionを使用します
conn = st.connection("gsheets", type=GSheetsConnection)

def get_all_data():
    return conn.read(worksheet="inventory", ttl=0)

def get_locations():
    df = conn.read(worksheet="locations", ttl=0)
    return df["location_name"].dropna().tolist()

def update_inventory(df):
    conn.update(worksheet="inventory", data=df)

def update_locations(df):
    conn.update(worksheet="locations", data=df)

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
    
    display_df = df.copy()
    if search_q:
        display_df = display_df[display_df.apply(lambda row: row.astype(str).str.contains(search_q).any(), axis=1)]
    
    if not display_df.empty:
        csv_data = display_df.to_csv(index=False).encode('utf_8_sig')
        st.download_button(label="📥 在庫リストをCSV保存", data=csv_data, file_name='inventory.csv', mime='text/csv')
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        if is_admin:
            with st.expander("🗑️ 特定の在庫データを個別に削除する"):
                del_sn = st.selectbox("削除するシリアルを選択", df['シリアル番号'].tolist())
                if st.button("選択した在庫を削除"):
                    new_df = df[df['シリアル番号'] != del_sn]
                    update_inventory(new_df)
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
                df = get_all_data()
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_row = {
                    "シリアル番号": sn, "商品名": p_name, "現在保管場所": loc, 
                    "入庫元": src, "出庫先": "", "ステータス": "在庫中", 
                    "最終更新日時": now, "登録・更新者": user_name
                }
                # 上書きまたは追加
                if sn in df["シリアル番号"].values:
                    df.loc[df["シリアル番号"] == sn] = new_row
                else:
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                
                update_inventory(df)
                st.success(f"登録完了: {sn}")

# --- 3. 一括登録 ---
elif choice == "📋 一括登録 (CSV/貼り付け)":
    st.subheader("📋 一括登録")
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
                df = get_all_data()
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                for _, row in df_input.iterrows():
                    new_row = {
                        "シリアル番号": str(row['sn']), "商品名": str(row['name']), "現在保管場所": target_loc, 
                        "入庫元": str(row['src']), "出庫先": "", "ステータス": "在庫中", 
                        "最終更新日時": now, "登録・更新者": user_name
                    }
                    if str(row['sn']) in df["シリアル番号"].values:
                        df.loc[df["シリアル番号"] == str(row['sn'])] = new_row
                    else:
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                
                update_inventory(df)
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
                df = get_all_data()
                if target_sn in df["シリアル番号"].values:
                    idx = df[df["シリアル番号"] == target_sn].index[0]
                    df.at[idx, "出庫先"] = new_dest
                    df.at[idx, "現在保管場所"] = new_dest
                    df.at[idx, "ステータス"] = new_status
                    df.at[idx, "最終更新日時"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    df.at[idx, "登録・更新者"] = user_name
                    update_inventory(df)
                    st.success("更新完了！")
                else:
                    st.error("シリアルが見つかりません。")

# --- 5. 各種管理 ---
elif choice == "⚙️ 各種管理（保管場所・データ削除）":
    st.subheader("⚙️ 管理者専用メニュー")
    
    st.markdown("### 🏘️ 保管場所の管理")
    col1, col2 = st.columns(2)
    with col1:
        new_loc = st.text_input("新しい場所を追加")
        if st.button("場所を登録"):
            if new_loc:
                loc_df = conn.read(worksheet="locations", ttl=0)
                if new_loc not in loc_df["location_name"].values:
                    loc_df = pd.concat([loc_df, pd.DataFrame([{"location_name": new_loc}])], ignore_index=True)
                    update_locations(loc_df)
                    st.success(f"追加: {new_loc}")
                    st.rerun()
                else:
                    st.error("登録済みです。")
    with col2:
        if location_options:
            del_loc = st.selectbox("削除する場所", location_options)
            if st.button("場所を削除"):
                loc_df = conn.read(worksheet="locations", ttl=0)
                loc_df = loc_df[loc_df["location_name"] != del_loc]
                update_locations(loc_df)
                st.warning(f"削除完了: {del_loc}")
                st.rerun()

    st.divider()
    st.markdown("### ⚠️ 在庫データの一括リセット")
    confirm = st.checkbox("全データを削除することに同意します")
    if st.button("🚨 全在庫データを削除する"):
        if confirm:
            empty_df = pd.DataFrame(columns=['シリアル番号', '商品名', '現在保管場所', '入庫元', '出庫先', 'ステータス', '最終更新日時', '登録・更新者'])
            update_inventory(empty_df)
            st.success("全データを消去しました。")
            st.rerun()
