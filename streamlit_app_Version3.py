import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

# ================= CONFIG =================
st.set_page_config(page_title="Inventory System", layout="wide")

# ================= UI =================
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa, #8b5cf6, #3b82f6, #0ea5e9);
}
div[data-testid="stVerticalBlock"] > div,
div[data-testid="stColumn"] > div {
    background: rgba(255,255,255,0.92);
    padding: 16px;
    border-radius: 14px;
    box-shadow: 0 4px 10px rgba(0,0,0,.15);
}
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.95);
}
input, textarea, select {
    background: white !important;
    color: black !important;
}
.stButton button {
    background: linear-gradient(90deg,#7c3aed,#3b82f6);
    color: white;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}
h1,h2,h3,h4,p,label,span { color:black; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ================= DATABASE =================
DB = "inventory.db"
def get_db():
    return sqlite3.connect(DB, check_same_thread=False)

db = get_db()
c = db.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE,
password TEXT,
role TEXT,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS products(
id INTEGER PRIMARY KEY AUTOINCREMENT,
sku TEXT,
name TEXT,
cost REAL,
price REAL,
stock INTEGER DEFAULT 0,
warehouse_stock INTEGER DEFAULT 0,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS sales(
id INTEGER PRIMARY KEY AUTOINCREMENT,
product_id INTEGER,
qty INTEGER,
cost_each REAL,
price_each REAL,
total REAL,
profit REAL,
sold_by INTEGER,
sold_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS store_status(
id INTEGER PRIMARY KEY,
status TEXT)""")

c.execute("SELECT COUNT(*) FROM store_status")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO store_status VALUES (1,'open')")

db.commit()

# ================= AUTH =================
def hash_pw(p): 
    return hashlib.sha256(p.encode()).hexdigest()

c.execute("SELECT * FROM users WHERE username='boss'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES(NULL,?,?,?,?)",
              ("boss", hash_pw("boss123"), "boss",
               datetime.datetime.utcnow().isoformat()))
    db.commit()

def login(u,p):
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u,hash_pw(p)))
    return c.fetchone()

# ================= STORE =================
def store_status():
    c.execute("SELECT status FROM store_status WHERE id=1")
    row = c.fetchone()
    return row[0] if row else "open"

def set_store(s):
    c.execute("UPDATE store_status SET status=? WHERE id=1",(s,))
    db.commit()

# ================= PRODUCT =================
def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", db)

def add_product(sku,name,cost,price):
    c.execute("""INSERT INTO products
    (sku,name,cost,price,created_at)
    VALUES(?,?,?,?,?)""",
    (sku,name,cost,price,datetime.datetime.utcnow().isoformat()))
    db.commit()

def update_product(pid,sku,name,cost,price):
    c.execute("""UPDATE products
    SET sku=?,name=?,cost=?,price=?
    WHERE id=?""",(sku,name,cost,price,pid))
    db.commit()

def delete_product(pid):
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (pid,))
    if c.fetchone()[0] > 0:
        return False,"Produk sudah pernah terjual"
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()
    return True,"Produk dihapus"

def add_warehouse_stock(pid,qty):
    c.execute("UPDATE products SET warehouse_stock=warehouse_stock+? WHERE id=?",
              (qty,pid))
    db.commit()

def move_stock(pid,qty):
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (pid,))
    row = c.fetchone()
    if row is None:
        return False,"Produk tidak ditemukan"
    ws = row[0]
    if qty > ws:
        return False,"Stok gudang tidak cukup"
    c.execute("""UPDATE products
    SET warehouse_stock=warehouse_stock-?,
        stock=stock+?
    WHERE id=?""",(qty,qty,pid))
    db.commit()
    return True,"Stok dipindahkan"

# ================= SALES =================
def sell(pid,qty,uid):
    c.execute("SELECT stock,cost,price FROM products WHERE id=?", (pid,))
    row = c.fetchone()
    if row is None:
        return False,"Produk tidak ditemukan"
    stock,cost,price = row
    if qty > stock:
        return False,"Stok tidak cukup"
    total = qty * price
    profit = (price - cost) * qty
    c.execute("""INSERT INTO sales
    (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
    VALUES(?,?,?,?,?,?,?,?)""",
    (pid,qty,cost,price,total,profit,uid,
     datetime.datetime.utcnow().isoformat()))
    c.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty,pid))
    db.commit()
    return True,"Penjualan berhasil"

# ================= PDF =================
def generate_sales_pdf(df):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    w,h = A4

    pdf.setFont("Helvetica-Bold",14)
    pdf.drawString(40,h-40,"LAPORAN PENJUALAN")

    pdf.setFont("Helvetica",10)
    y = h-80
    headers = df.columns.tolist()
    x = [40,170,250,330,410]

    for i,head in enumerate(headers):
        pdf.drawString(x[i],y,head)

    y -= 20
    pdf.setFont("Helvetica",9)

    for _,row in df.iterrows():
        if y < 60:
            pdf.showPage()
            y = h-60
            pdf.setFont("Helvetica",9)
        for i,val in enumerate(row):
            pdf.drawString(x[i],y,str(val))
        y -= 16

    pdf.save()
    buf.seek(0)
    return buf

# ================= SESSION =================
if "user" not in st.session_state: st.session_state.user=None
if "selected_product" not in st.session_state: st.session_state.selected_product=None
if "show_edit_product" not in st.session_state: st.session_state.show_edit_product=False

# ================= LOGIN =================
if st.session_state.user is None:
    st.title("Login Sistem")
    u = st.text_input("Username")
    p = st.text_input("Password",type="password")
    if st.button("Login"):
        user = login(u,p)
        if user:
            if user[3]=="karyawan" and store_status()=="closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user={"id":user[0],"username":user[1],"role":user[3]}
                st.rerun()
        else:
            st.error("Login gagal")

# ================= MAIN =================
else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"{user['username']} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.user=None
        st.rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home","Stok Gudang","Produk & Stok","Penjualan","Histori Penjualan","Manajemen User"]
        if role=="boss"
        else ["Home","Penjualan","Histori Penjualan"]
    )

    # HOME
    if menu=="Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {store_status().upper()}")
        if role=="boss":
            c1,c2 = st.columns(2)
            if c1.button("Toko Buka"): set_store("open"); st.rerun()
            if c2.button("Toko Tutup"): set_store("closed"); st.rerun()

    # STOK GUDANG
    elif menu=="Stok Gudang":
        st.header("Stok Gudang")

        with st.form("add"):
            st.subheader("Tambah Produk")
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Modal")
            price = st.number_input("Harga")
            if st.form_submit_button("Tambah"):
                add_product(sku,name,cost,price)
                st.rerun()

        df = get_products()
        if not df.empty:
            pid = st.selectbox("Pilih Produk",df["id"],
                               format_func=lambda x: df[df.id==x]["name"].iloc[0])
            row = df[df.id==pid].iloc[0]

            if st.button("Edit Produk"):
                st.session_state.show_edit_product = not st.session_state.show_edit_product

            if st.session_state.show_edit_product:
                with st.form("edit"):
                    sku = st.text_input("SKU",value=row["sku"])
                    name = st.text_input("Nama",value=row["name"])
                    cost = st.number_input("Modal",value=float(row["cost"]))
                    price = st.number_input("Harga",value=float(row["price"]))
                    c1,c2 = st.columns(2)
                    if c1.form_submit_button("Simpan"):
                        update_product(pid,sku,name,cost,price)
                        st.session_state.show_edit_product=False
                        st.rerun()
                    if c2.form_submit_button("Batal"):
                        st.session_state.show_edit_product=False
                        st.rerun()

            st.subheader("Tambah Stok Gudang")
            qty = st.number_input("Jumlah",min_value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid,qty)
                st.rerun()

            st.subheader("Hapus Produk")
            if st.button("Hapus Produk"):
                delete_product(pid)
                st.rerun()

            st.dataframe(df[["sku","name","warehouse_stock"]])

    # PRODUK & STOK
    elif menu=="Produk & Stok":
        st.header("Ambil Stok Harian")
        df = get_products()
        pid = st.selectbox("Produk",df["id"],
                           format_func=lambda x: df[df.id==x]["name"].iloc[0])
        qty = st.number_input("Jumlah Ambil",min_value=1)
        if st.button("Ambil Stok"):
            move_stock(pid,qty)
            st.rerun()
        st.dataframe(df[["sku","name","stock","warehouse_stock"]])

    # PENJUALAN
    elif menu=="Penjualan":
        st.header("Penjualan")
        df = get_products()
        cols = st.columns(3)
        for i,row in df.iterrows():
            with cols[i%3]:
                if st.button(f"{row['name']}\nStok:{row['stock']}",
                             key=f"p{row['id']}"):
                    st.session_state.selected_product=row["id"]

        if st.session_state.selected_product:
            prod = df[df.id==st.session_state.selected_product].iloc[0]
            qty = st.number_input("Qty",min_value=1)
            if st.button("Simpan"):
                sell(prod["id"],qty,user["id"])
                st.session_state.selected_product=None
                st.rerun()

    # HISTORI + PDF
    elif menu=="Histori Penjualan":
        st.header("Histori Penjualan")

        if role=="boss":
            df = pd.read_sql("""
            SELECT p.name AS Produk,
                   s.qty AS Qty,
                   s.total AS Total,
                   s.profit AS Profit,
                   date(s.sold_at) AS Tanggal
            FROM sales s
            JOIN products p ON s.product_id=p.id
            ORDER BY s.sold_at DESC
            """, db)

            st.dataframe(df)

            pdf = generate_sales_pdf(df)
            st.download_button(
                "Download Laporan PDF",
                data=pdf,
                file_name="laporan_penjualan.pdf",
                mime="application/pdf"
            )
        else:
            df = pd.read_sql("""
            SELECT p.name AS Produk,
                   s.qty AS Qty,
                   s.total AS Total,
                   date(s.sold_at) AS Tanggal
            FROM sales s
            JOIN products p ON s.product_id=p.id
            WHERE s.sold_by=?
            """, db, params=(user["id"],))
            st.dataframe(df)

    # USER
    elif menu=="Manajemen User":
        st.header("Manajemen User")
        with st.form("user"):
            u = st.text_input("Username")
            p = st.text_input("Password",type="password")
            r = st.selectbox("Role",["boss","karyawan"])
            if st.form_submit_button("Tambah"):
                try:
                    c.execute("INSERT INTO users VALUES(NULL,?,?,?,?)",
                              (u,hash_pw(p),r,
                               datetime.datetime.utcnow().isoformat()))
                    db.commit(); st.rerun()
                except:
                    st.error("Username sudah ada")
        st.dataframe(pd.read_sql("SELECT id,username,role FROM users",db))
