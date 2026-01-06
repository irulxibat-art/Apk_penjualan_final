import psycopg2
import streamlit as st
import pandas as pd
import hashlib
import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from supabase import create_client

supabase = create_client(
    st.secrets["https://kmzaakxrfyspaiargmdj.supabase.co"],
    st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImttemFha3hyZnlzcGFpYXJnbWRqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NzI4ODk3NiwiZXhwIjoyMDgyODY0OTc2fQ.r6IRyNKPFHMjkO35n-OUfESgPUH73kbnzLMnCx5e5GU"]
)

@st.cache_resource
def get_connection():
    return psycopg2.connect(st.secrets["https://kmzaakxrfyspaiargmdj.supabase.co"])

conn = get_connection()

# =============================
# PAGE CONFIG
# =============================
st.set_page_config(page_title="Inventory System", layout="wide")

# =============================
# SESSION STATE
# =============================
if "user" not in st.session_state:
    st.session_state.user = None

if "edit_product_id" not in st.session_state:
    st.session_state.edit_product_id = None

# =============================
# AUTH
# =============================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users VALUES (NULL,?,?,?,?)",
            ("boss", hash_password("boss123"), "boss",
             datetime.datetime.utcnow().isoformat())
        )
        conn.commit()

create_default_user()

def login_user(u, p):
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (u, hash_password(p))
    )
    return c.fetchone()

# =============================
# STORE STATUS
# =============================
def get_store_status():
    c = conn.cursor()
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store_status(status):
    conn.cursor().execute(
        "UPDATE store_status SET status=? WHERE id=1", (status,))
    conn.commit()

# =============================
# PRODUCT FUNCTIONS
# =============================
def add_product(sku, name, cost, price):
    conn.cursor().execute("""
        INSERT INTO products
        (sku,name,cost,price,stock,warehouse_stock,created_at)
        VALUES (?,?,?,?,0,0,?)
    """, (sku, name, cost, price,
          datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(pid, sku, name, cost, price, role):
    c = conn.cursor()

    if role != "boss":
        # SECURITY: karyawan tidak boleh ubah harga
        c.execute("""
            UPDATE products
            SET sku=?, name=?
            WHERE id=?
        """, (sku, name, pid))
    else:
        c.execute("""
            UPDATE products
            SET sku=?, name=?, cost=?, price=?
            WHERE id=?
        """, (sku, name, cost, price, pid))

    conn.commit()

def delete_product(pid):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (pid,))
    if c.fetchone()[0] > 0:
        return False, "Produk sudah pernah dijual"
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    return True, "Produk dihapus"

def add_warehouse_stock(pid, qty):
    conn.cursor().execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock + ?
        WHERE id=?
    """, (qty, pid))
    conn.commit()

def move_stock(pid, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (pid,))
    if qty > c.fetchone()[0]:
        return False, "Stok gudang tidak cukup"

    c.execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock - ?,
            stock = stock + ?
        WHERE id=?
    """, (qty, qty, pid))
    conn.commit()
    return True, "Stok dipindahkan"

def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", conn)

# =============================
# SALES
# =============================
def record_sale(pid, qty, user_id):
    c = conn.cursor()
    c.execute("SELECT stock,cost,price FROM products WHERE id=?", (pid,))
    stock, cost, price = c.fetchone()

    if qty > stock:
        return False, "Stok tidak cukup"

    total = qty * price
    profit = (price - cost) * qty

    c.execute("""
        INSERT INTO sales
        (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (pid, qty, cost, price, total, profit,
          user_id, datetime.datetime.utcnow().isoformat()))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?",
              (qty, pid))
    conn.commit()
    return True, "Penjualan berhasil"

def get_sales(role):
    if role == "boss":
        q = """SELECT p.name, s.qty, s.total, s.profit, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    else:
        q = """SELECT p.name, s.qty, s.total, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    return pd.read_sql(q, conn)

def get_today_summary():
    today = datetime.datetime.utcnow().date().isoformat()
    q = """
        SELECT 
            COALESCE(SUM(total),0),
            COALESCE(SUM(profit),0)
        FROM sales
        WHERE date(sold_at)=?
    """
    c = conn.cursor()
    c.execute(q, (today,))
    return c.fetchone()

def check_and_archive_daily_sales():
    today = datetime.date.today()

    c = conn.cursor()
    c.execute("SELECT MAX(archive_date) FROM sales_archive")
    last_archive = c.fetchone()[0]

    if last_archive == today.isoformat():
        return
        
    yesterday = today - datetime.timedelta(days=1)
    
    c.execute("""
     SELECT
         SUM(total),
         SUM(profit)
     FROM sales
     WHERE date(sold_at)=?
     """, (yesterday.isoformat(),))
    
    result = c.fetchone()
 
    if result[0] is None:
        return
    
    total_sales = result[0]
    total_profit = result[1]

    week_number = (yesterday.day - 1) // 7 + 1
    
    pdf_filename = (
        f"Laporan_Harian_"
        f"{yesterday.strftime('%A')}_"
        f"{yesterday.strftime('%d-%m-%Y')}_"
        f"Minggu-{week_number}.pdf"
    )

    df_yesterday = pd.read_sql(
        """
        SELECT p.name, s.qty, s.total, s.profit, s.sold_at
        FROM sales s
        JOIN products p ON s.product_id = p.id
        WHERE date(s.sold_at)=?
        """,
        conn,
        params=(yesterday.isoformat(),)
    )
    export_sales_pdf(
        df_yesterday,
        pdf_filename,
        title=f"Laporan Penjualan Harian {yesterday.strftime('%d-%m-%Y')}"
    )

    c.execute("""
        INSERT INTO sales_archive (
            archive_date,
            week_number,
            month,
            year,
            total_sales,
            total_profit,
            pdf_file,
            archived_at
        )
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        yesterday.isoformat(),
        week_number,
        yesterday.month,
        yesterday.year,
        total_sales,
        total_profit,
        pdf_filename,
        datetime.datetime.now().isoformat()
    ))
    
    conn.commit()

    c.execute(
        "DELETE FROM sales WHERE date(sold_at)=?",
        (yesterday.isoformat(),)
    )
    conn.commit()

# =============================
# PDF EXPORT (BOSS ONLY)
# =============================
def export_sales_pdf(df, filename, title):
    styles = getSampleStyleSheet()
    elements = []

    # Judul
    elements.append(Paragraph("LAPORAN PENJUALAN", styles["Title"]))
    elements.append(Paragraph(
        f"Tanggal Cetak: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}",
        styles["Normal"]
    ))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    # Tabel histori
    table_data = [df.columns.tolist()] + df.values.tolist()
    table = Table(table_data, repeatRows=1)
    elements.append(table)

    # =============================
    # TOTAL & P&L
    # =============================
    total_penjualan = df["total"].sum()
    total_profit = df["profit"].sum() if "profit" in df.columns else 0

    elements.append(Paragraph("<br/>", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Total Penjualan:</b> Rp {int(total_penjualan):,}",
        styles["Normal"]
    ))
    elements.append(Paragraph(
        f"<b>Total P&L:</b> Rp {int(total_profit):,}",
        styles["Normal"]
    ))

    doc.build(elements)
    return filename

# =============================
# LOGIN
# =============================
if st.session_state.user is None:
    st.title("Login Sistem")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(u, p)
        if user:
            if user[3] == "karyawan" and get_store_status() == "closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "role": user[3]
                }
                st.rerun()
        else:
            st.error("Login gagal")

# =============================
# MAIN APP
# =============================
else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"{user['username']} ({role})")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "Stok Gudang", "Produk & Stok",
         "Penjualan", "Histori Penjualan", "Manajemen User"]
        if role == "boss"
        else ["Home", "Penjualan", "Histori Penjualan"]
    )

    # =============================
    # HOME
    # =============================
    if menu == "Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {get_store_status().upper()}")

        if role == "boss":
            col1, col2 = st.columns(2)
            if col1.button("Buka Toko"):
                set_store_status("open")
                st.rerun()
            if col2.button("Tutup Toko"):
                set_store_status("closed")
                st.rerun()

    # =============================
    # STOK GUDANG
    # =============================
    elif menu == "Stok Gudang":
        st.header("Stok Gudang")

        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0)
            price = st.number_input("Harga Jual", min_value=0.0)
            if st.form_submit_button("Tambah Produk"):
                add_product(sku, name, cost, price)
                st.rerun()

        df = get_products()
        if not df.empty:
            pid = st.selectbox(
                "Pilih Produk",
                df["id"],
                format_func=lambda x: df[df.id == x]["name"].values[0]
            )

            row = df[df.id == pid].iloc[0]

            if st.button("✏️ Edit Produk"):
                st.session_state.edit_product_id = pid

            if st.session_state.edit_product_id == pid:
                with st.form("edit_prod"):
                    sku = st.text_input("SKU", row["sku"])
                    name = st.text_input("Nama Produk", row["name"])

                    if role == "boss":
                        cost = st.number_input(
                            "Harga Modal", value=row["cost"])
                        price = st.number_input(
                            "Harga Jual", value=row["price"])
                    else:
                        st.info("Harga hanya bisa diubah oleh boss")
                        cost = row["cost"]
                        price = row["price"]

                    if st.form_submit_button("Simpan"):
                        update_product(
                            pid, sku, name, cost, price, role)
                        st.session_state.edit_product_id = None
                        st.rerun()

            qty = st.number_input("Tambah Stok Gudang", min_value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid, qty)
                st.rerun()

            if st.button("Hapus Produk"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.dataframe(df[["sku", "name", "warehouse_stock"]])

    # =============================
    # PRODUK & STOK
    # =============================
    elif menu == "Produk & Stok":
        st.header("Stok Harian")

        df = get_products()

        if df.empty:
            st.info("Belum ada produk")
        else:
            pid = st.selectbox(
                "Pilih Produk",
                df["id"],
                format_func=lambda x: df[df.id == x]["name"].values[0]
            )

            qty = st.number_input("Jumlah Ambil dari Gudang", min_value=1)

            if st.button("Ambil ke Stok Harian"):
                ok, msg = move_stock(pid, qty)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.subheader("📦 Tabel Stok Harian")
            st.dataframe(df[["sku", "name", "stock"]])


    # =============================
    # PENJUALAN
    # =============================
    elif menu == "Penjualan":
        df = get_products()
        mapping = {
            f"{r['name']} (Sisa: {r['stock']})": r['id']
            for _, r in df.iterrows()
            }

        pilih = st.selectbox("Pilih Produk", mapping.keys())
        pid = mapping[pilih]
        sisa = int(df[df["id"] == pid]["stock"].values[0])
        if sisa == 0:
            st.warning("Stok produk ini HABIS")

        qty = st.number_input(
            "Qty",
            min_value=1,
            max_value=max(1, sisa),
            disabled=(sisa == 0)
            )

        if st.button("Simpan Penjualan"):
            ok, msg = record_sale(pid, qty, user["id"])
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # =============================
    # HISTORI PENJUALAN
    # =============================
    elif menu == "Histori Penjualan":
        check_and_archive_daily_sales()

        st.header("History Penjualan")

        if role == "boss":
            mode = st.radio(
            "Pilih Mode History",
            ["History Harian", "History Mingguan"]
                )
            if mode == "History Harian":
                df = pd.read_sql(
                    """
                    SELECT p.name, s.qty, s.total, s.profit, s.sold_at
                    FROM sales s
                    JOIN products p ON s.product_id = p.id
                    WHERE date(s.sold_at)=date('now')
                    """,
                    conn
                
                )

                st.subheader("History Harian (Hari Ini)")
                st.dataframe(df)

                total_df = pd.read_sql(
                    """
                    SELECT
                        SUM(total) AS total_sales,
                        SUM(profit) AS total_profit
                    FROM sales
                    WHERE date(sold_at)=date('now')
                    """,
                    conn
                )

                total_sales = total_df.iloc[0]["total_sales"] or 0
                total_profit = total_df.iloc[0]["total_profit"] or 0

                col1, col2 = st.columns(2)

                col1.metric(
                    label="Total Penjualan Hari Ini",
                    value=f"💸Rp {int(total_sales):,}"
                )

                col2.metric(
                    label="Total P&L Hari Ini",
                    value=f"💸Rp {int(total_profit):,}"
                )
            
            if mode == "History Mingguan":
                df = pd.read_sql(
                    """
                    SELECT
                        archive_date,
                        week_number,
                        total_sales,
                        total_profit,
                        pdf_file
                    FROM sales_archive
                    ORDER BY archive_date DESC
                    """,
                    conn
                )

                st.subheader("History Mingguan")
                st.dataframe(df)

        else:
            df = pd.read_sql(
                """
                SELECT p.name, s.qty, s.total, s.sold_at
                FROM sales s
                JOIN products p ON s.product_id = p.id
                WHERE date(s.sold_at)=date('now')
                """,
                conn
            )

            st.subheader("History Harian (Hari Ini)")
            st.dataframe(df)

            total_df = pd.read_sql(
                """
                SELECT
                    SUM(total) AS total_sales
                FROM sales
                WHERE date(sold_at)=date('now')
                """,
                conn
            )

            total_sales = total_df.iloc[0]["total_sales"] or 0   

            st.metric(
                label="Total Penjualan Hari Ini",
                value=f"💸Rp {int(total_sales):,}"
            )
            
    
    # =============================
    # USER MANAGEMENT
    # =============================
    elif menu == "Manajemen User":
        with st.form("add_user"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            r = st.selectbox("Role", ["boss", "karyawan"])
            if st.form_submit_button("Tambah User"):
                try:
                    conn.cursor().execute(
                        "INSERT INTO users VALUES (NULL,?,?,?,?)",
                        (u, hash_password(p), r,
                         datetime.datetime.utcnow().isoformat())
                    )
                    conn.commit()
                    st.rerun()
                except:
                    st.error("Username sudah digunakan")
