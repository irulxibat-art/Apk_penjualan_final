import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

# ===================================================
# UI THEME — LIGHT & FAST (OPTIMIZED)
# ===================================================
page_bg_css = """
<style>
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa 0%, #8b5cf6 30%, #3b82f6 65%, #0ea5e9 100%);
}

/* MAIN CONTAINER */
div[data-testid="stVerticalBlock"] > div,
div[data-testid="stColumn"] > div {
    background: rgba(255,255,255,0.90);
    padding: 16px;
    border-radius: 14px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
}

/* FORM */
.stForm {
    background: rgba(255,255,255,0.95);
    padding: 16px;
    border-radius: 14px;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.95);
}
section[data-testid="stSidebar"] * {
    color: black;
}

/* INPUT */
input, textarea, select {
    background: white !important;
    color: black !important;
    border-radius: 10px !important;
}

/* BUTTON */
.stButton button {
    background: linear-gradient(90deg, #7c3aed, #3b82f6);
    color: white;
    border-radius: 10px;
    padding: 8px 20px;
    font-weight: 600;
    border: none;
}
.stButton button:hover {
    opacity: 0.95;
}

/* TABLE */
.dataframe {
    background: white;
    border-radius: 12px;
}

/* TEXT */
h1, h2, h3, h4, p, span, label {
    color: black;
    font-weight: 700;
}
</style>
"""
st.markdown(page_bg_css, unsafe_allow_html=True)

# ===================================================
# DATABASE
# ===================================================
DB_NAME = "inventory.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT,
        name TEXT,
        cost REAL,
        price REAL,
        stock INTEGER DEFAULT 0,
        warehouse_stock INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        qty INTEGER,
        cost_each REAL,
        price_each REAL,
        total REAL,
        profit REAL,
        sold_by INTEGER,
        sold_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS store_status (
        id INTEGER PRIMARY KEY,
        status TEXT
    )""")

    c.execute("SELECT COUNT(*) FROM store_status")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO store_status VALUES (1,'open')")

    conn.commit()
    return conn

conn = init_db()

# ===================================================
# STORE STATUS
# ===================================================
def get_store_status():
    c = conn.cursor()
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store_status(status):
    c = conn.cursor()
    c.execute("UPDATE store_status SET status=? WHERE id=1",(status,))
    conn.commit()

# ===================================================
# AUTH
# ===================================================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                  ("boss", hash_password("boss123"), "boss",
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
create_default_user()

def login_user(u,p):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u, hash_password(p)))
    return c.fetchone()

# ===================================================
# PRODUCT
# ===================================================
def add_product(sku,name,cost,price):
    c = conn.cursor()
    c.execute("""
    INSERT INTO products (sku,name,cost,price,created_at)
    VALUES (?,?,?,?,?)
    """,(sku,name,cost,price,datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(pid,sku,name,cost,price):
    c = conn.cursor()
    c.execute("""
    UPDATE products SET sku=?,name=?,cost=?,price=? WHERE id=?
    """,(sku,name,cost,price,pid))
    conn.commit()

def delete_product(pid):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?",(pid,))
    if c.fetchone()[0]>0:
        return False,"Produk sudah ada transaksi"
    c.execute("DELETE FROM products WHERE id=?",(pid,))
    conn.commit()
    return True,"Produk dihapus"

def add_warehouse_stock(pid,qty):
    c = conn.cursor()
    c.execute("UPDATE products SET warehouse_stock=warehouse_stock+? WHERE id=?",
              (qty,pid))
    conn.commit()

def move_stock_from_warehouse(pid,qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?",(pid,))
    ws=c.fetchone()[0]
    if qty>ws:
        return False,"Stok gudang tidak cukup"
    c.execute("""
    UPDATE products SET warehouse_stock=warehouse_stock-?, stock=stock+?
    WHERE id=?
    """,(qty,qty,pid))
    conn.commit()
    return True,"Stok dipindah"

def get_products():
    return pd.read_sql_query("SELECT * FROM products ORDER BY name",conn)

# ===================================================
# SALES
# ===================================================
def record_sale(pid,qty,uid):
    c = conn.cursor()
    c.execute("SELECT stock,cost,price FROM products WHERE id=?",(pid,))
    stock,cost,price=c.fetchone()
    if qty>stock:
        return False,"Stok tidak cukup"
    total=qty*price
    profit=(price-cost)*qty
    c.execute("""
    INSERT INTO sales (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
    VALUES (?,?,?,?,?,?,?,?)
    """,(pid,qty,cost,price,total,profit,uid,
         datetime.datetime.utcnow().isoformat()))
    c.execute("UPDATE products SET stock=stock-? WHERE id=?",(qty,pid))
    conn.commit()
    return True,"Penjualan berhasil"

def get_sales(role):
    if role=="boss":
        q="""SELECT s.id,p.name,s.qty,s.price_each,s.total,s.profit,s.sold_at
             FROM sales s JOIN products p ON s.product_id=p.id"""
    else:
        q="""SELECT s.id,p.name,s.qty,s.price_each,s.total,s.sold_at
             FROM sales s JOIN products p ON s.product_id=p.id"""
    return pd.read_sql_query(q,conn)

def get_today_summary():
    today=datetime.date.today().isoformat()
    c=conn.cursor()
    c.execute("""
    SELECT COALESCE(SUM(total),0),COALESCE(SUM(profit),0)
    FROM sales WHERE date(sold_at)=?
    """,(today,))
    return c.fetchone()

def get_today_sales_user(uid):
    today=datetime.date.today().isoformat()
    c=conn.cursor()
    c.execute("""
    SELECT COALESCE(SUM(total),0)
    FROM sales WHERE sold_by=? AND date(sold_at)=?
    """,(uid,today))
    return c.fetchone()[0]

# ===================================================
# SESSION
# ===================================================
if "user" not in st.session_state:
    st.session_state.user=None

# ===================================================
# LOGIN
# ===================================================
if st.session_state.user is None:
    st.title("Login Sistem")
    u=st.text_input("Username")
    p=st.text_input("Password",type="password")
    if st.button("Login"):
        user=login_user(u,p)
        if user:
            if user[3]=="karyawan" and get_store_status()=="closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user={"id":user[0],"username":user[1],"role":user[3]}
                st.rerun()
        else:
            st.error("Login gagal")

# ===================================================
# MAIN APP
# ===================================================
else:
    user=st.session_state.user
    role=user["role"]

    st.sidebar.write(f"Login: {user['username']} ({role})")

    if role=="karyawan":
        st.sidebar.metric("Penjualan Hari Ini",
                          f"Rp {int(get_today_sales_user(user['id'])):,}")

    if st.sidebar.button("Logout"):
        st.session_state.user=None
        st.rerun()

    menu = st.sidebar.selectbox("Menu",
        ["Home","Stok Gudang","Produk & Stok","Penjualan","Histori Penjualan","Manajemen User"]
        if role=="boss"
        else ["Home","Penjualan","Histori Penjualan"]
    )

    if menu=="Home":
        st.header("Dashboard")
        status=get_store_status()
        st.subheader(f"Status Toko: {status.upper()}")
        if role=="boss":
            col1,col2=st.columns(2)
            if col1.button("Toko Buka"):
                set_store_status("open"); st.rerun()
            if col2.button("Toko Tutup"):
                set_store_status("closed"); st.rerun()

    elif menu=="Stok Gudang":
        st.header("Stok Gudang")
        with st.form("add"):
            sku=st.text_input("SKU")
            name=st.text_input("Nama")
            cost=st.number_input("Modal")
            price=st.number_input("Harga")
            if st.form_submit_button("Tambah"):
                add_product(sku,name,cost,price); st.rerun()
        df=get_products()
        if not df.empty:
            pid=st.selectbox("Produk",df["id"],format_func=lambda x:df[df.id==x]["name"].iloc[0])
            qty=st.number_input("Tambah Stok",min_value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid,qty); st.rerun()
            st.dataframe(df[["sku","name","warehouse_stock"]])

    elif menu=="Produk & Stok":
        st.header("Stok Harian")
        df=get_products()
        pid=st.selectbox("Produk",df["id"],format_func=lambda x:df[df.id==x]["name"].iloc[0])
        qty=st.number_input("Ambil",min_value=1)
        if st.button("Ambil"):
            ok,msg=move_stock_from_warehouse(pid,qty)
            st.success(msg) if ok else st.error(msg)
        st.dataframe(df[["sku","name","stock"]])

    elif menu=="Penjualan":
        st.header("Penjualan")
        df=get_products()
        pid=st.selectbox("Produk",df["id"],format_func=lambda x:df[df.id==x]["name"].iloc[0])
        qty=st.number_input("Qty",min_value=1)
        if st.button("Simpan"):
            ok,msg=record_sale(pid,qty,user["id"])
            st.success(msg) if ok else st.error(msg)

    elif menu=="Histori Penjualan":
        st.header("Histori")
        if role=="boss":
            total,profit=get_today_summary()
            st.metric("Total Hari Ini",f"Rp {int(total):,}")
            st.metric("P&L Hari Ini",f"Rp {int(profit):,}")
        st.dataframe(get_sales(role))

    elif menu=="Manajemen User":
        st.header("Manajemen User")
        with st.form("user"):
            u=st.text_input("Username")
            p=st.text_input("Password",type="password")
            r=st.selectbox("Role",["boss","karyawan"])
            if st.form_submit_button("Tambah"):
                try:
                    c=conn.cursor()
                    c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                              (u,hash_password(p),r,
                               datetime.datetime.utcnow().isoformat()))
                    conn.commit(); st.rerun()
                except:
                    st.error("Username sudah ada")
        st.dataframe(pd.read_sql_query("SELECT id,username,role FROM users",conn))
